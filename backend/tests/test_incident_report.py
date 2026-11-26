from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import func,select

from app.auth import verified_user
from app.models import Audit,Event,Incident,Membership,Source
from app import incident_report
from test_pipeline import environment,batch,ingest
from test_ai_analysis import setup as ai_setup


@pytest.fixture
def report(environment):
    app,c,owner,outsider,analyst=environment
    app.dependency_overrides[verified_user]=lambda:owner
    ingest(c,batch())
    incident=c.get('/api/incidents').json()[0]
    flow={'external_event_id':'report-flow','event_type':'NETWORK_FLOW','event_time':'2026-01-01T00:00:30Z',
        'protocol':'TCP','source_ip':'192.0.2.4','source_port':54321,'destination_ip':'198.51.100.8',
        'destination_port':22,'raw_data':{'provenance':'suricata_eve'}}
    assert ingest(c,{'events':[flow]}).status_code==200
    path='/api/incidents/'+incident['id']
    assert c.post(path+'/notes',json={'body':'Reviewed evidence. <script>alert("note")</script>','request_id':str(uuid4())}).status_code==201
    assert c.put(path+'/assignment',json={'assignee_id':analyst,'expected_revision':None,'request_id':str(uuid4())}).status_code==200
    c.patch(path,json={'status':'investigating'})
    with app.state.sessions.begin() as db:
        db.get(Incident,incident['id']).title='<img src="https://untrusted.test/leak">Synthetic report'
        source=db.scalar(select(Source));source.name='Sensor <script>bad</script>'
        source.token_hash='MUST_NOT_EXPORT_SOURCE_HASH'
        event=db.scalar(select(Event).where(Event.event_type=='LOGIN_FAILED'))
        event.raw_data={'password':'MUST_NOT_EXPORT_PASSWORD','token':'MUST_NOT_EXPORT_TOKEN','authentication_method':'password'}
        action=db.scalar(select(Audit).where(Audit.action=='incident.status_changed'))
        action.details={**action.details,'secret':'MUST_NOT_EXPORT_AUDIT_EXTRA'}
    return app,c,owner,outsider,analyst,path


def test_json_report_contains_complete_scoped_snapshot_without_credentials_or_writes(report,monkeypatch):
    app,c,owner,_,analyst,path=report
    monkeypatch.setattr('app.ai_analysis.call_openai',lambda *_:pytest.fail('Export must never invoke AI'))
    with app.state.sessions() as db:before=db.scalar(select(func.count()).select_from(Audit))
    response=c.get(path+'/report',params={'format':'json'})
    assert response.status_code==200
    data=response.json()
    assert data['report_version']==1 and data['prepared_for_user_id']==owner
    assert data['counts']=={'linked_evidence':5,'related_network_context':1,'analyst_notes':1,'history':3,'alerts':1}
    assert data['assignment']['assignee_id']==analyst and data['assignment']['active']
    assert data['incident']['status']=='investigating' and data['incident']['risk_score']==50
    assert data['saved_ai_analysis'] is None
    assert {e['event_type'] for e in data['linked_evidence']}=={'LOGIN_FAILED'}
    assert data['related_network_context'][0]['source_port']==54321
    assert data['analyst_notes'][0]['body'].startswith('Reviewed evidence.')
    for secret in ['MUST_NOT_EXPORT_SOURCE_HASH','MUST_NOT_EXPORT_PASSWORD','MUST_NOT_EXPORT_TOKEN','MUST_NOT_EXPORT_AUDIT_EXTRA','raw_data']:
        assert secret not in response.text
    assert response.headers['cache-control']=='no-store, private'
    assert response.headers['content-disposition'].endswith('.json"')
    assert response.headers['x-content-type-options']=='nosniff'
    with app.state.sessions() as db:assert db.scalar(select(func.count()).select_from(Audit))==before


def test_printable_report_escapes_all_untrusted_text_and_uses_no_external_assets(report):
    response=report[1].get(report[-1]+'/report')
    assert response.status_code==200
    html=response.text
    assert '<script' not in html and '<img' not in html and '<iframe' not in html
    assert '&lt;script&gt;' in html and '&lt;img' in html
    assert 'default-src &#x27;none&#x27;' in html or "default-src 'none'" in html
    for title in ['Linked evidence (5)','Related network context (1)','Analyst notes','Investigation history','Saved AI analysis']:
        assert title in html
    assert '@media print' in html and 'Print → Save as PDF' in html
    assert response.headers['content-disposition'].endswith('.html"')
    assert 'sandbox' in response.headers['content-security-policy']


def test_report_auth_scope_and_revoked_membership(report):
    app,c,_,outsider,analyst,path=report
    app.dependency_overrides[verified_user]=lambda:outsider
    assert c.get(path+'/report').status_code==404
    app.dependency_overrides[verified_user]=lambda:analyst
    assert c.get(path+'/report').status_code==200
    with app.state.sessions.begin() as db:db.delete(db.get(Membership,analyst))
    assert c.get(path+'/report').status_code==403
    app.dependency_overrides.clear()
    assert c.get(path+'/report').status_code==401


def test_bounds_fail_instead_of_silently_omitting_evidence_or_notes(report,monkeypatch):
    _,c,_,_,_,path=report
    monkeypatch.setattr(incident_report,'MAX_EVENTS',4)
    result=c.get(path+'/report')
    assert result.status_code==413 and 'No partial report' in result.json()['detail']
    assert 'content-disposition' not in result.headers
    monkeypatch.setattr(incident_report,'MAX_EVENTS',1000)
    monkeypatch.setattr(incident_report,'MAX_NOTES',0)
    assert c.get(path+'/report').status_code==413


def test_saved_ai_can_be_included_or_excluded_without_new_generation(environment,monkeypatch):
    app,c,_,_,_,path,calls=ai_setup(environment,monkeypatch)
    assert c.post(path,json={'request_id':str(uuid4())}).status_code==200
    app.state.settings=replace(app.state.settings,ai_enabled=False,openai_api_key='')
    report_path=path.removesuffix('/ai-analysis')+'/report'
    result=c.get(report_path,params={'format':'json'}).json()
    assert result['saved_ai_analysis']['answer']['summary']=='Failures were observed.'
    assert result['saved_ai_analysis']['outdated'] is False
    excluded=c.get(report_path,params={'format':'json','include_ai':'false'}).json()
    assert excluded['saved_ai_analysis'] is None and excluded['ai_included'] is False
    with app.state.sessions.begin() as db:db.get(Incident,path.split('/')[3]).risk_score=51
    stale=c.get(report_path,params={'format':'json'}).json()
    assert stale['saved_ai_analysis']['outdated'] is True
    html=c.get(report_path).text
    assert 'Evidence or model configuration has changed' in html
    assert '#event-' in html and len(calls)==1


def test_follow_up_answer_does_not_replace_report_summary(environment,monkeypatch):
    _,c,_,_,_,path,calls=ai_setup(environment,monkeypatch)
    summary=c.post(path,json={'request_id':str(uuid4())}).json()['analysis']
    assert c.post(path,json={'request_id':str(uuid4()),'question':'Did a login succeed?'}).status_code==200
    report_path=path.removesuffix('/ai-analysis')+'/report'
    result=c.get(report_path,params={'format':'json'}).json()['saved_ai_analysis']
    assert result['id']==summary['id'] and result['question'] is None
    assert result['outdated'] is False and len(calls)==2


def test_access_is_rechecked_before_export_delivery(report,monkeypatch):
    app,c,owner,_,_,path=report
    original=incident_report.html_report
    def revoke_after_render(payload):
        content=original(payload)
        with app.state.sessions.begin() as db:db.delete(db.get(Membership,owner))
        return content
    monkeypatch.setattr(incident_report,'html_report',revoke_after_render)
    assert c.get(path+'/report').status_code==403


def test_export_format_and_size_validation(report,monkeypatch):
    c,path=report[1],report[-1]
    assert c.get(path+'/report',params={'format':'csv'}).status_code==422
    assert c.get('/api/incidents/not-a-uuid/report').status_code==404
    monkeypatch.setattr(incident_report,'MAX_JSON_BYTES',10)
    assert c.get(path+'/report').status_code==413
