# backend/intelligence/deduplication.py
"""
Duplicate adverse event detection.

Flags a new AE report as a likely duplicate if a recent report from the
same patient shares at least half of its symptom set.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from database.client import supabase

logger = logging.getLogger(__name__)

_OVERLAP_THRESHOLD = 0.5


def check_duplicate(
    patient_id: str,
    symptoms: List[str],
    hours_window: int = 24,
) -> Tuple[bool, Optional[str]]:
    """
    Check whether a similar adverse event was already reported by this
    patient within the given time window.

    Returns (True, existing_ae_id) if a likely duplicate is found,
    otherwise (False, None).
    """
    try:
        cutoff = (datetime.now() - timedelta(hours=hours_window)).isoformat()

        result = (
            supabase.table("adverse_events")
            .select("id, symptoms")
            .eq("patient_id", patient_id)
            .gte("created_at", cutoff)
            .execute()
        )

        new_set = {s.lower() for s in symptoms}

        for ae in (result.data or []):
            existing = ae.get("symptoms", [])
            if not isinstance(existing, list):
                continue

            existing_set = {s.lower() for s in existing}
            if not new_set or not existing_set:
                continue

            overlap = len(new_set & existing_set)
            ratio = overlap / min(len(new_set), len(existing_set))

            if ratio >= _OVERLAP_THRESHOLD:
                return True, ae["id"]

        return False, None
    except Exception:
        logger.exception("check_duplicate failed (patient_id=%s)", patient_id)
        return False, None