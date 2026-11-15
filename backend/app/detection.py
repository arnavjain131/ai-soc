import hashlib
from collections import Counter, deque
from datetime import timedelta

from sqlalchemy import String, cast, select

from .models import Alert, AlertEvent, Event, Incident


def record_detection(session, evidence, rule_key, title, explanation, severity, score_components):
    identity = '|'.join([rule_key, *sorted(event.id for event in evidence)])
    key = hashlib.sha256(identity.encode()).hexdigest()
    if session.scalar(select(Alert.id).where(Alert.dedup_key == key)):
        return
    incident = Incident(workspace_id=evidence[0].workspace_id, title=title, severity=severity,
                        risk_score=sum(score_components.values()), score_components=score_components)
    session.add(incident)
    session.flush()
    alert = Alert(workspace_id=incident.workspace_id, incident_id=incident.id, dedup_key=key,
                  rule_key=rule_key, explanation=explanation)
    session.add(alert)
    session.flush()
    session.add_all(AlertEvent(alert_id=alert.id, event_id=event.id) for event in evidence)


def linked_events(rule_key):
    return select(AlertEvent.event_id).join(Alert).where(Alert.rule_key == rule_key)


def detect_distinct_pattern(session, incoming, *, rule_key, field, minimum, seconds, additional_filters,
                            title, explanation, severity, score_components):
    window_size = timedelta(seconds=seconds)
    candidates = session.scalars(
        select(Event).where(
            Event.workspace_id == incoming.workspace_id,
            Event.source_id == incoming.source_id,
            Event.source_ip == incoming.source_ip,
            Event.destination_ip == incoming.destination_ip,
            Event.event_type == incoming.event_type,
            Event.event_time.between(incoming.event_time - window_size, incoming.event_time + window_size),
            Event.id.not_in(linked_events(rule_key)),
            *additional_filters,
        ).order_by(Event.event_time, Event.id)
    )
    window = deque()
    distinct = Counter()
    for event in candidates:
        while window and event.event_time - window[0].event_time > window_size:
            value = getattr(window.popleft(), field)
            distinct[value] -= 1
            if not distinct[value]:
                del distinct[value]
        window.append(event)
        distinct[getattr(event, field)] += 1
        if len(distinct) >= minimum:
            evidence = list({getattr(item, field): item for item in window}.values())
            record_detection(session, evidence, rule_key, title, explanation, severity, score_components)
            return


def detect_suricata_alert(session, incoming):
    metadata = incoming.raw_data
    if metadata['severity'] not in (1, 2):
        return
    rule_key = 'suricata_priority_alert_v1'
    interval = timedelta(minutes=5)
    previous = session.scalar(select(Event.id).where(
        Event.workspace_id == incoming.workspace_id,
        Event.source_id == incoming.source_id,
        Event.source_ip == incoming.source_ip,
        Event.destination_ip == incoming.destination_ip,
        Event.destination_port == incoming.destination_port,
        Event.event_type == 'SURICATA_ALERT',
        cast(Event.raw_data['signature_id'].as_string(), String) == str(metadata['signature_id']),
        Event.raw_data['protocol'].as_string() == metadata['protocol'],
        Event.event_time.between(incoming.event_time - interval, incoming.event_time + interval),
        Event.id.in_(linked_events(rule_key)),
    ).limit(1))
    if previous is not None:
        return
    critical = metadata['severity'] == 1
    record_detection(
        session, [incoming], rule_key, f"Suricata alert: {metadata['signature']}"[:200],
        f"Suricata matched signature {metadata['signature_id']} with sensor severity {metadata['severity']}. "
        'Review the signature and network endpoints.',
        'critical' if critical else 'high',
        {'rule_severity': 40, 'network_signature': 40 if critical else 20},
    )


def evaluate_event(session, incoming):
    if incoming.event_type == 'LOGIN_FAILED':
        detect_brute_force(session, incoming)
        detect_distinct_pattern(
            session, incoming, rule_key='password_spray_v1', field='username', minimum=5, seconds=120,
            additional_filters=(Event.destination_port == incoming.destination_port,),
            title='Possible password spraying',
            explanation='Failed logins targeted at least 5 distinct accounts from the same source IP '
                        'against the same destination and service port within 120 seconds.',
            severity='high', score_components={'rule_severity': 35, 'account_diversity': 20},
        )
    elif incoming.event_type == 'NETWORK_FLOW' and incoming.raw_data['protocol'] == 'TCP':
        detect_distinct_pattern(
            session, incoming, rule_key='tcp_port_scan_v1', field='destination_port', minimum=8, seconds=60,
            additional_filters=(Event.raw_data['protocol'].as_string() == 'TCP',),
            title='Possible TCP port scan',
            explanation='TCP flow records from the same source IP targeted at least 8 distinct ports '
                        'on the same destination within 60 seconds. Check for authorized scanners.',
            severity='medium', score_components={'rule_severity': 30, 'port_diversity': 15},
        )
    elif incoming.event_type == 'SURICATA_ALERT':
        detect_suricata_alert(session, incoming)


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
    linked = set(session.scalars(
        linked_events('brute_force_v1').join(Event, Event.id == AlertEvent.event_id).where(*entity)
    ))
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
