#!/usr/bin/env bash
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo 'Run this installer with sudo.' >&2
    exit 1
fi
if [[ ! -t 0 ]]; then
    echo 'Run this installer in an interactive terminal.' >&2
    exit 1
fi

cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
log_dir=/var/log/suricata
eve_file="$log_dir/eve.json"
if [[ ! -f "$eve_file" ]] || ! systemctl is-active --quiet suricata.service; then
    echo 'Start Suricata and verify /var/log/suricata/eve.json before installing.' >&2
    exit 1
fi
if ! command -v setfacl >/dev/null; then
    echo 'Install the Ubuntu acl package, then rerun this installer.' >&2
    exit 1
fi
for file in suricata_forwarder.py suricata_eve.py ssh_journal.py ai-soc-suricata.service; do
    test -f "$file"
done

install -d -m 0755 /opt/ai-soc/suricata
install -d -m 0700 /etc/ai-soc
credential=/etc/ai-soc/suricata-source-token
if [[ ! -s "$credential" ]]; then
    IFS= read -rsp 'Ubuntu Suricata source token: ' token
    printf '\n'
    if [[ ! $token =~ ^[A-Za-z0-9_-]{1,256}$ ]]; then
        echo 'Invalid source token format.' >&2
        exit 1
    fi
    (umask 077; printf '%s\n' "$token" > "$credential")
    unset token
fi

# The forwarder needs directory traversal and read access for active and rotated EVE files.
getent group ai-soc-eve >/dev/null || groupadd --system ai-soc-eve
setfacl -m g:ai-soc-eve:r-x,d:g:ai-soc-eve:r-X "$log_dir"
setfacl -m g:ai-soc-eve:r-- "$eve_file"

install -m 0644 suricata_forwarder.py suricata_eve.py ssh_journal.py /opt/ai-soc/suricata/
install -m 0644 ai-soc-suricata.service /etc/systemd/system/
config=/etc/ai-soc/suricata-forwarder.conf
if [[ ! -e "$config" ]]; then
    (umask 077; cat > "$config" <<'EOF'
SOC_API_URL=https://ai-soc-api.onrender.com
SOC_EVE_PATH=/var/log/suricata/eve.json
SOC_FLOW_SOURCE_IP=10.0.2.2
SOC_FLOW_DESTINATION_IP=10.0.2.15
EOF
    )
fi
systemctl daemon-reload
systemctl enable ai-soc-suricata.service
systemctl restart ai-soc-suricata.service
systemctl is-active ai-soc-suricata.service
