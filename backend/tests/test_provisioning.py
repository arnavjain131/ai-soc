from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.database import database
from app.manage import grant_membership
from app.models import Audit, Base, Membership, Workspace


def test_cli_default_cannot_connect_or_create_a_workspace_without_explicit_target(monkeypatch, capsys):
    from app import manage
    monkeypatch.setattr('sys.argv',['app.manage','grant-member','--user-id',str(uuid4())])
    monkeypatch.setattr(manage,'database',lambda *_: pytest.fail('Must reject before opening a database'))
    with pytest.raises(SystemExit) as failure:
        manage.main()
    assert failure.value.code == 2
    assert 'requires --workspace-id' in capsys.readouterr().err


@pytest.fixture
def store():
    engine, sessions = database('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    try:
        yield sessions
    finally:
        engine.dispose()


def test_analyst_default_joins_existing_workspace_and_records_owner_operation(store):
    user = str(uuid4())
    with store.begin() as db:
        workspace = Workspace(name='Existing SOC'); db.add(workspace); db.flush()
        workspace_id = workspace.id
        assert grant_membership(db,user,workspace_id=workspace_id) == workspace_id
    with store() as db:
        member = db.get(Membership,user)
        assert member.role == 'analyst' and member.workspace_id == workspace_id
        audit = db.scalar(select(Audit))
        assert audit.action == 'membership.granted' and audit.actor == 'owner-cli'
        assert audit.target_id == user and audit.details == {'role':'analyst','provisioning':'owner-cli'}
        assert db.scalar(select(func.count()).select_from(Workspace)) == 1


def test_no_implicit_workspace_or_membership_is_created_for_an_analyst(store):
    with store.begin() as db:
        with pytest.raises(ValueError,match='requires --workspace-id'):
            grant_membership(db,str(uuid4()))
    with store() as db:
        for model in (Membership,Workspace,Audit):
            assert db.scalar(select(func.count()).select_from(model)) == 0


def test_duplicate_grant_never_promotes_or_moves_a_member(store):
    user = str(uuid4())
    with store.begin() as db:
        original, other = Workspace(name='Original'), Workspace(name='Other')
        db.add_all([original,other]);db.flush()
        original_id,other_id=original.id,other.id
        grant_membership(db,user,workspace_id=original_id)
    with pytest.raises(ValueError,match='already has'):
        with store.begin() as db:
            grant_membership(db,user,role='admin',workspace_id=other_id)
    with store() as db:
        assert db.get(Membership,user).role == 'analyst'
        assert db.get(Membership,user).workspace_id == original_id
        assert db.scalar(select(func.count()).select_from(Audit)) == 1


def test_invalid_workspace_does_not_create_membership(store):
    with pytest.raises(ValueError,match='does not exist'):
        with store.begin() as db:
            grant_membership(db,str(uuid4()),workspace_id=str(uuid4()))
    with store() as db:
        assert db.scalar(select(func.count()).select_from(Membership)) == 0


def test_explicit_first_admin_provisioning_still_works(store):
    user=str(uuid4())
    with store.begin() as db:
        workspace_id=grant_membership(db,user,role='admin')
    with store() as db:
        assert db.get(Membership,user).role == 'admin'
        assert db.get(Workspace,workspace_id).name == 'Private SOC'
