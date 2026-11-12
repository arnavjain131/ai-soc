import hashlib
from datetime import timedelta

from sqlalchemy import select

from .models import Alert, AlertEvent, Event, Incident


def detect_brute_force(session, incoming: Event):
    """Scan the affected event-time neighborhood, including late arrivals.

    v1 deliberately correlates only within one source and exact auth entity.
    A source row lock serializes ingestion in PostgreSQL for idempotent results.
    """
    if incoming.event_type != 'LOGIN_FAILED':
        return
    entity = (
        Event.workspace_id == incoming.workspace_id,
        Event.source_id == incoming.source_id,
        Event.event_type == 'LOGIN_FAILED',
        Event.username == incoming.username,
        Event.source_ip == incoming.source_ip,
        Event.destination_ip == incoming.destination_ip,
        Event.destination_port == incoming.destination_port,
    )
    events = list(session.scalars(select(Event).where(
        *entity,
        Event.event_time >= incoming.event_time - timedelta(seconds=120),
        Event.event_time <= incoming.event_time + timedelta(seconds=120),
    ).order_by(Event.event_time, Event.id)))
    # Existing evidence is never reused to create overlapping incidents.
    linked = set(session.scalars(select(AlertEvent.event_id).join(Event, Event.id == AlertEvent.event_id).where(*entity)))
    candidates = [e for e in events if e.id not in linked]
    for end in range(4, len(candidates)):
        window = [e for e in candidates[:end + 1] if candidates[end].event_time - e.event_time <= timedelta(seconds=120)]
        if len(window) < 5:
            continue
        evidence = window[:5]
        key = hashlib.sha256('|'.join(sorted(e.id for e in evidence)).encode()).hexdigest()
        if session.scalar(select(Alert).where(Alert.dedup_key == key)):
            continue
        incident = Incident(workspace_id=incoming.workspace_id, title=f'Possible brute force against {incoming.username}')
        session.add(incident)
        session.flush()
        alert = Alert(
            workspace_id=incoming.workspace_id, incident_id=incident.id, dedup_key=key,
            explanation='5 failed logins for the same user, source IP, target, and port within 120 seconds. This is suspicious activity, not proof of compromise.',
        )
        session.add(alert)
        session.flush()
        session.add_all([AlertEvent(alert_id=alert.id, event_id=e.id) for e in evidence])
        # One five-event cluster per invocation; remaining arrivals can form a new cluster.
        return
