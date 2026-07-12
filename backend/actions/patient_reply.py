# backend/actions/patient_reply.py
"""
Outbound patient reply delivery, all channels.

All functions are best-effort: failures are logged rather than raised,
since a failed reply shouldn't crash the calling workflow.

send_reply_on_original_channel() is the one every other module should
call. Pass force_channel explicitly whenever you have it, an AE's
actual `channel` field, not the patient's general preferred_channel,
which may not match how this specific report came in.
"""

import logging
import os
from typing import Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

_SMS_MAX_LENGTH = 160

_MEDICATION_SAFETY_LINE = (
    "Do not stop or change your study medication without speaking to "
    "your doctor first."
)


def build_acknowledgment_message(severity: Optional[str]) -> str:
    """
    Immediate, severity-tiered acknowledgment sent at intake, before any
    coordinator has reviewed the report. Deliberately does not promise a
    specific human response time, a coordinator's actual availability
    determines that, not this message, and a wrong promise here could
    make someone wait instead of seeking care.

    What IS true and stated for the urgent tier: notify_coordinator_urgent
    fires synchronously as part of the same request that processes the
    message, so "your care team is being notified right now" is an
    accurate, verifiable system-level claim, not a promise about when a
    human responds.
    """
    if severity in ("Severe", "Life-threatening"):
        return (
            "Thank you. Your report has been flagged as urgent and your "
            "care team is being notified right now. If you feel this is "
            "a medical emergency, please seek immediate medical care "
            "without waiting for a reply. " + _MEDICATION_SAFETY_LINE
        )
    if severity == "Moderate":
        return (
            "Thank you. We have received your report and it is being "
            "reviewed promptly by our medical team. If your symptoms "
            "feel severe or you are worried, please seek medical care "
            "and contact your site coordinator directly. " + _MEDICATION_SAFETY_LINE
        )
    return (
        "Thank you. We have received your report and it is being "
        "reviewed by our medical team. If you feel this is a medical "
        "emergency or your symptoms are severe, please seek immediate "
        "medical care and contact your site coordinator directly. " + _MEDICATION_SAFETY_LINE
    )


async def send_reply_on_original_channel(
    patient: dict,
    message: str,
    force_channel: Optional[str] = None,
):
    """
    Sends on the channel a specific report actually came in on when
    force_channel is given (e.g. ae.get("channel")), falling back to the
    patient's general preferred_channel only when the caller doesn't know
    which channel applies. Always pass force_channel when you have an AE
    record, that's the whole point of this parameter.
    """
    channel = force_channel or patient.get("preferred_channel", "whatsapp")

    if channel == "whatsapp":
        wa = patient.get("whatsapp_number", "")
        if wa:
            from channels.whatsapp_cloud import send_whatsapp_message
            await send_whatsapp_message(wa.lstrip("+"), message)
        else:
            logger.warning("No whatsapp_number on file for patient %s", patient.get("id"))

    elif channel == "sms":
        sms_num = patient.get("sms_number", "")
        if sms_num:
            from channels.sms_africas_talking import send_sms
            await send_sms(sms_num, _truncate_sms(message))
        else:
            logger.warning("No sms_number on file for patient %s", patient.get("id"))

    elif channel == "telegram":
        tid = patient.get("telegram_id")
        if tid:
            await send_telegram_reply(str(tid), message)
        else:
            logger.warning("No telegram_id on file for patient %s", patient.get("id"))

    elif channel == "email":
        email = patient.get("email")
        if email:
            from actions.notifications import _send_email
            await _send_email(to=email, subject="Update on your adverse event report", body=message)
        else:
            logger.warning("No email on file for patient %s", patient.get("id"))

    elif channel == "voice":
        # IVR calls are looked up by sms_number (see channels/voice_ivr.py),
        # so that's the number to reply to. No voice callback exists to
        # ring them back, a text reply is the practical option here.
        sms_num = patient.get("sms_number", "")
        if sms_num:
            from channels.sms_africas_talking import send_sms
            await send_sms(sms_num, _truncate_sms(message))
        else:
            logger.warning("No number on file to reply to voice report for patient %s", patient.get("id"))

    elif channel == "physical_mail":
        # No digital channel exists for the letter itself. Best effort:
        # use whatever contact method is on file, if any. If neither
        # exists, this is a real dead end, log it so staff know a
        # physical-letter reporter was never actually reached.
        wa = patient.get("whatsapp_number", "")
        sms_num = patient.get("sms_number", "")
        if wa:
            from channels.whatsapp_cloud import send_whatsapp_message
            await send_whatsapp_message(wa.lstrip("+"), message)
        elif sms_num:
            from channels.sms_africas_talking import send_sms
            await send_sms(sms_num, _truncate_sms(message))
        else:
            logger.warning(
                "Physical-letter reporter %s has no whatsapp_number or sms_number on file, "
                "could not send acknowledgment through any channel", patient.get("id"),
            )

    else:
        logger.warning("Unknown channel '%s' for patient %s, no reply sent", channel, patient.get("id"))


def _truncate_sms(message: str) -> str:
    if len(message) > _SMS_MAX_LENGTH:
        return message[: _SMS_MAX_LENGTH - 3] + "..."
    return message


async def send_whatsapp_reply(to_number: str, message: str):
    from channels.whatsapp_cloud import send_whatsapp_message
    to = to_number.replace("whatsapp:", "").lstrip("+")
    await send_whatsapp_message(to, message)


async def send_sms_reply(to_number: str, message: str):
    from channels.sms_africas_talking import send_sms
    await send_sms(to_number, _truncate_sms(message))


async def send_telegram_reply(chat_id: str, message: str):
    try:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.warning("No TELEGRAM_BOT_TOKEN configured, cannot send reply")
            return
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(url, json={"chat_id": int(chat_id), "text": message})
        if r.status_code == 200:
            logger.info("Telegram reply sent to %s", chat_id)
        else:
            logger.warning("Telegram reply failed: %s", r.text)
    except Exception:
        logger.exception("send_telegram_reply failed (chat_id=%s)", chat_id)