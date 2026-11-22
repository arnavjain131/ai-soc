import io
import gzip
import json
import sqlite3
from contextlib import closing
from unittest.mock import MagicMock
from urllib.error import URLError

import pytest

from collector.suricata_forwarder import collect, deliver, initialize, normalize, parse_ports


def flow(flow_id, **fields):
    entry = {
        'event_type': 'flow', 'flow_id': flow_id, 'timestamp': '2025-11-15T12:00:00Z',
        'src_ip': '10.0.2.2', 'src_port': 53050, 'dest_ip': '10.0.2.15', 'dest_port': 22,
        'proto': 'TCP',
    }
    return dict(entry, **fields)


def append(path, *records):
    with path.open('ab') as stream:
        for record in records:
            stream.write(json.dumps(record).encode() + b'\n')


def scan(db, log):
    return collect(db, log, '10.0.2.2', '10.0.2.15')


def pending(db):
    return [row[0] for row in db.execute('SELECT event_id FROM pending ORDER BY sequence')]


def test_checkpoint_and_retry_preserve_only_new_matching_flows(tmp_path):
    log = tmp_path / 'eve.json'
    state = tmp_path / 'queue.sqlite3'
    append(log, flow(1))
    second = json.dumps(flow(2)).encode()
    with closing(sqlite3.connect(state)) as db:
        initialize(db)
        assert scan(db, log) == 0
        append(log, flow(3, dest_port=443))
        with log.open('ab') as stream:
            stream.write(second[:60])
        assert scan(db, log) == 0
        assert pending(db) == []
    with log.open('ab') as stream:
        stream.write(second[60:] + b'\n')
    with closing(sqlite3.connect(state)) as db:
        initialize(db)
        assert scan(db, log) == 1
        assert scan(db, log) == 0
        expected = [normalize(flow(2))['external_event_id']]
        assert pending(db) == expected
        opener = MagicMock()
        opener.open.side_effect = URLError('offline')
        with pytest.raises(URLError):
            deliver(db, 'https://example.test/api/events/batch', 'test-token', opener)
        assert pending(db) == expected
    with closing(sqlite3.connect(state)) as db:
        assert pending(db) == expected
        opener.open.side_effect = None
        opener.open.return_value.__enter__.return_value = io.BytesIO(b'{"accepted":0,"duplicates":1}')
        assert deliver(db, 'https://example.test/api/events/batch', 'test-token', opener) == 1
        assert pending(db) == []


def test_rename_rotation_drains_previous_file_before_reading_new_file(tmp_path):
    log = tmp_path / 'eve.json'
    append(log, flow(1))
    with closing(sqlite3.connect(':memory:')) as db:
        initialize(db)
        assert scan(db, log) == 0
        append(log, flow(2))
        log.rename(tmp_path / 'eve.json.1')
        append(log, flow(3))
        assert scan(db, log) == 1
        assert scan(db, log) == 1
        assert scan(db, log) == 0
        assert pending(db) == [normalize(flow(i))['external_event_id'] for i in (2, 3)]


def test_forwards_matching_suricata_alert_without_packet_payload(tmp_path):
    log = tmp_path / 'eve.json'
    log.touch()
    alert = flow(3, event_type='alert', payload='discard me',
                 alert={'gid': 1, 'signature_id': 1234, 'signature': 'Fixture SSH alert', 'severity': 3})
    with closing(sqlite3.connect(':memory:')) as db:
        initialize(db)
        assert scan(db, log) == 0
        append(log, alert, alert, dict(alert, dest_port=443), dict(alert, alert={'severity': True}))
        assert scan(db, log) == 1
        payload, = db.execute('SELECT payload FROM pending').fetchone()
        event = json.loads(payload)
        assert event['event_type'] == 'SURICATA_ALERT'
        assert (event['signature_id'], event['signature'], event['severity']) == (1234, 'Fixture SSH alert', 3)
        assert event['raw_data'] == {'provenance': 'suricata_eve'}
        assert 'payload' not in event


def test_widening_ports_keeps_the_lab_peer_and_target_filter(tmp_path):
    log = tmp_path / 'eve.json'
    log.touch()
    with closing(sqlite3.connect(':memory:')) as db:
        initialize(db)
        assert scan(db, log) == 0
        allowed = flow(3, dest_port=443)
        append(log, allowed, flow(4, dest_port=80), flow(5, dest_port=443, src_ip='10.0.2.3'),
               flow(6, dest_port=443, dest_ip='10.0.2.16'))
        assert collect(db, log, '10.0.2.2', '10.0.2.15', parse_ports('22,443')) == 1
        assert pending(db) == [normalize(allowed)['external_event_id']]
    assert parse_ports('all') is None
    with pytest.raises(ValueError):
        parse_ports('22,65536')


def test_rewritten_log_leaves_checkpoint_and_pending_events_intact(tmp_path):
    log = tmp_path / 'eve.json'
    append(log, flow(1))
    with closing(sqlite3.connect(':memory:')) as db:
        initialize(db)
        assert scan(db, log) == 0
        append(log, flow(2))
        assert scan(db, log) == 1
        position = db.execute('SELECT * FROM eve_position').fetchone()
        log.write_bytes(b' ' * (log.stat().st_size + 5))
        with pytest.raises(RuntimeError, match='changed before the saved offset'):
            scan(db, log)
        assert db.execute('SELECT * FROM eve_position').fetchone() == position
        assert pending(db) == [normalize(flow(2))['external_event_id']]


def compress_copy(log, destination):
    with log.open('rb') as source, gzip.open(destination, 'wb') as target:
        target.write(source.read())


@pytest.mark.parametrize('compressed', [True, False])
def test_copytruncate_at_checkpoint_eof_recovers_fresh_non_ssh_flow(tmp_path, compressed):
    log, state = tmp_path / 'eve.json', tmp_path / 'queue.sqlite3'
    append(log, flow(1))
    with closing(sqlite3.connect(state)) as db:
        initialize(db)
        assert scan(db, log) == 0
        append(log, flow(2))
        assert scan(db, log) == 1
        checkpoint = db.execute('SELECT * FROM eve_position').fetchone()
    if compressed:
        compress_copy(log, tmp_path / 'eve.json.1.gz')
    else:
        (tmp_path / 'eve.json.1').write_bytes(log.read_bytes())
    log.write_bytes(b'')  # copytruncate retains this file's identity
    append(log, flow(3, dest_port=18080))
    with closing(sqlite3.connect(state)) as db:
        assert db.execute('SELECT * FROM eve_position').fetchone() == checkpoint
        assert collect(db, log, '10.0.2.2', '10.0.2.15', None) == 0
        assert pending(db) == [normalize(flow(2))['external_event_id']]
        assert collect(db, log, '10.0.2.2', '10.0.2.15', None) == 1
        assert collect(db, log, '10.0.2.2', '10.0.2.15', None) == 0
        assert pending(db) == [normalize(flow(2))['external_event_id'], normalize(flow(3, dest_port=18080))['external_event_id']]


def test_gzip_unread_tail_resumes_across_batches_and_process_restart(tmp_path, monkeypatch):
    monkeypatch.setattr('collector.suricata_forwarder.SCAN_LIMIT', 1)
    log, state = tmp_path / 'eve.json', tmp_path / 'queue.sqlite3'
    append(log, flow(1))
    with closing(sqlite3.connect(state)) as db:
        initialize(db)
        assert scan(db, log) == 0
    append(log, flow(2), flow(3))
    compress_copy(log, tmp_path / 'eve.json.1.gz')
    log.write_bytes(b'')
    fresh = flow(4, src_port=54004)
    append(log, fresh)
    with closing(sqlite3.connect(state)) as db:
        assert scan(db, log) == 1
        assert pending(db) == [normalize(flow(2))['external_event_id']]
    with closing(sqlite3.connect(state)) as db:
        assert scan(db, log) == 1
        assert scan(db, log) == 0  # verified end of archived generation
        assert scan(db, log) == 1
        assert scan(db, log) == 0
        assert pending(db) == [normalize(flow(i))['external_event_id'] for i in (2, 3)] + [normalize(fresh)['external_event_id']]


def test_rename_then_compress_recovers_via_verified_archive(tmp_path):
    log = tmp_path / 'eve.json'
    append(log, flow(1))
    with closing(sqlite3.connect(':memory:')) as db:
        initialize(db)
        assert scan(db, log) == 0
        append(log, flow(2))
        previous = tmp_path / 'old-raw-log'
        log.rename(previous)
        compress_copy(previous, tmp_path / 'eve.json.1.gz')
        append(log, flow(3, src_port=54003))
        assert scan(db, log) == 1
        assert scan(db, log) == 1
        assert scan(db, log) == 0
        assert pending(db) == [normalize(flow(2))['external_event_id'], normalize(flow(3, src_port=54003))['external_event_id']]


def test_archive_rotation_during_recovery_does_not_skip_intermediate_generation(tmp_path, monkeypatch):
    monkeypatch.setattr('collector.suricata_forwarder.SCAN_LIMIT', 1)
    log = tmp_path / 'eve.json'
    append(log, flow(1))
    with closing(sqlite3.connect(':memory:')) as db:
        initialize(db)
        scan(db, log)
        append(log, flow(2))
        archive = tmp_path / 'eve.json.1.gz'
        compress_copy(log, archive)
        log.write_bytes(b'')
        append(log, flow(3, src_port=54003))
        assert scan(db, log) == 1
        position = db.execute('SELECT * FROM eve_position').fetchone()
        archive.rename(tmp_path / 'eve.json.2.gz')
        compress_copy(log, archive)
        log.write_bytes(b'')
        append(log, flow(4, src_port=54004))
        with pytest.raises(RuntimeError, match='Multiple EVE rotations'):
            scan(db, log)
        assert db.execute('SELECT * FROM eve_position').fetchone() == position
        assert pending(db) == [normalize(flow(2))['external_event_id']]


@pytest.mark.parametrize('problem', ['mismatch', 'truncated', 'bad_crc', 'ambiguous', 'older_only', 'oversized'])
def test_unsafe_archives_leave_existing_checkpoint_and_queue_intact(tmp_path, monkeypatch, problem):
    log = tmp_path / 'eve.json'
    archive = tmp_path / 'eve.json.1.gz'
    append(log, flow(1))
    with closing(sqlite3.connect(':memory:')) as db:
        initialize(db)
        assert scan(db, log) == 0
        append(log, flow(2))
        assert scan(db, log) == 1
        checkpoint = db.execute('SELECT * FROM eve_position').fetchone()
        expected = pending(db)
        compress_copy(log, archive)
        if problem == 'mismatch':
            with gzip.open(archive, 'wb') as target:
                target.write(b'X' * log.stat().st_size)
        elif problem == 'truncated':
            archive.write_bytes(archive.read_bytes()[:-8])
        elif problem == 'bad_crc':
            data = bytearray(archive.read_bytes())
            data[-8] ^= 1
            archive.write_bytes(data)
        elif problem == 'ambiguous':
            (tmp_path / 'eve.json.1').write_bytes(log.read_bytes())
        elif problem == 'older_only':
            archive.rename(tmp_path / 'eve.json.2.gz')
        elif problem == 'oversized':
            monkeypatch.setattr('collector.suricata_forwarder.MAX_GZIP_BYTES', 32)
        log.write_bytes(b'new generation\n')
        with pytest.raises((RuntimeError, OSError, EOFError)):
            scan(db, log)
        assert db.execute('SELECT * FROM eve_position').fetchone() == checkpoint
        assert pending(db) == expected


def test_queue_capacity_blocks_recovery_without_changing_state(tmp_path, monkeypatch):
    log = tmp_path / 'eve.json'
    append(log, flow(1))
    with closing(sqlite3.connect(':memory:')) as db:
        initialize(db)
        scan(db, log)
        append(log, flow(2))
        assert scan(db, log) == 1
        position = db.execute('SELECT * FROM eve_position').fetchone()
        compress_copy(log, tmp_path / 'eve.json.1.gz')
        log.write_bytes(b'')
        append(log, flow(3))
        monkeypatch.setattr('collector.suricata_forwarder.QUEUE_LIMIT', 1)
        assert scan(db, log) == 0
        assert db.execute('SELECT * FROM eve_position').fetchone() == position
        assert pending(db) == [normalize(flow(2))['external_event_id']]


def test_recovery_rolls_back_partially_staged_events_on_error(tmp_path, monkeypatch):
    import collector.suricata_forwarder as forwarder
    log = tmp_path / 'eve.json'
    append(log, flow(1))
    with closing(sqlite3.connect(':memory:')) as db:
        initialize(db)
        scan(db, log)
        append(log, flow(2))
        position = db.execute('SELECT * FROM eve_position').fetchone()
        compress_copy(log, tmp_path / 'eve.json.1.gz')
        log.write_bytes(b'')
        append(log, flow(3, src_port=54003))
        original_read = forwarder.read_records
        def interrupted(*args):
            assert original_read(*args)[0] == 1
            raise RuntimeError('Simulated interruption')
        monkeypatch.setattr(forwarder, 'read_records', interrupted)
        with pytest.raises(RuntimeError, match='Simulated interruption'):
            scan(db, log)
        assert db.execute('SELECT * FROM eve_position').fetchone() == position
        assert pending(db) == []
