# backend/auth/dependencies.py
"""
Authentication and role-based access control for the ClinOps Autopilot API.

The frontend logs staff in via supabase-js and sends the resulting access
token as `Authorization: Bearer <token>` on every API call. This module
verifies that token against Supabase Auth, loads the matching `staff`
profile (role + trial assignments), and exposes FastAPI dependencies that
endpoints require.

This is the real enforcement layer. The RLS policies in the SQL migrations
are a backstop for any future direct frontend-to-Supabase access; they do
NOT protect these API endpoints, since the backend connects with the
service-role key and bypasses RLS.
"""

import logging
from typing import List, Optional

from fastapi import Depends, Header, HTTPException, status

from database.client import supabase

logger = logging.getLogger(__name__)


class CurrentUser:
    def __init__(self, id: str, email: str, role: str, full_name: str, trial_ids: List[str]):
        self.id = id
        self.email = email
        self.role = role
        self.full_name = full_name
        # trials this user is scoped to. Empty for admin/coordinator, who
        # see every trial regardless of what's in staff_trials.
        self.trial_ids = trial_ids

    def can_access_trial(self, trial_id: Optional[str]) -> bool:
        if self.role in ("admin", "coordinator"):
            return True
        if not trial_id:
            return False
        return trial_id in self.trial_ids


async def get_current_user(authorization: Optional[str] = Header(None)) -> CurrentUser:
    """
    Verify the bearer token against Supabase Auth, then load the staff
    profile for that user. 401 if the token is missing/invalid, 403 if
    the token is valid but there's no matching active staff profile
    (e.g. a Supabase auth user was created but never given a role).
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing or malformed Authorization header")

    token = authorization.split(" ", 1)[1]

    try:
        auth_response = supabase.auth.get_user(token)
        supabase_user = auth_response.user
    except Exception:
        logger.exception("Token verification failed")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    if not supabase_user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")

    try:
        result = (
            supabase.table("staff")
            .select("*, staff_trials(trial_id)")
            .eq("id", supabase_user.id)
            .eq("active", True)
            .single()
            .execute()
        )
        profile = result.data
    except Exception:
        profile = None

    if not profile:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No active staff profile for this account")

    trial_ids = [t["trial_id"] for t in (profile.get("staff_trials") or [])]

    return CurrentUser(
        id=profile["id"],
        email=profile.get("email", supabase_user.email),
        role=profile["role"],
        full_name=profile.get("full_name", ""),
        trial_ids=trial_ids,
    )


def require_role(*allowed_roles: str):
    """
    FastAPI dependency factory.

    Usage:
        @router.post("/approve/{ae_id}")
        async def approve_ae(
            ae_id: str,
            user: CurrentUser = Depends(require_role("admin", "coordinator", "pi")),
        ):
            ...
    """
    async def _check(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed_roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role '{user.role}' is not permitted to perform this action",
            )
        return user
    return _check