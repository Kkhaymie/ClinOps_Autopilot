# backend/database/queries.py
"""
Data access layer for the adverse-event reporting system.

Grouped by domain:
  - Patient / proxy reporter lookup
  - Adverse event CRUD + approval workflow
  - Message fragment assembly (multi-part inbound messages)
  - Safety signal detection
  - Dashboard stats
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from database.client import supabase

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Patient / proxy reporter lookup
# ---------------------------------------------------------------------------

def _get_patient_by_field(field: str, value: str) -> Optional[dict]:
    """Shared helper: fetch a single patient (with trial info) by a unique field."""
    try:
        result = (
            supabase.table("patients")
            .select("*, trials(*)")
            .eq(field, value)
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception:
        logger.exception("_get_patient_by_field failed (field=%s)", field)
        return None


def get_patient_by_whatsapp(phone: str) -> Optional[dict]:
    return _get_patient_by_field("whatsapp_number", phone)


def get_patient_by_sms(phone: str) -> Optional[dict]:
    return _get_patient_by_field("sms_number", phone)


def get_patient_by_telegram(telegram_id: str) -> Optional[dict]:
    return _get_patient_by_field("telegram_id", str(telegram_id))


def get_patient_by_email(email: str) -> Optional[dict]:
    return _get_patient_by_field("email", email.lower())


def get_patient_by_code(patient_code: str) -> Optional[dict]:
    return _get_patient_by_field("patient_code", patient_code)


def check_proxy_reporter(phone: str) -> Optional[dict]:
    """Look up a proxy reporter (e.g. caregiver) by phone, with nested patient/trial info."""
    try:
        result = (
            supabase.table("proxy_reporters")
            .select("*, patients(*, trials(*))")
            .or_(f"whatsapp_number.eq.{phone},sms_number.eq.{phone}")
            .limit(1)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception:
        logger.exception("check_proxy_reporter failed (phone=%s)", phone)
        return None


# ---------------------------------------------------------------------------
# Adverse events: CRUD + approval workflow
# ---------------------------------------------------------------------------

def save_adverse_event(ae_data: dict) -> Optional[dict]:
    try:
        result = supabase.table("adverse_events").insert(ae_data).execute()
        saved = result.data[0] if result.data else None
        if saved and saved.get("patient_id"):
            try:
                from intelligence.dropout_risk import recompute_dropout_risk
                recompute_dropout_risk(saved["patient_id"])
            except Exception:
                logger.exception("dropout risk recompute failed after save_adverse_event")
        return saved
    except Exception:
        logger.exception("save_adverse_event failed")
        return None


def get_pending_approvals() -> List[dict]:
    try:
        result = (
            supabase.table("adverse_events")
            .select(
                """
                *,
                patients(full_name, patient_code, language,
                         preferred_channel, country,
                         whatsapp_number, sms_number,
                         telegram_id, email),
                trials(trial_name, drug_name, regulatory_body,
                       sponsor_email, pi_email)
                """
            )
            .eq("status", "PENDING_APPROVAL")
            .order("created_at", desc=False)
            .execute()
        )
        return result.data or []
    except Exception:
        logger.exception("get_pending_approvals failed")
        return []


def update_ae_status(
    ae_id: str,
    status: str,
    approved_by: Optional[str] = None,
    notes: Optional[str] = None,
) -> Optional[dict]:
    try:
        payload = {"status": status}
        if approved_by:
            payload["approved_by"] = approved_by
            payload["approved_at"] = datetime.now().isoformat()
        if notes:
            payload["coordinator_notes"] = notes

        result = (
            supabase.table("adverse_events")
            .update(payload)
            .eq("id", ae_id)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception:
        logger.exception("update_ae_status failed (ae_id=%s)", ae_id)
        return None


def get_ae_report(ae_id: str) -> Optional[dict]:
    try:
        result = (
            supabase.table("adverse_events")
            .select("*, patients(*, trials(*))")
            .eq("id", ae_id)
            .single()
            .execute()
        )
        return result.data
    except Exception:
        logger.exception("get_ae_report failed (ae_id=%s)", ae_id)
        return None


def get_open_deadlines() -> List[dict]:
    try:
        result = (
            supabase.table("adverse_events")
            .select(
                """
                *,
                patients(full_name, patient_code,
                         preferred_channel, whatsapp_number,
                         sms_number, email),
                trials(regulatory_body, pi_email, sponsor_email)
                """
            )
            .in_("status", ["PENDING_APPROVAL", "APPROVED"])
            .eq("submitted_to_regulator", False)
            .not_.is_("regulatory_deadline", "null")
            .execute()
        )
        return result.data or []
    except Exception:
        logger.exception("get_open_deadlines failed")
        return []


def get_recent_aes_for_trial(trial_id: str, hours: int = 72) -> List[dict]:
    try:
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        result = (
            supabase.table("adverse_events")
            .select("id, patient_id, symptoms, drug_batch, created_at")
            .eq("trial_id", trial_id)
            .gte("created_at", cutoff)
            .execute()
        )
        return result.data or []
    except Exception:
        logger.exception("get_recent_aes_for_trial failed (trial_id=%s)", trial_id)
        return []


# ---------------------------------------------------------------------------
# Communications log
# ---------------------------------------------------------------------------

def log_communication(data: dict) -> None:
    try:
        supabase.table("communications_log").insert(data).execute()
    except Exception:
        logger.exception("log_communication failed")


# ---------------------------------------------------------------------------
# Message fragments (multi-part inbound message assembly)
# ---------------------------------------------------------------------------

def save_fragment(data: dict) -> Optional[dict]:
    try:
        result = supabase.table("message_fragments").insert(data).execute()
        return result.data[0] if result.data else None
    except Exception:
        logger.exception("save_fragment failed")
        return None


def get_recent_fragments(patient_identifier: str, minutes: int = 15) -> List[dict]:
    try:
        cutoff = (datetime.now() - timedelta(minutes=minutes)).isoformat()
        result = (
            supabase.table("message_fragments")
            .select("*")
            .eq("patient_identifier", patient_identifier)
            .eq("assembled", False)
            .gte("received_at", cutoff)
            .order("received_at")
            .execute()
        )
        return result.data or []
    except Exception:
        logger.exception(
            "get_recent_fragments failed (patient_identifier=%s)", patient_identifier
        )
        return []


def mark_fragments_assembled(ids: List[str]) -> None:
    for fragment_id in ids:
        try:
            supabase.table("message_fragments") \
                .update({"assembled": True}) \
                .eq("id", fragment_id) \
                .execute()
        except Exception:
            logger.exception(
                "mark_fragments_assembled failed (fragment_id=%s)", fragment_id
            )


# ---------------------------------------------------------------------------
# Unregistered senders (Fix #1)
# ---------------------------------------------------------------------------

def get_unregistered_reports(reviewed: Optional[bool] = None) -> List[dict]:
    try:
        query = supabase.table("unregistered_reports").select("*")
        if reviewed is not None:
            query = query.eq("reviewed", reviewed)
        result = query.order("created_at", desc=True).execute()
        return result.data or []
    except Exception:
        logger.exception("get_unregistered_reports failed")
        return []


def mark_unregistered_report_reviewed(
    report_id: str, reviewed_by: str, notes: Optional[str] = None
) -> Optional[dict]:
    try:
        result = (
            supabase.table("unregistered_reports")
            .update({
                "reviewed": True,
                "reviewed_by": reviewed_by,
                "reviewed_at": datetime.now().isoformat(),
                "resolution_notes": notes,
            })
            .eq("id", report_id)
            .execute()
        )
        return result.data[0] if result.data else None
    except Exception:
        logger.exception("mark_unregistered_report_reviewed failed (id=%s)", report_id)
        return None


# ---------------------------------------------------------------------------
# Low-priority batching digest (Scenario 2)
# ---------------------------------------------------------------------------

def get_low_priority_pending_summary() -> List[dict]:
    """Groups still-open Mild/Routine reports by trial for the daily
    batching digest (Scenario 2). One row per trial, with a count and the
    patient codes involved, capped preview handled by the caller.
    Self-limiting by design: once a report is approved/rejected it drops
    out of this query automatically, so there's no separate 'already
    digested' state to track."""
    try:
        result = (
            supabase.table("adverse_events")
            .select("id, trial_id, patients(patient_code), trials(trial_name)")
            .eq("status", "PENDING_APPROVAL")
            .eq("severity", "Mild")
            .eq("urgency", "Routine")
            .execute()
        )
        rows = result.data or []
    except Exception:
        logger.exception("get_low_priority_pending_summary failed")
        return []

    grouped: dict = {}
    for r in rows:
        tid = r.get("trial_id")
        if tid not in grouped:
            grouped[tid] = {
                "trial_id": tid,
                "trial_name": (r.get("trials") or {}).get("trial_name", "Unknown trial"),
                "count": 0,
                "patient_codes": [],
            }
        grouped[tid]["count"] += 1
        code = (r.get("patients") or {}).get("patient_code")
        if code:
            grouped[tid]["patient_codes"].append(code)

    return list(grouped.values())


# ---------------------------------------------------------------------------
# Internal response-time SLA (Fix #2), separate from the regulatory deadline
# ---------------------------------------------------------------------------

def get_pending_urgent_aes() -> List[dict]:
    """Severe/Life-threatening reports still awaiting a coordinator decision,
    regardless of category or whether a regulatory deadline was set."""
    try:
        result = (
            supabase.table("adverse_events")
            .select(
                """
                *,
                patients(patient_code, full_name),
                trials(trial_name, regulatory_body)
                """
            )
            .eq("status", "PENDING_APPROVAL")
            .in_("severity", ["Severe", "Life-threatening"])
            .execute()
        )
        return result.data or []
    except Exception:
        logger.exception("get_pending_urgent_aes failed")
        return []




def save_safety_signal(data: dict) -> Optional[dict]:
    try:
        result = supabase.table("safety_signals").insert(data).execute()
        return result.data[0] if result.data else None
    except Exception:
        logger.exception("save_safety_signal failed")
        return None


def get_open_safety_signals() -> List[dict]:
    try:
        result = (
            supabase.table("safety_signals")
            .select("*, trials(trial_name, drug_name, regulatory_body)")
            .eq("status", "OPEN")
            .order("detection_time", desc=True)
            .execute()
        )
        return result.data or []
    except Exception:
        logger.exception("get_open_safety_signals failed")
        return []


def get_all_ae_records(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    channel: Optional[str] = None,
) -> List[dict]:
    """Trial master file — every AE record, optionally filtered."""
    try:
        query = (
            supabase.table("adverse_events")
            .select(
                """
                *,
                patients(full_name, patient_code, country),
                trials(trial_name, drug_name, regulatory_body)
                """
            )
        )
        if status:
            query = query.eq("status", status)
        if severity:
            query = query.eq("severity", severity)
        if channel:
            query = query.eq("channel", channel)

        result = query.order("created_at", desc=True).execute()
        return result.data or []
    except Exception:
        logger.exception(
            "get_all_ae_records failed (status=%s, severity=%s, channel=%s)",
            status, severity, channel,
        )
        return []


def get_analytics_events(days: int = 30) -> List[dict]:
    """AE records from the last N days, for the analytics dashboard charts."""
    try:
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        result = (
            supabase.table("adverse_events")
            .select("id, severity, category, channel, status, language_detected, "
                    "trad_medicine_flag, created_at")
            .gte("created_at", cutoff)
            .order("created_at", desc=False)
            .execute()
        )
        return result.data or []
    except Exception:
        logger.exception("get_analytics_events failed (days=%s)", days)
        return []


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------

def get_dashboard_stats() -> dict:
    """Get stats for the analytics dashboard."""
    try:
        total = supabase.table("adverse_events") \
            .select("id", count="exact").execute()

        pending = supabase.table("adverse_events") \
            .select("id", count="exact") \
            .eq("status", "PENDING_APPROVAL").execute()

        severe = supabase.table("adverse_events") \
            .select("id", count="exact") \
            .in_("severity", ["Severe", "Life-threatening"]).execute()

        signals = supabase.table("safety_signals") \
            .select("id", count="exact") \
            .eq("status", "OPEN").execute()

        return {
            "total_aes": total.count or 0,
            "pending_approvals": pending.count or 0,
            "severe_events": severe.count or 0,
            "open_signals": signals.count or 0,
        }
    except Exception:
        logger.exception("get_dashboard_stats failed")
        return {}