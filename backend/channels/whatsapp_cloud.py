# backend/channels/whatsapp_cloud.py
# WhatsApp Cloud API (Meta) — production ready
# Works with ANY patient phone number worldwide
# No sandbox. No join codes. No expiry.

import os
import json
import hmac
import hashlib
import httpx
import cloudinary
import cloudinary.uploader
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from dotenv import load_dotenv

load_dotenv()

PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
ACCESS_TOKEN    = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
VERIFY_TOKEN    = os.getenv("WHATSAPP_VERIFY_TOKEN", "clinops_webhook_verify_2026")
APP_SECRET      = os.getenv("META_APP_SECRET", "")

GRAPH_API_URL = (
    f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
)

cloudinary.config(
    cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
    api_key=os.getenv("CLOUDINARY_API_KEY"),
    api_secret=os.getenv("CLOUDINARY_API_SECRET")
)

router = APIRouter()


# ─── WEBHOOK VERIFICATION ─────────────────────────────────────────
@router.get("/whatsapp-cloud")
async def verify_webhook(request: Request):
    """
    Meta calls this ONCE when you first configure the webhook.
    It verifies you own the server by checking your verify token.
    """
    params    = dict(request.query_params)
    mode      = params.get("hub.mode")
    token     = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("WhatsApp Cloud webhook verified successfully")
        return int(challenge)

    raise HTTPException(status_code=403, detail="Webhook verification failed")


# ─── WEBHOOK RECEIVER ─────────────────────────────────────────────
@router.post("/whatsapp-cloud")
async def receive_message(
    request: Request,
    background_tasks: BackgroundTasks
):
    """
    Receives ALL incoming WhatsApp messages from ANY phone number.
    Meta sends a POST here every time any patient messages you.
    """
    body_bytes = await request.body()

    # Verify the request genuinely came from Meta
    if APP_SECRET:
        sig      = request.headers.get("x-hub-signature-256", "")
        expected = "sha256=" + hmac.new(
            APP_SECRET.encode(), body_bytes, hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise HTTPException(403, "Invalid request signature")

    payload = json.loads(body_bytes)

    # Extract messages from Meta's nested payload structure
    try:
        entry   = payload["entry"][0]
        changes = entry["changes"][0]
        value   = changes["value"]
    except (KeyError, IndexError):
        return {"status": "ok"}   # Not a message event — ignore

    if "messages" not in value:
        return {"status": "ok"}   # Status update — ignore

    for message in value["messages"]:
        background_tasks.add_task(
            _process_message,
            message=message,
            metadata=value.get("metadata", {})
        )

    return {"status": "ok"}


# ─── CORE PROCESSING PIPELINE ────────────────────────────────────
async def _process_message(message: dict, metadata: dict):
    """
    Full ClinOps pipeline for one WhatsApp message.
    Handles text, audio, image, video.
    """
    from_number = message.get("from", "")     # Patient's real phone number
    msg_id      = message.get("id", "")
    msg_type    = message.get("type", "text")

    print(f"WhatsApp Cloud — from: +{from_number} | type: {msg_type}")

    # ── EXTRACT CONTENT BY TYPE ───────────────────────────────────
    body      = ""
    media_id  = None
    media_url = None

    if msg_type == "text":
        body = message.get("text", {}).get("body", "")

    elif msg_type == "audio":
        media_id = message.get("audio", {}).get("id")
        if media_id:
            media_url = await _get_media_url(media_id)

    elif msg_type == "image":
        media_id = message.get("image", {}).get("id")
        body     = message.get("image", {}).get("caption", "")
        if media_id:
            media_url = await _get_media_url(media_id)

    elif msg_type == "video":
        media_id = message.get("video", {}).get("id")
        body     = message.get("video", {}).get("caption", "")
        if media_id:
            media_url = await _get_media_url(media_id)

    elif msg_type == "document":
        media_id = message.get("document", {}).get("id")
        if media_id:
            media_url = await _get_media_url(media_id)

    else:
        print(f"Unhandled message type: {msg_type} — skipping")
        return

    # ── IDENTIFY PATIENT ──────────────────────────────────────────
    # Meta sends numbers without + prefix, our DB has them with +
    normalised_number = f"+{from_number}"

    from database.queries import (
        get_patient_by_whatsapp, check_proxy_reporter,
        save_adverse_event, log_communication,
        get_recent_fragments, save_fragment,
        mark_fragments_assembled
    )

    patient  = get_patient_by_whatsapp(normalised_number)
    is_proxy = False
    proxy_id = None

    if not patient:
        proxy = check_proxy_reporter(normalised_number)
        if proxy:
            patient  = proxy.get("patients")
            is_proxy = True
            proxy_id = proxy.get("id")
        else:
            # Unknown number — log it instead of discarding, then reply
            from actions.unregistered_intake import handle_unregistered_sender
            await handle_unregistered_sender(
                channel="whatsapp",
                raw_identifier=normalised_number,
                message_content=message.get("text", {}).get("body", "") if msg_type == "text" else body,
                message_type=msg_type,
            )
            await send_whatsapp_message(
                from_number,
                "Hello! Thank you for your message. We could not find "
                "your trial registration. Please contact your site "
                "coordinator directly for assistance."
            )
            return

    trial = patient.get("trials") or {}

    # ── FRAGMENT ASSEMBLY (unstable network handling) ─────────────
    if msg_type == "text" and body and len(body.strip()) < 60:
        frags = get_recent_fragments(normalised_number)
        if frags:
            save_fragment({
                "patient_identifier": normalised_number,
                "channel":            "whatsapp",
                "fragment_content":   body,
                "message_type":       "text"
            })
            print(f"Fragment buffered for +{from_number}")
            return

    frags = get_recent_fragments(normalised_number)
    if frags and msg_type == "text":
        all_parts = [f["fragment_content"] for f in frags] + [body]
        body      = " ".join(all_parts)
        mark_fragments_assembled([f["id"] for f in frags])

    # ── PROCESS MEDIA ─────────────────────────────────────────────
    from processing.unifier import unify_message

    stored_media_url = None
    auth_header = f"Bearer {ACCESS_TOKEN}"

    unified = await unify_message(msg_type, body, media_url, auth_header)
    content = unified["content"]
    transcript = unified["transcript"]

    if media_url:
        # video upload for audio because Cloudinary's "video" resource type
        # is what actually accepts audio containers here, same as before.
        folder = {"audio": "voice_notes", "image": "images", "video": "videos"}.get(msg_type, "media")
        resource_type = "image" if msg_type == "image" else "video"
        stored_media_url = await _store_to_cloudinary(
            media_url, resource_type, msg_id, folder, auth_header
        )

    # ── LANGUAGE PROCESSING ───────────────────────────────────────
    from intelligence.nigerian_language import process_nigerian_text
    lp        = process_nigerian_text(content)
    from intelligence.tcm_herbs import detect_tcm_herbs
    medicines = lp["traditional_medicines_detected"] + detect_tcm_herbs(content)

    # ── AI CLASSIFICATION ─────────────────────────────────────────
    from intelligence.agent_core import classify_adverse_event, calculate_deadline
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

    # ── DUPLICATE CHECK ───────────────────────────────────────────
    from intelligence.deduplication import check_duplicate
    is_dup, _ = check_duplicate(
        patient_id=patient["id"],
        symptoms=cl.get("symptoms", []),
        hours_window=24
    )
    if is_dup:
        await send_whatsapp_message(
            from_number,
            "We have already received your report. Our team is "
            "reviewing it and will contact you soon. Thank you."
        )
        return

    # ── CALCULATE REGULATORY DEADLINE ────────────────────────────
    dl = calculate_deadline(
        severity=cl.get("severity", "Mild"),
        country=patient.get("country", "Nigeria"),
        category=cl.get("category", "AE")
    )

    # ── SAVE ADVERSE EVENT ────────────────────────────────────────
    saved = save_adverse_event({
        "patient_id":          patient["id"],
        "trial_id":            patient.get("trial_id"),
        "channel":             "whatsapp",
        "message_type":        msg_type,
        "original_message":    body,
        "media_url":           stored_media_url,
        "transcript":          transcript,
        "symptoms":            cl.get("symptoms", []),
        "severity":            cl.get("severity", "Mild"),
        "urgency":             cl.get("urgency", "Routine"),
        "category":            cl.get("category", "AE"),
        "cultural_flags":      cl.get("cultural_flags", []),
        "trad_medicine_flag":  len(medicines) > 0,
        "trad_medicine_type":  (
            ", ".join(m["name"] for m in medicines) if medicines else None
        ),
        "trad_medicine_risk":  (
            medicines[0]["risk"] if medicines else None
        ),
        "language_detected":   lp["detected_language"],
        "ai_confidence":       cl.get("confidence", 0),
        "ai_model_used":       cl.get("model_used"),
        "draft_report":        cl,
        "draft_patient_reply": cl.get("draft_patient_reply"),
        "status":              "PENDING_APPROVAL",
        "regulatory_deadline": dl.get("deadline"),
        "drug_batch":          trial.get("drug_batch_current"),
        "is_proxy_report":     is_proxy,
        "proxy_reporter_id":   proxy_id,
        "emotional_distress_flag":  cl.get("emotional_distress_detected", False),
        "emotional_distress_notes": cl.get("emotional_distress_notes") or None,
    })

    # ── SEND PATIENT ACKNOWLEDGMENT ──────────────────────────────
    # Tiered by severity, not the AI's draft_patient_reply: this fires
    # before any coordinator has reviewed the classification, but cl is
    # already computed, so it's safe to differentiate by severity while
    # still not sending unreviewed AI-drafted text. The coordinator-
    # reviewed reply goes out separately after approval, via
    # notify_after_approval.
    from actions.patient_reply import build_acknowledgment_message
    await send_whatsapp_message(from_number, build_acknowledgment_message(cl.get("severity")))

    # ── URGENT COORDINATOR NOTIFICATION ──────────────────────────
    if cl.get("severity") in ["Severe", "Life-threatening"]:
        from actions.notifications import notify_coordinator_urgent
        await notify_coordinator_urgent(patient, cl, trial)

    if cl.get("emotional_distress_detected"):
        from actions.notifications import notify_emotional_distress
        await notify_emotional_distress(patient, cl, trial)

    # ── LOG COMMUNICATION ─────────────────────────────────────────
    log_communication({
        "patient_id":      patient["id"],
        "ae_id":           saved["id"] if saved else None,
        "direction":       "inbound",
        "channel":         "whatsapp",
        "message_content": body,
        "language_used":   lp["detected_language"],
        "delivery_status": "received"
    })

    # ── CHECK SAFETY SIGNAL ───────────────────────────────────────
    if patient.get("trial_id") and saved:
        from intelligence.pattern_detector import check_safety_signal
        signal = check_safety_signal(
            trial_id=patient["trial_id"],
            new_symptoms=cl.get("symptoms", []),
            drug_batch=trial.get("drug_batch_current"),
            new_ae_id=saved["id"]
        )
        if signal:
            from actions.notifications import notify_safety_signal
            await notify_safety_signal(signal, trial)

    print(
        f"WhatsApp AE saved — Severity: {cl.get('severity')} | "
        f"Patient: {patient.get('patient_code')} | "
        f"Language: {lp['detected_language']}"
    )


# ─── SEND WHATSAPP MESSAGE (to any number) ───────────────────────
async def send_whatsapp_message(to_number: str, message: str) -> bool:
    """
    Send a WhatsApp message to ANY phone number in the world.
    to_number: WITHOUT + prefix (Meta format e.g. "2348012345678")
               OR with + prefix (we strip it automatically)
    """
    to = to_number.lstrip("+")

    payload = {
        "messaging_product": "whatsapp",
        "recipient_type":    "individual",
        "to":                to,
        "type":              "text",
        "text":              {"body": message}
    }
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}",
        "Content-Type":  "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(GRAPH_API_URL, json=payload, headers=headers)
        if r.status_code == 200:
            print(f"WhatsApp sent → +{to}")
            return True
        else:
            print(f"WhatsApp send failed: {r.status_code} | {r.text}")
            return False
    except Exception as e:
        print(f"send_whatsapp_message error: {e}")
        return False


# ─── HELPERS ─────────────────────────────────────────────────────
async def _get_media_url(media_id: str) -> str:
    """Get the temporary download URL for a media file from Meta."""
    try:
        headers = {"Authorization": f"Bearer {ACCESS_TOKEN}"}
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(
                f"https://graph.facebook.com/v18.0/{media_id}",
                headers=headers
            )
        return r.json().get("url", "")
    except Exception as e:
        print(f"_get_media_url error: {e}")
        return ""


async def _store_to_cloudinary(
    url: str,
    resource_type: str,
    msg_id: str,
    folder: str,
    auth_header: str
) -> str:
    """Download media from Meta and upload to Cloudinary for permanent storage."""
    try:
        headers = {"Authorization": auth_header}
        async with httpx.AsyncClient(timeout=60) as c:
            r = await c.get(url, follow_redirects=True, headers=headers)
        import io
        result = cloudinary.uploader.upload(
            io.BytesIO(r.content),
            resource_type=resource_type,
            folder=f"clinops/{folder}",
            public_id=f"wa_{msg_id}"
        )
        return result.get("secure_url", "")
    except Exception as e:
        print(f"_store_to_cloudinary error: {e}")
        return url  # Return original URL as fallback