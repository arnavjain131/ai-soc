import hashlib
import secrets
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text

from .auth import Identity, verified_user
from .config import Settings
from .database import database
from .detection import detect_brute_force
from .models import Alert, AlertEvent, Audit, Event, Incident, Membership, Source, now
from .schemas import EventBatch, IncidentUpdate, SourceCreate


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


class BodyLimit:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        chunks, size = [], 0
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            size += len(message.get('body', b''))
            if size > 1048576:
                return await JSONResponse({'detail': 'Request exceeds 1 MiB'}, status_code=413)(scope, receive, send)
            chunks.append(message)
            if not message.get('more_body', False):
                break
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

    api = FastAPI(title='AI SOC API', version='0.1.0', lifespan=lifespan)
    api.state.settings, api.state.engine, api.state.sessions = settings, engine, sessions
    api.add_middleware(BodyLimit)
    api.add_middleware(CORSMiddleware, allow_origins=[x.strip() for x in settings.origins.split(',')],
                       allow_methods=['GET', 'POST', 'PATCH'], allow_headers=['Authorization', 'Content-Type', 'X-Source-Token'])

    @api.get('/health/live')
    def live():
        return {'status': 'ok', 'version': '0.1.0'}

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
            event = Event(workspace_id=source.workspace_id, source_id=source.id, **payload.model_dump())
            session.add(event)
            session.flush()
            detect_brute_force(session, event)
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

    def authorized_incident(session, identity, incident_id):
        incident = session.scalar(select(Incident).where(Incident.id == incident_id, Incident.workspace_id == identity.workspace_id))
        if not incident:
            raise HTTPException(404, 'Incident not found')
        return incident

    @api.get('/api/incidents/{incident_id}')
    def detail(incident_id: str, identity=Depends(member), session=Depends(session_dependency)):
        incident = authorized_incident(session, identity, incident_id)
        alerts = list(session.scalars(select(Alert).where(Alert.incident_id == incident.id)))
        evidence = session.scalars(select(Event).join(AlertEvent, AlertEvent.event_id == Event.id).join(Alert, Alert.id == AlertEvent.alert_id).where(
            Alert.incident_id == incident.id, Event.workspace_id == identity.workspace_id).order_by(Event.event_time, Event.id)).unique()
        return incident_json(incident) | {
            'alerts': [{'id': a.id, 'rule_key': a.rule_key, 'explanation': a.explanation} for a in alerts],
            'events': [{'id': e.id, 'event_time': iso(e.event_time), 'event_type': e.event_type, 'username': e.username,
                        'source_ip': e.source_ip, 'destination_ip': e.destination_ip, 'destination_port': e.destination_port} for e in evidence],
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

    return api


app = create_app()
