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
    app = create_app(Settings(database_url='sqlite:///:memory:', supabase_url='https://example.supabase.co', supabase_key='public-test-key'))
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
