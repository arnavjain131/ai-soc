"""Import a Suricata EVE flow from approved lab traffic."""

import argparse
import getpass
import hashlib
import json
import warnings
from datetime import datetime, timezone
from ipaddress import ip_address
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener

if __package__:
    from .ssh_journal import NoRedirect
else:
    from ssh_journal import NoRedirect


def normalize(entry):
    if not isinstance(entry, dict) or entry.get('event_type') != 'flow':
        return None
    return normalize_network_record(entry)


def normalize_alert(entry):
    if not isinstance(entry, dict) or entry.get('event_type') != 'alert':
        return None
    return normalize_network_record(entry)


def normalize_network_record(entry):
    protocol = entry.get('proto')
    if protocol not in ('TCP', 'UDP'):
        return None
    try:
        timestamp = datetime.fromisoformat(entry['timestamp'])
        if timestamp.tzinfo is None:
            return None
        timestamp = timestamp.astimezone(timezone.utc).isoformat()
        source_ip = str(ip_address(entry['src_ip']))
        destination_ip = str(ip_address(entry['dest_ip']))
        source_port, destination_port = entry['src_port'], entry['dest_port']
    except (KeyError, TypeError, ValueError, OverflowError):
        return None
    if any(type(port) is not int or not 1 <= port <= 65535 for port in (source_port, destination_port)):
        return None
    flow_id = entry.get('flow_id')
    is_alert = entry['event_type'] == 'alert'
    if (flow_id is not None or not is_alert) and (type(flow_id) is not int or not 0 <= flow_id < 2**64):
        return None
    identity = [flow_id, timestamp, protocol, source_ip, source_port, destination_ip, destination_port]
    metadata = {}
    if is_alert:
        alert = entry.get('alert')
        if not isinstance(alert, dict):
            return None
        signature_id, signature, severity = (alert.get(name) for name in ('signature_id', 'signature', 'severity'))
        if (type(signature_id) is not int or not 1 <= signature_id < 2**32
                or not isinstance(signature, str) or not signature.strip()
                or type(severity) is not int or not 1 <= severity <= 255):
            return None
        metadata = {'signature_id': signature_id, 'signature': signature.strip()[:256], 'severity': severity}
        identity.extend((alert.get('gid'), signature_id))
    digest = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    return {
        'external_event_id': f"suricata-{entry['event_type']}-{digest}",
        'event_type': 'SURICATA_ALERT' if is_alert else 'NETWORK_FLOW',
        'event_time': timestamp, 'protocol': protocol,
        'source_ip': source_ip, 'source_port': source_port,
        'destination_ip': destination_ip, 'destination_port': destination_port,
        'raw_data': {'provenance': 'suricata_eve'},
        **metadata,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('eve_file', help='Path to an EVE JSON Lines file')
    parser.add_argument('--source-ip', required=True, type=ip_address)
    parser.add_argument('--destination-ip', required=True, type=ip_address)
    parser.add_argument('--destination-port', required=True, type=int)
    parser.add_argument('--api-url', help='HTTPS API origin. Omit to preview without sending.')
    args = parser.parse_args()
    if not 1 <= args.destination_port <= 65535:
        parser.error('Destination port must be between 1 and 65535.')
    if args.api_url:
        try:
            origin = urlsplit(args.api_url.rstrip('/'))
            if (origin.scheme != 'https' or not origin.hostname or origin.username is not None
                    or origin.path or origin.query or origin.fragment):
                raise ValueError
        except ValueError:
            parser.error('Use an HTTPS API origin.')
    latest = None
    try:
        with open(args.eve_file, encoding='utf-8', errors='replace') as records:
            for line in records:
                try:
                    event = normalize(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if event and (event['source_ip'], event['destination_ip'], event['destination_port']) == (
                    str(args.source_ip), str(args.destination_ip), args.destination_port,
                ):
                    latest = event
    except OSError:
        parser.exit(1, 'Could not read the EVE file. Check the path and file permissions.\n')
    if latest is None:
        parser.exit(1, 'No matching TCP or UDP flow found.\n')
    if not args.api_url:
        print(json.dumps(latest, indent=2))
        return
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            token = getpass.getpass('Source token: ').strip()
    except (EOFError, getpass.GetPassWarning):
        parser.exit(1, 'Run the importer in an interactive terminal with hidden input.\n')
    if not token.isascii() or not token or len(token) > 256 or not all(c.isalnum() or c in '-_' for c in token):
        parser.exit(1, 'Invalid source token format.\n')
    request = Request(args.api_url.rstrip('/') + '/api/events/batch', data=json.dumps({'events': [latest]}).encode(),
                      headers={'Content-Type': 'application/json', 'X-Source-Token': token})
    try:
        with build_opener(NoRedirect()).open(request, timeout=60) as response:
            ack = json.loads(response.read(4096))
    except HTTPError as error:
        parser.exit(1, f'Ingestion failed with HTTP {error.code}.\n')
    except (URLError, TimeoutError, OSError, ValueError):
        parser.exit(1, 'Request failed or the API response could not be read. You can retry the same record.\n')
    if ack not in ({'accepted': 1, 'duplicates': 0}, {'accepted': 0, 'duplicates': 1}):
        parser.exit(1, 'Unexpected API acknowledgement.\n')
    print(json.dumps(ack))


if __name__ == '__main__':
    main()
