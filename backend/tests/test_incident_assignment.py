from uuid import uuid4

import pytest
from sqlalchemy import func,select

from app.auth import verified_user
from app.models import Audit,Incident,Membership
from app.incident_assignment import ASSIGNED,CHECKED
from test_pipeline import environment,batch,ingest


@pytest.fixture
def assignment(environment):
    app,c,owner,outsider,analyst=environment
    app.dependency_overrides[verified_user]=lambda:owner
    ingest(c,batch())
    row=c.get('/api/incidents').json()[0]
    return app,c,owner,outsider,analyst,row['id'],'/api/incidents/'+row['id']+'/assignment'


def payload(user,revision=None,request=None):return {'assignee_id':user,'expected_revision':revision,'request_id':request or str(uuid4())}


def test_assign_reassign_unassign_and_minimal_audit_history(assignment):
    app,c,owner,_,analyst,i,path=assignment
    before=c.get('/api/incidents/'+i).json()
    assert c.get(path).json()=={'assignee_id':None,'revision':None,'active':False,'is_self':False}
    first=c.put(path,json=payload(analyst)).json()['assignment']
    assert first['assignee_id']==analyst and first['active'] and not first['is_self']
    second=c.put(path,json=payload(owner,first['revision'])).json()['assignment']
    assert second['is_self']
    final=c.put(path,json=payload(None,second['revision'])).json()['assignment']
    assert final['assignee_id'] is None and final['revision']!=second['revision']
    history=c.get('/api/incidents/'+i+'/audit').json()
    assert history['total']==3 and [r['action'] for r in history['items']]==[ASSIGNED]*3
    assert history['items'][0]['details']=={'before':owner,'after':None}
    assert all(set(r['details'])=={'before','after'} for r in history['items'])
    after=c.get('/api/incidents/'+i).json()
    for field in ['status','risk_score','events','alerts','related_network_events']:assert after[field]==before[field]


def test_same_request_does_not_duplicate_or_reapply_after_another_edit(assignment):
    app,c,owner,_,analyst,i,path=assignment
    original=payload(analyst)
    first=c.put(path,json=original).json()['assignment']
    assert c.put(path,json=original).json()['replayed'] is True
    new=c.put(path,json=payload(owner,first['revision'])).json()['assignment']
    replay=c.put(path,json=original).json()
    assert replay['replayed'] and replay['assignment']==new
    assert c.put(path,json={**original,'assignee_id':owner}).status_code==409
    with app.state.sessions() as db:assert db.scalar(select(func.count()).select_from(Audit).where(Audit.action==ASSIGNED))==2


def test_stale_revision_and_same_owner_noop(assignment):
    app,c,owner,_,analyst,i,path=assignment
    current=c.put(path,json=payload(owner)).json()['assignment']
    assert c.put(path,json=payload(analyst)).status_code==409
    unchanged=payload(owner,current['revision'])
    assert c.put(path,json=unchanged).json()['changed'] is False
    assert c.put(path,json=unchanged).json()['replayed'] is True
    assert c.get(path).json()['revision']==current['revision']
    assert c.get('/api/incidents/'+i+'/audit').json()['total']==1
    with app.state.sessions() as db:assert db.scalar(select(func.count()).select_from(Audit).where(Audit.action==CHECKED))==1


def test_candidates_and_assignment_scope_restrictions(assignment):
    app,c,owner,outsider,analyst,i,path=assignment
    assert c.put(path,json=payload(outsider)).status_code==422
    assert c.put(path,json=payload(str(uuid4()))).status_code==422
    app.dependency_overrides[verified_user]=lambda:analyst
    members=c.get('/api/assignment-candidates',params={'limit':1}).json()
    assert members['total']==2 and members['has_more']
    assert set(members['items'][0])=={'user_id','role','is_self'}
    assert c.put(path,json=payload(analyst)).status_code==200
    app.dependency_overrides[verified_user]=lambda:outsider
    assert c.get(path).status_code==404 and c.put(path,json=payload(outsider)).status_code==404
    assert c.get('/api/assignment-candidates').json()['total']==1
    app.dependency_overrides.clear()
    assert c.get(path).status_code==401 and c.put(path,json=payload(owner)).status_code==401
    assert c.get('/api/assignment-candidates').status_code==401


def test_revoked_owner_stays_in_history_but_is_inactive_and_cannot_be_selected(assignment):
    app,c,owner,_,analyst,i,path=assignment
    first=c.put(path,json=payload(analyst)).json()['assignment']
    with app.state.sessions.begin() as db:db.delete(db.get(Membership,analyst))
    assert c.get(path).json()['assignee_id']==analyst and c.get(path).json()['active'] is False
    assert c.get('/api/assignment-candidates').json()['total']==1
    assert c.get('/api/incidents/search?assignee=inactive').json()['total']==1
    assert c.get('/api/incidents/search?assignee=unassigned').json()['total']==0
    assert c.put(path,json=payload(analyst,first['revision'])).status_code==422
    assert c.put(path,json=payload(None,first['revision'])).status_code==200
    assert c.get('/api/incidents/search?assignee=inactive').json()['total']==0


def test_queue_ownership_filters_and_current_owner_summary(assignment):
    app,c,owner,_,analyst,i,path=assignment
    assert c.get('/api/incidents/search?assignee=unassigned').json()['total']==1
    first=c.put(path,json=payload(owner)).json()['assignment']
    page=c.get('/api/incidents/search?assignee=me').json()
    assert page['total']==1 and page['items'][0]['assignment']==first
    assert c.get('/api/incidents/search',params={'assignee':owner}).json()['total']==1
    assert c.get('/api/incidents/search',params={'assignee':analyst}).json()['total']==0
    assert c.get('/api/incidents/search?assignee=invalid').status_code==422
    app.dependency_overrides[verified_user]=lambda:analyst
    assert c.get('/api/incidents/search?assignee=me').json()['total']==0


@pytest.mark.parametrize('extra',[{'assignee_id':'bad'},{'expected_revision':'bad'},{'request_id':'bad'},
    {'actor':'spoof'},{'workspace_id':'spoof'}])
def test_invalid_assignment_inputs_are_rejected(assignment,extra):
    _,c,owner,_,_,_,path=assignment
    assert c.put(path,json={**payload(owner),**extra}).status_code==422


def test_closed_incident_assignment_does_not_reopen_and_revoked_actor_cannot_write(assignment):
    app,c,owner,_,analyst,i,path=assignment
    c.patch('/api/incidents/'+i,json={'status':'closed'})
    assert c.put(path,json=payload(owner)).status_code==200
    assert c.get('/api/incidents/'+i).json()['status']=='closed'
    with app.state.sessions.begin() as db:db.delete(db.get(Membership,analyst))
    app.dependency_overrides[verified_user]=lambda:analyst
    assert c.put(path,json=payload(owner)).status_code==403


def test_browser_preflight_allows_assignment_put_for_configured_origin(assignment):
    response=assignment[1].options(assignment[-1],headers={'Origin':'http://localhost:5173',
        'Access-Control-Request-Method':'PUT','Access-Control-Request-Headers':'authorization,content-type'})
    assert response.status_code==200 and 'PUT' in response.headers['access-control-allow-methods']
    assert response.headers['access-control-allow-origin']=='http://localhost:5173'
