# backend/actions/patient_reply.py
# Central reply dispatcher — always send back through here, never call a
# channel's send function directly, so every reply respects the patient's
# preferred/original channel.

import logging
import os

from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


async def send_reply_on_original_channel(
    patient: dict,
    message: str,
    force_channel: str = None,
) -> bool:
    """
    Send a reply to the patient on the channel they reported through
    (or their stored preferred_channel, or an explicit override).
    """
    channel = force_channel or patient.get("preferred_channel", "whatsapp")

    try:
        if channel == "whatsapp":
            wa_number = patient.get("whatsapp_number", "")
            if not wa_number:
                logger.warning("No WhatsApp number on file for patient %s", patient.get("id"))
                return False
            from channels.whatsapp_cloud import send_whatsapp_message
            return await send_whatsapp_message(wa_number.lstrip("+"), message)

        elif channel == "sms":
            sms_number = patient.get("sms_number", "")
            if not sms_number:
                logger.warning("No SMS number on file for patient %s", patient.get("id"))
                return False
            from channels.sms_africas_talking import send_sms
            return await send_sms(sms_number, message)

        elif channel == "telegram":
            chat_id = patient.get("telegram_id")
            if not chat_id:
                logger.warning("No Telegram id on file for patient %s", patient.get("id"))
                return False
            return await send_telegram_reply(str(chat_id), message)

        else:
            logger.warning("Unknown channel '%s' for patient %s", channel, patient.get("id"))
            return False

    except Exception:
        logger.exception("send_reply_on_original_channel failed (patient_id=%s, channel=%s)",
                          patient.get("id"), channel)
        return False


async def send_whatsapp_reply(to_number: str, message: str) -> bool:
    """Send WhatsApp via the WhatsApp Cloud API (Meta)."""
    from channels.whatsapp_cloud import send_whatsapp_message
    to = to_number.replace("whatsapp:", "").lstrip("+")
    return await send_whatsapp_message(to, message)


async def send_sms_reply(to_number: str, message: str) -> bool:
    """Send SMS via Africa's Talking."""
    from channels.sms_africas_talking import send_sms
    return await send_sms(to_number, message)


async def send_telegram_reply(chat_id: str, message: str) -> bool:
    """Send a message via the Telegram Bot API directly."""
    try:
        import httpx
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            logger.warning("TELEGRAM_BOT_TOKEN not configured")
            return False

        url = f"https://api.telegram.org/bot{token}/sendMessage"
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(url, json={"chat_id": int(chat_id), "text": message})

        if r.status_code == 200:
            logger.info("Telegram reply sent to %s", chat_id)
            return True
        logger.warning("Telegram reply failed (%s): %s", r.status_code, r.text)
        return False

    except Exception:
        logger.exception("send_telegram_reply failed (chat_id=%s)", chat_id)
        return False