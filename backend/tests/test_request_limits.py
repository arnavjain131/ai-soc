import asyncio

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import BodyLimit, create_app
from app.models import Base, Event
from app.request_limits import Admission, RequestProtection


def config(**kwargs):
    values = dict(database_url='sqlite:///:memory:', request_burst=1, supabase_url='', supabase_key='')
    values.update(kwargs)
    return Settings(**values)


def test_limit_precedes_auth_and_database_and_keeps_cors(monkeypatch):
    app = create_app(config(supabase_url='https://example.supabase.co', supabase_key='test'))
    calls = []
    def auth(*args, **kwargs):
        calls.append(1)
        import httpx
        return httpx.Response(401, request=httpx.Request('GET', 'https://example.supabase.co'))
    monkeypatch.setattr('app.auth.httpx.get', auth)
    with TestClient(app) as client:
        headers = {'Authorization': 'Bearer synthetic', 'Origin': 'http://localhost:5173'}
        assert client.get('/api/me', headers=headers).status_code == 401
        response = client.get('/api/incidents', headers=headers)
        assert response.status_code == 429 and len(calls) == 1
        assert int(response.headers['retry-after']) >= 1
        assert response.headers['access-control-allow-origin'] == headers['Origin']
        assert 'Retry-After' in response.headers['access-control-expose-headers']
        assert 'synthetic' not in response.text


def test_ingest_throttle_does_not_persist_or_acknowledge_events():
    app = create_app(config())
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        # Reserve its allowance without invoking the ingestion route.
        assert app.state.admission.admit('ingest', b'synthetic-source') == 0
        app.state.admission.active -= 1
        result = client.post('/api/events/batch', json={'events': []}, headers={'X-Source-Token': 'synthetic-source'})
        assert result.status_code == 429
        assert 'accepted' not in result.json()
        with app.state.sessions() as db:
            assert db.query(Event).count() == 0


def test_retry_refills_and_other_credentials_and_ingestion_have_separate_budgets():
    moment = [100.0]
    gate = Admission(config(), clock=lambda: moment[0])
    def attempt(group, key):
        delay = gate.admit(group, key)
        if not delay:
            gate.active -= 1
        return delay
    assert attempt('api', b'a') == 0
    assert attempt('api', b'a') == 1
    assert attempt('api', b'b') == 0
    assert attempt('ingest', b'a') == 0
    moment[0] += 1
    assert attempt('api', b'a') == 0


def test_rotating_credentials_and_spoofed_ip_cannot_escape_aggregate_budget():
    app = create_app(config())
    with TestClient(app) as client:
        for index in range(4):
            assert client.get('/api/me', headers={'Authorization': f'Bearer invalid-{index}'}).status_code == 503
        denied = client.get('/api/me', headers={'Authorization': 'Bearer new', 'X-Forwarded-For': '192.0.2.33'})
        assert denied.status_code == 429
        assert client.get('/health/live').status_code == 200
        assert client.post('/api/events/batch', json={'events': []}).status_code == 422


def test_table_capacity_fails_closed_then_reclaims_idle_entries():
    moment = [100.0]
    gate = Admission(config(), clock=lambda: moment[0], capacity=2)
    for key in (b'a', b'b'):
        assert gate.admit('api', key) == 0
        gate.active -= 1
    assert gate.admit('api', b'c') == 120
    assert len(gate.credentials) == 2
    moment[0] += 121
    assert gate.admit('api', b'c') == 0
    assert len(gate.credentials) == 1


def test_oversized_header_is_rejected_without_auth_service(monkeypatch):
    app = create_app(config())
    def forbidden(*args, **kwargs):
        pytest.fail('Auth service must not be called')
    monkeypatch.setattr('app.auth.httpx.get', forbidden)
    with TestClient(app) as client:
        assert client.get('/api/me', headers={'Authorization': 'Bearer ' + 'x'*8192}).status_code == 401


def test_preflight_and_readiness_have_independent_allowances():
    app = create_app(config())
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as client:
        for _ in range(6):
            assert client.options('/api/me', headers={'Origin': 'http://localhost:5173',
                'Access-Control-Request-Method': 'GET'}).status_code == 200
        assert client.get('/api/me').status_code == 401
        for _ in range(10):
            assert client.get('/health/ready').status_code == 200
        assert client.get('/health/ready').status_code == 429
        assert client.get('/health/live').status_code == 200


def test_concurrent_work_is_bounded_and_slots_release_after_error():
    async def exercise():
        entered, release = asyncio.Event(), asyncio.Event()
        gate = Admission(config(request_max_in_flight=1, request_burst=30))
        async def app(scope, receive, send):
            entered.set()
            await release.wait()
            raise RuntimeError('synthetic failure')
        protected = RequestProtection(app, gate)
        scope = {'type':'http', 'path':'/api/me', 'headers':[]}
        output = []
        async def send(message): output.append(message)
        async def receive(): return {'type':'http.request', 'body':b''}
        first = asyncio.create_task(protected(scope, receive, send))
        await entered.wait()
        await protected(scope, receive, send)
        assert output[0]['status'] == 429 and gate.active == 1
        release.set()
        with pytest.raises(RuntimeError): await first
        assert gate.active == 0
    asyncio.run(exercise())


def test_body_timeout_releases_admission_slot(monkeypatch):
    async def exercise():
        async def timeout(awaitable, timeout):
            awaitable.close()
            raise TimeoutError
        monkeypatch.setattr('app.main.asyncio.wait_for', timeout)
        async def app(scope, receive, send): pytest.fail('Route must not execute')
        gate = Admission(config())
        protected = RequestProtection(BodyLimit(app), gate)
        output=[]
        async def send(message): output.append(message)
        async def receive(): return {'type':'http.request', 'body':b''}
        await protected({'type':'http', 'path':'/api/me', 'headers':[]},receive,send)
        assert output[0]['status'] == 408 and gate.active == 0
    asyncio.run(exercise())


def test_chunked_body_limit_does_not_require_content_length():
    async def exercise():
        chunks = iter([{'type':'http.request', 'body':b'x' * 600000, 'more_body':True},
                       {'type':'http.request', 'body':b'x' * 600000, 'more_body':False}])
        output = []
        async def receive(): return next(chunks)
        async def send(message): output.append(message)
        async def app(scope, receive, send): pytest.fail('Oversized body must not reach route')
        gate = Admission(config())
        await RequestProtection(BodyLimit(app),gate)(
            {'type':'http','path':'/api/events/batch','headers':[]},receive,send)
        assert output[0]['status'] == 413 and gate.active == 0
    asyncio.run(exercise())


def test_fragmented_upload_is_replayed_as_one_complete_body():
    async def exercise():
        chunks = iter([{'type':'http.request','body':b'','more_body':True} for _ in range(100)] +
                      [{'type':'http.request','body':b'{"events":','more_body':True},
                       {'type':'http.request','body':b'[]}', 'more_body':False}])
        async def receive(): return next(chunks)
        async def send(message): pass
        async def app(scope, receive, send):
            assert await receive() == {'type':'http.request','body':b'{"events":[]}', 'more_body':False}
        await BodyLimit(app)({'type':'http','path':'/api/events/batch'}, receive, send)
    asyncio.run(exercise())


@pytest.mark.parametrize('field,value', [('request_burst',0), ('request_max_in_flight',65),
    ('request_per_credential',1), ('request_pool_per_minute',0)])
def test_invalid_limits_fail_startup(field, value):
    with pytest.raises(ValueError): config(**{field:value}).validate()
