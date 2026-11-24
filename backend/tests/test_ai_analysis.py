from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import func,select

from app.auth import verified_user
from app.ai_analysis import REQUESTED,COMPLETED,FAILED
from app.ai_provider import AIProviderError
from app.models import Audit,Event,Incident,Membership
from test_pipeline import environment,batch,ingest
from test_ai_grounding import answer


def setup(environment,monkeypatch,**settings):
    app,client,owner,outsider,analyst=environment
    app.state.settings=replace(app.state.settings,ai_enabled=True,openai_api_key='synthetic',**settings)
    app.dependency_overrides[verified_user]=lambda:owner
    ingest(client,batch())
    item=client.get('/api/incidents').json()[0]
    calls=[]
    def provider(config,context):
        calls.append(context)
        return {'answer':answer(context),'model':config.ai_model,'usage':{'input_tokens':100,'output_tokens':100}}
    monkeypatch.setattr('app.ai_analysis.call_openai',provider)
    return app,client,owner,outsider,analyst,'/api/incidents/'+item['id']+'/ai-analysis',calls


def test_disabled_ai_does_not_call_provider_or_reserve_a_request(environment,monkeypatch):
    app,client,owner,_,_=environment
    app.dependency_overrides[verified_user]=lambda:owner
    ingest(client,batch())
    item=client.get('/api/incidents').json()[0]
    monkeypatch.setattr('app.ai_analysis.call_openai',lambda *_:pytest.fail('Disabled AI must never call a provider'))
    path='/api/incidents/'+item['id']+'/ai-analysis'
    assert client.get(path).json()['enabled'] is False
    assert client.post(path,json={'request_id':str(uuid4())}).status_code==503
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.action==REQUESTED))==0


def test_generation_persists_cited_analysis_and_retry_and_new_requests_reuse_it(environment,monkeypatch):
    app,client,owner,_,analyst,path,calls=setup(environment,monkeypatch)
    before=client.get(path.removesuffix('/ai-analysis')).json()
    request_id=str(uuid4())
    first=client.post(path,json={'request_id':request_id})
    assert first.status_code==200 and first.json()['cached'] is False
    assert client.post(path,json={'request_id':request_id}).json()['cached'] is True
    assert client.post(path,json={'request_id':str(uuid4())}).json()['cached'] is True
    assert len(calls)==1
    status=client.get(path).json()
    assert status['quota']['daily_used']==1 and status['latest']['outdated'] is False
    assert client.get(path.removesuffix('/ai-analysis')).json()==before
    app.dependency_overrides[verified_user]=lambda:analyst
    assert client.get(path).json()['latest']['id']==first.json()['analysis']['id']
    assert client.post(path,json={'request_id':str(uuid4())}).json()['cached'] is True
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.action==COMPLETED))==1


def test_other_workspace_and_anonymous_requests_never_reach_provider(environment,monkeypatch):
    app,client,_,outsider,_,path,calls=setup(environment,monkeypatch)
    app.dependency_overrides[verified_user]=lambda:outsider
    assert client.get(path).status_code==404
    assert client.post(path,json={'request_id':str(uuid4())}).status_code==404
    app.dependency_overrides.clear()
    assert client.post(path,json={'request_id':str(uuid4())}).status_code==401
    assert not calls


def test_failure_reservation_counts_once_and_explicit_new_attempt_hits_quota(environment,monkeypatch):
    app,client,_,_,_,path,_=setup(environment,monkeypatch,ai_daily_limit=1)
    calls=[]
    def unavailable(*_):calls.append(1);raise AIProviderError('provider_unavailable')
    monkeypatch.setattr('app.ai_analysis.call_openai',unavailable)
    payload={'request_id':str(uuid4())}
    assert client.post(path,json=payload).status_code==502
    assert client.post(path,json=payload).status_code==502
    response=client.post(path,json={'request_id':str(uuid4())})
    assert response.status_code==429 and 'Retry-After' in response.headers
    assert len(calls)==1
    assert client.get(path).json()['quota']['daily_used']==1
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.action==FAILED))==1


def test_new_evidence_marks_saved_output_old_and_old_request_id_cannot_generate_again(environment,monkeypatch):
    app,client,_,_,_,path,calls=setup(environment,monkeypatch)
    payload={'request_id':str(uuid4())}
    assert client.post(path,json=payload).status_code==200
    ingest(client,batch(seconds=(70,),prefix='new-evidence'))
    # Rule deduplication may retain its original five evidence links; force a legitimate stored priority update instead.
    with app.state.sessions.begin() as db:
        db.get(Incident,path.split('/')[3]).risk_score=51
    assert client.get(path).json()['latest']['outdated'] is True
    assert client.post(path,json=payload).status_code==409
    assert client.post(path,json={'request_id':str(uuid4())}).status_code==200
    assert len(calls)==2


def test_actor_revoked_during_inference_cannot_receive_result(environment,monkeypatch):
    app,client,owner,_,_,path,_=setup(environment,monkeypatch)
    def provider(config,context):
        with app.state.sessions.begin() as db:
            db.delete(db.get(Membership,owner))
        return {'answer':answer(context),'model':config.ai_model,'usage':{}}
    monkeypatch.setattr('app.ai_analysis.call_openai',provider)
    assert client.post(path,json={'request_id':str(uuid4())}).status_code==403


def test_request_body_cannot_override_provider_model_or_identity(environment,monkeypatch):
    _,client,_,_,_,path,calls=setup(environment,monkeypatch)
    assert client.post(path,json={'request_id':str(uuid4()),'model':'expensive-model'}).status_code==422
    assert client.post(path,json={'request_id':'invalid'}).status_code==422
    assert not calls


def test_saved_analysis_remains_readable_when_provider_is_disabled(environment,monkeypatch):
    app,client,_,_,_,path,calls=setup(environment,monkeypatch)
    assert client.post(path,json={'request_id':str(uuid4())}).status_code==200
    app.state.settings=replace(app.state.settings,ai_enabled=False)
    status=client.get(path).json()
    assert status['enabled'] is False and status['latest']['answer']['summary']=='Failures were observed.'
    assert client.post(path,json={'request_id':str(uuid4())}).status_code==503
    assert len(calls)==1


def test_read_only_request_recovery_returns_exact_result_and_cache_receipt(environment,monkeypatch):
    app,client,owner,_,analyst,path,calls=setup(environment,monkeypatch)
    first_id=str(uuid4())
    first=client.post(path,json={'request_id':first_id}).json()['analysis']
    # Simulate the client losing that POST response; GET alone recovers it.
    recovered=client.get(path,params={'request_id':first_id}).json()
    assert recovered['request']=={'state':'completed','analysis':first}
    assert recovered['quota']['daily_used']==1
    cache_id=str(uuid4())
    assert client.post(path,json={'request_id':cache_id}).json()['cached'] is True
    assert client.get(path,params={'request_id':cache_id}).json()['request']['analysis']['id']==first['id']
    assert client.get(path,params={'request_id':str(uuid4())}).json()['request']=={'state':'not_found'}
    app.dependency_overrides[verified_user]=lambda:analyst
    other=client.get(path,params={'request_id':first_id}).json()
    assert other['request']=={'state':'not_found'}  # Receipts belong to their requesting actor.
    assert other['latest']['id']==first['id']  # Saved analysis remains workspace-readable.
    assert len(calls)==1


def test_request_status_distinguishes_pending_failed_and_unrelated_saved_answer(environment,monkeypatch):
    app,client,owner,_,_,path,calls=setup(environment,monkeypatch)
    client.post(path,json={'request_id':str(uuid4())})
    request_id=str(uuid4())
    with app.state.sessions.begin() as db:
        existing=db.scalar(select(Audit).where(Audit.action==REQUESTED))
        pending=Audit(workspace_id=existing.workspace_id,actor=owner,action=REQUESTED,target_id=existing.target_id,
            details={**existing.details,'request_id':request_id})
        db.add(pending)
    status=client.get(path,params={'request_id':request_id}).json()
    assert status['latest'] and status['request']=={'state':'pending'}
    with app.state.sessions.begin() as db:
        db.add(Audit(workspace_id=pending.workspace_id,actor=owner,action=FAILED,target_id=pending.target_id,
            details={'request_record_id':pending.id,'error_code':'provider_unavailable'}))
    assert client.get(path,params={'request_id':request_id}).json()['request']=={'state':'failed','error_code':'provider_unavailable'}
    assert len(calls)==1


def test_request_recovery_respects_auth_scope_and_uuid_validation(environment,monkeypatch):
    app,client,_,outsider,_,path,calls=setup(environment,monkeypatch)
    assert client.get(path,params={'request_id':'invalid'}).status_code==422
    app.dependency_overrides[verified_user]=lambda:outsider
    assert client.get(path,params={'request_id':str(uuid4())}).status_code==404
    app.dependency_overrides.clear()
    assert client.get(path,params={'request_id':str(uuid4())}).status_code==401
    assert not calls


def test_failed_status_returns_only_allowlisted_safe_diagnostics(environment,monkeypatch):
    app,client,owner,_,_,path,calls=setup(environment,monkeypatch)
    def invalid(*_):raise AIProviderError('invalid_evidence_citation')
    monkeypatch.setattr('app.ai_analysis.call_openai',invalid)
    request_id=str(uuid4())
    assert client.post(path,json={'request_id':request_id}).status_code==502
    assert client.get(path,params={'request_id':request_id}).json()['request']=={
        'state':'failed','error_code':'invalid_evidence_citation'}
    with app.state.sessions.begin() as db:
        failure=db.scalar(select(Audit).where(Audit.action==FAILED))
        failure.details={**failure.details,'error_code':'private-raw-error'}
    response=client.get(path,params={'request_id':request_id})
    assert response.json()['request']=={'state':'failed','error_code':'provider_unavailable'}
    assert 'private-raw-error' not in response.text
