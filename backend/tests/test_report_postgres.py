"""Opt-in report snapshot proof on the disposable loopback PostgreSQL lab."""
import os
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import text,create_engine
from sqlalchemy.orm import sessionmaker

from app import incident_report
from app.auth import verified_user
from app.config import Settings
from app.incident_journal import NOTE_ACTION
from app.main import create_app
from app.models import Audit,Incident,Membership,Workspace
from test_assignment_postgres import postgres


def test_report_is_read_only_repeatable_snapshot_while_writer_commits(postgres,monkeypatch):
    user=str(uuid4())
    with postgres.begin() as db:
        workspace=Workspace(name='Synthetic report snapshot');db.add(workspace);db.flush()
        db.add(Membership(user_id=user,workspace_id=workspace.id,role='admin'))
        incident=Incident(workspace_id=workspace.id,title='Before snapshot');db.add(incident);db.flush()
    app=create_app(Settings(database_url=os.environ['SOC_TEST_POSTGRES_URL'],supabase_url='https://example.supabase.co',
        supabase_key='synthetic',ai_enabled=False,openai_api_key=''))
    app.dependency_overrides[verified_user]=lambda:user
    original=incident_report.bounded
    changed=[]
    def concurrent_writer(session,query,maximum,label):
        assert session.execute(text('SHOW transaction_isolation')).scalar_one()=='repeatable read'
        assert session.execute(text('SHOW transaction_read_only')).scalar_one()=='on'
        if not changed:
            with postgres.begin() as writer:
                writer.get(Incident,incident.id).title='After concurrent commit'
                writer.add(Audit(workspace_id=workspace.id,actor=user,action=NOTE_ACTION,target_id=incident.id,
                    details={'body':'Note committed after report snapshot','request_id':str(uuid4())}))
            changed.append(True)
        return original(session,query,maximum,label)
    monkeypatch.setattr(incident_report,'bounded',concurrent_writer)
    path='/api/incidents/'+incident.id+'/report?format=json'
    with TestClient(app) as client:
        first=client.get(path)
        assert first.status_code==200
        assert first.json()['incident']['title']=='Before snapshot'
        assert first.json()['analyst_notes']==[]
        second=client.get(path)
        assert second.status_code==200 and second.json()['incident']['title']=='After concurrent commit'
        assert len(second.json()['analyst_notes'])==1


def test_report_releases_auth_read_before_snapshot_with_one_connection(postgres):
    user=str(uuid4())
    with postgres.begin() as db:
        workspace=Workspace(name='Synthetic constrained pool');db.add(workspace);db.flush()
        db.add(Membership(user_id=user,workspace_id=workspace.id,role='admin'))
        incident=Incident(workspace_id=workspace.id,title='One connection export');db.add(incident);db.flush()
    target=os.environ['SOC_TEST_POSTGRES_URL']
    app=create_app(Settings(database_url=target,supabase_url='https://example.supabase.co',supabase_key='synthetic',ai_enabled=False,openai_api_key=''))
    app.state.engine.dispose()
    small=create_engine(target,pool_size=1,max_overflow=0,pool_timeout=1,hide_parameters=True)
    app.state.engine=small;app.state.sessions=sessionmaker(small,expire_on_commit=False)
    app.dependency_overrides[verified_user]=lambda:user
    try:
        with TestClient(app) as client:
            response=client.get('/api/incidents/'+incident.id+'/report?format=json')
            assert response.status_code==200 and response.json()['incident']['title']=='One connection export'
    finally:small.dispose()
