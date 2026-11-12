from dataclasses import dataclass

import httpx
from fastapi import HTTPException, Request


@dataclass
class Identity:
    user_id: str
    workspace_id: str
    role: str


def verified_user(request: Request) -> str:
    """Validate with the project's Auth server, including expiry/revocation checks."""
    config = request.app.state.settings
    authorization = request.headers.get('Authorization', '')
    if not authorization.startswith('Bearer ') or not authorization[7:]:
        raise HTTPException(401, 'Sign in to access the analyst workspace')
    if not config.supabase_url or not config.supabase_key:
        raise HTTPException(503, 'Private authentication is not configured')
    try:
        response = httpx.get(
            config.supabase_url + '/auth/v1/user',
            headers={'Authorization': authorization, 'apikey': config.supabase_key},
            timeout=8,
        )
        if response.status_code in (401, 403):
            raise HTTPException(401, 'Your session is invalid or expired')
        response.raise_for_status()
        user_id = response.json()['id']
        from uuid import UUID
        return str(UUID(user_id))
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(503, 'Authentication service is unavailable') from exc
