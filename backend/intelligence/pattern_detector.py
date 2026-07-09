# backend/intelligence/pattern_detector.py
"""
Cross-patient safety signal detection.

Looks for clusters of overlapping symptoms across recent adverse events
in the same trial (within a rolling time window) and raises a safety
signal when enough distinct patients are affected.
"""

import logging
from datetime import datetime
from typing import List, Optional

from database.client import supabase
from database.queries import get_recent_aes_for_trial, save_safety_signal

logger = logging.getLogger(__name__)

SIGNAL_THRESHOLD = 3
_SIGNAL_WINDOW_HOURS = 72


def check_safety_signal(
    trial_id: str,
    new_symptoms: List[str],
    drug_batch: str,
    new_ae_id: str,
) -> Optional[dict]:
    """
    Check whether this new AE, combined with recent AEs for the same trial,
    forms a safety signal (>= SIGNAL_THRESHOLD distinct patients with
    overlapping symptoms within the signal window). Saves and returns the
    signal record if one is detected, otherwise returns None.
    """
    try:
        recent = get_recent_aes_for_trial(trial_id, hours=_SIGNAL_WINDOW_HOURS)
        if len(recent) < SIGNAL_THRESHOLD - 1:
            return None

        new_set = {s.lower() for s in new_symptoms}
        matching_patients = set()
        matching_aes = []

        for ae in recent:
            if ae["id"] == new_ae_id:
                continue

            ae_symptoms = ae.get("symptoms", [])
            if not isinstance(ae_symptoms, list):
                continue

            ae_set = {s.lower() for s in ae_symptoms}
            if new_set and ae_set and (new_set & ae_set):
                matching_patients.add(ae["patient_id"])
                matching_aes.append(ae)

        # Include the current patient in the affected set
        current = (
            supabase.table("adverse_events")
            .select("patient_id")
            .eq("id", new_ae_id)
            .single()
            .execute()
        )
        if current.data:
            matching_patients.add(current.data["patient_id"])

        if len(matching_patients) < SIGNAL_THRESHOLD:
            return None

        batch_consistent = all(
            ae.get("drug_batch") == drug_batch
            for ae in matching_aes
            if ae.get("drug_batch")
        )

        recommendation = (
            f"SAFETY SIGNAL: {len(matching_patients)} patients "
            f"report overlapping symptoms within {_SIGNAL_WINDOW_HOURS} hours."
        )
        if batch_consistent:
            recommendation += f" Drug batch {drug_batch} implicated."
        recommendation += " Recommend immediate medical review."

        signal = {
            "trial_id": trial_id,
            "signal_type": "cluster_same_symptoms",
            "affected_patient_ids": list(matching_patients),
            "affected_patient_count": len(matching_patients),
            "common_symptoms": new_symptoms,
            "drug_batch": drug_batch if batch_consistent else None,
            "detection_time": datetime.now().isoformat(),
            "status": "OPEN",
            "recommendation": recommendation,
        }

        saved = save_safety_signal(signal)
        logger.warning(
            "Safety signal saved: %s patients affected (trial_id=%s)",
            len(matching_patients), trial_id,
        )
        return saved

    except Exception:
        logger.exception("check_safety_signal failed (trial_id=%s)", trial_id)
        return None