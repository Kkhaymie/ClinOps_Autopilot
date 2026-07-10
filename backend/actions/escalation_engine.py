# backend/actions/escalation_engine.py
"""
Resolves escalation_rules against real staff and sends the alert.

This is the engine notifications.py calls; it has no knowledge of "AE" or
"safety signal" as concepts, it just takes (trial_id, severity, category,
timing, message) and fires whatever rules match, to whatever staff hold
the matching role.
"""

import logging
from typing import List, Optional

from database.audit import log_audit
from database.client import supabase

logger = logging.getLogger(__name__)


def get_matching_rules(
    trial_id: Optional[str], severity: str, category: str, timing: str
) -> List[dict]:
    """
    Trial-specific rules take precedence over default (trial_id IS NULL)
    rules for the same (recipient_role, channel) pair, so a trial can
    override the default routing without duplicating every rule.
    """
    try:
        result = (
            supabase.table("escalation_rules")
            .select("*")
            .eq("active", True)
            .eq("timing", timing)
            .in_("severity", [severity, "ANY"])
            .in_("category", [category, "ANY"])
            .execute()
        )
        rules = result.data or []
    except Exception:
        logger.exception("get_matching_rules failed (trial_id=%s)", trial_id)
        return []

    trial_specific = [r for r in rules if r.get("trial_id") == trial_id]
    defaults = [r for r in rules if r.get("trial_id") is None]
    covered = {(r["recipient_role"], r["channel"]) for r in trial_specific}
    return trial_specific + [
        r for r in defaults if (r["recipient_role"], r["channel"]) not in covered
    ]


def get_staff_for_role(trial_id: Optional[str], role: str) -> List[dict]:
    """Admin/coordinator see every trial, so any active staff with that role
    qualifies. PI/sponsor/site_staff are scoped via staff_trials."""
    try:
        if role in ("admin", "coordinator"):
            result = (
                supabase.table("staff")
                .select("*")
                .eq("role", role)
                .eq("active", True)
                .execute()
            )
            return result.data or []

        if not trial_id:
            return []

        result = (
            supabase.table("staff")
            .select("*, staff_trials!inner(trial_id)")
            .eq("role", role)
            .eq("active", True)
            .eq("staff_trials.trial_id", trial_id)
            .execute()
        )
        return result.data or []
    except Exception:
        logger.exception(
            "get_staff_for_role failed (trial_id=%s, role=%s)", trial_id, role
        )
        return []


async def _dispatch(channel: str, staff_member: dict, message: str, subject: Optional[str]) -> bool:
    try:
        if channel == "whatsapp":
            phone = staff_member.get("phone")
            if not phone:
                return False
            from channels.whatsapp_cloud import send_whatsapp_message
            return await send_whatsapp_message(phone.lstrip("+"), message)

        if channel == "sms":
            phone = staff_member.get("phone")
            if not phone:
                return False
            from channels.sms_africas_talking import send_sms
            return await send_sms(phone, message)

        if channel == "telegram":
            chat_id = staff_member.get("telegram_chat_id")
            if not chat_id:
                logger.warning(
                    "No telegram_chat_id on staff %s, skipping telegram escalation",
                    staff_member.get("id"),
                )
                return False
            from actions.patient_reply import send_telegram_reply
            return await send_telegram_reply(chat_id, message)

        if channel == "email":
            email = staff_member.get("email")
            if not email:
                return False
            from actions.notifications import _send_email
            await _send_email(to=email, subject=subject or "ClinOps Alert", body=message)
            return True

    except Exception:
        logger.exception(
            "dispatch failed (channel=%s, staff=%s)", channel, staff_member.get("id")
        )
        return False

    return False


async def run_escalation(
    trial_id: Optional[str],
    severity: str,
    category: str,
    timing: str,
    message: str,
    subject: Optional[str] = None,
) -> None:
    rules = get_matching_rules(trial_id, severity, category, timing)
    if not rules:
        logger.info(
            "No escalation rules matched (trial=%s, severity=%s, category=%s, timing=%s)",
            trial_id, severity, category, timing,
        )
        return

    for rule in rules:
        recipients = get_staff_for_role(trial_id, rule["recipient_role"])
        if not recipients:
            logger.warning(
                "Escalation rule %s matched but no active staff with role=%s for trial=%s",
                rule["id"], rule["recipient_role"], trial_id,
            )
            continue

        for staff_member in recipients:
            sent = await _dispatch(rule["channel"], staff_member, message, subject)
            log_audit(
                table_name="escalation_rules",
                record_id=rule["id"],
                action="FIRE",
                new_values={
                    "staff_id": staff_member.get("id"),
                    "channel": rule["channel"],
                    "sent": sent,
                    "trial_id": trial_id,
                    "severity": severity,
                    "category": category,
                    "timing": timing,
                },
            )