import json
from dataclasses import replace
from datetime import datetime,timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func,select

from app.ai_grounding import answer_schema,validate_answer,AnswerValidationError
from app.ai_history import similar_incidents
from app.auth import verified_user
from app.models import Alert,Audit,Incident,Membership
from test_ai_analysis import setup
from test_ai_grounding import answer
from test_pipeline import environment


ANCHOR=datetime(2026,6,1,12)


def seed(app,path,owner,outsider):
    with app.state.sessions.begin() as db:
        current=db.get(Incident,path.split('/')[3]);current.created_at=ANCHOR
        workspace=db.get(Membership,owner).workspace_id
        other_workspace=db.get(Membership,outsider).workspace_id
        def case(name,days,rules=('brute_force_v1',),scope=workspace):
            item=Incident(workspace_id=scope,title=name,created_at=ANCHOR-timedelta(days=days),status='closed')
            db.add(item);db.flush()
            for rule in rules:
                db.add(Alert(workspace_id=scope,incident_id=item.id,rule_key=rule,dedup_key=uuid4().hex,
                             explanation='Synthetic history fixture only'))
            return item.id
        ids={
            'recent':case('PRIVATE-PAST-ACCOUNT 192.0.2.99 <script>unsafe</script>',1),
            'second':case('Second earlier case',2),
            'third':case('Third earlier case',3),
            'fourth':case('Fourth earlier case',4),
            'future':case('Future case',-1),
            'expired':case('Expired case',181),
            'unrelated':case('Different detection',.5,('tcp_port_scan_v1',)),
            'outsider':case('OTHER-WORKSPACE-SECRET',.25,scope=other_workspace),
        }
    return workspace,other_workspace,ids


def test_history_is_workspace_scoped_bounded_and_read_only(environment,monkeypatch):
    app,c,owner,outsider,_,path,calls=setup(environment,monkeypatch)
    workspace,_,ids=seed(app,path,owner,outsider)
    with app.state.sessions() as db:before=db.scalar(select(func.count()).select_from(Audit))
    status=c.get(path).json()
    assert [item['id'] for item in status['similar_incidents']]==[ids['recent'],ids['second'],ids['third']]
    assert status['history_retrieval']=={'method':'shared-rule-v1','lookback_days':180,'display_limit':3,'ai_limit':2}
    assert status['quota']['daily_used']==0 and not calls
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(Audit))==before
        assert similar_incidents(db,'wrong-workspace',path.split('/')[3])==[]
        assert similar_incidents(db,workspace,path.split('/')[3],limit=999)==status['similar_incidents']
    app.dependency_overrides[verified_user]=lambda:outsider
    assert c.get(path).status_code==404


def test_cross_workspace_alert_links_cannot_create_a_match(environment,monkeypatch):
    app,c,owner,outsider,_,path,_=setup(environment,monkeypatch)
    workspace,other,ids=seed(app,path,owner,outsider)
    with app.state.sessions.begin() as db:
        # Even inconsistent historical rows cannot bypass both join scopes.
        for incident_id,alert_workspace in ((ids['outsider'],workspace),(ids['unrelated'],other)):
            db.add(Alert(workspace_id=alert_workspace,incident_id=incident_id,rule_key='brute_force_v1',
                         dedup_key=uuid4().hex,explanation='Synthetic inconsistent row'))
    matched={item['id'] for item in c.get(path).json()['similar_incidents']}
    assert ids['outsider'] not in matched and ids['unrelated'] not in matched


def test_shared_rule_count_ranks_before_recency_and_window_has_exact_bounds(environment,monkeypatch):
    app,c,owner,outsider,_,path,_=setup(environment,monkeypatch)
    workspace,_,ids=seed(app,path,owner,outsider)
    with app.state.sessions.begin() as db:
        for incident_id in (path.split('/')[3],ids['third']):
            db.add(Alert(workspace_id=workspace,incident_id=incident_id,rule_key='tcp_port_scan_v1',
                         dedup_key=uuid4().hex,explanation='Synthetic additional rule'))
    assert c.get(path).json()['similar_incidents'][0]['id']==ids['third']
    with app.state.sessions.begin() as db:
        # Use a separate rule to isolate boundary assertions.
        current=db.get(Incident,path.split('/')[3]);current.created_at=ANCHOR-timedelta(days=170)
        recent=db.get(Incident,ids['recent']);recent.created_at=current.created_at-timedelta(days=180)
    result=c.get(path).json()['similar_incidents']
    assert ids['recent'] in {item['id'] for item in result}
    with app.state.sessions.begin() as db:
        db.get(Incident,ids['recent']).created_at-=timedelta(microseconds=1)
    assert ids['recent'] not in {item['id'] for item in c.get(path).json()['similar_incidents']}


def test_provider_gets_only_two_allowlisted_metadata_records_and_distinct_citation_namespace(environment,monkeypatch):
    app,c,owner,outsider,_,path,calls=setup(environment,monkeypatch)
    _,_,ids=seed(app,path,owner,outsider)
    payload={'request_id':str(uuid4()),'question':'Are there similar earlier incidents?'}
    response=c.post(path,json=payload)
    assert response.status_code==200
    context=calls[0]
    cases=context['historical_cases']
    assert [item['id'] for item in cases]==[ids['recent'],ids['second']]
    assert set(cases[0])=={'id','created_at','status','severity','risk_score','shared_rules'}
    for private in ('PRIVATE-PAST-ACCOUNT','192.0.2.99','OTHER-WORKSPACE-SECRET','<script>'):
        assert private not in json.dumps(context)
    schema=answer_schema(context)
    assert 'historical_observations' in schema['required']
    assert schema['$defs']['HistoricalObservation']['properties']['case_ids']['items']['enum']==sorted(item['id'] for item in cases)
    valid=answer(context)
    valid['historical_observations']=[{'text':'Earlier case metadata shares the detection rule; outcomes remain unverified.', 'case_ids':[ids['recent']]}]
    assert validate_answer(valid,context)
    for invalid_id in (ids['third'],ids['outsider'],str(uuid4())):
        invalid={**valid,'historical_observations':[{'text':'Untrusted claim','case_ids':[invalid_id]}]}
        with pytest.raises(AnswerValidationError) as failure:validate_answer(invalid,context)
        assert failure.value.code=='invalid_case_citation'
    invalid=answer(context);invalid['observations'][0]['event_ids']=[ids['recent']]
    with pytest.raises(AnswerValidationError):validate_answer(invalid,context)


def test_history_changes_mark_saved_answer_old_without_a_new_model_call(environment,monkeypatch):
    app,c,owner,outsider,_,path,calls=setup(environment,monkeypatch)
    _,_,ids=seed(app,path,owner,outsider)
    request_id=str(uuid4())
    saved=c.post(path,json={'request_id':request_id,'question':'Are there earlier incidents?'}).json()['analysis']
    assert saved['historical_cases'][0]['status']=='closed'
    assert c.get(path).json()['questions'][0]['outdated'] is False
    with app.state.sessions.begin() as db:db.get(Incident,ids['recent']).status='false_positive'
    state=c.get(path,params={'request_id':request_id}).json()
    assert state['questions'][0]['outdated'] and state['request']['analysis']['outdated']
    assert state['questions'][0]['historical_cases']==saved['historical_cases']
    assert state['similar_incidents'][0]['status']=='false_positive'
    assert state['quota']['daily_used']==1 and len(calls)==1
    assert c.post(path,json={'request_id':request_id,'question':'Are there earlier incidents?'}).status_code==409


def test_case_list_remains_available_with_ai_disabled_and_handles_no_matches(environment,monkeypatch):
    app,c,owner,outsider,_,path,calls=setup(environment,monkeypatch)
    assert c.get(path).json()['similar_incidents']==[]
    seed(app,path,owner,outsider)
    app.state.settings=replace(app.state.settings,ai_enabled=False,openai_api_key='')
    state=c.get(path).json()
    assert not state['enabled'] and len(state['similar_incidents'])==3 and not calls


def test_report_retains_cited_historical_metadata_and_escapes_comparison(environment,monkeypatch):
    app,c,owner,outsider,_,path,_=setup(environment,monkeypatch)
    _,_,ids=seed(app,path,owner,outsider)
    def provider(config,context):
        result=answer(context)
        result['historical_observations']=[{'text':'Earlier pattern <script>unsafe</script>', 'case_ids':[ids['recent']]}]
        return {'answer':result,'model':config.ai_model,'usage':{}}
    monkeypatch.setattr('app.ai_analysis.call_openai',provider)
    assert c.post(path,json={'request_id':str(uuid4())}).status_code==200
    report_path=path.removesuffix('/ai-analysis')+'/report'
    data=c.get(report_path,params={'format':'json'}).json()['saved_ai_analysis']
    assert data['outdated'] is False and data['historical_cases'][0]['id']==ids['recent']
    html=c.get(report_path).text
    assert 'Earlier case metadata supplied to AI' in html
    assert '&lt;script&gt;unsafe&lt;/script&gt;' in html and '<script>' not in html
    assert 'PRIVATE-PAST-ACCOUNT' not in html and 'OTHER-WORKSPACE-SECRET' not in html
