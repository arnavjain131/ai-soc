"""Forward OpenSSH authentication outcomes from the local system journal."""

import hashlib
import json
import logging
import os
import re
import sqlite3
import subprocess
import time
from contextlib import closing
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener


AUTH_MESSAGE = re.compile(
    r'^(Accepted|Failed) (password|publickey|keyboard-interactive(?:/pam)?) '
    r'for (?:invalid user )?(\S{1,128}) from (\S+) port ([0-9]{1,5})(?:\s|$)'
)
QUEUE_LIMIT = 5000
BATCH_SIZE = 50
SCAN_LIMIT = 250
LOG = logging.getLogger('ai-soc-ssh')


def normalize(entry, destination_ip):
    message = entry.get('MESSAGE')
    if not isinstance(message, str):
        return None
    match = AUTH_MESSAGE.match(message)
    if not match:
        return None
    outcome, method, username, peer, peer_port = match.groups()
    try:
        source_ip = str(ip_address(peer))
        if not 1 <= int(peer_port) <= 65535:
            return None
        timestamp = datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(
            microseconds=int(entry['__REALTIME_TIMESTAMP'])
        )
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    event_id = hashlib.sha256(entry['__CURSOR'].encode()).hexdigest()
    return {
        'external_event_id': f'ssh-journal-{event_id}',
        'event_time': timestamp.isoformat(),
        'event_type': 'LOGIN_SUCCEEDED' if outcome == 'Accepted' else 'LOGIN_FAILED',
        'source_ip': source_ip,
        'destination_ip': destination_ip,
        'destination_port': 22,
        'username': username,
        'raw_data': {'provenance': 'openssh_journal', 'authentication_method': method},
    }


def initialize(db, since):
    with db:
        db.execute('CREATE TABLE IF NOT EXISTS checkpoint (id INTEGER PRIMARY KEY, since INTEGER NOT NULL, cursor TEXT)')
        db.execute('INSERT OR IGNORE INTO checkpoint (id, since) VALUES (1, ?)', (since,))
        db.execute('''CREATE TABLE IF NOT EXISTS pending (
            sequence INTEGER PRIMARY KEY, event_id TEXT UNIQUE NOT NULL, payload TEXT NOT NULL
        )''')


def collect(db, destination_ip):
    since, cursor = db.execute('SELECT since, cursor FROM checkpoint WHERE id = 1').fetchone()
    count = db.execute('SELECT count(*) FROM pending').fetchone()[0]
    if count >= QUEUE_LIMIT:
        return 0
    command = [
        'journalctl', '--system', '--no-pager', '--quiet', '--output=json',
        '--output-fields=MESSAGE', '-t', 'sshd', '-t', 'sshd-session',
    ]
    if cursor:
        command.append(f'--after-cursor={cursor}')
    else:
        command.append(f'--since=@{since}')

    added = 0
    with db, subprocess.Popen(command, stdout=subprocess.PIPE, text=True, encoding='utf-8') as journal:
        try:
            for index, line in enumerate(journal.stdout, start=1):
                entry = json.loads(line)
                cursor = entry['__CURSOR']
                if not isinstance(cursor, str) or not cursor:
                    raise ValueError('Invalid journal cursor')
                event = normalize(entry, destination_ip)
                if event:
                    result = db.execute('INSERT OR IGNORE INTO pending (event_id, payload) VALUES (?, ?)', (
                        event['external_event_id'], json.dumps(event),
                    ))
                    added += result.rowcount
                if count + added >= QUEUE_LIMIT or index >= SCAN_LIMIT:
                    journal.terminate()
                    journal.wait()
                    break
            else:
                if journal.wait():
                    raise RuntimeError('journalctl failed')
            db.execute('UPDATE checkpoint SET cursor = ? WHERE id = 1', (cursor,))
        finally:
            if journal.poll() is None:
                journal.terminate()
    return added


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def deliver(db, endpoint, token, opener):
    rows = db.execute('SELECT sequence, payload FROM pending ORDER BY sequence LIMIT ?', (BATCH_SIZE,)).fetchall()
    if not rows:
        return 0
    payload = json.dumps({'events': [json.loads(row[1]) for row in rows]}).encode()
    request = Request(endpoint, data=payload, headers={
        'Content-Type': 'application/json', 'X-Source-Token': token,
    })
    with opener.open(request, timeout=45) as response:
        ack = json.loads(response.read(4096))
    counts = [ack.get(name) for name in ('accepted', 'duplicates')] if isinstance(ack, dict) else []
    if len(counts) != 2 or any(type(n) is not int or n < 0 for n in counts) or sum(counts) != len(rows):
        raise ValueError('Invalid ingestion acknowledgement')
    with db:
        db.executemany('DELETE FROM pending WHERE sequence = ?', [(row[0],) for row in rows])
    return len(rows)


def run(db, endpoint, token, destination_ip):
    opener = build_opener(NoRedirect())
    retry_at = 0
    retry_delay = 5
    while True:
        try:
            added = collect(db, destination_ip)
            if added:
                LOG.info('Queued %d SSH events', added)
        except (OSError, KeyError, RuntimeError, ValueError):
            LOG.warning('Journal read failed. Check journal access and cursor availability')

        if time.monotonic() >= retry_at:
            try:
                delivered = deliver(db, endpoint, token, opener)
                retry_delay = 5
                if delivered:
                    LOG.info('API acknowledged %d SSH events', delivered)
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                status = f'HTTP {exc.code}' if isinstance(exc, HTTPError) else type(exc).__name__
                LOG.warning('Delivery failed (%s). Queue retained. Retrying in %d seconds', status, retry_delay)
                retry_at = time.monotonic() + retry_delay
                retry_delay = min(retry_delay * 2, 120)
        time.sleep(5)


def main():
    logging.basicConfig(level=logging.INFO, format='%(levelname)s %(message)s')
    try:
        base_url = os.environ['SOC_API_URL'].rstrip('/')
        parsed_url = urlsplit(base_url)
        if (parsed_url.scheme != 'https' or not parsed_url.hostname or parsed_url.username is not None
                or parsed_url.path or parsed_url.query or parsed_url.fragment):
            raise ValueError('Expected HTTPS origin')
        destination_ip = str(ip_address(os.environ['SOC_SSH_DESTINATION_IP']))
        lookback = int(os.environ.get('SOC_SSH_LOOKBACK_MINUTES', '0'))
        if not 0 <= lookback <= 60:
            raise ValueError('Lookback outside 0–60 minutes')
        token = (Path(os.environ['CREDENTIALS_DIRECTORY']) / 'source-token').read_text(encoding='utf-8').strip()
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,256}', token):
            raise ValueError('Invalid source token')
        state = Path(os.environ['STATE_DIRECTORY']) / 'queue.sqlite3'
    except (KeyError, OSError, ValueError):
        raise SystemExit('Check collector environment settings and the source-token credential file.') from None

    with closing(sqlite3.connect(state)) as db:
        initialize(db, int(time.time()) - lookback * 60)
        run(db, base_url + '/api/events/batch', token, destination_ip)


if __name__ == '__main__':
    main()
