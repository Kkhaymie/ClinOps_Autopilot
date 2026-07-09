# backend/actions/notifications.py
# Sends alerts to coordinators, sponsors, and PIs
import os
from dotenv import load_dotenv

load_dotenv()

COORDINATOR_WHATSAPP = os.getenv("COORDINATOR_WHATSAPP_NUMBER", "")
COORDINATOR_EMAIL    = os.getenv("COORDINATOR_EMAIL", "")


async def notify_coordinator_urgent(
    patient: dict,
    classification: dict,
    trial: dict
):
    """
    Immediately alert coordinator for Severe and Life-threatening events.
    Called BEFORE coordinator approval so they can act fast.
    """
    severity     = classification.get("severity", "Unknown")
    patient_code = patient.get("patient_code", "Unknown")
    symptoms     = ", ".join(classification.get("symptoms", []))
    trial_name   = trial.get("trial_name", "Unknown")

    message = (
        f"⚠️ URGENT AE ALERT — {severity.upper()}\n"
        f"Patient: {patient_code}\n"
        f"Trial: {trial_name}\n"
        f"Symptoms: {symptoms}\n"
        f"Action required: Log in to ClinOps dashboard immediately."
    )

    # Send WhatsApp to coordinator
    if COORDINATOR_WHATSAPP:
        from channels.whatsapp_cloud import send_whatsapp_message
        wa = COORDINATOR_WHATSAPP.lstrip("+")
        await send_whatsapp_message(wa, message)

    # Send email to PI for life-threatening events
    if severity == "Life-threatening":
        pi_email = trial.get("pi_email")
        if pi_email:
            await _send_email(
                to=pi_email,
                subject=f"[ClinOps] LIFE-THREATENING AE — {patient_code}",
                body=message
            )
        # Also WhatsApp the PI
        pi_phone = trial.get("pi_phone", "")
        if pi_phone:
            from channels.whatsapp_cloud import send_whatsapp_message
            await send_whatsapp_message(pi_phone.lstrip("+"), message)


async def notify_after_approval(
    ae: dict,
    patient: dict,
    trial: dict
):
    """
    Called after coordinator approves an AE.
    Sends confirmations to patient, sponsor, and PI.
    """
    severity     = ae.get("severity", "Mild")
    patient_code = patient.get("patient_code", "Unknown")
    symptoms     = ", ".join(ae.get("symptoms", []))
    channel      = patient.get("preferred_channel", "whatsapp")

    # 1. Patient confirmation reply
    reply = ae.get("draft_patient_reply") or (
        "Your adverse event report has been reviewed by our medical team. "
        "We will follow up with you within 24 hours."
    )
    from actions.patient_reply import send_reply_on_original_channel
    await send_reply_on_original_channel(patient, reply)

    # 2. Sponsor email for Severe/SAE events
    sponsor_email = trial.get("sponsor_email")
    if sponsor_email and severity in ["Severe", "Life-threatening"]:
        await _send_email(
            to=sponsor_email,
            subject=(
                f"[ClinOps AE Report] {severity} — "
                f"Patient {patient_code} — {trial.get('trial_name', '')}"
            ),
            body=(
                f"A {severity} adverse event has been approved for reporting.\n\n"
                f"Patient: {patient_code}\n"
                f"Trial: {trial.get('trial_name')}\n"
                f"Drug: {trial.get('drug_name')}\n"
                f"Batch: {ae.get('drug_batch', 'Unknown')}\n"
                f"Symptoms: {symptoms}\n"
                f"Language of report: {ae.get('language_detected')}\n"
                f"Traditional medicine flag: {ae.get('trad_medicine_flag')}\n"
                f"Regulatory body: {trial.get('regulatory_body')}\n\n"
                f"Please log in to ClinOps Autopilot to view full report."
            )
        )

    # 3. Coordinator confirmation WhatsApp
    if COORDINATOR_WHATSAPP:
        from channels.whatsapp_cloud import send_whatsapp_message
        wa_no = COORDINATOR_WHATSAPP.lstrip("+")
        label = "⚠️ APPROVED — URGENT" if severity in [
            "Severe", "Life-threatening"
        ] else "✅ APPROVED"
        await send_whatsapp_message(
            wa_no,
            f"{label} AE Report\n"
            f"Patient: {patient_code} | Severity: {severity}\n"
            f"Channel: {ae.get('channel')} | "
            f"Language: {ae.get('language_detected')}"
        )


async def notify_safety_signal(signal: dict, trial: dict):
    """
    Broadcast safety signal alert to coordinator, sponsor, and PI.
    Called automatically when pattern detector fires.
    """
    count    = signal.get("affected_patient_count", 0)
    symptoms = ", ".join(signal.get("common_symptoms", []))
    batch    = signal.get("drug_batch") or "Multiple batches"

    message = (
        f"🚨 SAFETY SIGNAL DETECTED\n"
        f"{count} patients report similar symptoms within 72 hours.\n"
        f"Common symptoms: {symptoms}\n"
        f"Drug batch: {batch}\n"
        f"Trial: {trial.get('trial_name', 'Unknown')}\n"
        f"Immediate batch review recommended. "
        f"Check ClinOps Safety Signals dashboard."
    )

    # WhatsApp to coordinator
    if COORDINATOR_WHATSAPP:
        from channels.whatsapp_cloud import send_whatsapp_message
        await send_whatsapp_message(
            COORDINATOR_WHATSAPP.lstrip("+"), message
        )

    # Email to sponsor
    sponsor_email = trial.get("sponsor_email")
    if sponsor_email:
        await _send_email(
            to=sponsor_email,
            subject=(
                f"[ClinOps URGENT] Safety Signal — "
                f"{count} patients — {trial.get('trial_name')}"
            ),
            body=message
        )

    # WhatsApp to PI
    pi_phone = trial.get("pi_phone", "")
    if pi_phone:
        from channels.whatsapp_cloud import send_whatsapp_message
        await send_whatsapp_message(pi_phone.lstrip("+"), message)


async def _send_email(to: str, subject: str, body: str):
    """Send email via Gmail SMTP."""
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

        msg            = MIMEMultipart()
        msg["From"]    = smtp_user
        msg["To"]      = to
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)

        print(f"Email sent to {to}: {subject}")
    except Exception as e:
        print(f"_send_email error to {to}: {e}")
