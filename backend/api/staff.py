# backend/api/staff.py
"""
Staff management: admin-only. Creating a staff member creates the
underlying Supabase Auth user via the admin API (needs the service-role
key, which this backend already uses everywhere else) and the staff
profile row in one step, so nobody has to do this by hand in SQL.
"""

from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from auth.dependencies import require_role, CurrentUser
from database.audit import log_audit
from database.client import supabase

router = APIRouter(prefix="/api/staff", tags=["staff"])


class CreateStaffRequest(BaseModel):
    email: str
    password: str
    full_name: str
    role: str  # admin | coordinator | pi | sponsor | site_staff
    phone: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    trial_ids: List[str] = []


@router.get("/trials")
async def list_trials(user: CurrentUser = Depends(require_role("admin"))):
    """Trials available to assign a staff member to."""
    result = supabase.table("trials").select("id, trial_name, drug_name").execute()
    return {"data": result.data or []}


@router.get("")
async def list_staff(user: CurrentUser = Depends(require_role("admin"))):
    result = (
        supabase.table("staff")
        .select("*, staff_trials(trial_id)")
        .order("created_at", desc=True)
        .execute()
    )
    return {"data": result.data or []}


@router.post("")
async def create_staff(
    payload: CreateStaffRequest,
    user: CurrentUser = Depends(require_role("admin")),
):
    # 1. Create the underlying Supabase Auth user
    try:
        auth_result = supabase.auth.admin.create_user({
            "email": payload.email,
            "password": payload.password,
            "email_confirm": True,
        })
    except Exception as e:
        return {"success": False, "error": f"Failed to create auth user: {e}"}

    new_user = getattr(auth_result, "user", None)
    if not new_user:
        return {"success": False, "error": "Failed to create auth user"}

    # 2. Create the staff profile, keyed to that same auth user id
    staff_result = supabase.table("staff").insert({
        "id": new_user.id,
        "email": payload.email,
        "full_name": payload.full_name,
        "role": payload.role,
        "phone": payload.phone,
        "telegram_chat_id": payload.telegram_chat_id,
    }).execute()

    if not staff_result.data:
        return {
            "success": False,
            "error": "Auth user was created but the staff profile failed. "
                     "Check the Supabase Auth dashboard for an orphaned user.",
        }

    staff_id = staff_result.data[0]["id"]

    # 3. Trial assignments (admin/coordinator ignore these, harmless to store)
    for trial_id in payload.trial_ids:
        supabase.table("staff_trials").insert({
            "staff_id": staff_id, "trial_id": trial_id
        }).execute()

    log_audit(
        table_name="staff", record_id=staff_id, action="CREATE",
        user_id=user.id, new_values={"email": payload.email, "role": payload.role},
    )

    return {"success": True, "data": staff_result.data[0]}


@router.post("/{staff_id}/deactivate")
async def deactivate_staff(staff_id: str, user: CurrentUser = Depends(require_role("admin"))):
    result = supabase.table("staff").update({"active": False}).eq("id", staff_id).execute()
    if result.data:
        log_audit(table_name="staff", record_id=staff_id, action="DEACTIVATE", user_id=user.id)
    return {"success": bool(result.data)}


@router.post("/{staff_id}/reactivate")
async def reactivate_staff(staff_id: str, user: CurrentUser = Depends(require_role("admin"))):
    result = supabase.table("staff").update({"active": True}).eq("id", staff_id).execute()
    if result.data:
        log_audit(table_name="staff", record_id=staff_id, action="REACTIVATE", user_id=user.id)
    return {"success": bool(result.data)}


@router.post("/{staff_id}/trials/{trial_id}")
async def assign_trial(staff_id: str, trial_id: str, user: CurrentUser = Depends(require_role("admin"))):
    result = supabase.table("staff_trials").insert({
        "staff_id": staff_id, "trial_id": trial_id
    }).execute()
    if result.data:
        log_audit(
            table_name="staff_trials", record_id=staff_id, action="ASSIGN_TRIAL",
            user_id=user.id, new_values={"trial_id": trial_id},
        )
    return {"success": bool(result.data)}


@router.delete("/{staff_id}/trials/{trial_id}")
async def unassign_trial(staff_id: str, trial_id: str, user: CurrentUser = Depends(require_role("admin"))):
    supabase.table("staff_trials").delete().eq("staff_id", staff_id).eq("trial_id", trial_id).execute()
    log_audit(
        table_name="staff_trials", record_id=staff_id, action="UNASSIGN_TRIAL",
        user_id=user.id, old_values={"trial_id": trial_id},
    )
    return {"success": True}