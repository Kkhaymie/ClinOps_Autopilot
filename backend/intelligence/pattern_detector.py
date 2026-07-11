# backend/intelligence/pattern_detector.py
from database.queries import get_recent_aes_for_trial, save_safety_signal
from database.client import supabase
from datetime import datetime
from typing import List

SIGNAL_THRESHOLD = 3   # 3+ patients with same symptoms = safety signal
HOURS_WINDOW     = 72  # Check within 72-hour window


def check_safety_signal(
    trial_id: str,
    new_symptoms: List[str],
    drug_batch: str,
    new_ae_id: str
) -> dict:
    """
    After every new AE, check if a cross-patient safety signal
    has formed. If 3+ patients report overlapping symptoms within
    72 hours, generate a Safety Signal Alert automatically.
    """
    try:
        recent = get_recent_aes_for_trial(trial_id, hours=HOURS_WINDOW)

        if len(recent) < SIGNAL_THRESHOLD - 1:
            return None

        new_set          = {s.lower() for s in new_symptoms if s}
        matching_patients = set()
        matching_aes      = []

        for ae in recent:
            if ae["id"] == new_ae_id:
                continue
            ae_syms = ae.get("symptoms", [])
            if not isinstance(ae_syms, list):
                continue
            ae_set = {s.lower() for s in ae_syms if s}
            if new_set and ae_set and (new_set & ae_set):
                matching_patients.add(ae["patient_id"])
                matching_aes.append(ae)

        # Include the current patient
        try:
            cur = supabase.table("adverse_events")\
                .select("patient_id")\
                .eq("id", new_ae_id)\
                .single().execute()
            if cur.data:
                matching_patients.add(cur.data["patient_id"])
        except Exception:
            pass

        if len(matching_patients) >= SIGNAL_THRESHOLD:
            batch_consistent = drug_batch and all(
                ae.get("drug_batch") == drug_batch
                for ae in matching_aes
                if ae.get("drug_batch")
            )

            signal = {
                "trial_id":              trial_id,
                "signal_type":           "cluster_same_symptoms",
                "affected_patient_ids":  list(matching_patients),
                "affected_patient_count": len(matching_patients),
                "common_symptoms":       new_symptoms,
                "drug_batch":            drug_batch if batch_consistent else None,
                "detection_time":        datetime.now().isoformat(),
                "status":                "OPEN",
                "recommendation": (
                    f"SAFETY SIGNAL: {len(matching_patients)} patients "
                    f"report overlapping symptoms within {HOURS_WINDOW} hours."
                    + (f" Drug batch {drug_batch} implicated."
                       if batch_consistent else "")
                    + " Recommend immediate medical review and potential batch hold."
                )
            }

            saved = save_safety_signal(signal)
            print(f"SAFETY SIGNAL SAVED — {len(matching_patients)} patients")
            return saved

        return None

    except Exception as e:
        print(f"check_safety_signal error: {e}")
        return None
