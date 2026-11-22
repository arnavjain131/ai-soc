from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.auth import verified_user
from app.models import Event, Membership, Source
from test_pipeline import environment, batch, ingest, network_fixture


def test_authentication_list_and_details_are_workspace_scoped(environment):
    app, client, owner, outsider, analyst = environment
    assert client.get('/api/events/security').status_code == 401
    assert client.get('/api/events/security/unknown').status_code == 401
    assert ingest(client, batch()).json()['accepted'] == 5
    app.dependency_overrides[verified_user] = lambda: owner
    page = client.get('/api/events/security').json()
    assert page['total'] == 5
    event_id = page['items'][0]['id']
    app.dependency_overrides[verified_user] = lambda: analyst
    assert client.get('/api/events/security/' + event_id).status_code == 200
    app.dependency_overrides[verified_user] = lambda: outsider
    assert client.get('/api/events/security').json()['total'] == 0
    assert client.get('/api/events/security/' + event_id).status_code == 404
    app.dependency_overrides[verified_user] = lambda: 'non-member'
    assert client.get('/api/events/security').status_code == 403


def test_filters_include_successes_without_incidents_and_exclude_network_events(environment):
    app, client, owner, *_ = environment
    failed = batch((0, 10), user='alice')['events']
    success = dict(failed[0], external_event_id='success', event_type='LOGIN_SUCCEEDED', username='bob')
    assert ingest(client, {'events': failed + [success, network_fixture('network')]}).json()['accepted'] == 4
    app.dependency_overrides[verified_user] = lambda: owner
    assert client.get('/api/incidents').json() == []
    page = client.get('/api/events/security').json()
    assert page['total'] == 3
    source_id = page['items'][0]['source_id']
    assert {row['event_type'] for row in page['items']} == {'LOGIN_FAILED', 'LOGIN_SUCCEEDED'}
    assert client.get('/api/events/security', params={'event_type': 'LOGIN_SUCCEEDED'}).json()['total'] == 1
    filters = dict(username='alice', source_ip='192.0.2.4', destination_ip='198.51.100.8', source_id=source_id,
                   start_time='2026-01-01T00:00:10Z', end_time='2026-01-01T05:30:10+05:30')
    result = client.get('/api/events/security', params=filters).json()
    assert result['total'] == 1
    assert result['items'][0]['event_time'] == '2026-01-01T00:00:10Z'
    for field, value in [('username', 'ALICE'), ('username', '%'), ('source_ip', '192.0.2.99')]:
        assert client.get('/api/events/security', params=filters | {field: value}).json()['total'] == 0
    with app.state.sessions() as db:
        network_id = db.scalar(select(Event.id).where(Event.event_type == 'NETWORK_FLOW'))
    assert client.get('/api/events/security/' + network_id).status_code == 404


def test_other_workspace_source_filter_cannot_leak_records(environment):
    app, client, owner, outsider, _ = environment
    ingest(client, batch((0,)))
    app.dependency_overrides[verified_user] = lambda: outsider
    other_source = client.post('/api/sources', json={'name': 'Other workspace'}).json()
    response = client.post('/api/events/batch', json=batch((0,), prefix='other'),
                           headers={'X-Source-Token': other_source['token']})
    assert response.status_code == 200
    app.dependency_overrides[verified_user] = lambda: owner
    assert client.get('/api/events/security').json()['total'] == 1
    assert client.get('/api/events/security', params={'source_id': other_source['id']}).json()['items'] == []


def test_pagination_is_deterministic_and_snapshot_excludes_late_ingestion(environment):
    app, client, owner, *_ = environment
    ingest(client, batch((0, 0, 0, 0, 0)))
    app.dependency_overrides[verified_user] = lambda: owner
    first = client.get('/api/events/security', params={'limit': 2}).json()
    assert first['total'] == 5 and first['has_more']
    snapshot = first['as_of']
    with app.state.sessions.begin() as db:
        source = db.scalar(select(Source))
        db.add(Event(workspace_id=source.workspace_id, source_id=source.id, external_event_id='late-arrival',
                     event_type='LOGIN_SUCCEEDED', event_time=datetime(2025, 12, 31),
                     ingested_at=datetime.fromisoformat(snapshot.replace('Z', '')) + timedelta(seconds=1),
                     username='late', source_ip='192.0.2.4', destination_ip='198.51.100.8', destination_port=22))
    second = client.get('/api/events/security', params={'limit': 2, 'offset': 2, 'as_of': snapshot}).json()
    third = client.get('/api/events/security', params={'limit': 2, 'offset': 4, 'as_of': snapshot}).json()
    identifiers = [row['id'] for page in (first, second, third) for row in page['items']]
    assert len(identifiers) == len(set(identifiers)) == 5
    assert identifiers == sorted(identifiers)
    assert second['total'] == third['total'] == 5
    assert not third['has_more']
    assert client.get('/api/events/security', params={'limit': 2, 'as_of': snapshot}).json() == first


@pytest.mark.parametrize('filters', [
    {'start_time': '2026-01-01T00:00:00'}, {'as_of': '2026-01-01T00:00:00'},
    {'start_time': '2026-01-02T00:00:00Z', 'end_time': '2026-01-01T00:00:00Z'},
    {'source_ip': "x' OR 1=1"}, {'destination_ip': 'invalid'}, {'event_type': 'NETWORK_FLOW'},
    {'limit': 101}, {'offset': -1}, {'source_id': 'not-a-uuid'},
])
def test_invalid_filters_are_rejected(environment, filters):
    app, client, owner, *_ = environment
    app.dependency_overrides[verified_user] = lambda: owner
    assert client.get('/api/events/security', params=filters).status_code == 422


@pytest.mark.parametrize('provenance', ['openssh_journal', 'synthetic_pipeline_test'])
def test_event_details_preserve_precision_and_only_expose_safe_metadata(environment, provenance):
    app, client, owner, *_ = environment
    event = batch((0,))['events'][0] | {
        'event_time': '2026-01-01T00:00:00.123456Z',
        'raw_data': {'authentication_method': 'password', 'provenance': provenance,
                     'credential': 'synthetic-private-value'},
    }
    ingest(client, {'events': [event]})
    app.dependency_overrides[verified_user] = lambda: owner
    page = client.get('/api/events/security').json()
    row, = page['items']
    detail = client.get('/api/events/security/' + row['id'])
    assert detail.status_code == 200
    assert detail.json()['event_time'] == '2026-01-01T00:00:00.123456Z'
    assert detail.json()['authentication_method'] == 'password'
    assert detail.json()['provenance'] == provenance
    assert 'raw_data' not in row and 'raw_data' not in detail.json()
    assert 'synthetic-private-value' not in detail.text
    assert 'token_hash' not in detail.text
