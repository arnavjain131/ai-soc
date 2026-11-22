"""Append-only analyst notes and incident-scoped audit history."""

from uuid import UUID

from fastapi import Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select

from .models import Audit, Incident


NOTE_ACTION = 'incident.note_added'
HISTORY_ACTIONS = (NOTE_ACTION, 'incident.status_changed')


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    body: str = Field(min_length=1, max_length=2000)
    request_id: UUID

    @field_validator('body')
    @classmethod
    def non_blank(cls, value):
        value = value.strip()
        if not value:
            raise ValueError('A note must contain text')
        return value


def common_json(row):
    return {'id': row.id, 'actor_id': row.actor, 'created_at': row.created_at.isoformat() + 'Z'}


def note_json(row):
    return common_json(row) | {'body': row.details['body']}


def audit_json(row):
    details = {}
    if row.action == 'incident.status_changed':
        allowed = ('open', 'investigating', 'closed', 'false_positive')
        details = {key: row.details.get(key) if row.details.get(key) in allowed else None
                   for key in ('before', 'after')}
    return common_json(row) | {'action': row.action, 'details': details}


def install_incident_journal_routes(api, member, session_dependency, authorized_incident):
    def scoped(identity, incident_id):
        return select(Audit).where(Audit.workspace_id == identity.workspace_id,
                                   Audit.target_id == incident_id)

    def page(session, query, serialize, limit, offset):
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.scalars(query.order_by(Audit.created_at.desc(), Audit.id.desc()).limit(limit).offset(offset))
        return {'items': [serialize(row) for row in rows], 'total': total,
                'limit': limit, 'offset': offset, 'has_more': offset + limit < total}

    @api.get('/api/incidents/{incident_id}/notes')
    def notes(incident_id: str, identity=Depends(member), session=Depends(session_dependency),
              limit: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0, le=1000000)):
        authorized_incident(session, identity, incident_id)
        return page(session, scoped(identity, incident_id).where(Audit.action == NOTE_ACTION),
                    note_json, limit, offset)

    @api.post('/api/incidents/{incident_id}/notes', status_code=201)
    def add_note(incident_id: str, payload: NoteCreate, response: Response,
                 identity=Depends(member), session=Depends(session_dependency)):
        incident = authorized_incident(session, identity, incident_id)
        # Serialize identical retries in PostgreSQL without adding schema or indexes.
        session.execute(select(Incident.id).where(Incident.id == incident.id,
                         Incident.workspace_id == identity.workspace_id).with_for_update()).scalar_one()
        existing = session.scalar(scoped(identity, incident_id).where(
            Audit.action == NOTE_ACTION, Audit.actor == identity.user_id,
            Audit.details['request_id'].as_string() == str(payload.request_id),
        ))
        if existing:
            if existing.details['body'] != payload.body:
                raise HTTPException(409, 'This request ID was already used for a different note')
            response.status_code = 200
            return note_json(existing)
        row = Audit(workspace_id=identity.workspace_id, actor=identity.user_id,
                    action=NOTE_ACTION, target_id=incident.id,
                    details={'body': payload.body, 'request_id': str(payload.request_id)})
        session.add(row)
        session.commit()
        return note_json(row)

    @api.get('/api/incidents/{incident_id}/audit')
    def audit(incident_id: str, identity=Depends(member), session=Depends(session_dependency),
              limit: int = Query(10, ge=1, le=100), offset: int = Query(0, ge=0, le=1000000)):
        authorized_incident(session, identity, incident_id)
        return page(session, scoped(identity, incident_id).where(Audit.action.in_(HISTORY_ACTIONS)),
                    audit_json, limit, offset)
