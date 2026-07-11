# backend/actions/notifications.py
"""
Sends alerts to coordinators, sponsors, and PIs.

Public function signatures (notify_coordinator_urgent, notify_after_approval,
notify_safety_signal) are unchanged from before, so none of the four channel
handlers or dashboard.py need to change. Internally, each now just builds a
message and hands it to the escalation engine, which resolves configurable
escalation_rules to real staff and sends. The old hardcoded
"WhatsApp to coordinator, email PI if life-threatening" logic is gone; that
routing now lives in the escalation_rules table (see db/003 for the seed
that reproduces the old defaults).
"""

import os
from dotenv import load_dotenv

from actions.escalation_engine import run_escalation

load_dotenv()


async def notify_coordinator_urgent(patient: dict, classification: dict, trial: dict):
    """
    Alert staff for Severe / Life-threatening events, per whatever
    escalation_rules match this trial (or the default rules if the trial
    has none of its own). Called BEFORE coordinator approval so staff can
    act fast; the channel handlers already gate this to Severe/
    Life-threatening before calling it.
    """
    severity = classification.get("severity", "Unknown")
    patient_code = patient.get("patient_code", "Unknown")
    symptoms = ", ".join(classification.get("symptoms", []))
    trial_name = trial.get("trial_name", "Unknown")
    category = classification.get("category", "AE")

    message = (
        f"⚠️ URGENT AE ALERT — {severity.upper()}\n"
        f"Patient: {patient_code}\n"
        f"Trial: {trial_name}\n"
        f"Symptoms: {symptoms}\n"
        f"Action required: Log in to ClinOps dashboard immediately."
    )

    await run_escalation(
        trial_id=trial.get("id"),
        severity=severity,
        category=category,
        timing="immediate",
        message=message,
        subject=f"[ClinOps] {severity} AE — {patient_code}",
    )


async def notify_emotional_distress(patient: dict, classification: dict, trial: dict):
    """
    Alerts staff when the classifier flags possible emotional distress in
    a report, independent of the AE's clinical severity, a Mild-severity
    report can still carry real distress in how it's written. Fires
    alongside notify_coordinator_urgent when both apply; they're
    different signals and a coordinator seeing both isn't noise.

    Deliberately keeps emotional_distress_notes out of the message text.
    WhatsApp/SMS previews can surface on a lock screen, sensitive content
    doesn't belong there. Staff open the dashboard for the actual detail.
    """
    patient_code = patient.get("patient_code", "Unknown")
    trial_name = trial.get("trial_name", "Unknown")

    message = (
        f"💬 Report flagged for possible emotional distress\n"
        f"Patient: {patient_code}\n"
        f"Trial: {trial_name}\n"
        f"This is a wellbeing flag, separate from clinical severity. "
        f"Please review the full report in the ClinOps dashboard."
    )

    await run_escalation(
        trial_id=trial.get("id"),
        severity="ANY",
        category="EMOTIONAL_DISTRESS",
        timing="immediate",
        message=message,
        subject=f"[ClinOps] Possible emotional distress — {patient_code}",
    )


async def notify_after_approval(ae: dict, patient: dict, trial: dict):
    """
    Called after a coordinator/PI approves an AE. The patient confirmation
    reply always goes out on the patient's own reporting channel, that's
    not an escalation and isn't configurable. Everything else (sponsor,
    PI, coordinator notification of the approval) goes through the
    escalation engine's 'after_approval' timing.
    """
    severity = ae.get("severity", "Mild")
    patient_code = patient.get("patient_code", "Unknown")
    symptoms = ", ".join(ae.get("symptoms", []))
    category = ae.get("category", "AE")

    # 1. Patient confirmation reply
    reply = ae.get("draft_patient_reply") or (
        "Your adverse event report has been reviewed by our medical team. "
        "We will follow up with you within 24 hours."
    )
    from actions.patient_reply import send_reply_on_original_channel
    await send_reply_on_original_channel(patient, reply)

    # 2. Staff escalation per configured rules
    message = (
        f"✅ APPROVED AE Report\n"
        f"Patient: {patient_code} | Severity: {severity}\n"
        f"Trial: {trial.get('trial_name')}\n"
        f"Drug: {trial.get('drug_name')}\n"
        f"Batch: {ae.get('drug_batch', 'Unknown')}\n"
        f"Symptoms: {symptoms}\n"
        f"Language of report: {ae.get('language_detected')}\n"
        f"Traditional medicine flag: {ae.get('trad_medicine_flag')}\n"
        f"Regulatory body: {trial.get('regulatory_body')}\n\n"
        f"Please log in to ClinOps Autopilot to view full report."
    )

    await run_escalation(
        trial_id=trial.get("id") or ae.get("trial_id"),
        severity=severity,
        category=category,
        timing="after_approval",
        message=message,
        subject=(
            f"[ClinOps AE Report] {severity} — "
            f"Patient {patient_code} — {trial.get('trial_name', '')}"
        ),
    )


async def notify_safety_signal(signal: dict, trial: dict):
    """
    Broadcast a safety signal alert. Called automatically when the pattern
    detector fires. Modeled as category='SAFETY_SIGNAL', severity='ANY' so
    it's routed through the same configurable rules table as everything
    else, rather than its own hardcoded path.
    """
    count = signal.get("affected_patient_count", 0)
    symptoms = ", ".join(signal.get("common_symptoms", []))
    batch = signal.get("drug_batch") or "Multiple batches"

    message = (
        f"🚨 SAFETY SIGNAL DETECTED\n"
        f"{count} patients report similar symptoms within 72 hours.\n"
        f"Common symptoms: {symptoms}\n"
        f"Drug batch: {batch}\n"
        f"Trial: {trial.get('trial_name', 'Unknown')}\n"
        f"Immediate batch review recommended. "
        f"Check ClinOps Safety Signals dashboard."
    )

    await run_escalation(
        trial_id=trial.get("id"),
        severity="ANY",
        category="SAFETY_SIGNAL",
        timing="immediate",
        message=message,
        subject=(
            f"[ClinOps URGENT] Safety Signal — "
            f"{count} patients — {trial.get('trial_name')}"
        ),
    )


async def _send_email(to: str, subject: str, body: str):
    """Send email via SMTP. Unchanged from before; the escalation engine
    lazy-imports this for the 'email' channel."""
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart

        smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
        smtp_port = int(os.getenv("SMTP_PORT", "587"))
        smtp_user = os.getenv("SMTP_USER")
        smtp_pass = os.getenv("SMTP_PASS")

        if not smtp_user or not smtp_pass:
            print(f"No SMTP config — skipping email to {to}")
            return

        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        print(f"Email sent to {to}: {subject}")
    except Exception as e:
        print(f"_send_email error to {to}: {e}")