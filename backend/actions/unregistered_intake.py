# backend/actions/unregistered_intake.py
"""
Fix #1: previously, a message from a phone/email not in the patient
table got a "we couldn't find your registration" auto-reply and was
then discarded entirely, nothing stored, nobody alerted. If that sender
was a real patient texting from a borrowed or new phone about an actual
adverse event, it was gone with no trace.

Every channel handler's "patient not found" branch should call this
before returning.
"""

import logging
from typing import Optional

from database.audit import log_audit
from database.client import supabase

logger = logging.getLogger(__name__)


async def handle_unregistered_sender(
    channel: str,
    raw_identifier: str,
    message_content: str = "",
    message_type: str = "text",
    media_url: Optional[str] = None,
) -> Optional[dict]:
    saved = None
    try:
        result = supabase.table("unregistered_reports").insert({
            "channel": channel,
            "raw_identifier": raw_identifier,
            "message_type": message_type,
            "message_content": message_content,
            "media_url": media_url,
        }).execute()
        saved = result.data[0] if result.data else None
    except Exception:
        logger.exception(
            "Failed to log unregistered sender (channel=%s, identifier=%s)",
            channel, raw_identifier,
        )

    if saved:
        log_audit(
            table_name="unregistered_reports", record_id=saved["id"], action="RECEIVED",
            new_values={"channel": channel, "raw_identifier": raw_identifier},
        )

    # Trial-agnostic: we don't know which trial this sender belongs to,
    # so trial_id=None. get_staff_for_role already treats coordinator/
    # admin as global regardless of trial, so this still reaches someone.
    from actions.escalation_engine import run_escalation
    preview = (message_content or "")[:300]
    await run_escalation(
        trial_id=None,
        severity="ANY",
        category="UNREGISTERED_SENDER",
        timing="immediate",
        message=(
            f"📥 UNREGISTERED SENDER\n"
            f"Channel: {channel}\n"
            f"From: {raw_identifier}\n"
            f"Message: {preview or '(no text, media only)'}\n"
            f"Not in the patient database. Review in Staff → Unregistered Reports "
            f"and link to a patient or register them."
        ),
        subject=f"[ClinOps] Unregistered sender on {channel}",
    )

    return saved
