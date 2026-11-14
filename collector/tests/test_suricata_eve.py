from collector.suricata_eve import normalize


def test_flow_normalization_preserves_tuple_and_excludes_payload():
    entry = {
        'event_type': 'flow', 'flow_id': 123, 'timestamp': '2025-11-15T17:30:00.123456+0530',
        'src_ip': '192.0.2.2', 'src_port': 51234, 'dest_ip': '198.51.100.15', 'dest_port': 22,
        'proto': 'TCP', 'payload': 'not needed for telemetry',
    }
    event = normalize(entry)
    assert event['event_time'] == '2025-11-15T12:00:00.123456+00:00'
    assert (event['source_ip'], event['source_port']) == ('192.0.2.2', 51234)
    assert (event['destination_ip'], event['destination_port']) == ('198.51.100.15', 22)
    assert event['raw_data'] == {'provenance': 'suricata_eve'}
    assert normalize(dict(entry, payload='different')) == event
    assert normalize(dict(entry, src_port=True)) is None
    assert normalize(dict(entry, event_type='alert')) is None
