# backend/channels/email_receiver.py
# Email is handled by n8n polling Gmail every 5 minutes
# n8n posts to this endpoint when a patient email arrives
from fastapi import APIRouter
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()


@router.post("/email-inbound")
async def email_inbound(payload: dict):
    """
    Called by n8n when a new patient email arrives.
    n8n polls Gmail every 5 minutes and posts here.
    This keeps Gmail OAuth complexity out of the backend.
    """
    from_email = payload.get("from_email", "").lower().strip()
    subject    = payload.get("subject", "")
    body       = payload.get("body", "")
    content    = f"{subject}. {body}".strip()

    from database.queries import (
        get_patient_by_email, save_adverse_event, log_communication
    )
    from intelligence.nigerian_language import process_nigerian_text
    from intelligence.agent_core import (
        classify_adverse_event, calculate_deadline
    )
    from intelligence.deduplication import check_duplicate
    from intelligence.pattern_detector import check_safety_signal

    patient = get_patient_by_email(from_email)
    if not patient:
        return {"status": "patient_not_found", "email": from_email}

    trial     = patient.get("trials") or {}
    lp        = process_nigerian_text(content)
    medicines = lp["traditional_medicines_detected"]

    cl = classify_adverse_event(
        clinical_summary=lp["processed_text"],
        patient_context={
            "trial_name":      trial.get("trial_name"),
            "drug_name":       trial.get("drug_name"),
            "last_dose_date":  patient.get("last_dose_date"),
            "country":         patient.get("country", "Nigeria"),
            "known_allergies": patient.get("known_allergies"),
        },
        traditional_medicines=medicines
    )

    is_dup, _ = check_duplicate(
        patient_id=patient["id"],
        symptoms=cl.get("symptoms", []),
        hours_window=24
    )
    if is_dup:
        return {"status": "duplicate"}

    dl = calculate_deadline(
        severity=cl.get("severity", "Mild"),
        country=patient.get("country", "Nigeria"),
        category=cl.get("category", "AE")
    )

    saved = save_adverse_event({
        "patient_id":          patient["id"],
        "trial_id":            patient.get("trial_id"),
        "channel":             "email",
        "message_type":        "text",
        "original_message":    content,
        "symptoms":            cl.get("symptoms", []),
        "severity":            cl.get("severity", "Mild"),
        "urgency":             cl.get("urgency", "Routine"),
        "category":            cl.get("category", "AE"),
        "language_detected":   lp["detected_language"],
        "ai_confidence":       cl.get("confidence", 0),
        "ai_model_used":       cl.get("model_used"),
        "trad_medicine_flag":  len(medicines) > 0,
        "trad_medicine_type":  (
            ", ".join(m["name"] for m in medicines) if medicines else None
        ),
        "draft_report":        cl,
        "draft_patient_reply": cl.get("draft_patient_reply"),
        "status":              "PENDING_APPROVAL",
        "regulatory_deadline": dl.get("deadline"),
        "drug_batch":          trial.get("drug_batch_current"),
    })

    if cl.get("severity") in ["Severe", "Life-threatening"]:
        from actions.notifications import notify_coordinator_urgent
        await notify_coordinator_urgent(patient, cl, trial)

    log_communication({
        "patient_id":      patient["id"],
        "ae_id":           saved["id"] if saved else None,
        "direction":       "inbound",
        "channel":         "email",
        "message_content": content,
        "language_used":   lp["detected_language"],
        "delivery_status": "received"
    })

    if patient.get("trial_id") and saved:
        signal = check_safety_signal(
            trial_id=patient["trial_id"],
            new_symptoms=cl.get("symptoms", []),
            drug_batch=trial.get("drug_batch_current"),
            new_ae_id=saved["id"]
        )
        if signal:
            from actions.notifications import notify_safety_signal
            await notify_safety_signal(signal, trial)

    return {
        "status": "saved",
        "ae_id":  saved["id"] if saved else None,
        "severity": cl.get("severity")
    }
