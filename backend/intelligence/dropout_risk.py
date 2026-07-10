# backend/intelligence/dropout_risk.py
"""
Dropout risk scoring for patients.dropout_risk_score, a column that
already existed in the schema with nothing writing to it.

Deliberately a transparent, inspectable checklist rather than a trained
model, coordinators can see exactly why a score is what it is:
- recent AE severity (higher severity = higher risk)
- unresolved reports piling up (2+ still PENDING_APPROVAL)
- staleness of last recorded dose (no dose logged in 30+ days may mean
  the patient has quietly stopped attending or taking the drug)

Recomputed after every new AE for that patient, called from
database.queries.save_adverse_event() so it stays current without every
channel handler needing to remember to call it.
"""

import logging
from datetime import datetime, timedelta

from database.client import supabase

logger = logging.getLogger(__name__)

_LOOKBACK_DAYS = 90
_MAX_SCORE = 10.0
_STALE_DOSE_DAYS = 30


def recompute_dropout_risk(patient_id: str) -> None:
    if not patient_id:
        return
    try:
        cutoff = (datetime.now() - timedelta(days=_LOOKBACK_DAYS)).isoformat()
        aes = (
            supabase.table("adverse_events")
            .select("severity, status, created_at")
            .eq("patient_id", patient_id)
            .gte("created_at", cutoff)
            .execute()
        ).data or []

        score = 0.0
        unresolved = 0
        for ae in aes:
            sev = ae.get("severity")
            if sev == "Life-threatening":
                score += 1.5
            elif sev == "Severe":
                score += 1.0
            elif sev == "Moderate":
                score += 0.5
            if ae.get("status") == "PENDING_APPROVAL":
                unresolved += 1

        if unresolved >= 2:
            score += 1.0

        patient_result = (
            supabase.table("patients")
            .select("last_dose_date")
            .eq("id", patient_id)
            .single()
            .execute()
        )
        last_dose = (patient_result.data or {}).get("last_dose_date")
        if last_dose:
            try:
                days_since = (
                    datetime.now().date() - datetime.fromisoformat(last_dose).date()
                ).days
                if days_since > _STALE_DOSE_DAYS:
                    score += 1.0
            except Exception:
                pass  # unparsable date, don't let this break scoring

        score = round(min(score, _MAX_SCORE), 2)

        supabase.table("patients").update(
            {"dropout_risk_score": score}
        ).eq("id", patient_id).execute()

    except Exception:
        logger.exception("recompute_dropout_risk failed (patient_id=%s)", patient_id)
