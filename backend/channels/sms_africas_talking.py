# backend/channels/sms_africas_talking.py
# Africa's Talking SMS — for patients without smartphones/data.
# Works with any Nigerian phone number, no verified-sender-list restriction
# (unlike WhatsApp/Meta test numbers).

import os
import logging

import africastalking
from fastapi import APIRouter, Request, BackgroundTasks
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

AT_USERNAME = os.getenv("AT_USERNAME", "sandbox")
AT_API_KEY = os.getenv("AT_API_KEY", "")
AT_SENDER = os.getenv("AT_SENDER_ID", "ClinOps")

africastalking.initialize(AT_USERNAME, AT_API_KEY)
_sms = africastalking.SMS

router = APIRouter()


# ─── WEBHOOK RECEIVER ─────────────────────────────────────────────
# NOTE: route is /sms-at — this is the exact path configured as the
# callback URL in the Africa's Talking dashboard. Don't rename this
# without updating that callback.
@router.post("/sms-at")
async def receive_sms(request: Request, background_tasks: BackgroundTasks):
    """
    Africa's Talking posts incoming SMS as application/x-www-form-urlencoded
    with fields: from, to, text, date, id, linkId.
    """
    form = await request.form()
    from_number = str(form.get("from", ""))
    body = str(form.get("text", ""))
    msg_id = str(form.get("id", ""))

    logger.info("SMS from %s: %s", from_number, body[:60])

    # Process in the background so Africa's Talking gets an immediate
    # empty 200 response and doesn't retry/timeout on us.
    background_tasks.add_task(_process_sms, from_number=from_number, body=body, msg_id=msg_id)

    return {}


# ─── CORE PROCESSING PIPELINE ─────────────────────────────────────
async def _process_sms(from_number: str, body: str, msg_id: str):
    """Full ClinOps pipeline for one inbound SMS."""
    from database.queries import (
        get_patient_by_sms, check_proxy_reporter,
        save_adverse_event, log_communication,
    )
    from intelligence.nigerian_language import process_nigerian_text
    from intelligence.agent_core import classify_adverse_event, calculate_deadline
    from intelligence.deduplication import check_duplicate
    from intelligence.pattern_detector import check_safety_signal

    patient = get_patient_by_sms(from_number)
    is_proxy = False
    proxy_id = None

    if not patient:
        proxy = check_proxy_reporter(from_number)
        if proxy:
            patient = proxy.get("patients")
            is_proxy = True
            proxy_id = proxy.get("id")
        else:
            logger.info("Unknown SMS sender: %s", from_number)
            from actions.unregistered_intake import handle_unregistered_sender
            await handle_unregistered_sender(
                channel="sms",
                raw_identifier=from_number,
                message_content=body,
                message_type="text",
            )
            await send_sms(
                from_number,
                "ClinOps: We could not find your registration. "
                "Please contact your site coordinator."
            )
            return

    trial = patient.get("trials") or {}

    # ── LANGUAGE PROCESSING ────────────────────────────────────────
    lp = process_nigerian_text(body)
    from intelligence.tcm_herbs import detect_tcm_herbs
    medicines = lp["traditional_medicines_detected"] + detect_tcm_herbs(body)

    # ── AI CLASSIFICATION ───────────────────────────────────────────
    cl = classify_adverse_event(
        clinical_summary=lp["processed_text"],
        patient_context={
            "trial_name": trial.get("trial_name"),
            "drug_name": trial.get("drug_name"),
            "last_dose_date": patient.get("last_dose_date"),
            "country": patient.get("country", "Nigeria"),
            "known_allergies": patient.get("known_allergies"),
        },
        traditional_medicines=medicines,
    )

    # ── DUPLICATE CHECK ──────────────────────────────────────────────
    is_dup, _ = check_duplicate(
        patient_id=patient["id"],
        symptoms=cl.get("symptoms", []),
        hours_window=24,
    )
    if is_dup:
        await send_sms(
            from_number,
            "ClinOps: We already received your report. "
            "Our nurse will contact you soon."
        )
        return

    # ── CALCULATE REGULATORY DEADLINE ────────────────────────────────
    dl = calculate_deadline(
        severity=cl.get("severity", "Mild"),
        country=patient.get("country", "Nigeria"),
        category=cl.get("category", "AE"),
    )

    # ── SAVE ADVERSE EVENT ────────────────────────────────────────────
    saved = save_adverse_event({
        "patient_id": patient["id"],
        "trial_id": patient.get("trial_id"),
        "channel": "sms",
        "message_type": "text",
        "original_message": body,
        "symptoms": cl.get("symptoms", []),
        "severity": cl.get("severity", "Mild"),
        "urgency": cl.get("urgency", "Routine"),
        "category": cl.get("category", "AE"),
        "language_detected": lp["detected_language"],
        "ai_confidence": cl.get("confidence", 0),
        "ai_model_used": cl.get("model_used"),
        "trad_medicine_flag": len(medicines) > 0,
        "trad_medicine_type": (
            ", ".join(m["name"] for m in medicines) if medicines else None
        ),
        "trad_medicine_risk": medicines[0]["risk"] if medicines else None,
        "draft_report": cl,
        "draft_patient_reply": cl.get("draft_patient_reply"),
        "status": "PENDING_APPROVAL",
        "regulatory_deadline": dl.get("deadline"),
        "drug_batch": trial.get("drug_batch_current"),
        "is_proxy_report": is_proxy,
        "proxy_reporter_id": proxy_id,
        "emotional_distress_flag": cl.get("emotional_distress_detected", False),
        "emotional_distress_notes": cl.get("emotional_distress_notes") or None,
    })

    # ── SEND PATIENT ACKNOWLEDGMENT (kept short — SMS is billed per segment) ──
    _sms_ack = {
        "Severe": "ClinOps: URGENT, your care team is being notified now. If this is an emergency, seek care immediately. Do not stop medication without doctor advice.",
        "Life-threatening": "ClinOps: URGENT, your care team is being notified now. If this is an emergency, seek care immediately. Do not stop medication without doctor advice.",
        "Moderate": "ClinOps: Report received, reviewed promptly. If severe, seek care and contact your coordinator. Do not stop medication without doctor advice.",
    }
    await send_sms(
        from_number,
        _sms_ack.get(
            cl.get("severity"),
            "ClinOps: Report received, under review. If emergency or severe, seek care now and contact your coordinator. Do not stop medication without doctor advice.",
        )
    )

    # ── URGENT COORDINATOR NOTIFICATION ───────────────────────────────
    if cl.get("severity") in ["Severe", "Life-threatening"]:
        from actions.notifications import notify_coordinator_urgent
        await notify_coordinator_urgent(patient, cl, trial)

    if cl.get("emotional_distress_detected"):
        from actions.notifications import notify_emotional_distress
        await notify_emotional_distress(patient, cl, trial)

    # ── LOG COMMUNICATION ──────────────────────────────────────────────
    log_communication({
        "patient_id": patient["id"],
        "ae_id": saved["id"] if saved else None,
        "direction": "inbound",
        "channel": "sms",
        "message_content": body,
        "language_used": lp["detected_language"],
        "delivery_status": "received",
    })

    # ── CHECK SAFETY SIGNAL ───────────────────────────────────────────
    if patient.get("trial_id") and saved:
        signal = check_safety_signal(
            trial_id=patient["trial_id"],
            new_symptoms=cl.get("symptoms", []),
            drug_batch=trial.get("drug_batch_current"),
            new_ae_id=saved["id"],
        )
        if signal:
            from actions.notifications import notify_safety_signal
            await notify_safety_signal(signal, trial)

    logger.info(
        "SMS AE saved — Severity: %s | Patient: %s",
        cl.get("severity"), patient.get("patient_code")
    )


# ─── SEND SMS (to any number) ─────────────────────────────────────
async def send_sms(to: str, message: str) -> bool:
    """Send SMS to any Nigerian/African phone number via Africa's Talking."""
    try:
        msg = message[:160] if len(message) > 160 else message
        result = _sms.send(message=msg, recipients=[to], sender_id=AT_SENDER)
        logger.info("SMS sent to %s: %s", to, result)
        return True
    except Exception:
        logger.exception("send_sms failed (to=%s)", to)
        return False


async def send_sms_bulk(recipients: list, message: str) -> dict:
    """Send the same SMS to multiple recipients (e.g. coordinator alerts)."""
    try:
        msg = message[:160] if len(message) > 160 else message
        result = _sms.send(message=msg, recipients=recipients, sender_id=AT_SENDER)
        return {"success": True, "result": result}
    except Exception as e:
        logger.exception("send_sms_bulk failed")
        return {"success": False, "error": str(e)}