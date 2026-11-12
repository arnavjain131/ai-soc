"""Explicit local setup and owner-only membership provisioning."""
import argparse
from uuid import UUID

from sqlalchemy import select

from .config import Settings
from .database import database
from .models import Base, Membership, Workspace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('init-local', help='Create development SQLite tables only')
    grant = sub.add_parser('grant-member', help='Owner-only provisioning after creating a Supabase Auth user')
    grant.add_argument('--user-id', required=True, type=lambda x: str(UUID(x)))
    grant.add_argument('--role', choices=['admin', 'analyst'], default='admin')
    grant.add_argument('--workspace-id', type=lambda x: str(UUID(x)))
    grant.add_argument('--workspace-name', default='Private SOC')
    args = parser.parse_args()
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
            if session.get(Membership, args.user_id):
                parser.error('User already has a membership; edit roles through a reviewed administrative operation')
            if args.workspace_id:
                workspace = session.get(Workspace, args.workspace_id)
                if not workspace:
                    parser.error('Workspace does not exist')
            else:
                workspace = Workspace(name=args.workspace_name)
                session.add(workspace)
                session.flush()
            session.add(Membership(user_id=args.user_id, workspace_id=workspace.id, role=args.role))
            print(f'Granted {args.role} membership in workspace {workspace.id}')
    engine.dispose()


if __name__ == '__main__':
    main()
