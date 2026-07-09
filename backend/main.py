# backend/main.py
import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

# ── Windows asyncio fix ───────────────────────────────────────────
if os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown logic."""
    print("=" * 50)
    print("Starting ClinOps Autopilot...")
    print("=" * 50)

    # Start compliance clock (checks deadlines every hour)
    from actions.compliance_clock import start_scheduler
    start_scheduler()

    # Start Telegram bot
    from channels.telegram_receiver import setup_telegram_bot
    await setup_telegram_bot()

    # Configure Cloudinary
    import cloudinary
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET")
    )

    print("ClinOps Autopilot is running.")
    print("Dashboard API: http://localhost:8000/docs")
    yield
    print("ClinOps Autopilot shutting down.")


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

# ── REGISTER CHANNEL WEBHOOKS ─────────────────────────────────────
from channels.whatsapp_cloud      import router as wa_router
from channels.sms_africas_talking import router as sms_router
from channels.email_receiver      import router as email_router

app.include_router(wa_router,    prefix="/webhook")
app.include_router(sms_router,   prefix="/webhook")
app.include_router(email_router, prefix="/api")

# ── DASHBOARD API ROUTES ──────────────────────────────────────────
from fastapi import APIRouter
from database.queries import (
    get_pending_approvals, update_ae_status, get_ae_report,
    get_open_deadlines, get_open_safety_signals,
    get_dashboard_stats, get_analytics_events,
    get_all_ae_records, get_patient_by_code
)
from database.client import supabase

api = APIRouter(prefix="/api")


@api.get("/health")
async def health():
    return {
        "status":  "running",
        "product": "ClinOps Autopilot",
        "company": "Sentara Health Technologies"
    }


@api.get("/stats")
async def stats():
    return get_dashboard_stats()


@api.get("/pending-approvals")
async def pending_approvals():
    return {"data": get_pending_approvals()}


@api.get("/ae/{ae_id}")
async def get_ae(ae_id: str):
    return {"data": get_ae_report(ae_id)}


@api.post("/approve/{ae_id}")
async def approve_ae(
    ae_id:       str,
    approved_by: str = "coordinator",
    notes:       str = None
):
    result = update_ae_status(ae_id, "APPROVED", approved_by, notes)

    # Trigger post-approval notifications
    if result:
        ae      = get_ae_report(ae_id)
        patient = ae.get("patients", {}) if ae else {}
        trial   = ae.get("trials", {})   if ae else {}
        if ae and patient:
            from actions.notifications import notify_after_approval
            await notify_after_approval(ae, patient, trial)

    return {"success": bool(result), "data": result}


@api.post("/reject/{ae_id}")
async def reject_ae(ae_id: str, reason: str = None):
    result = update_ae_status(ae_id, "REJECTED", notes=reason)
    return {"success": bool(result), "data": result}


@api.get("/compliance-clock")
async def compliance_clock():
    return {"data": get_open_deadlines()}


@api.get("/safety-signals")
async def safety_signals():
    return {"data": get_open_safety_signals()}


@api.get("/analytics/events")
async def analytics_events(days: int = 30):
    return {"data": get_analytics_events(days)}


@api.get("/trial-master-file")
async def trial_master_file(
    status:   str = None,
    severity: str = None,
    channel:  str = None
):
    return {"data": get_all_ae_records(status, severity, channel)}


@api.post("/upload-letter")
async def upload_letter(
    file:         UploadFile = File(...),
    patient_code: str        = Form(...),
    language:     str        = Form(default="English")
):
    """Physical letter upload endpoint for reception staff."""
    try:
        contents = await file.read()

        # Find patient
        patient = get_patient_by_code(patient_code)
        if not patient:
            return {"success": False, "error": f"Patient {patient_code} not found"}

        # Upload scan to Cloudinary
        import cloudinary.uploader, io
        upload   = cloudinary.uploader.upload(
            io.BytesIO(contents),
            folder="clinops/physical_letters",
            resource_type="image"
        )
        scan_url = upload.get("secure_url", "")

        # OCR the handwritten letter
        from processing.image_processor import perform_handwriting_ocr
        ocr = await perform_handwriting_ocr(scan_url, language)

        # Use English translation if available
        content = (
            ocr.get("translated_to_english") or
            ocr.get("transcribed_text") or ""
        )

        # Language processing
        from intelligence.nigerian_language import process_nigerian_text
        lp        = process_nigerian_text(content)
        medicines = lp["traditional_medicines_detected"]

        # AI classification
        trial = patient.get("trials") or {}
        from intelligence.agent_core import (
            classify_adverse_event, calculate_deadline
        )
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

        # Date discrepancy check
        letter_date = ocr.get("letter_date_mentioned")
        backdated   = False
        gap_days    = 0
        if letter_date:
            from datetime import datetime
            try:
                written  = datetime.strptime(letter_date, "%Y-%m-%d")
                gap_days = (datetime.now() - written).days
                backdated = gap_days > 3
            except Exception:
                pass

        dl = calculate_deadline(
            severity=cl.get("severity", "Mild"),
            country=patient.get("country", "Nigeria"),
            category=cl.get("category", "AE")
        )

        from database.queries import save_adverse_event
        saved = save_adverse_event({
            "patient_id":          patient["id"],
            "trial_id":            patient.get("trial_id"),
            "channel":             "physical_mail",
            "message_type":        "handwriting",
            "original_message":    ocr.get("transcribed_text", ""),
            "media_url":           scan_url,
            "transcript":          content,
            "symptoms":            cl.get("symptoms", []),
            "severity":            cl.get("severity", "Mild"),
            "urgency":             cl.get("urgency", "Routine"),
            "category":            cl.get("category", "AE"),
            "language_detected":   ocr.get("script_detected", language),
            "ai_confidence":       ocr.get("overall_confidence", 0),
            "ai_model_used":       "pixtral-large-latest",
            "trad_medicine_flag":  lp["has_high_risk_medicine"],
            "trad_medicine_type":  (
                ", ".join(m["name"] for m in medicines) if medicines else None
            ),
            "draft_report":        cl,
            "draft_patient_reply": cl.get("draft_patient_reply"),
            "status":              "PENDING_APPROVAL",
            "regulatory_deadline": dl.get("deadline"),
            "drug_batch":          trial.get("drug_batch_current"),
            "is_backdated":        backdated,
            "backdated_gap_days":  gap_days,
        })

        return {
            "success":        True,
            "ae_id":          saved["id"] if saved else None,
            "backdated":      backdated,
            "gap_days":       gap_days,
            "ocr_confidence": ocr.get("overall_confidence", 0),
            "routing":        ocr.get("routing", "AUTO_PROCESS"),
            "severity":       cl.get("severity")
        }

    except Exception as e:
        print(f"upload_letter error: {e}")
        return {"success": False, "error": str(e)}


app.include_router(api)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
