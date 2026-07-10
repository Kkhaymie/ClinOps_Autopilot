# backend/main.py
import os
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("clinops")

# Windows needs the selector event loop policy for some async libs.
if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _configure_cloudinary():
    import cloudinary
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET")
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic. Each integration is isolated so one
    misconfigured service (e.g. missing Telegram token) doesn't take
    the whole API down."""
    logger.info("Starting ClinOps Autopilot...")

    try:
        from actions.compliance_clock import start_scheduler
        start_scheduler()
    except Exception:
        logger.exception("Compliance clock failed to start")

    try:
        from channels.telegram_receiver import setup_telegram_bot
        await setup_telegram_bot()
    except Exception:
        logger.exception("Telegram bot failed to start")

    try:
        _configure_cloudinary()
    except Exception:
        logger.exception("Cloudinary configuration failed")

    logger.info("ClinOps Autopilot is running. Docs: http://localhost:8000/docs")
    yield
    logger.info("ClinOps Autopilot shutting down.")


app = FastAPI(
    title="ClinOps Autopilot API",
    description=(
        "Omnichannel Clinical Trial Adverse Event Management — "
        "Sentara Health Technologies"
    ),
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# ── ROUTERS ─────────────────────────────────────────────────────
from channels.whatsapp_cloud import router as wa_router
from channels.sms_africas_talking import router as sms_router
from channels.email_receiver import router as email_router
from channels.voice_ivr import router as voice_router
from api.dashboard import router as dashboard_router
from api.staff import router as staff_router

app.include_router(wa_router, prefix="/webhook")
app.include_router(sms_router, prefix="/webhook")
app.include_router(voice_router, prefix="/webhook")
app.include_router(email_router, prefix="/api")
app.include_router(dashboard_router)
app.include_router(staff_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)