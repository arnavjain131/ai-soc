from uuid import uuid4

import pytest

from app.auth import verified_user
from app.models import Audit, Membership
from test_pipeline import environment, ingest, batch


def incident_setup(environment):
    app, client, owner, outsider, analyst = environment
    ingest(client, batch())
    app.dependency_overrides[verified_user] = lambda: owner
    incident, = client.get('/api/incidents').json()
    return app, client, owner, outsider, analyst, incident


def payload(body='Reviewed the linked authentication evidence.'):
    return {'body': body, 'request_id': str(uuid4())}


def test_notes_and_history_require_membership_and_incident_workspace(environment):
    app, client, owner, outsider, analyst, incident = incident_setup(environment)
    path = '/api/incidents/' + incident['id']
    app.dependency_overrides.clear()
    for suffix in ('/notes', '/audit'):
        assert client.get(path + suffix).status_code == 401
    assert client.post(path + '/notes', json=payload()).status_code == 401
    app.dependency_overrides[verified_user] = lambda: outsider
    assert client.get(path + '/notes').status_code == 404
    assert client.get(path + '/audit').status_code == 404
    assert client.post(path + '/notes', json=payload()).status_code == 404
    app.dependency_overrides[verified_user] = lambda: 'non-member'
    assert client.get(path + '/notes').status_code == 403
    app.dependency_overrides[verified_user] = lambda: analyst
    saved = client.post(path + '/notes', json=payload()).json()
    assert saved['actor_id'] == analyst
    app.dependency_overrides[verified_user] = lambda: owner
    assert client.get(path + '/notes').json()['items'][0]['id'] == saved['id']


def test_note_is_append_only_audited_and_does_not_change_incident_evidence(environment):
    app, client, owner, _, _, incident = incident_setup(environment)
    path = '/api/incidents/' + incident['id']
    before = client.get(path).json()
    response = client.post(path + '/notes', json=payload('  <script>untrusted text</script>  '))
    assert response.status_code == 201
    note = response.json()
    assert note['body'] == '<script>untrusted text</script>'
    assert note['actor_id'] == owner and note['created_at'].endswith('Z')
    assert 'request_id' not in note and 'workspace_id' not in note
    assert client.get(path).json() == before
    audit, = client.get(path + '/audit').json()['items']
    assert audit['id'] == note['id'] and audit['action'] == 'incident.note_added'
    assert audit['details'] == {}
    for method in (client.patch, client.delete):
        assert method(path + '/notes/' + note['id']).status_code in (404, 405)
    assert client.get(path + '/notes').json()['items'] == [note]
    assert client.patch(path, json={'status': 'closed'}).status_code == 200
    assert client.post(path + '/notes', json=payload('Follow-up after closure.')).status_code == 201
    assert client.get(path).json()['status'] == 'closed'


def test_retry_deduplicates_and_reused_key_with_changed_body_conflicts(environment):
    app, client, owner, _, analyst, incident = incident_setup(environment)
    path = '/api/incidents/' + incident['id'] + '/notes'
    request = payload()
    first = client.post(path, json=request)
    retry = client.post(path, json=request)
    assert first.status_code == 201 and retry.status_code == 200
    assert retry.json() == first.json()
    assert client.post(path, json=request | {'body': 'A different note.'}).status_code == 409
    assert client.get(path).json()['total'] == 1
    app.dependency_overrides[verified_user] = lambda: analyst
    assert client.post(path, json=request).status_code == 201
    assert client.get(path).json()['total'] == 2


def test_history_only_includes_this_incident_and_allowed_actions(environment):
    app, client, owner, outsider, _, incident = incident_setup(environment)
    path = '/api/incidents/' + incident['id']
    with app.state.sessions.begin() as db:
        other_workspace = db.get(Membership, outsider).workspace_id
        for workspace, target, action in (
            (other_workspace, incident['id'], 'incident.note_added'),
            (db.get(Membership, owner).workspace_id, str(uuid4()), 'incident.note_added'),
            (db.get(Membership, owner).workspace_id, incident['id'], 'source.created'),
        ):
            db.add(Audit(workspace_id=workspace, actor=outsider, action=action, target_id=target,
                         details={'body': 'must stay hidden', 'token': 'synthetic-private-value'}))
    assert client.get(path + '/notes').json()['total'] == 0
    assert client.patch(path, json={'status': 'investigating'}).status_code == 200
    response = client.get(path + '/audit')
    audit, = response.json()['items']
    assert audit['action'] == 'incident.status_changed'
    assert audit['details'] == {'before': 'open', 'after': 'investigating'}
    assert audit['actor_id'] == owner
    assert 'synthetic-private-value' not in response.text
    assert 'must stay hidden' not in response.text


def test_notes_and_history_pagination(environment):
    app, client, owner, _, _, incident = incident_setup(environment)
    path = '/api/incidents/' + incident['id']
    for i in range(3):
        assert client.post(path + '/notes', json=payload(f'Note {i}')).status_code == 201
    for suffix in ('/notes', '/audit'):
        first = client.get(path + suffix, params={'limit': 2}).json()
        second = client.get(path + suffix, params={'limit': 2, 'offset': 2}).json()
        assert first['total'] == second['total'] == 3
        assert first['has_more'] and not second['has_more']
        assert len({row['id'] for row in first['items'] + second['items']}) == 3


@pytest.mark.parametrize('note_payload', [
    {'body': '', 'request_id': str(uuid4())}, {'body': ' \n ', 'request_id': str(uuid4())},
    {'body': 'x' * 2001, 'request_id': str(uuid4())}, {'body': 'note', 'request_id': 'invalid'},
    {'body': 'note', 'request_id': str(uuid4()), 'actor_id': 'spoofed'}, {'body': 'note'},
])
def test_invalid_notes_cannot_write_audit_rows(environment, note_payload):
    app, client, owner, _, _, incident = incident_setup(environment)
    path = '/api/incidents/' + incident['id'] + '/notes'
    assert client.post(path, json=note_payload).status_code == 422
    assert client.get(path).json()['total'] == 0
