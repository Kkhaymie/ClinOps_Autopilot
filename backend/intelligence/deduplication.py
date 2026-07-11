# backend/intelligence/deduplication.py
"""
Duplicate adverse-event report detection.

Patients often report the same event twice — once by WhatsApp text, again
by voice note a few minutes later, or a proxy reporter re-sends after not
hearing back. This checks whether a newly classified report looks like a
duplicate of something the same patient already submitted recently, so we
don't create two AE records or message the patient twice.

Called from: channels/whatsapp_cloud.py, channels/sms_africas_talking.py,
channels/email_receiver.py, channels/telegram_receiver.py — always *after*
AI classification, since it compares on the classifier's symptom list.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from database.client import supabase

logger = logging.getLogger(__name__)


def check_duplicate(
    patient_id: str,
    symptoms: List[str],
    hours_window: int = 24,
) -> Tuple[bool, Optional[str]]:
    """
    Check if the same patient already reported an overlapping set of
    symptoms — possibly on a different channel — within the time window.

    Returns:
        (is_duplicate, original_ae_id) — original_ae_id is None if no
        duplicate was found.
    """
    try:
        cutoff = (datetime.now() - timedelta(hours=hours_window)).isoformat()
        r = (
            supabase.table("adverse_events")
            .select("id, symptoms")
            .eq("patient_id", patient_id)
            .gte("created_at", cutoff)
            .execute()
        )
        if not r.data:
            return False, None

        new_set = {s.lower() for s in symptoms if s}
        if not new_set:
            return False, None

        for ae in r.data:
            existing = ae.get("symptoms", [])
            if not isinstance(existing, list):
                continue
            existing_set = {s.lower() for s in existing if s}
            if not existing_set:
                continue

            overlap = len(new_set & existing_set)
            ratio = overlap / min(len(new_set), len(existing_set))
            if ratio >= 0.5:
                return True, ae["id"]

        return False, None

    except Exception:
        logger.exception("check_duplicate failed (patient_id=%s)", patient_id)
        # Fail open: if the dedup check itself errors, don't block the
        # report from being saved.
        return False, None