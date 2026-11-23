from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth import verified_user
from app.config import Settings
from app.main import create_app, token_hash
from app.models import Alert, Audit, Base, Event, Membership, Source, Workspace


@pytest.fixture
def environment():
    app = create_app(Settings(database_url='sqlite:///:memory:', supabase_url='https://example.supabase.co', supabase_key='public-test-key', ai_enabled=False, openai_api_key=''))
    Base.metadata.create_all(app.state.engine)
    owner, outsider, analyst = (str(uuid4()) for _ in range(3))
    with app.state.sessions.begin() as db:
        workspace, other = Workspace(name='Private'), Workspace(name='Other')
        db.add_all([workspace, other]); db.flush()
        db.add_all([Membership(user_id=owner, workspace_id=workspace.id, role='admin'),
                    Membership(user_id=outsider, workspace_id=other.id, role='admin'),
                    Membership(user_id=analyst, workspace_id=workspace.id, role='analyst')])
        db.add(Source(workspace_id=workspace.id, name='Auth', token_hash=token_hash('test-source')))
    with TestClient(app) as client:
        yield app, client, owner, outsider, analyst


def batch(seconds=(0, 15, 30, 45, 60), user='admin', prefix='event'):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return {'events': [dict(external_event_id=f'{prefix}-{i}', event_time=(base + timedelta(seconds=second)).isoformat(),
                           event_type='LOGIN_FAILED', source_ip='192.0.2.4', destination_ip='198.51.100.8',
                           destination_port=22, username=user) for i, second in enumerate(seconds)]}


def ingest(client, payload):
    return client.post('/api/events/batch', json=payload, headers={'X-Source-Token': 'test-source'})


def test_network_flow_is_persisted_and_visible_only_to_members(environment):
    app, client, owner, outsider, _ = environment
    flow = {
        'external_event_id': 'flow-one', 'event_type': 'NETWORK_FLOW',
        'event_time': '2025-11-15T12:00:00.123456Z', 'protocol': 'TCP',
        'source_ip': '192.0.2.2', 'source_port': 51234,
        'destination_ip': '198.51.100.15', 'destination_port': 22,
        'raw_data': {'provenance': 'suricata_eve'},
    }
    assert client.get('/api/events/network').status_code == 401
    assert ingest(client, {'events': [flow]}).json() == {'accepted': 1, 'duplicates': 0}
    assert ingest(client, {'events': [flow]}).json() == {'accepted': 0, 'duplicates': 1}
    app.dependency_overrides[verified_user] = lambda: outsider
    assert client.get('/api/events/network').json() == []
    app.dependency_overrides[verified_user] = lambda: owner
    record, = client.get('/api/events/network').json()
    assert record['event_time'] == flow['event_time']
    for field in ('source_ip', 'source_port', 'destination_ip', 'destination_port', 'protocol'):
        assert record[field] == flow[field]
    assert client.get('/api/incidents').json() == []


def test_incident_network_context_matches_workspace_endpoints_protocol_and_time(environment):
    app, client, owner, outsider, _ = environment
    with app.state.sessions.begin() as db:
        for user, token in [(owner, 'lab-network'), (outsider, 'other-network')]:
            workspace = db.get(Membership, user).workspace_id
            db.add(Source(workspace_id=workspace, name='Suricata', token_hash=token_hash(token)))

    flow = {
        'external_event_id': 'early-flow', 'event_type': 'NETWORK_FLOW',
        'event_time': '2026-01-01T00:00:30Z', 'protocol': 'TCP',
        'source_ip': '192.0.2.4', 'source_port': 51234,
        'destination_ip': '198.51.100.8', 'destination_port': 22,
        'raw_data': {'provenance': 'suricata_eve'},
    }
    alert = dict(flow, external_event_id='late-alert', event_type='SURICATA_ALERT',
                 event_time='2026-01-01T00:02:30Z', signature_id=1234,
                 signature='Fixture lab SSH alert', severity=3)

    def send(token, *events):
        return client.post('/api/events/batch', json={'events': list(events)}, headers={'X-Source-Token': token})

    assert send('lab-network', flow).json() == {'accepted': 1, 'duplicates': 0}
    assert ingest(client, batch()).json() == {'accepted': 5, 'duplicates': 0}
    app.dependency_overrides[verified_user] = lambda: owner
    incident, = client.get('/api/incidents').json()
    path = '/api/incidents/' + incident['id']
    assert [e['event_type'] for e in client.get(path).json()['related_network_events']] == ['NETWORK_FLOW']
    assert send('other-network', alert).status_code == 200
    assert send('lab-network', alert, dict(flow, external_event_id='wrong-port', destination_port=443),
                dict(flow, external_event_id='old', event_time='2025-12-31T23:57:59Z'),
                dict(flow, external_event_id='udp', protocol='UDP')).json() == {'accepted': 4, 'duplicates': 0}
    assert send('lab-network', alert).json() == {'accepted': 0, 'duplicates': 1}
    assert send('lab-network', dict(alert, severity=True)).status_code == 422

    result = client.get(path).json()
    assert len(result['events']) == 5
    assert len(result['alerts']) == 1
    related = result['related_network_events']
    assert [e['event_type'] for e in related] == ['NETWORK_FLOW', 'SURICATA_ALERT']
    assert related[1]['signature'] == alert['signature']
    assert related[1]['source_name'] == 'Suricata'
    assert len(client.get('/api/incidents').json()) == 1
    assert [e['signature_id'] for e in client.get('/api/events/network').json() if e['event_type'] == 'SURICATA_ALERT'] == [1234]
    app.dependency_overrides[verified_user] = lambda: outsider
    assert client.get(path).status_code == 404


def test_pipeline_evidence_and_retry_are_idempotent(environment):
    app, client, owner, *_ = environment
    app.dependency_overrides[verified_user] = lambda: owner
    assert ingest(client, batch()).json() == {'accepted': 5, 'duplicates': 0}
    assert ingest(client, batch()).json() == {'accepted': 0, 'duplicates': 5}
    incidents = client.get('/api/incidents').json()
    assert len(incidents) == 1
    detail = client.get('/api/incidents/' + incidents[0]['id']).json()
    assert len(detail['events']) == 5
    assert detail['risk_score'] == sum(detail['score_components'].values()) == 50
    assert detail['alerts'][0]['rule_key'] == 'brute_force_v1'
    assert client.get('/api/dashboard/stats').json()['events'] == 5


@pytest.mark.parametrize('seconds,expected', [((0, 30, 60, 90, 120), 1), ((0, 30, 60, 90, 121), 0), ((0, 10, 20, 30), 0)])
def test_detection_time_window_edges(environment, seconds, expected):
    app, client, owner, *_ = environment
    app.dependency_overrides[verified_user] = lambda: owner
    assert ingest(client, batch(seconds)).status_code == 200
    assert len(client.get('/api/incidents').json()) == expected


def test_late_arrival_and_duplicate_in_same_batch(environment):
    app, client, owner, *_ = environment
    app.dependency_overrides[verified_user] = lambda: owner
    payload = batch((0, 30, 60, 90, 120))
    assert ingest(client, {'events': payload['events'][1:]}).json()['accepted'] == 4
    assert ingest(client, {'events': [payload['events'][0], payload['events'][0]]}).json() == {'accepted': 1, 'duplicates': 1}
    assert len(client.get('/api/incidents').json()) == 1


def test_entities_are_not_mixed(environment):
    app, client, owner, *_ = environment
    app.dependency_overrides[verified_user] = lambda: owner
    ingest(client, batch((0, 15, 30, 45), user='admin'))
    ingest(client, batch((55,), user='another-user', prefix='other'))
    assert client.get('/api/incidents').json() == []


def test_password_spray_counts_distinct_accounts_and_keeps_brute_force_separate(environment):
    app, client, owner, *_ = environment
    app.dependency_overrides[verified_user] = lambda: owner
    ingest(client, batch(user='alice'))
    others = batch((70, 80, 90, 120), prefix='other-accounts')['events']
    for event, name in zip(others, ('bob', 'carol', 'dave', 'erin')):
        event['username'] = name
    assert ingest(client, {'events': others[:3]}).json()['accepted'] == 3
    assert {row['title'] for row in client.get('/api/incidents').json()} == {'Possible brute force against alice'}
    assert ingest(client, {'events': others[3:]}).json()['accepted'] == 1
    incidents = client.get('/api/incidents').json()
    spray, = [row for row in incidents if row['title'] == 'Possible password spraying']
    detail = client.get('/api/incidents/' + spray['id']).json()
    assert detail['alerts'][0]['rule_key'] == 'password_spray_v1'
    assert {row['username'] for row in detail['events']} == {'alice', 'bob', 'carol', 'dave', 'erin'}
    assert len(incidents) == 2


def network_fixture(event_id, seconds=0, **fields):
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    event = {
        'external_event_id': event_id, 'event_type': 'NETWORK_FLOW',
        'event_time': (base + timedelta(seconds=seconds)).isoformat(),
        'source_ip': '192.0.2.4', 'source_port': 51000, 'destination_ip': '198.51.100.8',
        'destination_port': 22, 'protocol': 'TCP', 'raw_data': {'provenance': 'suricata_eve'},
    }
    return event | fields


def test_tcp_port_scan_groups_distinct_ports_and_supports_late_events(environment):
    app, client, owner, outsider, _ = environment
    app.dependency_overrides[verified_user] = lambda: owner
    with app.state.sessions.begin() as db:
        db.add(Source(workspace_id=db.get(Membership, outsider).workspace_id,
                      name='Other sensor', token_hash=token_hash('other-source')))
    flows = [network_fixture(f'flow-{port}', i * 8, destination_port=port)
             for i, port in enumerate(range(10001, 10009))]
    noise = [
        network_fixture('same-port', 45, destination_port=10008),
        network_fixture('udp', 45, destination_port=10001, protocol='UDP'),
        network_fixture('other-destination', 45, destination_port=10001, destination_ip='198.51.100.9'),
        network_fixture('other-peer', 45, destination_port=10001, source_ip='192.0.2.5'),
        network_fixture('expired', -61, destination_port=10001),
    ]
    assert ingest(client, {'events': flows[1:] + noise}).status_code == 200
    assert client.post('/api/events/batch', json={'events': [flows[0]]},
                       headers={'X-Source-Token': 'other-source'}).status_code == 200
    assert client.get('/api/incidents').json() == []
    assert ingest(client, {'events': [flows[0]]}).json() == {'accepted': 1, 'duplicates': 0}
    assert ingest(client, {'events': [flows[0]]}).json() == {'accepted': 0, 'duplicates': 1}
    incident, = client.get('/api/incidents').json()
    detail = client.get('/api/incidents/' + incident['id']).json()
    assert incident['severity'] == 'medium'
    assert detail['alerts'][0]['rule_key'] == 'tcp_port_scan_v1'
    assert {row['destination_port'] for row in detail['events']} == set(range(10001, 10009))
    assert all(row['protocol'] == 'TCP' and row['source_port'] == 51000 for row in detail['events'])


def test_suricata_priority_alerts_create_incidents_and_throttle_repeats(environment):
    app, client, owner, *_ = environment
    app.dependency_overrides[verified_user] = lambda: owner
    fields = dict(event_type='SURICATA_ALERT', signature_id=4_000_000_001, signature='Test sensor alert')
    records = [
        network_fixture('informational', severity=3, **fields),
        network_fixture('priority-one', 10, severity=1, **fields),
        network_fixture('repeat', 15, severity=1, **fields),
        network_fixture('priority-two', 311, severity=2, **fields),
    ]
    assert ingest(client, {'events': records}).json() == {'accepted': 4, 'duplicates': 0}
    incidents = client.get('/api/incidents').json()
    assert sorted(row['severity'] for row in incidents) == ['critical', 'high']
    assert len(client.get('/api/events/network').json()) == 4
    for incident in incidents:
        detail = client.get('/api/incidents/' + incident['id']).json()
        assert detail['alerts'][0]['rule_key'] == 'suricata_priority_alert_v1'
        evidence, = detail['events']
        assert evidence['signature_id'] == 4_000_000_001
        assert evidence['severity'] in (1, 2)


def test_access_boundaries_and_membership(environment):
    app, client, owner, outsider, _ = environment
    assert client.get('/api/incidents').status_code == 401
    assert client.post('/api/events/batch', json=batch()).status_code == 401
    ingest(client, batch())
    app.dependency_overrides[verified_user] = lambda: owner
    incident_id = client.get('/api/incidents').json()[0]['id']
    app.dependency_overrides[verified_user] = lambda: outsider
    assert client.get('/api/incidents').json() == []
    assert client.get('/api/incidents/' + incident_id).status_code == 404
    assert client.patch('/api/incidents/' + incident_id, json={'status': 'closed'}).status_code == 404
    app.dependency_overrides[verified_user] = lambda: str(uuid4())
    assert client.get('/api/me').status_code == 403


def test_disposition_is_audited_and_terminal(environment):
    app, client, owner, *_ = environment
    app.dependency_overrides[verified_user] = lambda: owner
    ingest(client, batch())
    incident_id = client.get('/api/incidents').json()[0]['id']
    assert client.patch('/api/incidents/' + incident_id, json={'status': 'closed'}).status_code == 200
    assert client.patch('/api/incidents/' + incident_id, json={'status': 'open'}).status_code == 409
    with app.state.sessions() as db:
        audit = db.scalar(select(Audit).where(Audit.action == 'incident.status_changed'))
        assert audit.details == {'before': 'open', 'after': 'closed'}


def test_source_admin_permissions_revocation_and_no_hash_leak(environment):
    app, client, owner, _, analyst = environment
    app.dependency_overrides[verified_user] = lambda: analyst
    assert client.post('/api/sources', json={'name': 'test'}).status_code == 403
    app.dependency_overrides[verified_user] = lambda: owner
    source = client.post('/api/sources', json={'name': 'new'}).json()
    assert source['token'] not in client.get('/api/sources').text
    assert 'token_hash' not in client.get('/api/sources').text
    client.post(f"/api/sources/{source['id']}/revoke")
    assert client.post('/api/events/batch', json=batch(), headers={'X-Source-Token': source['token']}).status_code == 401


def test_batch_validation_and_body_limit(environment):
    _, client, *_ = environment
    payload = batch()
    payload['events'][-1]['event_time'] = '2026-01-01T00:01:00'
    assert ingest(client, payload).status_code == 422
    payload = batch(); payload['events'][0]['workspace_id'] = 'injected'
    assert ingest(client, payload).status_code == 422
    assert client.post('/api/events/batch', content=b'x' * 1048577, headers={'Content-Type': 'application/json'}).status_code == 413


def test_auth_server_validation_and_outage(environment, monkeypatch):
    _, client, owner, *_ = environment
    def auth_response(url, **kwargs):
        assert url == 'https://example.supabase.co/auth/v1/user'
        assert kwargs['headers']['Authorization'] == 'Bearer sample'
        return httpx.Response(200, json={'id': owner}, request=httpx.Request('GET', url))
    monkeypatch.setattr('app.auth.httpx.get', auth_response)
    assert client.get('/api/me', headers={'Authorization': 'Bearer sample'}).status_code == 200
    monkeypatch.setattr('app.auth.httpx.get', lambda url, **kw: httpx.Response(401, request=httpx.Request('GET', url)))
    assert client.get('/api/me', headers={'Authorization': 'Bearer sample'}).status_code == 401
    def outage(*a, **kw):
        raise httpx.ConnectError('offline')
    monkeypatch.setattr('app.auth.httpx.get', outage)
    assert client.get('/api/me', headers={'Authorization': 'Bearer sample'}).status_code == 503


def test_production_rejects_sqlite():
    with pytest.raises(ValueError, match='PostgreSQL'):
        create_app(Settings(environment='production', database_url='sqlite:///:memory:'))
