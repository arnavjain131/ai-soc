"""Opt-in real row-lock proofs on an explicitly disposable loopback database."""
import os,re
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import func,select
from sqlalchemy.engine import make_url

from app.auth import Identity
from app.database import database
from app.incident_assignment import AssignmentUpdate,ASSIGNED,assignment_summaries,set_assignment,latest_assignee
from app.memberships import revoke_membership
from app.models import Audit,Base,Incident,Membership,Workspace


@pytest.fixture
def postgres():
    target=os.getenv('SOC_TEST_POSTGRES_URL')
    if not target:pytest.skip('Requires a disposable local PostgreSQL database')
    parsed=make_url(target)
    assert parsed.host=='127.0.0.1' and parsed.port==55432
    assert re.fullmatch(r'ai_soc_membership_test_[a-f0-9]{8}',parsed.database or '')
    engine,sessions=database(target)
    Base.metadata.create_all(engine)
    try:yield sessions
    finally:engine.dispose()


def setup(sessions):
    owner,analyst=str(uuid4()),str(uuid4())
    with sessions.begin() as db:
        workspace=Workspace(name='Synthetic ownership concurrency');db.add(workspace);db.flush()
        db.add_all([Membership(user_id=owner,workspace_id=workspace.id,role='admin'),Membership(user_id=analyst,workspace_id=workspace.id,role='analyst')])
        incident=Incident(workspace_id=workspace.id,title='Synthetic incident');db.add(incident);db.flush()
    return Identity(owner,workspace.id,'admin'),analyst,incident.id


@pytest.mark.parametrize('same_request',[False,True])
def test_concurrent_assignment_retries_and_competing_edits(postgres,same_request):
    identity,analyst,incident_id=setup(postgres)
    request_id=uuid4();barrier=Barrier(2)
    def attempt(index):
        with postgres() as db:
            barrier.wait(timeout=10)
            try:
                result=set_assignment(db,identity,incident_id,AssignmentUpdate(assignee_id=analyst if same_request or index==0 else identity.user_id,
                    expected_revision=None,request_id=request_id if same_request else uuid4()))
                return 'replayed' if result['replayed'] else 'saved'
            except HTTPException as error:
                assert error.status_code==409;db.rollback();return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:outcomes=list(pool.map(attempt,[0,1]))
    assert sorted(outcomes)==(['replayed','saved'] if same_request else ['conflict','saved'])
    with postgres() as db:
        assert db.scalar(select(func.count()).select_from(Audit).where(Audit.target_id==incident_id,Audit.action==ASSIGNED))==1
        assert db.scalar(select(Incident.id).where(Incident.id==incident_id,latest_assignee(identity.workspace_id).is_not(None)))==incident_id


def test_assignment_and_member_revocation_share_serialization_lock(postgres):
    identity,analyst,incident_id=setup(postgres);barrier=Barrier(2)
    def assign():
        with postgres() as db:
            barrier.wait(timeout=10)
            try:set_assignment(db,identity,incident_id,AssignmentUpdate(assignee_id=analyst,expected_revision=None,request_id=uuid4()));return 'saved'
            except HTTPException as error:assert error.status_code==422;db.rollback();return 'ineligible'
    def revoke():
        with postgres.begin() as db:
            barrier.wait(timeout=10);revoke_membership(db,analyst,identity.workspace_id)
    with ThreadPoolExecutor(max_workers=2) as pool:
        a,b=pool.submit(assign),pool.submit(revoke);assert a.result() in ('saved','ineligible');b.result()
    with postgres() as db:
        assert db.get(Membership,analyst) is None
        state=assignment_summaries(db,identity.workspace_id,[incident_id],identity.user_id)[incident_id]
        assert state['active'] is False
        assert state['assignee_id'] in (analyst,None)
        active_members=select(Membership.user_id).where(Membership.workspace_id==identity.workspace_id)
        inactive=db.scalar(select(Incident.id).where(Incident.id==incident_id,
            latest_assignee(identity.workspace_id).not_in(active_members)))
        assert inactive==(incident_id if state['assignee_id'] else None)
