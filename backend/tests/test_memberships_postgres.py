"""Opt-in concurrency proof against an explicitly supplied disposable local DB."""
import os
import re
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from app.database import database
from app.memberships import revoke_membership
from app.models import Audit, Base, Membership, Workspace


def test_concurrent_owner_revocations_keep_one_administrator():
    target = os.getenv('SOC_TEST_POSTGRES_URL')
    if not target:
        pytest.skip('Requires an isolated disposable local PostgreSQL database')
    parsed = make_url(target)
    assert parsed.host == '127.0.0.1' and parsed.port == 55432
    assert re.fullmatch(r'ai_soc_membership_test_[a-f0-9]{8}',parsed.database or '')
    engine,sessions = database(target)
    try:
        Base.metadata.create_all(engine)
        ids=[str(uuid4()),str(uuid4())]
        with sessions.begin() as db:
            workspace=Workspace(name='Synthetic concurrency check');db.add(workspace);db.flush()
            workspace_id=workspace.id
            for user_id in ids:
                db.add(Membership(user_id=user_id,workspace_id=workspace_id,role='admin'))
        barrier=Barrier(2)
        def remove(user_id):
            try:
                with sessions.begin() as db:
                    barrier.wait(timeout=10)
                    revoke_membership(db,user_id,workspace_id)
                return 'revoked'
            except ValueError as error:
                assert 'last workspace administrator' in str(error)
                return 'protected'
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(remove,ids)) == ['protected','revoked']
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(Membership).where(
                Membership.workspace_id==workspace_id,Membership.role=='admin')) == 1
            assert db.scalar(select(func.count()).select_from(Audit).where(
                Audit.workspace_id==workspace_id,Audit.action=='membership.revoked')) == 1
    finally:
        engine.dispose()


@pytest.mark.parametrize('same_request',[False,True])
def test_concurrent_ai_reservations_cannot_double_debit_or_bypass_quota(same_request):
    from fastapi import HTTPException
    from app.auth import Identity
    from app.ai_analysis import AnalysisRequest,REQUESTED,reserve
    from app.config import Settings
    target=os.getenv('SOC_TEST_POSTGRES_URL')
    if not target:pytest.skip('Requires an isolated disposable local PostgreSQL database')
    parsed=make_url(target)
    assert parsed.host=='127.0.0.1' and parsed.port==55432
    assert re.fullmatch(r'ai_soc_membership_test_[a-f0-9]{8}',parsed.database or '')
    engine,sessions=database(target)
    try:
        Base.metadata.create_all(engine)
        user_id=str(uuid4())
        with sessions.begin() as db:
            workspace=Workspace(name='Synthetic AI quota concurrency');db.add(workspace);db.flush()
            workspace_id=workspace.id
            db.add(Membership(user_id=user_id,workspace_id=workspace_id,role='admin'))
        identity=Identity(user_id,workspace_id,'admin')
        settings=Settings(database_url='sqlite:///:memory:',ai_enabled=True,openai_api_key='synthetic',ai_daily_limit=1)
        request_ids=[uuid4(),uuid4()]
        if same_request:request_ids[1]=request_ids[0]
        incident_id=str(uuid4())
        barrier=Barrier(2)
        def attempt(request_id):
            with sessions() as db:
                barrier.wait(timeout=10)
                try:
                    reservation,cached=reserve(db,identity,incident_id,AnalysisRequest(request_id=request_id),{},settings)
                    assert reservation is not None and cached is None
                    return 'reserved'
                except HTTPException as error:
                    assert error.status_code==(409 if same_request else 429)
                    db.rollback()
                    return 'blocked'
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert sorted(pool.map(attempt,request_ids))==['blocked','reserved']
        with sessions() as db:
            assert db.scalar(select(func.count()).select_from(Audit).where(
                Audit.workspace_id==workspace_id,Audit.action==REQUESTED))==1
    finally:
        engine.dispose()
