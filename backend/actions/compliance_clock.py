# backend/actions/compliance_clock.py
"""
Hourly job that checks every open AE against its regulatory deadline and
escalates through the same rules engine as everything else, instead of
just printing to console. Dedupes by tracking the highest alert level
already sent per AE, so a still-open deadline doesn't re-fire the same
alert every hour.
"""

from datetime import datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from actions.escalation_engine import run_escalation
from database.client import supabase
from database.queries import get_open_deadlines, get_pending_urgent_aes, get_low_priority_pending_summary

scheduler = AsyncIOScheduler()

_ALERT_LEVELS = ("WARNING", "URGENT", "MISSED")  # ascending severity

# Fix #2: internal response-time SLA, separate from the regulatory
# deadline. A Life-threatening report shouldn't sit unactioned for the
# multi-day regulatory window before anyone hears about it, staff
# should hear about it within the hour.
_SLA_LEVELS = ("WARNING", "URGENT", "BREACHED")  # ascending severity
_SLA_THRESHOLDS_MINUTES = {"WARNING": 30, "URGENT": 60, "BREACHED": 120}


def start_scheduler():
    """Start all three clocks: the hourly regulatory-deadline check, a
    15-minute internal response-time SLA check for Severe/Life-threatening
    reports (Fix #2), and a once-daily low-priority digest for Mild/
    Routine reports (Scenario 2)."""
    scheduler.add_job(
        _check_deadlines,
        "interval",
        hours=1,
        id="compliance_clock",
        replace_existing=True,
        next_run_time=datetime.now(),
    )
    scheduler.add_job(
        _check_response_sla,
        "interval",
        minutes=15,
        id="response_sla_clock",
        replace_existing=True,
        next_run_time=datetime.now(),
    )
    scheduler.add_job(
        _send_low_priority_digest,
        "cron",
        hour=8,
        minute=0,
        id="low_priority_digest",
        replace_existing=True,
        # Deliberately NOT next_run_time=datetime.now() like the other two.
        # Those check time-sensitive thresholds, catching up immediately on
        # restart matters. A digest is about a fixed daily cadence; firing
        # it on every server restart during development/deploys would spam
        # coordinators instead of helping them.
    )
    scheduler.start()
    print("Compliance clock started — deadlines hourly, response SLA every 15 minutes, digest daily at 08:00")


def _level_for(hours_remaining: float) -> str | None:
    if hours_remaining <= 0:
        return "MISSED"
    if hours_remaining <= 24:
        return "URGENT"
    if hours_remaining <= 48:
        return "WARNING"
    return None


async def _check_deadlines():
    print(f"Compliance clock running: {datetime.now().strftime('%H:%M %d/%m/%Y')}")

    aes = get_open_deadlines()
    if not aes:
        print("Compliance clock: no open deadlines")
        return

    for ae in aes:
        dl = ae.get("regulatory_deadline")
        if not dl:
            continue
        try:
            deadline = datetime.fromisoformat(dl.replace("Z", "+00:00"))
            now = datetime.now().astimezone()
            hrs = (deadline - now).total_seconds() / 3600

            level = _level_for(hrs)
            if not level:
                continue  # not within 48h of the deadline yet

            already_sent = ae.get("last_deadline_alert_level")
            already_index = _ALERT_LEVELS.index(already_sent) if already_sent in _ALERT_LEVELS else -1
            if _ALERT_LEVELS.index(level) <= already_index:
                continue  # already alerted at this level or worse, don't repeat hourly

            patient = ae.get("patients") or {}
            trial = ae.get("trials") or {}
            code = patient.get("patient_code", "UNKNOWN")
            body = trial.get("regulatory_body", "NAFDAC")
            sev = ae.get("severity", "Unknown")

            print(
                f"{level} — {abs(hrs):.0f}h "
                f"{'overdue' if level == 'MISSED' else 'remaining'}: {code} | {body} | {sev}"
            )

            message = (
                f"⏰ REGULATORY DEADLINE {level}\n"
                f"Patient: {code} | Severity: {sev}\n"
                f"Regulatory body: {body}\n"
                f"{'Overdue by' if level == 'MISSED' else 'Time remaining'}: {abs(hrs):.0f} hours\n"
                f"Trial: {trial.get('trial_name', 'Unknown')}"
            )

            await run_escalation(
                trial_id=ae.get("trial_id"),
                severity="ANY",
                category=f"DEADLINE_{level}",
                timing="immediate",
                message=message,
                subject=f"[ClinOps] Deadline {level} — {code}",
            )

            supabase.table("adverse_events").update(
                {"last_deadline_alert_level": level}
            ).eq("id", ae["id"]).execute()

        except Exception as e:
            print(f"Clock error for AE {ae.get('id')}: {e}")


async def _check_response_sla():
    """Fix #2: check every Severe/Life-threatening report still awaiting a
    coordinator decision against internal response-time thresholds (30 /
    60 / 120 minutes), independent of the regulatory deadline."""
    aes = get_pending_urgent_aes()
    if not aes:
        return

    for ae in aes:
        try:
            created = datetime.fromisoformat(ae["created_at"].replace("Z", "+00:00"))
            now = datetime.now().astimezone()
            minutes_elapsed = (now - created).total_seconds() / 60

            level = None
            for lvl in reversed(_SLA_LEVELS):  # BREACHED checked before URGENT before WARNING
                if minutes_elapsed >= _SLA_THRESHOLDS_MINUTES[lvl]:
                    level = lvl
                    break
            if not level:
                continue

            already_sent = ae.get("last_sla_alert_level")
            already_index = _SLA_LEVELS.index(already_sent) if already_sent in _SLA_LEVELS else -1
            if _SLA_LEVELS.index(level) <= already_index:
                continue  # already alerted at this level or worse

            patient = ae.get("patients") or {}
            trial = ae.get("trials") or {}
            code = patient.get("patient_code", "UNKNOWN")
            sev = ae.get("severity", "Unknown")

            print(
                f"RESPONSE SLA {level} — {minutes_elapsed:.0f}min unactioned: "
                f"{code} | {sev}"
            )

            message = (
                f"⏱ RESPONSE TIME {level}\n"
                f"Patient: {code} | Severity: {sev}\n"
                f"Still awaiting a decision after {minutes_elapsed:.0f} minutes.\n"
                f"Trial: {trial.get('trial_name', 'Unknown')}\n"
                f"This is an internal response-time alert, separate from the "
                f"regulatory reporting deadline."
            )

            await run_escalation(
                trial_id=ae.get("trial_id"),
                severity="ANY",
                category=f"RESPONSE_SLA_{level}",
                timing="immediate",
                message=message,
                subject=f"[ClinOps] Response SLA {level} — {code}",
            )

            supabase.table("adverse_events").update(
                {"last_sla_alert_level": level}
            ).eq("id", ae["id"]).execute()

        except Exception as e:
            print(f"Response SLA clock error for AE {ae.get('id')}: {e}")


async def _send_low_priority_digest():
    """Scenario 2: batches Mild/Routine reports into one daily digest per
    trial instead of the coordinator having to notice and review each one
    individually in real time. Severe/Life-threatening reports are
    completely untouched by this, they still go through the immediate
    escalation paths exactly as before, this only covers the bucket that
    currently gets zero notification of any kind."""
    summary = get_low_priority_pending_summary()
    if not summary:
        return

    for row in summary:
        if row["count"] == 0:
            continue

        codes_preview = ", ".join(row["patient_codes"][:10])
        if row["count"] > 10:
            codes_preview += f", +{row['count'] - 10} more"

        message = (
            f"📋 DAILY LOW-PRIORITY DIGEST\n"
            f"Trial: {row['trial_name']}\n"
            f"{row['count']} Mild/Routine report(s) awaiting review: {codes_preview}\n"
            f"None require same-day action. Batch review at your convenience "
            f"in Pending Approvals."
        )

        await run_escalation(
            trial_id=row["trial_id"],
            severity="Mild",
            category="DAILY_DIGEST",
            timing="immediate",
            message=message,
            subject=f"[ClinOps] Daily digest — {row['count']} routine reports — {row['trial_name']}",
        )