"""Read-only, workspace-scoped incident queue. Legacy list API stays intact."""
from datetime import datetime
from typing import Literal

from fastapi import Depends, HTTPException, Query
from sqlalchemy import func, or_, select

from .models import Alert, Incident, now
from .security_events import utc_filter, timestamp


def install_incident_search(api, member, session_dependency, serialize):
    @api.get('/api/incidents/search')
    def search(
        identity=Depends(member), session=Depends(session_dependency),
        q: str = Query('', max_length=200),
        status: Literal['open','investigating','closed','false_positive'] | None=None,
        severity: Literal['critical','high','medium','low'] | None=None,
        rule_key: Literal['brute_force_v1','password_spray_v1','tcp_port_scan_v1','suricata_priority_alert_v1'] | None=None,
        start_time: datetime | None=None, end_time: datetime | None=None,
        as_of: datetime | None=None,
        sort: Literal['newest','oldest','risk']='newest',
        limit: int=Query(25,ge=1,le=100), offset: int=Query(0,ge=0,le=1000000),
    ):
        start,end,cutoff=utc_filter(start_time),utc_filter(end_time),utc_filter(as_of)
        if start and end and start>end:
            raise HTTPException(422,'Start time must not be after end time')
        instant=now()
        if cutoff and cutoff>instant:
            raise HTTPException(422,'Queue snapshot time must not be in the future')
        cutoff=cutoff or instant
        query=select(Incident).where(Incident.workspace_id==identity.workspace_id,Incident.created_at<=cutoff)
        if q.strip():
            literal=q.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            pattern='%'+literal+'%'
            query=query.where(or_(Incident.title.ilike(pattern,escape='\\'),Incident.id.ilike(pattern,escape='\\')))
        if status:query=query.where(Incident.status==status)
        if severity:query=query.where(Incident.severity==severity)
        if start:query=query.where(Incident.created_at>=start)
        if end:query=query.where(Incident.created_at<=end)
        if rule_key:
            query=query.where(select(Alert.id).where(Alert.workspace_id==identity.workspace_id,
                Alert.incident_id==Incident.id,Alert.rule_key==rule_key).exists())
        total=session.scalar(select(func.count()).select_from(query.subquery()))
        order=(Incident.created_at.asc(),Incident.id.asc()) if sort=='oldest' else (
            (Incident.risk_score.desc(),Incident.created_at.desc(),Incident.id.asc()) if sort=='risk'
            else (Incident.created_at.desc(),Incident.id.asc()))
        rows=session.scalars(query.order_by(*order).limit(limit).offset(offset))
        return {'items':[serialize(row) for row in rows],'total':total,'offset':offset,'limit':limit,
            'has_more':offset+limit<total,'as_of':timestamp(cutoff)}
