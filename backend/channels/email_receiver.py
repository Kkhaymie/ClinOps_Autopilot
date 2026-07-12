# backend/channels/email_receiver.py
# Email is handled by n8n polling Gmail every 5 minutes.
# n8n posts to this endpoint when a patient email arrives.
#
# ATTACHMENT SUPPORT: this endpoint now accepts an optional "attachments"
# array. The n8n workflow needs to be updated to extract attachments from
# the Gmail message, upload each to somewhere with a fetchable URL (e.g.
# Cloudinary, or Gmail's own attachment API if it returns one), and post:
#
#   {
#     "from_email": "patient@example.com",
#     "subject": "...",
#     "body": "...",
#     "attachments": [
#       {"url": "https://...", "content_type": "image/jpeg", "filename": "rash.jpg"}
#     ]
#   }
#
# If "attachments" is omitted or empty, behavior is unchanged from before.
# Only image/*, audio/*, video/* content types are processed; anything
# else (e.g. a PDF) is currently skipped, not an error.

from fastapi import APIRouter
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

_TYPE_PREFIXES = {"image": "image", "audio": "audio", "video": "video"}


async def _process_attachments(attachments: list) -> dict:
    """Runs each attachment through the unifier and merges the results.
    Returns dict with content_parts, message_type, media_url, transcript,
    visible_symptoms, trad_medicine_hints."""
    from processing.unifier import unify_message

    content_parts = []
    message_type = "text"
    media_url = None
    transcript = None
    visible_symptoms = []
    trad_medicine_hints = []

    for att in attachments or []:
        url = att.get("url")
        content_type = att.get("content_type", "")
        if not url:
            continue

        att_type = None
        for prefix, mtype in _TYPE_PREFIXES.items():
            if content_type.startswith(prefix):
                att_type = mtype
                break
        if not att_type:
            continue  # unsupported attachment type, skip rather than fail the whole email

        unified = await unify_message(att_type, "", url)
        if unified["content"]:
            content_parts.append(unified["content"])
        visible_symptoms += unified["visible_symptoms"]
        trad_medicine_hints += unified["trad_medicine_hints"]
        if unified["transcript"]:
            transcript = unified["transcript"]
        if media_url is None:
            media_url = url
            message_type = att_type

    return {
        "content_parts": content_parts,
        "message_type": message_type,
        "media_url": media_url,
        "transcript": transcript,
        "visible_symptoms": visible_symptoms,
        "trad_medicine_hints": trad_medicine_hints,
    }


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
    attachments = payload.get("attachments", []) or []

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
        from actions.unregistered_intake import handle_unregistered_sender
        await handle_unregistered_sender(
            channel="email",
            raw_identifier=from_email,
            message_content=f"{subject}. {body}".strip(),
            message_type="text",
        )
        return {"status": "patient_not_found", "email": from_email}

    trial = patient.get("trials") or {}

    att_result = await _process_attachments(attachments)
    content = f"{subject}. {body}".strip()
    if att_result["content_parts"]:
        content = (content + " " + " ".join(att_result["content_parts"])).strip()

    from intelligence.tcm_herbs import detect_tcm_herbs
    lp        = process_nigerian_text(content)
    medicines = lp["traditional_medicines_detected"] + detect_tcm_herbs(content)

    # merge traditional medicine names spotted in attached images with the
    # ones the text scan found, so both feed the classifier and get flagged
    for name in att_result["trad_medicine_hints"]:
        if not any(m["name"].lower() == name.lower() for m in medicines):
            medicines.append({"name": name, "risk": "MODERATE", "note": "Detected in attached image"})

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
        "message_type":        att_result["message_type"],
        "original_message":    content,
        "media_url":           att_result["media_url"],
        "transcript":          att_result["transcript"],
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
        "emotional_distress_flag":  cl.get("emotional_distress_detected", False),
        "emotional_distress_notes": cl.get("emotional_distress_notes") or None,
    })

    # Fixed acknowledgment, same reasoning as WhatsApp/Telegram: fires
    # before coordinator review. cl is already computed by this point, so
    # this can be tiered by severity without sending unreviewed AI text.
    if from_email:
        from actions.notifications import _send_email
        from actions.patient_reply import build_acknowledgment_message
        await _send_email(
            to=from_email,
            subject="We have received your report",
            body=build_acknowledgment_message(cl.get("severity")),
        )

    if cl.get("severity") in ["Severe", "Life-threatening"]:
        from actions.notifications import notify_coordinator_urgent
        await notify_coordinator_urgent(patient, cl, trial)

    if cl.get("emotional_distress_detected"):
        from actions.notifications import notify_emotional_distress
        await notify_emotional_distress(patient, cl, trial)

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
        "severity": cl.get("severity"),
        "attachments_processed": len([a for a in attachments if a.get("url")]),
    }