# backend/channels/sms_receiver.py
"""
SMS inbound message webhook (Twilio).

Simpler pipeline than the WhatsApp receiver — no media, no fragment
assembly — but the same core flow: identify patient -> language
processing -> AI classification -> duplicate check -> save AE -> reply
-> safety signal check.
"""

import logging
from typing import Optional, Tuple

from fastapi import APIRouter, BackgroundTasks, Form

from actions.patient_reply import send_sms_reply
from database.queries import (
    check_proxy_reporter,
    get_patient_by_sms,
    log_communication,
    save_adverse_event,
)
from intelligence.agent_core import calculate_deadline, classify_adverse_event
from intelligence.deduplication import check_duplicate
from intelligence.nigerian_language import process_nigerian_text
from intelligence.pattern_detector import check_safety_signal

logger = logging.getLogger(__name__)

router = APIRouter()

_STANDARD_SMS_REPLY = (
    "Report received. Nurse will contact you. "
    "Do not stop medication without doctor guidance."
)


@router.post("/sms")
async def sms_webhook(
    background_tasks: BackgroundTasks,
    Body: str = Form(default=""),
    From: str = Form(default=""),
    MessageSid: str = Form(default=""),
):
    background_tasks.add_task(_process_sms, body=Body, from_number=From, sid=MessageSid)
    return {"status": "received"}


async def _identify_patient(from_number: str) -> Tuple[Optional[dict], bool, Optional[str]]:
    """
    Resolve the sender to a patient record.
    Returns (patient, is_proxy_report, proxy_reporter_id).
    """
    patient = get_patient_by_sms(from_number)
    if patient:
        return patient, False, None

    proxy = check_proxy_reporter(from_number)
    if proxy:
        return proxy.get("patients"), True, proxy.get("id")

    return None, False, None


async def _process_sms(body: str, from_number: str, sid: str) -> None:
    logger.info("SMS from %s: %s", from_number, body[:60])

    # ── Identify patient ───────────────────────────────────────────
    patient, is_proxy, proxy_id = await _identify_patient(from_number)
    if not patient:
        logger.warning("Unknown SMS sender: %s", from_number)
        return

    trial = patient.get("trials") or {}

    # ── Language processing ─────────────────────────────────────────
    language_processed = process_nigerian_text(body)
    medicines = language_processed["traditional_medicines_detected"]

    # ── AI classification ────────────────────────────────────────────
    classification = classify_adverse_event(
        clinical_summary=language_processed["processed_text"],
        patient_context={
            "drug_name": trial.get("drug_name"),
            "last_dose_date": patient.get("last_dose_date"),
            "country": patient.get("country", "Nigeria"),
            "known_allergies": patient.get("known_allergies"),
        },
        traditional_medicines=medicines,
    )

    # ── Duplicate check ──────────────────────────────────────────────
    is_duplicate, _ = check_duplicate(
        patient_id=patient["id"],
        symptoms=classification.get("symptoms", []),
        hours_window=24,
    )
    if is_duplicate:
        return

    # ── Regulatory deadline ────────────────────────────────────────────
    deadline_info = calculate_deadline(
        severity=classification.get("severity", "Mild"),
        country=patient.get("country", "Nigeria"),
        category=classification.get("category", "AE"),
    )

    # ── Save adverse event ──────────────────────────────────────────────
    saved = save_adverse_event({
        "patient_id": patient["id"],
        "trial_id": patient.get("trial_id"),
        "channel": "sms",
        "message_type": "text",
        "original_message": body,
        "symptoms": classification.get("symptoms", []),
        "severity": classification.get("severity", "Mild"),
        "urgency": classification.get("urgency", "Routine"),
        "category": classification.get("category", "AE"),
        "language_detected": language_processed["detected_language"],
        "ai_confidence": classification.get("confidence", 0),
        "ai_model_used": classification.get("model_used"),
        "trad_medicine_flag": len(medicines) > 0,
        "trad_medicine_type": (
            ", ".join(m["name"] for m in medicines) if medicines else None
        ),
        "draft_report": classification,
        "draft_patient_reply": classification.get("draft_patient_reply"),
        "status": "PENDING_APPROVAL",
        "regulatory_deadline": deadline_info.get("deadline"),
        "drug_batch": trial.get("drug_batch_current"),
        "is_proxy_report": is_proxy,
        "proxy_reporter_id": proxy_id,
    })

    # ── Reply to patient (SMS replies must be very short) ────────────────
    await send_sms_reply(from_number, _STANDARD_SMS_REPLY)

    # ── Log communication ───────────────────────────────────────────────
    log_communication({
        "patient_id": patient["id"],
        "ae_id": saved["id"] if saved else None,
        "direction": "inbound",
        "channel": "sms",
        "message_content": body,
        "language_used": language_processed["detected_language"],
        "delivery_status": "received",
    })

    # ── Safety signal check ─────────────────────────────────────────────
    if patient.get("trial_id") and saved:
        check_safety_signal(
            trial_id=patient["trial_id"],
            new_symptoms=classification.get("symptoms", []),
            drug_batch=trial.get("drug_batch_current"),
            new_ae_id=saved["id"],
        )