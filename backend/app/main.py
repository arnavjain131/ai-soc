import hashlib
import asyncio
import secrets
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text

from .auth import Identity, verified_user
from .config import Settings
from .database import database
from .detection import evaluate_event
from .models import Alert, AlertEvent, Audit, Event, Incident, Membership, Source, now
from .schemas import EventBatch, IncidentUpdate, NetworkRecord, SourceCreate, SuricataAlert
from .security_events import install_security_event_routes
from .incident_journal import install_incident_journal_routes
from .request_limits import Admission, RequestProtection
from .memberships import install_membership_routes
from .ai_analysis import install_ai_routes


NETWORK_TYPES = ('NETWORK_FLOW', 'SURICATA_ALERT')
API_VERSION = '0.7.2'


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def session_dependency(request: Request):
    with request.app.state.sessions() as session:
        yield session


def member(user_id=Depends(verified_user), session=Depends(session_dependency)):
    membership = session.get(Membership, user_id)
    if not membership or membership.role not in ('admin', 'analyst'):
        raise HTTPException(403, 'An administrator must grant workspace access')
    return Identity(user_id, membership.workspace_id, membership.role)


def iso(value):
    return value.isoformat(timespec='seconds') + 'Z'


def incident_json(incident):
    return {name: getattr(incident, name) for name in (
        'id', 'title', 'status', 'severity', 'risk_score', 'score_components'
    )} | {'created_at': iso(incident.created_at), 'updated_at': iso(incident.updated_at)}


def network_event_json(event, source_name):
    fields = {
        'id': event.id, 'event_time': event.event_time.isoformat() + 'Z',
        'event_type': event.event_type, 'source_name': source_name,
        'source_ip': event.source_ip, 'source_port': event.raw_data['source_port'],
        'destination_ip': event.destination_ip, 'destination_port': event.destination_port,
        'protocol': event.raw_data['protocol'],
    }
    if event.event_type == 'SURICATA_ALERT':
        fields.update({name: event.raw_data[name] for name in ('signature_id', 'signature', 'severity')})
    return fields


def network_query(workspace_id):
    return (
        select(Event, Source.name)
        .join(Source, (Source.id == Event.source_id) & (Source.workspace_id == Event.workspace_id))
        .where(Event.workspace_id == workspace_id, Event.event_type.in_(NETWORK_TYPES))
    )


def related_network_events(session, workspace_id, evidence):
    failures = [event for event in evidence if event.event_type == 'LOGIN_FAILED']
    if not failures:
        return []
    # All contributing failures for this rule share the same network endpoints.
    first, last = failures[0], failures[-1]
    window = timedelta(minutes=2)
    rows = session.execute(
        network_query(workspace_id)
        .where(
            Event.source_ip == first.source_ip,
            Event.destination_ip == first.destination_ip,
            Event.destination_port == first.destination_port,
            Event.raw_data['protocol'].as_string() == 'TCP',
            Event.event_time.between(first.event_time - window, last.event_time + window),
        )
        .order_by(Event.event_time, Event.id)
        .limit(50)
    )
    return [network_event_json(event, source_name) for event, source_name in rows]


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or (scope['path'] == '/health/live' and scope['method'] == 'GET'):
            return await self.app(scope, receive, send)
        body = bytearray()
        deadline = asyncio.get_running_loop().time() + 15
        while True:
            try:
                message = await asyncio.wait_for(receive(), timeout=max(0, deadline - asyncio.get_running_loop().time()))
            except TimeoutError:
                return await JSONResponse({'detail': 'Request body timed out'}, status_code=408)(scope, receive, send)
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            if len(body) + len(chunk) > 1048576:
                return await JSONResponse({'detail': 'Request exceeds 1 MiB'}, status_code=413)(scope, receive, send)
            body.extend(chunk)
            if not message.get('more_body', False):
                break
        # Keep one bounded buffer rather than retaining an object for each tiny
        # incoming chunk. This also bounds overhead for empty/chopped uploads.
        chunks = [{'type': 'http.request', 'body': bytes(body), 'more_body': False}]
        async def replay():
            return chunks.pop(0) if chunks else await receive()
        await self.app(scope, replay, send)


def create_app(settings=None):
    settings = settings or Settings()
    settings.validate()
    engine, sessions = database(settings.database_url)

    @asynccontextmanager
    async def lifespan(_):
        yield
        engine.dispose()

    api = FastAPI(title='AI SOC API', version=API_VERSION, lifespan=lifespan)
    api.state.settings, api.state.engine, api.state.sessions = settings, engine, sessions
    api.state.admission = Admission(settings)
    api.add_middleware(BodyLimit)
    api.add_middleware(RequestProtection, admission=api.state.admission)
    api.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.origins.split(',')],
                       allow_methods=['GET', 'POST', 'PATCH', 'DELETE'], allow_headers=['Authorization', 'Content-Type', 'X-Source-Token'],
                       expose_headers=['Retry-After'])

    @api.get('/health/live')
    def live():
        return {'status': 'ok', 'version': API_VERSION}

    @api.get('/health/ready')
    def ready(session=Depends(session_dependency)):
        try:
            session.execute(text('SELECT id FROM soc_workspaces LIMIT 1'))
            return {'status': 'ready'}
        except Exception:
            return JSONResponse({'status': 'database_unavailable_or_not_initialized'}, status_code=503)

    @api.get('/api/me')
    def me(identity=Depends(member)):
        return vars(identity)

    @api.post('/api/events/batch')
    def ingest(batch: EventBatch, request: Request, session=Depends(session_dependency)):
        credential = request.headers.get('X-Source-Token', '')
        if not credential or len(credential) > 256:
            raise HTTPException(401, 'A valid source token is required')
        source = session.scalar(select(Source).where(Source.token_hash == token_hash(credential), Source.enabled.is_(True)).with_for_update())
        if not source:
            raise HTTPException(401, 'Source token is invalid or revoked')
        accepted = duplicates = 0
        for payload in sorted(batch.events, key=lambda x: (x.event_time, x.external_event_id)):
            existing = session.scalar(select(Event.id).where(Event.source_id == source.id, Event.external_event_id == payload.external_event_id))
            if existing:
                duplicates += 1
                continue
            fields = payload.model_dump()
            if isinstance(payload, NetworkRecord):
                metadata = ['source_port', 'protocol']
                if isinstance(payload, SuricataAlert):
                    metadata.extend(('signature_id', 'signature', 'severity'))
                for name in metadata:
                    fields['raw_data'][name] = fields.pop(name)
                fields['username'] = ''
            event = Event(workspace_id=source.workspace_id, source_id=source.id, **fields)
            session.add(event)
            session.flush()
            evaluate_event(session, event)
            accepted += 1
        source.last_seen = now()
        session.commit()
        return {'accepted': accepted, 'duplicates': duplicates}

    @api.get('/api/dashboard/stats')
    def stats(identity=Depends(member), session=Depends(session_dependency)):
        counts = {key: session.scalar(select(func.count()).select_from(model).where(model.workspace_id == identity.workspace_id))
                  for key, model in [('events', Event), ('alerts', Alert), ('incidents', Incident), ('sources', Source)]}
        counts['open_incidents'] = session.scalar(select(func.count()).select_from(Incident).where(
            Incident.workspace_id == identity.workspace_id, Incident.status.in_(['open', 'investigating'])))
        return counts

    @api.get('/api/incidents')
    def incidents(identity=Depends(member), session=Depends(session_dependency), limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        rows = session.scalars(select(Incident).where(Incident.workspace_id == identity.workspace_id).order_by(Incident.created_at.desc(), Incident.id).limit(limit).offset(offset))
        return [incident_json(row) for row in rows]

    @api.get('/api/events/network')
    def network_events(identity=Depends(member), session=Depends(session_dependency), limit: int = Query(25, ge=1, le=100)):
        rows = session.execute(
            network_query(identity.workspace_id)
            .order_by(Event.event_time.desc(), Event.id)
            .limit(limit)
        )
        return [network_event_json(event, source_name) for event, source_name in rows]

    def authorized_incident(session, identity, incident_id):
        incident = session.scalar(select(Incident).where(Incident.id == incident_id, Incident.workspace_id == identity.workspace_id))
        if not incident:
            raise HTTPException(404, 'Incident not found')
        return incident

    @api.get('/api/incidents/{incident_id}')
    def detail(incident_id: str, identity=Depends(member), session=Depends(session_dependency)):
        incident = authorized_incident(session, identity, incident_id)
        alerts = list(session.scalars(select(Alert).where(Alert.incident_id == incident.id)))
        rows = session.execute(
            select(Event, Source.name)
            .join(AlertEvent, AlertEvent.event_id == Event.id)
            .join(Alert, Alert.id == AlertEvent.alert_id)
            .join(Source, (Source.id == Event.source_id) & (Source.workspace_id == Event.workspace_id))
            .where(Alert.incident_id == incident.id, Event.workspace_id == identity.workspace_id)
            .order_by(Event.event_time, Event.id)
        ).unique().all()
        events = [
            network_event_json(event, source_name) if event.event_type in NETWORK_TYPES else {
                'id': event.id, 'event_time': event.event_time.isoformat() + 'Z', 'event_type': event.event_type,
                'username': event.username, 'source_ip': event.source_ip,
                'destination_ip': event.destination_ip, 'destination_port': event.destination_port,
            }
            for event, source_name in rows
        ]
        return incident_json(incident) | {
            'alerts': [{'id': a.id, 'rule_key': a.rule_key, 'explanation': a.explanation} for a in alerts],
            'events': events,
            'related_network_events': related_network_events(session, identity.workspace_id, [event for event, _ in rows]),
        }

    @api.patch('/api/incidents/{incident_id}')
    def update(incident_id: str, payload: IncidentUpdate, identity=Depends(member), session=Depends(session_dependency)):
        incident = authorized_incident(session, identity, incident_id)
        if incident.status in ('closed', 'false_positive') and payload.status != incident.status:
            raise HTTPException(409, 'Terminal incidents cannot be reopened in this version')
        previous = incident.status
        incident.status, incident.updated_at = payload.status, now()
        session.add(Audit(workspace_id=identity.workspace_id, actor=identity.user_id, action='incident.status_changed',
                          target_id=incident.id, details={'before': previous, 'after': payload.status}))
        session.commit()
        return incident_json(incident)

    @api.post('/api/sources', status_code=201)
    def add_source(payload: SourceCreate, identity=Depends(member), session=Depends(session_dependency)):
        if identity.role != 'admin':
            raise HTTPException(403, 'Administrator access required')
        token = secrets.token_urlsafe(32)
        source = Source(workspace_id=identity.workspace_id, name=payload.name, token_hash=token_hash(token))
        session.add(source)
        session.flush()
        session.add(Audit(workspace_id=identity.workspace_id, actor=identity.user_id, action='source.created', target_id=source.id))
        session.commit()
        return {'id': source.id, 'name': source.name, 'token': token}

    @api.get('/api/sources')
    def sources(identity=Depends(member), session=Depends(session_dependency)):
        return [{'id': s.id, 'name': s.name, 'enabled': s.enabled, 'last_seen': iso(s.last_seen) if s.last_seen else None}
                for s in session.scalars(select(Source).where(Source.workspace_id == identity.workspace_id).order_by(Source.name).limit(100))]

    @api.post('/api/sources/{source_id}/revoke')
    def revoke(source_id: str, identity=Depends(member), session=Depends(session_dependency)):
        if identity.role != 'admin':
            raise HTTPException(403, 'Administrator access required')
        source = session.scalar(select(Source).where(Source.id == source_id, Source.workspace_id == identity.workspace_id))
        if not source:
            raise HTTPException(404, 'Source not found')
        source.enabled = False
        session.add(Audit(workspace_id=identity.workspace_id, actor=identity.user_id, action='source.revoked', target_id=source.id))
        session.commit()
        return {'revoked': True}

    install_security_event_routes(api, member, session_dependency)
    install_incident_journal_routes(api, member, session_dependency, authorized_incident)
    install_membership_routes(api, member, session_dependency)
    install_ai_routes(api, member, session_dependency, authorized_incident, detail)
    return api


app = create_app()
