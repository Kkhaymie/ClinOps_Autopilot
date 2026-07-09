# backend/actions/compliance_clock.py
import os
from apscheduler.schedulers.background import BackgroundScheduler
from database.queries import get_open_deadlines
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

scheduler = BackgroundScheduler()


def start_scheduler():
    """Start the compliance clock. Runs every hour automatically."""
    scheduler.add_job(
        _check_deadlines,
        "interval",
        hours=1,
        id="compliance_clock",
        replace_existing=True,
        next_run_time=datetime.now()  # Run immediately on startup too
    )
    scheduler.start()
    print("Compliance clock started — checking deadlines every hour")


def _check_deadlines():
    """
    Check every open AE report against its regulatory deadline.
    Prints alerts and (in production) sends notifications.
    """
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
            deadline = datetime.fromisoformat(
                dl.replace("Z", "+00:00")
            )
            now  = datetime.now().astimezone()
            hrs  = (deadline - now).total_seconds() / 3600

            patient = ae.get("patients") or {}
            trial   = ae.get("trials") or {}
            code    = patient.get("patient_code", "UNKNOWN")
            body    = trial.get("regulatory_body", "NAFDAC")
            sev     = ae.get("severity", "Unknown")

            if hrs <= 0:
                print(
                    f"CRITICAL — MISSED DEADLINE: {code} | {body} | "
                    f"{sev} | Overdue by {abs(hrs):.0f} hours"
                )
            elif hrs <= 24:
                print(
                    f"URGENT — {hrs:.0f}h remaining: {code} | {body} | {sev}"
                )
            elif hrs <= 48:
                print(
                    f"WARNING — {hrs:.0f}h remaining: {code} | {body} | {sev}"
                )
            # else: no action needed yet

        except Exception as e:
            print(f"Clock error for AE {ae.get('id')}: {e}")
