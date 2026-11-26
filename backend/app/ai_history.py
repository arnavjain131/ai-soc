"""Bounded earlier-case retrieval, always constrained to one workspace."""
from datetime import timedelta
from uuid import UUID

from sqlalchemy import and_,func,select

from .models import Alert,Incident

LOOKBACK_DAYS=180
DISPLAY_LIMIT=3
AI_LIMIT=2
METHOD='shared-rule-v1'


def similar_incidents(session,workspace_id,incident_id,limit=DISPLAY_LIMIT):
    current=session.scalar(select(Incident).where(Incident.workspace_id==workspace_id,Incident.id==incident_id))
    if current is None:
        return []
    rules=sorted(set(session.scalars(select(Alert.rule_key).where(
        Alert.workspace_id==workspace_id,Alert.incident_id==current.id).distinct().order_by(Alert.rule_key).limit(20))))
    if not rules:
        return []
    shared=func.count(func.distinct(Alert.rule_key))
    columns=(Incident.id,Incident.title,Incident.status,Incident.severity,Incident.risk_score,Incident.created_at)
    rows=session.execute(select(*columns,shared.label('shared_count')).join(Alert,and_(
        Alert.incident_id==Incident.id,Alert.workspace_id==Incident.workspace_id)).where(
        Incident.workspace_id==workspace_id,Incident.id!=current.id,
        Incident.created_at<current.created_at,
        Incident.created_at>=current.created_at-timedelta(days=LOOKBACK_DAYS),
        Alert.rule_key.in_(rules)).group_by(*columns)
        .order_by(shared.desc(),Incident.created_at.desc(),Incident.id)
        .limit(max(0,min(DISPLAY_LIMIT,limit)))).all()
    if not rows:
        return []
    matching={row.id:[] for row in rows}
    for case_id,rule in session.execute(select(Alert.incident_id,Alert.rule_key).where(
        Alert.workspace_id==workspace_id,Alert.incident_id.in_(matching),Alert.rule_key.in_(rules)).distinct()):
        matching[case_id].append(rule)
    return [{'id':row.id,'title':row.title,'created_at':row.created_at.isoformat()+'Z',
             'status':row.status,'severity':row.severity,'risk_score':row.risk_score,
             'shared_rules':sorted(matching[row.id])} for row in rows]


def historical_context(cases):
    """Explicit allowlist: never forward case titles, identities, notes or logs."""
    return [{'id':str(UUID(item['id'])),'created_at':item['created_at'],
             'status':item['status'] if item['status'] in ('open','investigating','closed','false_positive') else 'unknown',
             'severity':item['severity'] if item['severity'] in ('low','medium','high','critical') else 'unknown',
             'risk_score':item['risk_score'] if type(item['risk_score']) is int and 0<=item['risk_score']<=100 else None,
             'shared_rules':item['shared_rules']} for item in cases[:AI_LIMIT]]


def history_info():
    return {'method':METHOD,'lookback_days':LOOKBACK_DAYS,'display_limit':DISPLAY_LIMIT,'ai_limit':AI_LIMIT}
