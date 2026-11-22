"""Read-only authentication event browsing, scoped by existing membership."""

from datetime import datetime, timezone
from ipaddress import ip_address
from typing import Literal
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from sqlalchemy import func, select

from .models import Event, Source, now


AUTH_TYPES = ('LOGIN_FAILED', 'LOGIN_SUCCEEDED')


def utc_filter(value):
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(422, 'Time filters must include an explicit timezone')
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def timestamp(value):
    return value.isoformat() + 'Z'


def event_json(event, source_name, details=False):
    result = {
        'id': event.id, 'event_time': timestamp(event.event_time),
        'ingested_at': timestamp(event.ingested_at), 'event_type': event.event_type,
        'source_id': event.source_id, 'source_name': source_name, 'username': event.username,
        'source_ip': event.source_ip, 'destination_ip': event.destination_ip,
        'destination_port': event.destination_port,
    }
    if details:
        # Arbitrary raw payloads can contain credentials. Expose only known metadata.
        method = event.raw_data.get('authentication_method')
        provenance = event.raw_data.get('provenance')
        result['authentication_method'] = method if method in (
            'password', 'publickey', 'keyboard-interactive', 'keyboard-interactive/pam',
        ) else None
        result['provenance'] = provenance if provenance in ('openssh_journal', 'synthetic_pipeline_test') else None
    return result


def scoped_query(workspace_id):
    return select(Event, Source.name).join(
        Source, (Source.id == Event.source_id) & (Source.workspace_id == Event.workspace_id),
    ).where(Event.workspace_id == workspace_id, Event.event_type.in_(AUTH_TYPES))


def install_security_event_routes(api, member, session_dependency):
    @api.get('/api/events/security')
    def security_events(
        identity=Depends(member), session=Depends(session_dependency),
        event_type: Literal['LOGIN_FAILED', 'LOGIN_SUCCEEDED'] | None = None,
        username: str | None = Query(None, min_length=1, max_length=128),
        source_ip: str | None = Query(None, max_length=45),
        destination_ip: str | None = Query(None, max_length=45),
        source_id: UUID | None = None,
        start_time: datetime | None = None, end_time: datetime | None = None,
        as_of: datetime | None = None,
        limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=1000000),
    ):
        start, end = utc_filter(start_time), utc_filter(end_time)
        if start and end and start > end:
            raise HTTPException(422, 'Start time must not be after end time')
        snapshot = utc_filter(as_of) if as_of else now()
        query = scoped_query(identity.workspace_id).where(Event.ingested_at <= snapshot)
        for field, value in ((Event.event_type, event_type), (Event.username, username),
                             (Event.source_id, str(source_id) if source_id else None)):
            if value is not None:
                query = query.where(field == value)
        for field, value in ((Event.source_ip, source_ip), (Event.destination_ip, destination_ip)):
            if value is not None:
                try:
                    normalized = str(ip_address(value))
                except ValueError:
                    raise HTTPException(422, 'IP filters must be valid IP addresses') from None
                query = query.where(field == normalized)
        if start:
            query = query.where(Event.event_time >= start)
        if end:
            query = query.where(Event.event_time <= end)
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.execute(query.order_by(Event.event_time.desc(), Event.id).limit(limit).offset(offset))
        return {
            'items': [event_json(event, name) for event, name in rows],
            'total': total, 'limit': limit, 'offset': offset,
            'has_more': offset + limit < total, 'as_of': timestamp(snapshot),
        }

    @api.get('/api/events/security/{event_id}')
    def security_event(event_id: str, identity=Depends(member), session=Depends(session_dependency)):
        row = session.execute(scoped_query(identity.workspace_id).where(Event.id == event_id)).first()
        if not row:
            raise HTTPException(404, 'Security event not found')
        return event_json(row[0], row[1], details=True)
