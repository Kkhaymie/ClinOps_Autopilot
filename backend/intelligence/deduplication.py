# backend/intelligence/deduplication.py
"""
Duplicate adverse-event report detection.

Patients often report the same event twice — e.g. once by WhatsApp text and
again by voice note a few minutes later, or a proxy reporter re-sends after
not hearing back. This module checks whether a newly classified report looks
like a duplicate of something the same patient already submitted recently,
so we don't create two AE records (and don't message the patient twice).

Called from: channels/whatsapp_cloud.py, channels/email_receiver.py,
channels/telegram_receiver.py — always *after* AI classification, since it
compares on the classifier's normalized `symptoms` list.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from database.client import supabase

logger = logging.getLogger(__name__)


def _normalize_symptom(s: str) -> str:
    return s.strip().lower()


def _symptom_overlap(a: List[str], b: List[str]) -> float:
    """Jaccard-style overlap between two symptom lists, 0.0-1.0."""
    set_a = {_normalize_symptom(s) for s in (a or [])}
    set_b = {_normalize_symptom(s) for s in (b or [])}
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union) if union else 0.0


def check_duplicate(
    patient_id: str,
    symptoms: List[str],
    hours_window: int = 24,
    overlap_threshold: float = 0.5,
) -> Tuple[bool, Optional[dict]]:
    """
    Check whether this patient has already reported a very similar set of
    symptoms within the recent window.

    Args:
        patient_id: patient's UUID.
        symptoms: normalized symptom list from classify_adverse_event().
        hours_window: how far back to look for prior reports.
        overlap_threshold: minimum symptom-set similarity (Jaccard) to
            consider two reports duplicates of each other.

    Returns:
        (is_duplicate, matching_record_or_None)
    """
    try:
        cutoff = (datetime.now() - timedelta(hours=hours_window)).isoformat()
        result = (
            supabase.table("adverse_events")
            .select("id, symptoms, created_at, status")
            .eq("patient_id", patient_id)
            .gte("created_at", cutoff)
            .order("created_at", desc=True)
            .execute()
        )
        recent_events = result.data or []
    except Exception:
        logger.exception("check_duplicate failed (patient_id=%s)", patient_id)
        # Fail open: if the dedup check itself errors, don't block the
        # report from being saved — a false negative here just means a
        # possible duplicate record, which a coordinator can merge later.
        return False, None

    if not symptoms:
        return False, None

    for event in recent_events:
        overlap = _symptom_overlap(symptoms, event.get("symptoms") or [])
        if overlap >= overlap_threshold:
            return True, event

    return False, None