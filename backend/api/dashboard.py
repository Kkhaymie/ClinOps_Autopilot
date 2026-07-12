# backend/api/dashboard.py
"""Dashboard + AE workflow REST routes, split out of main.py so the app
entrypoint stays focused on wiring, not endpoint logic.

Authorization note: the backend connects to Supabase with the service-role
key, which bypasses RLS. Enforcement happens here, via the require_role /
CurrentUser dependencies, not via the SQL-level policies.
"""

import io
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form

from auth.dependencies import get_current_user, require_role, CurrentUser
from database.audit import log_audit
from database.client import supabase
from database.queries import (
    get_pending_approvals, update_ae_status, get_ae_report,
    get_open_deadlines, get_open_safety_signals,
    get_dashboard_stats, get_analytics_events,
    get_all_ae_records, get_patient_by_code, save_adverse_event,
    get_unregistered_reports, mark_unregistered_report_reviewed
)

router = APIRouter(prefix="/api")


def _trial_scope(records: list, user: CurrentUser) -> list:
    """Filter a list of AE/signal/deadline records to trials this user can
    see. Admins and coordinators see everything; PI/sponsor/site_staff are
    scoped to their assigned trials (staff_trials)."""
    if user.role in ("admin", "coordinator"):
        return records
    return [r for r in records if r.get("trial_id") in user.trial_ids]


@router.get("/health")
async def health():
    # Deliberately unauthenticated: used for uptime checks / load balancers.
    return {
        "status": "running",
        "product": "ClinOps Autopilot",
        "company": "Sentara Health Technologies"
    }


@router.get("/stats")
async def stats(user: CurrentUser = Depends(get_current_user)):
    return get_dashboard_stats()


@router.get("/pending-approvals")
async def pending_approvals(
    user: CurrentUser = Depends(require_role("admin", "coordinator", "pi"))
):
    return {"data": _trial_scope(get_pending_approvals(), user)}


@router.get("/ae/{ae_id}")
async def get_ae(ae_id: str, user: CurrentUser = Depends(get_current_user)):
    ae = get_ae_report(ae_id)
    if not ae:
        return {"data": None}
    allowed = (
        user.role in ("admin", "coordinator")
        or ae.get("trial_id") in user.trial_ids
        or ae.get("submitted_by_staff_id") == user.id
    )
    if not allowed:
        return {"data": None, "error": "Not authorized for this record"}
    return {"data": ae}


@router.post("/approve/{ae_id}")
async def approve_ae(
    ae_id: str,
    notes: str = None,
    user: CurrentUser = Depends(require_role("admin", "coordinator", "pi")),
):
    before = get_ae_report(ae_id)
    if before and not user.can_access_trial(before.get("trial_id")):
        return {"success": False, "error": "Not authorized for this trial"}

    result = update_ae_status(ae_id, "APPROVED", user.full_name, notes)
    if result:
        supabase.table("adverse_events").update(
            {"approved_by_id": user.id}
        ).eq("id", ae_id).execute()

        log_audit(
            table_name="adverse_events", record_id=ae_id, action="APPROVE",
            user_id=user.id,
            old_values={"status": before.get("status") if before else None},
            new_values={"status": "APPROVED", "notes": notes},
        )

        ae = get_ae_report(ae_id)
        patient = ae.get("patients", {}) if ae else {}
        trial = ae.get("trials", {}) if ae else {}
        if ae and patient:
            from actions.notifications import notify_after_approval
            await notify_after_approval(ae, patient, trial)

    return {"success": bool(result), "data": result}


@router.post("/reject/{ae_id}")
async def reject_ae(
    ae_id: str,
    reason: str = None,
    user: CurrentUser = Depends(require_role("admin", "coordinator", "pi")),
):
    before = get_ae_report(ae_id)
    if before and not user.can_access_trial(before.get("trial_id")):
        return {"success": False, "error": "Not authorized for this trial"}

    result = update_ae_status(ae_id, "REJECTED", notes=reason)
    if result:
        log_audit(
            table_name="adverse_events", record_id=ae_id, action="REJECT",
            user_id=user.id,
            old_values={"status": before.get("status") if before else None},
            new_values={"status": "REJECTED", "reason": reason},
        )
    return {"success": bool(result), "data": result}


@router.get("/compliance-clock")
async def compliance_clock(user: CurrentUser = Depends(get_current_user)):
    return {"data": _trial_scope(get_open_deadlines(), user)}


@router.get("/safety-signals")
async def safety_signals(user: CurrentUser = Depends(get_current_user)):
    return {"data": _trial_scope(get_open_safety_signals(), user)}


@router.get("/analytics/events")
async def analytics_events(days: int = 30, user: CurrentUser = Depends(get_current_user)):
    return {"data": _trial_scope(get_analytics_events(days), user)}


@router.get("/trial-master-file")
async def trial_master_file(
    status: str = None, severity: str = None, channel: str = None,
    user: CurrentUser = Depends(get_current_user),
):
    return {"data": _trial_scope(get_all_ae_records(status, severity, channel), user)}


@router.post("/upload-letter")
async def upload_letter(
    file: UploadFile = File(...),
    patient_code: str = Form(...),
    language: str = Form(default="English"),
    user: CurrentUser = Depends(require_role("admin", "coordinator", "site_staff")),
):
    """Manual/physical intake endpoint for reception and site staff.
    Same media pipeline and classification as the patient-facing channels;
    the only difference is a human triggers it from the admin panel rather
    than a webhook firing it. submitted_by_staff_id records who did it."""
    try:
        contents = await file.read()

        patient = get_patient_by_code(patient_code)
        if not patient:
            return {"success": False, "error": f"Patient {patient_code} not found"}

        if not user.can_access_trial(patient.get("trial_id")):
            return {"success": False, "error": "Not authorized for this patient's trial"}

        import cloudinary.uploader
        upload = cloudinary.uploader.upload(
            io.BytesIO(contents),
            folder="clinops/physical_letters",
            resource_type="image"
        )
        scan_url = upload.get("secure_url", "")

        from processing.image_processor import perform_handwriting_ocr
        ocr = await perform_handwriting_ocr(scan_url, language)

        content = ocr.get("translated_to_english") or ocr.get("transcribed_text") or ""

        from intelligence.nigerian_language import process_nigerian_text
        from intelligence.tcm_herbs import detect_tcm_herbs
        lp = process_nigerian_text(content)
        medicines = lp["traditional_medicines_detected"] + detect_tcm_herbs(content)

        trial = patient.get("trials") or {}
        from intelligence.agent_core import classify_adverse_event, calculate_deadline
        cl = classify_adverse_event(
            clinical_summary=lp["processed_text"],
            patient_context={
                "trial_name": trial.get("trial_name"),
                "drug_name": trial.get("drug_name"),
                "last_dose_date": patient.get("last_dose_date"),
                "country": patient.get("country", "Nigeria"),
                "known_allergies": patient.get("known_allergies"),
            },
            traditional_medicines=medicines
        )

        letter_date = ocr.get("letter_date_mentioned")
        backdated = False
        gap_days = 0
        if letter_date:
            try:
                written = datetime.strptime(letter_date, "%Y-%m-%d")
                gap_days = (datetime.now() - written).days
                backdated = gap_days > 3
            except Exception:
                pass

        dl = calculate_deadline(
            severity=cl.get("severity", "Mild"),
            country=patient.get("country", "Nigeria"),
            category=cl.get("category", "AE")
        )

        saved = save_adverse_event({
            "patient_id": patient["id"],
            "trial_id": patient.get("trial_id"),
            "channel": "physical_mail",
            "message_type": "handwriting",
            "original_message": ocr.get("transcribed_text", ""),
            "media_url": scan_url,
            "transcript": content,
            "symptoms": cl.get("symptoms", []),
            "severity": cl.get("severity", "Mild"),
            "urgency": cl.get("urgency", "Routine"),
            "category": cl.get("category", "AE"),
            "language_detected": ocr.get("script_detected", language),
            "ai_confidence": ocr.get("overall_confidence", 0),
            "ai_model_used": "pixtral-large-latest",
            "trad_medicine_flag": lp["has_high_risk_medicine"],
            "trad_medicine_type": (
                ", ".join(m["name"] for m in medicines) if medicines else None
            ),
            "draft_report": cl,
            "draft_patient_reply": cl.get("draft_patient_reply"),
            "status": "PENDING_APPROVAL",
            "regulatory_deadline": dl.get("deadline"),
            "drug_batch": trial.get("drug_batch_current"),
            "is_backdated": backdated,
            "backdated_gap_days": gap_days,
            "submitted_by_staff_id": user.id,
        })

        if saved:
            log_audit(
                table_name="adverse_events", record_id=saved["id"], action="STAFF_SUBMIT",
                user_id=user.id,
                new_values={"channel": "physical_mail", "severity": cl.get("severity")},
                ai_model="pixtral-large-latest", ai_confidence=ocr.get("overall_confidence", 0),
            )
            # A physical letter has no digital reply channel of its own.
            # Best effort: use whatever contact info is on the patient's
            # record. send_reply_on_original_channel already handles the
            # whatsapp-then-sms fallback and logs a warning if neither
            # exists, this channel sent no acknowledgment at all before.
            # Same tiered builder as every other channel: the urgent-tier
            # claim (care team notified now) is equally true here, that
            # alert fires synchronously as part of this same upload.
            from actions.patient_reply import send_reply_on_original_channel, build_acknowledgment_message
            await send_reply_on_original_channel(
                patient,
                build_acknowledgment_message(cl.get("severity")),
                force_channel="physical_mail",
            )
            if cl.get("emotional_distress_detected"):
                from actions.notifications import notify_emotional_distress
                await notify_emotional_distress(patient, cl, trial)

        return {
            "success": True,
            "ae_id": saved["id"] if saved else None,
            "backdated": backdated,
            "gap_days": gap_days,
            "ocr_confidence": ocr.get("overall_confidence", 0),
            "routing": ocr.get("routing", "AUTO_PROCESS"),
            "severity": cl.get("severity")
        }

    except Exception as e:
        print(f"upload_letter error: {e}")
        return {"success": False, "error": str(e)}


# ── ESCALATION RULES (configurable routing) ────────────────────────

@router.get("/escalation-rules")
async def list_escalation_rules(
    trial_id: Optional[str] = None,
    user: CurrentUser = Depends(require_role("admin", "coordinator")),
):
    query = supabase.table("escalation_rules").select("*")
    if trial_id:
        query = query.eq("trial_id", trial_id)
    result = query.execute()
    return {"data": result.data or []}


@router.post("/escalation-rules")
async def create_escalation_rule(
    rule: dict,
    user: CurrentUser = Depends(require_role("admin", "coordinator")),
):
    result = supabase.table("escalation_rules").insert(rule).execute()
    saved = result.data[0] if result.data else None
    if saved:
        log_audit(
            table_name="escalation_rules", record_id=saved["id"],
            action="CREATE", user_id=user.id, new_values=rule,
        )
    return {"success": bool(saved), "data": saved}


@router.post("/escalation-rules/{rule_id}/deactivate")
async def deactivate_escalation_rule(
    rule_id: str,
    user: CurrentUser = Depends(require_role("admin", "coordinator")),
):
    result = supabase.table("escalation_rules").update(
        {"active": False}
    ).eq("id", rule_id).execute()
    if result.data:
        log_audit(
            table_name="escalation_rules", record_id=rule_id,
            action="DEACTIVATE", user_id=user.id,
        )
    return {"success": bool(result.data)}


# ── UNREGISTERED SENDERS (Fix #1) ───────────────────────────────────

@router.get("/unregistered-reports")
async def list_unregistered_reports(
    reviewed: bool = None,
    user: CurrentUser = Depends(require_role("admin", "coordinator")),
):
    return {"data": get_unregistered_reports(reviewed)}


@router.post("/unregistered-reports/{report_id}/resolve")
async def resolve_unregistered_report(
    report_id: str,
    notes: str = None,
    user: CurrentUser = Depends(require_role("admin", "coordinator")),
):
    result = mark_unregistered_report_reviewed(report_id, user.id, notes)
    if result:
        log_audit(
            table_name="unregistered_reports", record_id=report_id,
            action="RESOLVE", user_id=user.id, new_values={"notes": notes},
        )
    return {"success": bool(result), "data": result}