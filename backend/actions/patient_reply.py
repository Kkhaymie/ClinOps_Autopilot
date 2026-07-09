# backend/actions/patient_reply.py
"""
Outbound patient reply delivery across channels (WhatsApp, SMS, Telegram).

All three functions are best-effort: failures are logged rather than
raised, since a failed reply shouldn't crash the calling workflow.
"""

import logging
import os
from typing import Optional

import httpx
from dotenv import load_dotenv
from twilio.rest import Client

load_dotenv()

logger = logging.getLogger(__name__)

_twilio = Client(
    os.getenv("TWILIO_ACCOUNT_SID"),
    os.getenv("TWILIO_AUTH_TOKEN"),
)

_SMS_MAX_LENGTH = 160


async def send_whatsapp_reply(to: str, message: str) -> bool:
    try:
        if not to.startswith("whatsapp:"):
            to = f"whatsapp:{to}"

        _twilio.messages.create(
            from_=os.getenv("TWILIO_WHATSAPP_NUMBER"),
            to=to,
            body=message,
        )
        logger.info("WhatsApp sent -> %s", to)
        return True
    except Exception:
        logger.exception("send_whatsapp_reply failed (to=%s)", to)
        return False


async def send_sms_reply(to: str, message: str) -> bool:
    try:
        if len(message) > _SMS_MAX_LENGTH:
            message = message[: _SMS_MAX_LENGTH - 3] + "..."

        _twilio.messages.create(
            from_=os.getenv("TWILIO_SMS_NUMBER"),
            to=to,
            body=message,
        )
        logger.info("SMS sent -> %s", to)
        return True
    except Exception:
        logger.exception("send_sms_reply failed (to=%s)", to)
        return False


async def send_telegram_reply(chat_id: str, message: str) -> bool:
    try:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        url = f"https://api.telegram.org/bot{token}/sendMessage"

        async with httpx.AsyncClient() as client:
            await client.post(url, json={"chat_id": int(chat_id), "text": message})

        logger.info("Telegram sent -> %s", chat_id)
        return True
    except Exception:
        logger.exception("send_telegram_reply failed (chat_id=%s)", chat_id)
        return False