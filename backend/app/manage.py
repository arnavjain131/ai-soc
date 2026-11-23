"""Explicit local setup and owner-only membership provisioning."""
import argparse
from uuid import UUID

from .config import Settings
from .database import database
from .models import Audit, Base, Membership, Workspace


def grant_membership(session, user_id, role='analyst', workspace_id=None, workspace_name='Private SOC'):
    if role not in ('admin', 'analyst'):
        raise ValueError('Unsupported membership role')
    if role == 'analyst' and not workspace_id:
        raise ValueError('Analyst provisioning requires --workspace-id for an existing workspace')
    if session.get(Membership, user_id):
        raise ValueError('User already has a membership; use a reviewed administrative operation for changes')
    if workspace_id:
        workspace = session.get(Workspace, workspace_id)
        if not workspace:
            raise ValueError('Workspace does not exist')
    else:
        workspace = Workspace(name=workspace_name)
        session.add(workspace)
        session.flush()
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
    args = parser.parse_args()
    if args.command == 'grant-member' and args.role == 'analyst' and not args.workspace_id:
        parser.error('Analyst provisioning requires --workspace-id for an existing workspace')
    config = Settings()
    config.validate()
    engine, sessions = database(config.database_url)
    if args.command == 'init-local':
        if not config.database_url.startswith('sqlite') or config.environment == 'production':
            parser.error('Use the versioned SQL migration for PostgreSQL')
        Base.metadata.create_all(engine)
        print('Local development schema initialized. No user or source credentials were created.')
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
