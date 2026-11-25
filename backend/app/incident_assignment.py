"""Audited incident ownership using the existing append-only audit store."""
from datetime import timedelta
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from .memberships import lock_workspace
from .models import Audit, Incident, Membership, now

ASSIGNED='incident.assignment_changed'
CHECKED='incident.assignment_checked'


class AssignmentUpdate(BaseModel):
    model_config=ConfigDict(extra='forbid')
    assignee_id: UUID | None
    expected_revision: UUID | None
    request_id: UUID


def latest_assignee(workspace_id):
    return select(Audit.details['after'].as_string()).where(Audit.workspace_id==workspace_id,
        Audit.target_id==Incident.id,Audit.action==ASSIGNED).order_by(Audit.created_at.desc(),Audit.id.desc()).limit(1).correlate(Incident).scalar_subquery()


def assignment_summaries(session,workspace_id,incident_ids,viewer_id):
    if not incident_ids:return {}
    ranked=select(Audit.id.label('id'),func.row_number().over(partition_by=Audit.target_id,
        order_by=(Audit.created_at.desc(),Audit.id.desc())).label('rank')).where(
        Audit.workspace_id==workspace_id,Audit.target_id.in_(incident_ids),Audit.action==ASSIGNED).subquery()
    rows=list(session.scalars(select(Audit).where(Audit.id.in_(select(ranked.c.id).where(ranked.c.rank==1)))))
    users={row.details['after'] for row in rows if row.details.get('after')}
    active=set(session.scalars(select(Membership.user_id).where(Membership.workspace_id==workspace_id,
        Membership.user_id.in_(users),Membership.role.in_(('admin','analyst'))))) if users else set()
    result={incident_id:{'assignee_id':None,'revision':None,'active':False,'is_self':False} for incident_id in incident_ids}
    for row in rows:
        user=row.details.get('after')
        result[row.target_id]={'assignee_id':user,'revision':row.id,'active':user in active,'is_self':user==viewer_id}
    return result


def set_assignment(session,identity,incident_id,payload):
    # Membership writers use the same workspace lock. Recheck after acquiring it.
    lock_workspace(session,identity.workspace_id)
    actor=session.scalar(select(Membership).where(Membership.user_id==identity.user_id,
        Membership.workspace_id==identity.workspace_id,Membership.role.in_(('admin','analyst'))).execution_options(populate_existing=True))
    if not actor:raise HTTPException(403,'Workspace membership is required')
    incident=session.scalar(select(Incident).where(Incident.id==incident_id,Incident.workspace_id==identity.workspace_id).with_for_update())
    if not incident:raise HTTPException(404,'Incident not found')
    desired=str(payload.assignee_id) if payload.assignee_id else None
    expected=str(payload.expected_revision) if payload.expected_revision else None
    previous=session.scalar(select(Audit).where(Audit.workspace_id==identity.workspace_id,Audit.target_id==incident_id,
        Audit.actor==identity.user_id,Audit.action.in_((ASSIGNED,CHECKED)),Audit.details['request_id'].as_string()==str(payload.request_id)))
    if previous:
        if previous.details.get('after')!=desired or previous.details.get('expected_revision')!=expected:
            raise HTTPException(409,'This request ID was already used for a different assignment')
        current=assignment_summaries(session,identity.workspace_id,[incident_id],identity.user_id)[incident_id]
        session.commit()
        return {'assignment':current,'replayed':True,'changed':previous.action==ASSIGNED}
    current=assignment_summaries(session,identity.workspace_id,[incident_id],identity.user_id)[incident_id]
    if current['revision']!=expected:raise HTTPException(409,'Assignment changed. Refresh ownership before saving again.')
    if desired:
        candidate=session.scalar(select(Membership).where(Membership.workspace_id==identity.workspace_id,
            Membership.user_id==desired,Membership.role.in_(('admin','analyst'))))
        if not candidate:raise HTTPException(422,'Assignee must be an approved member of this workspace')
    changed=current['assignee_id']!=desired
    instant=now()
    if current['revision']:
        last=session.get(Audit,current['revision'])
        instant=max(instant,last.created_at+timedelta(microseconds=1))
    row=Audit(workspace_id=identity.workspace_id,actor=identity.user_id,action=ASSIGNED if changed else CHECKED,
        target_id=incident_id,created_at=instant,details={'before':current['assignee_id'],'after':desired,
            'expected_revision':expected,'request_id':str(payload.request_id)})
    session.add(row)
    if changed:incident.updated_at=instant
    session.flush()
    result=assignment_summaries(session,identity.workspace_id,[incident_id],identity.user_id)[incident_id]
    session.commit()
    return {'assignment':result,'replayed':False,'changed':changed}


def install_assignment_routes(api,member,session_dependency,authorized_incident):
    @api.get('/api/assignment-candidates')
    def candidates(identity=Depends(member),session=Depends(session_dependency),
        limit:int=Query(50,ge=1,le=100),offset:int=Query(0,ge=0,le=1000000)):
        query=select(Membership).where(Membership.workspace_id==identity.workspace_id,Membership.role.in_(('admin','analyst')))
        total=session.scalar(select(func.count()).select_from(query.subquery()))
        rows=session.scalars(query.order_by(Membership.user_id).limit(limit).offset(offset))
        return {'items':[{'user_id':r.user_id,'role':r.role,'is_self':r.user_id==identity.user_id} for r in rows],
            'total':total,'offset':offset,'limit':limit,'has_more':offset+limit<total}

    @api.get('/api/incidents/{incident_id}/assignment')
    def ownership(incident_id:str,identity=Depends(member),session=Depends(session_dependency)):
        authorized_incident(session,identity,incident_id)
        return assignment_summaries(session,identity.workspace_id,[incident_id],identity.user_id)[incident_id]

    @api.put('/api/incidents/{incident_id}/assignment')
    def assign(incident_id:str,payload:AssignmentUpdate,identity=Depends(member),session=Depends(session_dependency)):
        authorized_incident(session,identity,incident_id)
        return set_assignment(session,identity,incident_id,payload)
