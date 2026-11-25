from datetime import datetime,timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func,select

from app.auth import verified_user
from app.models import Alert,Audit,Incident,Membership
from test_pipeline import environment


@pytest.fixture
def queue(environment):
    app,client,owner,outsider,analyst=environment
    ids=[]
    with app.state.sessions.begin() as db:
        workspace=db.get(Membership,owner).workspace_id
        other=db.get(Membership,outsider).workspace_id
        for i in range(132):
            row=Incident(workspace_id=workspace,title=f'Fixture incident {i:03}',
                status=['open','investigating','closed','false_positive'][i%4],
                severity=['high','medium','low','critical'][i%4],risk_score=i%101,
                created_at=datetime(2026,1,1)+timedelta(minutes=i//2))
            db.add(row);db.flush();ids.append(row.id)
            db.add(Alert(workspace_id=workspace,incident_id=row.id,rule_key='tcp_port_scan_v1' if i%2==0 else 'brute_force_v1',
                dedup_key=str(uuid4()),explanation='Synthetic test rule'))
        db.add(Incident(workspace_id=other,title='Fixture incident secret',created_at=datetime(2026,1,1)))
        db.add(Alert(workspace_id=workspace,incident_id=ids[0],rule_key='tcp_port_scan_v1',dedup_key=str(uuid4()),explanation='Second alert same incident'))
    app.dependency_overrides[verified_user]=lambda:owner
    return app,client,owner,outsider,analyst,ids


def test_queue_pages_beyond_legacy_100_without_duplicates_and_does_not_write(queue):
    app,c,owner,outsider,analyst,ids=queue
    path='/api/incidents/search'
    page=c.get(path,params={'limit':25}).json()
    assert page['total']==132 and page['has_more'] and len(page['items'])==25
    found=[]
    for offset in range(0,132,25):
        response=c.get(path,params={'limit':25,'offset':offset,'as_of':page['as_of']})
        assert response.status_code==200
        found.extend(row['id'] for row in response.json()['items'])
    assert len(found)==len(set(found))==132 and set(found)==set(ids)
    assert c.get(path,params={'q':ids[0]}).json()['items'][0]['id']==ids[0]
    assert isinstance(c.get('/api/incidents').json(),list)  # Legacy shape remains compatible.
    with app.state.sessions() as db:assert db.scalar(select(func.count()).select_from(Audit))==0


def test_combined_filters_search_all_records_and_alerts_do_not_duplicate_incidents(queue):
    _,c,_,_,_,ids=queue
    page=c.get('/api/incidents/search',params={'status':'open','severity':'high','rule_key':'tcp_port_scan_v1','sort':'oldest'}).json()
    assert page['total']==33 and len({r['id'] for r in page['items']})==25
    assert c.get('/api/incidents/search',params={'q':'  FIXTURE INCIDENT 001  '}).json()['items'][0]['id']==ids[1]
    assert c.get('/api/incidents/search',params={'status':'open','severity':'critical'}).json()['total']==0


def test_literal_wildcards_backslashes_and_sql_like_text_are_not_patterns(queue):
    app,c,_,_,_,ids=queue
    with app.state.sessions.begin() as db:db.get(Incident,ids[0]).title=r'100%_path\sensor'
    for q in ['%','_',chr(92),'100%_path']:
        result=c.get('/api/incidents/search',params={'q':q}).json()
        assert result['total']==1 and result['items'][0]['id']==ids[0]
    assert c.get('/api/incidents/search',params={'q':"' OR 1=1 --"}).json()['total']==0


def test_queue_ordering_and_inclusive_timezone_filters(queue):
    _,c,_,_,_,ids=queue
    params={'start_time':'2026-01-01T05:30:00+05:30','end_time':'2026-01-01T00:00:00Z','sort':'oldest'}
    rows=c.get('/api/incidents/search',params=params).json()['items']
    assert [r['id'] for r in rows]==sorted(ids[:2])
    risk=c.get('/api/incidents/search',params={'sort':'risk','limit':100}).json()['items']
    assert [r['risk_score'] for r in risk]==sorted([r['risk_score'] for r in risk],reverse=True)


def test_new_arrivals_do_not_shift_existing_snapshot_pages(queue):
    app,c,owner,_,_,ids=queue
    page=c.get('/api/incidents/search',params={'limit':25}).json()
    with app.state.sessions.begin() as db:
        db.add(Incident(workspace_id=db.get(Membership,owner).workspace_id,title='New arrival',
            created_at=datetime.fromisoformat(page['as_of'].rstrip('Z'))+timedelta(microseconds=1)))
    same=c.get('/api/incidents/search',params={'limit':25,'as_of':page['as_of']}).json()
    assert same['items']==page['items'] and same['total']==132
    fresh=c.get('/api/incidents/search').json()
    assert fresh['total']==133 and fresh['items'][0]['title']=='New arrival'


@pytest.mark.parametrize('params',[{'status':'bad'},{'severity':'extreme'},{'rule_key':'injected'},
    {'sort':'title;drop'},{'limit':101},{'offset':-1},{'q':'x'*201},
    {'start_time':'2026-01-01T00:00:00'},
    {'start_time':'2026-01-02T00:00:00Z','end_time':'2026-01-01T00:00:00Z'},
    {'as_of':'2099-01-01T00:00:00Z'}])
def test_invalid_queue_filters_fail_safely(queue,params):
    assert queue[1].get('/api/incidents/search',params=params).status_code==422


def test_queue_scope_and_access_control(queue):
    app,c,owner,outsider,analyst,ids=queue
    app.dependency_overrides[verified_user]=lambda:outsider
    assert c.get('/api/incidents/search',params={'q':ids[0]}).json()['total']==0
    assert c.get('/api/incidents/search').json()['total']==1
    app.dependency_overrides[verified_user]=lambda:analyst
    assert c.get('/api/incidents/search').json()['total']==132
    with app.state.sessions.begin() as db:db.delete(db.get(Membership,analyst))
    assert c.get('/api/incidents/search').status_code==403
    app.dependency_overrides.clear()
    assert c.get('/api/incidents/search').status_code==401
