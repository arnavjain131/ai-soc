"""Queue and forward TCP flows and alerts from the lab's Suricata EVE log."""

import hashlib
import json
import logging
import os
import re
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import build_opener

if __package__:
    from .ssh_journal import NoRedirect, QUEUE_LIMIT, deliver
    from .suricata_eve import normalize, normalize_alert
else:
    from ssh_journal import NoRedirect, QUEUE_LIMIT, deliver
    from suricata_eve import normalize, normalize_alert


LOG = logging.getLogger('ai-soc-suricata')
MAX_LINE = 1024 * 1024
SCAN_LIMIT = 250
ANCHOR_SIZE = 128
SSH_PORTS = frozenset({22})


def parse_ports(value):
    if value == 'all':
        return None
    ports = frozenset(int(port) for port in value.split(','))
    if any(not 1 <= port <= 65535 for port in ports):
        raise ValueError('Destination port out of range')
    return ports


def initialize(db):
    with db:
        db.execute('''CREATE TABLE IF NOT EXISTS eve_position (
            id INTEGER PRIMARY KEY, device INTEGER NOT NULL, inode INTEGER NOT NULL,
            offset INTEGER NOT NULL, anchor BLOB NOT NULL
        )''')
        db.execute('''CREATE TABLE IF NOT EXISTS pending (
            sequence INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL
        )''')


def file_identity(stream):
    stat = os.fstat(stream.fileno())
    return stat.st_dev, stat.st_ino


def fingerprint(stream, offset):
    start = max(0, offset - ANCHOR_SIZE)
    stream.seek(start)
    return hashlib.sha256(stream.read(offset - start)).digest()


def save_position(db, stream, offset):
    db.execute('INSERT OR REPLACE INTO eve_position VALUES (1, ?, ?, ?, ?)', (
        *file_identity(stream), offset, fingerprint(stream, offset),
    ))


def open_checkpoint_file(path, identity):
    # Suricata can rename a file and open a new one during log rotation.
    # Look in the same directory for the previous, uncompressed file.
    for candidate in path.parent.glob(f'{path.name}*'):
        try:
            if candidate.is_symlink() or not candidate.is_file():
                continue
            stat = candidate.stat()
            if (stat.st_dev, stat.st_ino) != identity:
                continue
            stream = candidate.open('rb')
        except FileNotFoundError:
            continue
        if file_identity(stream) == identity:
            return stream
        stream.close()
    raise RuntimeError('Previous EVE file is unavailable. Check log rotation and retention.')


def read_records(db, stream, offset, source_ip, destination_ip, capacity, ports):
    added = 0
    stream.seek(offset)
    for _ in range(SCAN_LIMIT):
        line = stream.readline(MAX_LINE + 1)
        if not line:
            return added, offset, True
        if len(line) > MAX_LINE:
            raise RuntimeError('EVE record exceeds the supported line size.')
        if not line.endswith(b'\n'):
            break
        try:
            entry = json.loads(line)
            event = normalize(entry) or normalize_alert(entry)
        except ValueError:
            event = None
        if (event and (event['source_ip'], event['destination_ip'], event['protocol']) ==
                (source_ip, destination_ip, 'TCP') and (ports is None or event['destination_port'] in ports)):
            if datetime.fromisoformat(event['event_time']) > datetime.now(timezone.utc) + timedelta(minutes=4):
                LOG.warning('Suricata timestamp is ahead of the clock. Check time synchronization.')
                break
            result = db.execute('INSERT OR IGNORE INTO pending (event_id, payload) VALUES (?, ?)', (
                event['external_event_id'], json.dumps(event),
            ))
            added += result.rowcount
        offset = stream.tell()
        if added >= capacity:
            break
    return added, offset, False


def collect(db, path, source_ip, destination_ip, ports=SSH_PORTS):
    with db, path.open('rb') as current:
        capacity = QUEUE_LIMIT - db.execute('SELECT count(*) FROM pending').fetchone()[0]
        position = db.execute('SELECT device, inode, offset, anchor FROM eve_position WHERE id = 1').fetchone()
        if position is None:
            # Baseline at the current end so old traffic is left on the VM.
            current.seek(0, os.SEEK_END)
            save_position(db, current, current.tell())
            return 0
        if capacity <= 0:
            return 0
        device, inode, offset, anchor = position
        rotated = (device, inode) != file_identity(current)
        stream = open_checkpoint_file(path, (device, inode)) if rotated else current
        try:
            if os.fstat(stream.fileno()).st_size < offset or fingerprint(stream, offset) != anchor:
                raise RuntimeError('EVE log changed before the saved offset. Check rotation before resuming.')
            added, offset, at_end = read_records(db, stream, offset, source_ip, destination_ip, capacity, ports)
            if rotated and at_end:
                save_position(db, current, 0)
            else:
                save_position(db, stream, offset)
            return added
        finally:
            if rotated:
                stream.close()


def run(db, endpoint, token, path, source_ip, destination_ip, ports):
    opener = build_opener(NoRedirect())
    retry_at = 0
    backoff = 5
    while True:
        try:
            added = collect(db, path, source_ip, destination_ip, ports)
            if added:
                LOG.info('Queued %d Suricata events', added)
        except RuntimeError as error:
            LOG.warning('%s', error)
        except OSError:
            LOG.warning('Cannot read the EVE log. Check the path and service permissions.')
        if time.monotonic() >= retry_at:
            try:
                count = deliver(db, endpoint, token, opener)
                backoff = 5
                if count:
                    LOG.info('API acknowledged %d Suricata events', count)
            except (OSError, ValueError) as error:
                reason = f'HTTP {error.code}' if isinstance(error, HTTPError) else type(error).__name__
                LOG.warning('Delivery failed (%s). Queue retained. Retrying in %d seconds.', reason, backoff)
                retry_at = time.monotonic() + backoff
                backoff = min(backoff * 2, 120)
        time.sleep(5)


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    try:
        api_url = os.environ['SOC_API_URL'].rstrip('/')
        origin = urlsplit(api_url)
        if (origin.scheme != 'https' or not origin.hostname or origin.username is not None
                or origin.path or origin.query or origin.fragment):
            raise ValueError('Expected an HTTPS API origin')
        path = Path(os.environ['SOC_EVE_PATH'])
        if not path.is_absolute():
            raise ValueError('Expected an absolute EVE log path')
        source_ip = str(ip_address(os.environ['SOC_FLOW_SOURCE_IP']))
        destination_ip = str(ip_address(os.environ['SOC_FLOW_DESTINATION_IP']))
        ports = parse_ports(os.environ.get('SOC_FLOW_DESTINATION_PORTS', '22').strip())
        token = (Path(os.environ['CREDENTIALS_DIRECTORY']) / 'source-token').read_text(encoding='utf-8').strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', token):
            raise ValueError('Invalid source token format')
        state = Path(os.environ['STATE_DIRECTORY']) / 'queue.sqlite3'
    except (KeyError, OSError, ValueError):
        raise SystemExit('Check the Suricata forwarder configuration and source-token credential.') from None

    with closing(sqlite3.connect(state)) as db:
        initialize(db)
        run(db, api_url + '/api/events/batch', token, path, source_ip, destination_ip, ports)


if __name__ == '__main__':
    main()
