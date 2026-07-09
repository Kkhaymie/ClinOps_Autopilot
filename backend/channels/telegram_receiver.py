# backend/channels/telegram_receiver.py
import os
import cloudinary.uploader
from telegram import Update
from telegram.ext import (
    Application, MessageHandler,
    filters, ContextTypes
)
from dotenv import load_dotenv

load_dotenv()

_app = None


async def setup_telegram_bot():
    """Initialise Telegram bot and start polling for messages."""
    global _app
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("No TELEGRAM_BOT_TOKEN — Telegram disabled")
        return

    _app = Application.builder().token(token).build()
    _app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, _handle_text))
    _app.add_handler(MessageHandler(filters.VOICE,  _handle_voice))
    _app.add_handler(MessageHandler(filters.PHOTO,  _handle_photo))
    _app.add_handler(MessageHandler(filters.VIDEO,  _handle_video))

    await _app.initialize()
    await _app.start()
    await _app.updater.start_polling(drop_pending_updates=True)
    print("Telegram bot polling started")


async def _handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid     = str(update.effective_user.id)
    patient = _get_patient(tid)
    if not patient:
        await update.message.reply_text(
            "We could not find your trial registration. "
            "Please contact your site coordinator."
        )
        return
    await _pipeline(patient, update.message.text, "text", None, update)


async def _handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid     = str(update.effective_user.id)
    patient = _get_patient(tid)
    if not patient:
        return
    vf      = await ctx.bot.get_file(update.message.voice.file_id)
    vb      = await vf.download_as_bytearray()
    from processing.audio_processor import transcribe_bytes
    tr      = await transcribe_bytes(bytes(vb), ".ogg")
    content = tr.get("transcript", "")
    try:
        up  = cloudinary.uploader.upload(
            bytes(vb), resource_type="video",
            folder="clinops/telegram_voice"
        )
        url = up.get("secure_url")
    except Exception:
        url = None
    await _pipeline(patient, content, "audio", url, update)


async def _handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid     = str(update.effective_user.id)
    patient = _get_patient(tid)
    if not patient:
        return
    photo   = update.message.photo[-1]
    pf      = await ctx.bot.get_file(photo.file_id)
    from processing.image_processor import analyse_symptom_image
    an      = await analyse_symptom_image(pf.file_path)
    content = (an.get("medical_description", "") + " " + (update.message.caption or "")).strip()
    await _pipeline(patient, content, "image", pf.file_path, update)


async def _handle_video(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    tid     = str(update.effective_user.id)
    patient = _get_patient(tid)
    if not patient:
        return
    vf      = await ctx.bot.get_file(update.message.video.file_id)
    from processing.video_processor import process_video_message
    vr      = await process_video_message(vf.file_path)
    content = vr.get("merged_clinical_summary", "")
    await _pipeline(patient, content, "video", vf.file_path, update)


def _get_patient(telegram_id: str):
    from database.queries import get_patient_by_telegram
    return get_patient_by_telegram(telegram_id)


async def _pipeline(patient, content, msg_type, media_url, update):
    """Full ClinOps pipeline for Telegram messages."""
    from database.queries import (
        save_adverse_event, log_communication
    )
    from intelligence.nigerian_language import process_nigerian_text
    from intelligence.agent_core import (
        classify_adverse_event, calculate_deadline
    )
    from intelligence.deduplication import check_duplicate
    from intelligence.pattern_detector import check_safety_signal

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
        await update.message.reply_text(
            "We have already received your report. "
            "Our team will be in touch. Thank you."
        )
        return

    dl = calculate_deadline(
        severity=cl.get("severity", "Mild"),
        country=patient.get("country", "Nigeria"),
        category=cl.get("category", "AE")
    )

    saved = save_adverse_event({
        "patient_id":          patient["id"],
        "trial_id":            patient.get("trial_id"),
        "channel":             "telegram",
        "message_type":        msg_type,
        "original_message":    content,
        "media_url":           media_url,
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

    reply = cl.get(
        "draft_patient_reply",
        "Your report has been received. Our team will follow up. Thank you."
    )
    await update.message.reply_text(reply)

    if cl.get("severity") in ["Severe", "Life-threatening"]:
        from actions.notifications import notify_coordinator_urgent
        await notify_coordinator_urgent(patient, cl, trial)

    log_communication({
        "patient_id":      patient["id"],
        "ae_id":           saved["id"] if saved else None,
        "direction":       "inbound",
        "channel":         "telegram",
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
