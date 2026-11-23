"""Explicit local setup and owner-only membership provisioning."""
import argparse
from uuid import UUID

from .config import Settings
from .database import database
from .models import Audit, Base, Membership, Workspace
from .memberships import lock_workspace, revoke_membership


def grant_membership(session, user_id, role='analyst', workspace_id=None, workspace_name='Private SOC'):
    if role not in ('admin', 'analyst'):
        raise ValueError('Unsupported membership role')
    if role == 'analyst' and not workspace_id:
        raise ValueError('Analyst provisioning requires --workspace-id for an existing workspace')
    if session.get(Membership, user_id):
        raise ValueError('User already has a membership; use a reviewed administrative operation for changes')
    if workspace_id:
        try:
            workspace = lock_workspace(session, workspace_id)
        except LookupError:
            raise ValueError('Workspace does not exist') from None
    else:
        workspace = Workspace(name=workspace_name)
        session.add(workspace)
        session.flush()
    if session.get(Membership, user_id):
        raise ValueError('User already has a membership; use a reviewed administrative operation for changes')
    session.add(Membership(user_id=user_id, workspace_id=workspace.id, role=role))
    session.add(Audit(workspace_id=workspace.id, actor='owner-cli', action='membership.granted',
                      target_id=user_id, details={'role': role, 'provisioning': 'owner-cli'}))
    return workspace.id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init-local', help='Create development SQLite tables only')
    grant = sub.add_parser('grant-member', help='Owner-only provisioning after creating a Supabase Auth user')
    grant.add_argument('--user-id', required=True, type=lambda x: str(UUID(x)))
    grant.add_argument('--role', choices=['admin', 'analyst'], default='analyst')
    grant.add_argument('--workspace-id', type=lambda x: str(UUID(x)))
    grant.add_argument('--workspace-name', default='Private SOC')
    revoke = sub.add_parser('revoke-member', help='Revoke only workspace membership, preserving Auth user and telemetry')
    revoke.add_argument('--user-id', required=True, type=lambda x: str(UUID(x)))
    revoke.add_argument('--workspace-id', required=True, type=lambda x: str(UUID(x)))
    revoke.add_argument('--confirm-user-id', required=True, type=lambda x: str(UUID(x)))
    args = parser.parse_args()
    if args.command == 'grant-member' and args.role == 'analyst' and not args.workspace_id:
        parser.error('Analyst provisioning requires --workspace-id for an existing workspace')
    if args.command == 'revoke-member' and args.user_id != args.confirm_user_id:
        parser.error('Confirmation must exactly match the user ID to revoke')
    config = Settings()
    config.validate()
    engine, sessions = database(config.database_url)
    if args.command == 'init-local':
        if not config.database_url.startswith('sqlite') or config.environment == 'production':
            parser.error('Use the versioned SQL migration for PostgreSQL')
        Base.metadata.create_all(engine)
        print('Local development schema initialized. No user or source credentials were created.')
    elif args.command == 'revoke-member':
        with sessions.begin() as session:
            try:
                revoke_membership(session, args.user_id, args.workspace_id)
            except (LookupError, ValueError) as error:
                parser.error(str(error))
        print(f'Revoked workspace membership for user {args.user_id}. Auth account and telemetry retained.')
    else:
        with sessions.begin() as session:
            try:
                workspace_id = grant_membership(session, args.user_id, args.role, args.workspace_id, args.workspace_name)
            except ValueError as error:
                parser.error(str(error))
        print(f'Granted {args.role} membership in workspace {workspace_id}')
    engine.dispose()


if __name__ == '__main__':
    main()
