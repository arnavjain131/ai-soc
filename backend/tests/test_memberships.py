from uuid import uuid4

import pytest
from sqlalchemy import func, select

from app.auth import verified_user
from app.memberships import revoke_membership
from app.models import Audit, Membership, Source, Workspace
from test_pipeline import environment


def test_lists_only_current_workspace_and_requires_administrator(environment):
    app, client, owner, outsider, analyst = environment
    assert client.get('/api/members').status_code == 401
    app.dependency_overrides[verified_user] = lambda: analyst
    assert client.get('/api/members').status_code == 403
    assert client.get('/api/members/audit').status_code == 403
    assert client.delete('/api/members/' + owner).status_code == 403
    app.dependency_overrides[verified_user] = lambda: owner
    result = client.get('/api/members').json()
    assert {row['user_id'] for row in result['items']} == {owner, analyst}
    assert result['admin_count'] == 1 and result['total'] == 2
    assert next(row for row in result['items'] if row['is_self'])['user_id'] == owner
    assert outsider not in str(result)


def test_revocation_denies_subsequent_private_requests_and_preserves_sources(environment):
    app, client, owner, _, analyst = environment
    app.dependency_overrides[verified_user] = lambda: owner
    with app.state.sessions() as db:
        sources = [(source.id,source.token_hash,source.enabled) for source in db.scalars(select(Source))]
    assert client.delete('/api/members/' + analyst).json() == {'revoked':True,'user_id':analyst}
    assert client.delete('/api/members/' + analyst).status_code == 404
    with app.state.sessions() as db:
        assert db.get(Membership,analyst) is None
        assert [(source.id,source.token_hash,source.enabled) for source in db.scalars(select(Source))] == sources
    audit, = client.get('/api/members/audit').json()['items']
    assert audit['action'] == 'membership.revoked' and audit['actor'] == owner
    assert audit['user_id'] == analyst and audit['role'] == 'analyst'
    app.dependency_overrides[verified_user] = lambda: analyst
    assert client.get('/api/me').status_code == 403
    assert client.get('/api/incidents').status_code == 403


def test_last_admin_and_other_workspace_revocations_do_not_write_audit(environment):
    app, client, owner, outsider, _ = environment
    app.dependency_overrides[verified_user] = lambda: owner
    assert client.delete('/api/members/' + owner).status_code == 409
    assert client.delete('/api/members/' + outsider).status_code == 404
    assert client.delete('/api/members/' + str(uuid4())).status_code == 404
    assert client.get('/api/members/audit').json()['items'] == []
    with app.state.sessions() as db:
        assert db.get(Membership,owner).role == 'admin'


def test_self_revocation_is_refused_even_with_another_admin(environment):
    app, client, owner, _, analyst = environment
    with app.state.sessions.begin() as db:
        db.get(Membership,analyst).role = 'admin'
    app.dependency_overrides[verified_user] = lambda: owner
    result = client.delete('/api/members/' + owner)
    assert result.status_code == 409 and 'own' in result.json()['detail']
    assert client.delete('/api/members/' + analyst).status_code == 200
    assert client.get('/api/members').json()['admin_count'] == 1


def test_owner_cli_cannot_remove_last_admin(environment):
    app, _, owner, _, _ = environment
    with pytest.raises(ValueError,match='last workspace administrator'):
        with app.state.sessions.begin() as db:
            workspace_id = db.get(Membership,owner).workspace_id
            revoke_membership(db,owner,workspace_id)


def test_mutation_rechecks_stale_administrator_identity(environment):
    app, _, owner, _, analyst = environment
    with app.state.sessions.begin() as db:
        workspace_id = db.get(Membership,owner).workspace_id
        db.get(Membership,owner).role = 'analyst'
    with pytest.raises(PermissionError):
        with app.state.sessions.begin() as db:
            revoke_membership(db,analyst,workspace_id,owner)
    with app.state.sessions() as db:
        assert db.get(Membership,analyst) is not None


def test_history_filters_workspace_actions_and_private_metadata(environment):
    app, client, owner, outsider, analyst = environment
    with app.state.sessions.begin() as db:
        own = db.get(Membership,owner).workspace_id
        other = db.get(Membership,outsider).workspace_id
        db.add_all([Audit(workspace_id=own,actor='owner-cli',action='membership.granted',target_id=analyst,
                          details={'role':'analyst','private':'must-not-return'}),
                    Audit(workspace_id=other,actor=outsider,action='membership.granted',target_id=outsider,details={}),
                    Audit(workspace_id=own,actor=owner,action='incident.note_added',target_id=str(uuid4()),details={'body':'private-note'})])
    app.dependency_overrides[verified_user] = lambda: owner
    result = client.get('/api/members/audit').json()
    assert result['total'] == 1 and len(result['items']) == 1
    assert 'must-not-return' not in str(result) and 'private-note' not in str(result)
    assert 'details' not in result['items'][0]


def test_pagination_and_delete_cors_are_bounded(environment):
    app, client, owner, _, _ = environment
    app.dependency_overrides[verified_user] = lambda: owner
    first = client.get('/api/members?limit=1').json()
    second = client.get('/api/members?limit=1&offset=1').json()
    assert first['has_more'] and not second['has_more']
    assert first['items'][0]['user_id'] != second['items'][0]['user_id']
    assert client.get('/api/members?limit=101').status_code == 422
    assert client.get('/api/members/audit?offset=-1').status_code == 422
    assert client.delete('/api/members/not-a-uuid').status_code == 422
    response = client.options('/api/members/' + owner,headers={'Origin':'http://localhost:5173',
        'Access-Control-Request-Method':'DELETE','Access-Control-Request-Headers':'authorization'})
    assert response.status_code == 200 and 'DELETE' in response.headers['access-control-allow-methods']


def test_cli_revoke_requires_exact_confirmation_before_database_access(monkeypatch):
    from app import manage
    monkeypatch.setattr('sys.argv',['app.manage','revoke-member','--user-id',str(uuid4()),
        '--workspace-id',str(uuid4()),'--confirm-user-id',str(uuid4())])
    monkeypatch.setattr(manage,'database',lambda *_: pytest.fail('Must reject before connecting'))
    with pytest.raises(SystemExit) as failure:
        manage.main()
    assert failure.value.code == 2
