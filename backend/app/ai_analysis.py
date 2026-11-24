"""Authorized on-demand AI analysis with durable reservations and history."""
import hashlib
import json
import math
from datetime import timedelta
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from .ai_grounding import GroundedAnswer, build_context
from .ai_provider import AIProviderError, call_openai, PROMPT_VERSION, REQUEST_INSTRUCTIONS
from .memberships import lock_workspace
from .models import Audit, Membership, now


REQUESTED='incident.ai_requested'
COMPLETED='incident.ai_completed'
FAILED='incident.ai_failed'
CACHE_HIT='incident.ai_cache_hit'


class AnalysisRequest(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id: UUID


def context_hash(context, model):
    value=json.dumps({'context':context,'model':model,'instructions':REQUEST_INSTRUCTIONS,
        'prompt_version':PROMPT_VERSION,'schema':GroundedAnswer.model_json_schema()},sort_keys=True,separators=(',',':'))
    return hashlib.sha256(value.encode()).hexdigest()


def actor_still_authorized(session, identity):
    membership=session.scalar(select(Membership).where(Membership.user_id==identity.user_id,
        Membership.workspace_id==identity.workspace_id).execution_options(populate_existing=True))
    if not membership or membership.role not in ('admin','analyst'):
        raise HTTPException(403,'Workspace membership is required')


def scoped(identity, incident_id):
    return select(Audit).where(Audit.workspace_id==identity.workspace_id,Audit.target_id==incident_id)


def quota(session, identity, settings):
    instant=now()
    day=instant.replace(hour=0,minute=0,second=0,microsecond=0)
    month=day.replace(day=1)
    base=select(func.count()).select_from(Audit).where(Audit.workspace_id==identity.workspace_id,Audit.action==REQUESTED)
    daily=session.scalar(base.where(Audit.created_at>=day))
    monthly=session.scalar(base.where(Audit.created_at>=month))
    return {'daily_used':daily,'daily_limit':settings.ai_daily_limit,
            'monthly_used':monthly,'monthly_limit':settings.ai_monthly_limit}


def present(row, digest):
    data=row.details
    context=data['context']
    return {'id':row.id,'generated_at':row.created_at.isoformat()+'Z','actor_id':row.actor,
        'provider':'OpenAI','model':data['model'],'requested_model':data['requested_model'],
        'context_hash':data['context_hash'],'outdated':data['context_hash']!=digest,
        'answer':data['answer'],'references':context['references'],
        'context_limitations':context['limitations'],
        'omitted_linked_events':context['omitted_linked_events'],
        'omitted_related_events':context['omitted_related_events'],
        'knowledge_version':context['knowledge_version'],'usage':data.get('usage',{})}


def request_status(session, identity, incident_id, request_id, digest):
    """Read a specific actor's receipt without reserving quota or invoking AI."""
    query=scoped(identity,incident_id)
    receipt=session.scalar(query.where(Audit.action.in_((REQUESTED,CACHE_HIT)),
        Audit.actor==identity.user_id,Audit.details['request_id'].as_string()==str(request_id)))
    if not receipt:
        return {'state':'not_found'}
    if receipt.action==CACHE_HIT:
        complete=session.scalar(query.where(Audit.action==COMPLETED,Audit.id==receipt.details['result_id']))
    else:
        complete=session.scalar(query.where(Audit.action==COMPLETED,
            Audit.details['request_record_id'].as_string()==receipt.id))
    if complete:
        return {'state':'completed','analysis':present(complete,digest)}
    failed=session.scalar(query.where(Audit.action==FAILED,
        Audit.details['request_record_id'].as_string()==receipt.id))
    return {'state':'failed' if failed else 'pending'}


def reserve(session, identity, incident_id, payload, context, settings):
    lock_workspace(session,identity.workspace_id)
    actor_still_authorized(session,identity)
    digest=context_hash(context,settings.ai_model)
    query=scoped(identity,incident_id)
    previous=session.scalar(query.where(Audit.action.in_((REQUESTED,CACHE_HIT)),
        Audit.details['request_id'].as_string()==str(payload.request_id)))
    if previous:
        if previous.actor!=identity.user_id or previous.details['context_hash']!=digest:
            raise HTTPException(409,'This request belongs to another actor or evidence version. Refresh and start a new analysis.')
        if previous.action==CACHE_HIT:
            complete=session.scalar(query.where(Audit.id==previous.details['result_id'],Audit.action==COMPLETED))
        else:
            complete=session.scalar(query.where(Audit.action==COMPLETED,
                Audit.details['request_record_id'].as_string()==previous.id))
        if complete:
            session.commit()
            return None,present(complete,digest)
        failed=session.scalar(query.where(Audit.action==FAILED,
            Audit.details['request_record_id'].as_string()==previous.id))
        if failed:
            raise HTTPException(502,'The previous attempt failed. A new attempt needs a new request and counts toward the AI quota.')
        raise HTTPException(409,'This analysis request is pending or incomplete. Wait and retry the same request; do not automatically create another.')
    cached=session.scalar(query.where(Audit.action==COMPLETED,
        Audit.details['context_hash'].as_string()==digest).order_by(Audit.created_at.desc(),Audit.id.desc()).limit(1))
    if cached:
        session.add(Audit(workspace_id=identity.workspace_id,actor=identity.user_id,action=CACHE_HIT,target_id=incident_id,
            details={'request_id':str(payload.request_id),'context_hash':digest,'result_id':cached.id}))
        session.commit()
        return None,present(cached,digest)
    limits=quota(session,identity,settings)
    if limits['daily_used']>=limits['daily_limit'] or limits['monthly_used']>=limits['monthly_limit']:
        instant=now()
        day=instant.replace(hour=0,minute=0,second=0,microsecond=0)
        reset=day+timedelta(days=1)
        if limits['monthly_used']>=limits['monthly_limit']:
            reset=(day.replace(day=1)+timedelta(days=32)).replace(day=1)
        retry=str(max(1,math.ceil((reset-instant).total_seconds())))
        raise HTTPException(429,'Workspace AI generation quota reached. Saved analyses remain available.',headers={'Retry-After':retry})
    recent=list(session.scalars(select(Audit).where(Audit.workspace_id==identity.workspace_id,
        Audit.action==REQUESTED,Audit.created_at>=now()-timedelta(seconds=90))))
    if recent:
        finished=set(session.scalars(select(Audit.details['request_record_id'].as_string()).where(
            Audit.workspace_id==identity.workspace_id,Audit.action.in_((COMPLETED,FAILED)),
            Audit.details['request_record_id'].as_string().in_([row.id for row in recent]))))
        if any(row.id not in finished for row in recent):
            raise HTTPException(409,'Another workspace AI analysis is pending. Wait before starting another.')
    reservation=Audit(workspace_id=identity.workspace_id,actor=identity.user_id,action=REQUESTED,target_id=incident_id,
        details={'request_id':str(payload.request_id),'context_hash':digest,'requested_model':settings.ai_model,'prompt_version':PROMPT_VERSION})
    session.add(reservation)
    session.commit()  # Persist the debit and release DB connection/row lock before inference.
    return reservation,None


def install_ai_routes(api, member, session_dependency, authorized_incident, load_detail):
    @api.get('/api/incidents/{incident_id}/ai-analysis')
    def status(incident_id: str, request: Request, request_id: UUID | None=None,
               identity=Depends(member), session=Depends(session_dependency)):
        authorized_incident(session,identity,incident_id)
        settings=request.app.state.settings
        try:
            context=build_context(load_detail(incident_id,identity,session))
            digest=context_hash(context,settings.ai_model)
        except ValueError:
            digest=None
        latest=session.scalar(scoped(identity,incident_id).where(Audit.action==COMPLETED)
            .order_by(Audit.created_at.desc(),Audit.id.desc()).limit(1))
        return {'enabled':settings.ai_enabled and bool(settings.openai_api_key),
                'provider':'OpenAI','model':settings.ai_model,'has_evidence':digest is not None,
                'quota':quota(session,identity,settings),'latest':present(latest,digest) if latest else None,
                'request':request_status(session,identity,incident_id,request_id,digest) if request_id else None}

    @api.post('/api/incidents/{incident_id}/ai-analysis')
    def analyze(incident_id: str, payload: AnalysisRequest, request: Request,
                identity=Depends(member), session=Depends(session_dependency)):
        authorized_incident(session,identity,incident_id)
        settings=request.app.state.settings
        if not settings.ai_enabled or not settings.openai_api_key:
            raise HTTPException(503,'AI is not enabled. The project owner must configure the server-side provider first.')
        try:
            context=build_context(load_detail(incident_id,identity,session))
        except ValueError:
            raise HTTPException(409,'Selected incident evidence is unavailable or cannot be safely prepared for AI.') from None
        reservation,cached=reserve(session,identity,incident_id,payload,context,settings)
        if cached:
            return {'cached':True,'analysis':cached}
        try:
            result=call_openai(settings,context)
        except AIProviderError as failure:
            session.add(Audit(workspace_id=identity.workspace_id,actor=identity.user_id,action=FAILED,target_id=incident_id,
                details={'request_record_id':reservation.id,'error_code':failure.code}))
            session.commit()
            raise HTTPException(502,'AI analysis could not be completed ('+failure.code+'). No result was accepted; the reserved attempt still counts toward quota.') from None
        completed=Audit(workspace_id=identity.workspace_id,actor=identity.user_id,action=COMPLETED,target_id=incident_id,
            details={**result,'requested_model':settings.ai_model,'context_hash':reservation.details['context_hash'],
                     'request_record_id':reservation.id,'prompt_version':PROMPT_VERSION,'context':context})
        session.add(completed)
        session.commit()
        actor_still_authorized(session,identity)
        return {'cached':False,'analysis':present(completed,reservation.details['context_hash'])}
