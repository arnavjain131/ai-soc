#!/usr/bin/env bash
# Targeted lab upgrade: preserves credentials, configuration, queue and SSH feed.
set -euo pipefail
umask 077

if [[ $EUID -ne 0 || ! -t 0 ]]; then
    echo 'Run this upgrade with sudo in an interactive Ubuntu terminal.' >&2
    exit 1
fi
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
source_file="$PWD/suricata_forwarder.py"
installed=/opt/ai-soc/suricata/suricata_forwarder.py
state=/var/lib/ai-soc-suricata/queue.sqlite3
archive=/var/log/suricata/eve.json.1.gz
for file in "$source_file" "$installed" "$state" "$archive"; do
    [[ -f "$file" && ! -L "$file" ]] || { echo 'Expected upgrade files are missing or symlinked; no changes made.' >&2; exit 1; }
done
command -v setfacl >/dev/null
getent group ai-soc-eve >/dev/null
systemctl is-active --quiet ai-soc-suricata.service
python3 - "$source_file" <<'PY'
import ast, pathlib, sys
ast.parse(pathlib.Path(sys.argv[1]).read_text())
PY

install -d -m 0700 /var/backups/ai-soc-suricata
backup=$(mktemp -d /var/backups/ai-soc-suricata/rotation-XXXXXXXX)
cp -p -- "$installed" "$backup/suricata_forwarder.py"
getfacl -p -- "$archive" > "$backup/archive.acl"
stopped=0
success=0
finish() {
    status=$?
    trap - EXIT
    if [[ $success -ne 1 && $stopped -eq 1 ]]; then
        install -m 0644 "$backup/suricata_forwarder.py" "$installed" || true
        setfacl --restore="$backup/archive.acl" || true
        systemctl start ai-soc-suricata.service || true
        echo 'Upgrade did not complete. Original code restored; queue/checkpoint were not reset.' >&2
    fi
    echo "Backup directory: $backup"
    exit "$status"
}
trap finish EXIT
stopped=1
systemctl stop ai-soc-suricata.service
python3 - "$source_file" "$backup" <<'PY'
import importlib.util
import pathlib
import shutil
import sqlite3
import sys

backup = pathlib.Path(sys.argv[2])
state = pathlib.Path('/var/lib/ai-soc-suricata/queue.sqlite3')
log = pathlib.Path('/var/log/suricata/eve.json')
archive = pathlib.Path(str(log) + '.1.gz')
with sqlite3.connect(state.as_uri() + '?mode=ro', uri=True) as original:
    with sqlite3.connect(backup / 'queue.sqlite3') as snapshot:
        original.backup(snapshot)
    position = original.execute('SELECT device, inode, offset, anchor FROM eve_position WHERE id=1').fetchone()
    count = original.execute('SELECT count(*) FROM pending').fetchone()[0]
if not position:
    raise SystemExit('Expected checkpoint is missing; upgrade stopped.')
stat = log.stat()
if position[:2] != (stat.st_dev, stat.st_ino) or stat.st_size >= position[2]:
    raise SystemExit('Checkpoint no longer matches the diagnosed truncation case; upgrade stopped.')
sys.path.insert(0, '/opt/ai-soc/suricata')
spec = importlib.util.spec_from_file_location('rotation_upgrade', sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with module.open_copytruncate_archive(log, position[2], position[3]) as stream:
    stream.seek(0, 2)
    if stream.tell() != position[2]:
        raise SystemExit('Archive has an unread tail; review before applying this targeted lab upgrade.')
    shutil.copyfile(archive, backup / 'eve.json.1.gz')
print(f'Archive verified at saved EOF. SQLite backup complete; {count} pending event(s) preserved.')
PY

# Grant only read access to the existing service group for the verified archive.
setfacl -m g:ai-soc-eve:r-- "$archive"
install -m 0644 "$source_file" "$installed"
systemctl start ai-soc-suricata.service
systemctl is-active --quiet ai-soc-suricata.service
success=1
echo 'Rotation fix installed; Suricata forwarder started. Verify API acknowledgements next.'
echo 'Sensor, SSH collector, source token, configuration and detection thresholds were not changed.'
