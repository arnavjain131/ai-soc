"""Workspace-scoped access management; no Auth users or telemetry are deleted."""
from uuid import UUID

from fastapi import Depends, HTTPException, Query
from sqlalchemy import func, select

from .models import Audit, Membership, Workspace


MEMBER_ACTIONS = ('membership.granted', 'membership.revoked')


def lock_workspace(session, workspace_id):
    workspace = session.scalar(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
    if not workspace:
        raise LookupError('Workspace does not exist')
    return workspace


def revoke_membership(session, user_id, workspace_id, actor='owner-cli'):
    # All supported membership writers serialize on the same workspace row.
    lock_workspace(session, workspace_id)
    if actor != 'owner-cli':
        current = session.scalar(select(Membership).where(Membership.user_id == actor,
            Membership.workspace_id == workspace_id).execution_options(populate_existing=True))
        if not current or current.role != 'admin':
            raise PermissionError('Administrator access is required')
    target = session.scalar(select(Membership).where(Membership.user_id == user_id,
        Membership.workspace_id == workspace_id).execution_options(populate_existing=True))
    if not target:
        raise LookupError('Member not found')
    if target.role == 'admin':
        admins = session.scalar(select(func.count()).select_from(Membership).where(
            Membership.workspace_id == workspace_id, Membership.role == 'admin'))
        if admins <= 1:
            raise ValueError('The last workspace administrator cannot be removed')
    if actor == user_id:
        raise ValueError('You cannot revoke your own workspace access')
    role = target.role
    session.delete(target)
    session.add(Audit(workspace_id=workspace_id, actor=actor, action='membership.revoked',
                      target_id=user_id, details={'role': role, 'provisioning': 'owner-cli' if actor == 'owner-cli' else 'admin-api'}))


def install_membership_routes(api, member, session_dependency):
    def admin(identity=Depends(member)):
        if identity.role != 'admin':
            raise HTTPException(403, 'Administrator access is required')
        return identity

    @api.get('/api/members')
    def members(identity=Depends(admin), session=Depends(session_dependency),
                limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=1000000)):
        query = select(Membership).where(Membership.workspace_id == identity.workspace_id)
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        admins = session.scalar(select(func.count()).select_from(Membership).where(
            Membership.workspace_id == identity.workspace_id, Membership.role == 'admin'))
        rows = session.scalars(query.order_by(Membership.user_id).limit(limit).offset(offset))
        return {'items': [{'user_id': row.user_id, 'role': row.role,
                          'is_self': row.user_id == identity.user_id} for row in rows],
                'total': total, 'admin_count': admins, 'limit': limit, 'offset': offset,
                'has_more': offset + limit < total}

    @api.get('/api/members/audit')
    def history(identity=Depends(admin), session=Depends(session_dependency),
                limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=1000000)):
        query = select(Audit).where(Audit.workspace_id == identity.workspace_id,
                                    Audit.action.in_(MEMBER_ACTIONS))
        total = session.scalar(select(func.count()).select_from(query.subquery()))
        rows = session.scalars(query.order_by(Audit.created_at.desc(), Audit.id.desc()).limit(limit).offset(offset))
        return {'items': [{'id': row.id, 'actor': row.actor, 'action': row.action,
                          'user_id': row.target_id, 'created_at': row.created_at.isoformat() + 'Z',
                          'role': row.details.get('role') if row.details.get('role') in ('admin', 'analyst') else None}
                         for row in rows], 'total': total, 'limit': limit, 'offset': offset,
                'has_more': offset + limit < total}

    @api.delete('/api/members/{user_id}')
    def revoke(user_id: UUID, identity=Depends(admin), session=Depends(session_dependency)):
        try:
            revoke_membership(session, str(user_id), identity.workspace_id, identity.user_id)
            session.commit()
        except PermissionError as error:
            raise HTTPException(403, str(error)) from None
        except LookupError as error:
            raise HTTPException(404, str(error)) from None
        except ValueError as error:
            raise HTTPException(409, str(error)) from None
        return {'revoked': True, 'user_id': str(user_id)}
