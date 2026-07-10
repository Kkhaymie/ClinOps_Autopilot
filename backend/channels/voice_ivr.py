# backend/channels/voice_ivr.py
"""
Voice/IVR intake via Africa's Talking Voice API (Scenario 15).

DISCRETIONARY DESIGN DECISIONS — I was asked to use my own judgment here
rather than block on a vendor/region decision. These are the calls made,
and why, so they're a decision record, not silent assumptions:

1. Provider: Africa's Talking Voice, not Twilio, Exotel, or anyone else.
   This project already has a live Africa's Talking account and API key
   for SMS; Voice reuses that same vendor relationship and credential
   pattern instead of onboarding a new one. I verified the current API
   shape before writing this: the webhook receives a POST with
   callerNumber / callSessionState / isActive, and you respond with XML
   (<Response><Say>/<GetDigits>/<Record>...</Response>). Same
   request-response shape as the SMS webhook already in this codebase.

2. Scope: Nigeria only. Scenario 15 originally named India specifically,
   but Africa's Talking's confirmed strength is African telecom, I have
   no verified evidence of its call quality or coverage in India. Rather
   than guess a provider for a market this build isn't currently
   prioritizing, India/Singapore/Japan IVR is left unbuilt. That needs
   its own provider evaluation when it's actually the priority, guessing
   here risks a wrong vendor choice with real account/cost consequences.

3. Prompts are English only. Africa's Talking's built-in text-to-speech
   language coverage for Nigerian Pidgin, Yoruba, Igbo, or Hausa isn't
   something I could verify, so I'm not shipping prompts that might be
   mispronounced or unsupported. The <Say> calls below can be swapped
   for <Play url="..."> pointing at a Cloudinary-hosted recording once
   real audio exists in those languages, that's a content task for a
   human speaker, not something to fabricate.

4. No live call transfer. Pressing 2 gives spoken instructions to
   contact the coordinator directly; it does not bridge the call to a
   real coordinator's phone. An actual on-call transfer system is a
   materially bigger feature, this codebase has no concept of
   coordinator call availability to transfer into yet.

5. Reuses the existing audio pipeline entirely, this is the actual
   payoff of building IVR last. Once a symptom recording is captured, it
   goes through transcribe_voice_note() (Groq Whisper), the exact
   function that already transcribes WhatsApp/Telegram voice notes, then
   the same process_nigerian_text -> classify_adverse_event ->
   save_adverse_event pipeline every other channel uses. IVR isn't a
   parallel system, it's one more way audio gets in.

OPERATIONAL REQUIREMENT NOT YET IN env.example: PUBLIC_BASE_URL, the
publicly reachable HTTPS base URL for this deployment (e.g.
https://your-app.up.railway.app). Africa's Talking needs full URLs for
the GetDigits/Record callbackUrl attributes, not relative paths. Set
this before registering the voice callback in the Africa's Talking
dashboard.

UNVERIFIED ASSUMPTION, worth confirming once you're testing against a
real account: whether Africa's Talking's recordingUrl requires an auth
header to fetch. transcribe_voice_note() supports passing one if it
turns out to be needed, none is passed below because I found no
confirmation either way in what I could verify.
"""

import os

from fastapi import APIRouter, BackgroundTasks, Request, Response

router = APIRouter()

_GREETING = (
    "Welcome to Clin Ops Autopilot. "
    "Press 1 to report a side effect. "
    "Press 2 to reach your trial coordinator."
)
_RECORD_PROMPT = (
    "Please describe what you are experiencing after the beep. "
    "Press the hash key when you are done."
)
_CLOSING = "Thank you. Your report has been received and a coordinator will follow up with you. Goodbye."
_COORDINATOR_INFO = "Please contact your trial site coordinator directly using the number they gave you at enrollment. Goodbye."
_NOT_FOUND = "We could not find your trial registration on this number. Please contact your site coordinator directly. Goodbye."
_NO_INPUT = "Sorry, I did not get that."


def _callback_base() -> str:
    return os.getenv("PUBLIC_BASE_URL", "https://your-domain.example.com")


def _xml_response(inner: str) -> Response:
    body = f'<?xml version="1.0" encoding="UTF-8"?><Response>{inner}</Response>'
    return Response(content=body, media_type="text/xml")


@router.post("/voice-at")
async def handle_call(request: Request):
    """
    Africa's Talking posts here when a call starts (callSessionState ==
    'new'). isActive == '0' means the call already ended, nothing useful
    to respond with at that point.
    """
    form = await request.form()
    caller_number = str(form.get("callerNumber", ""))
    is_active = str(form.get("isActive", "0"))

    if is_active != "1":
        return _xml_response("")

    from database.queries import get_patient_by_sms
    patient = get_patient_by_sms(caller_number)

    if not patient:
        from actions.unregistered_intake import handle_unregistered_sender
        await handle_unregistered_sender(
            channel="voice",
            raw_identifier=caller_number,
            message_content="",
            message_type="audio",
        )
        return _xml_response(f"<Say>{_NOT_FOUND}</Say>")

    return _xml_response(
        f'<GetDigits timeout="15" finishOnKey="#" '
        f'callbackUrl="{_callback_base()}/webhook/voice-at/menu">'
        f"<Say>{_GREETING}</Say>"
        f"</GetDigits>"
    )


@router.post("/voice-at/menu")
async def handle_menu_choice(request: Request):
    form = await request.form()
    digits = str(form.get("dtmfDigits", ""))

    if digits == "1":
        return _xml_response(
            f"<Say>{_RECORD_PROMPT}</Say>"
            f'<Record finishOnKey="#" maxLength="120" trimSilence="true" '
            f'callbackUrl="{_callback_base()}/webhook/voice-at/recording"/>'
        )
    if digits == "2":
        return _xml_response(f"<Say>{_COORDINATOR_INFO}</Say>")

    return _xml_response(f"<Say>{_NO_INPUT}</Say><Say>{_COORDINATOR_INFO}</Say>")


@router.post("/voice-at/recording")
async def handle_recording(request: Request, background_tasks: BackgroundTasks):
    """
    Fires once the patient finishes their spoken report. recordingUrl is
    an MP3 Africa's Talking hosts. The XML response has to go back
    immediately, transcription and classification can't happen inline,
    so this hands off to BackgroundTasks, same pattern the WhatsApp and
    SMS webhooks already use for exactly this reason.
    """
    form = await request.form()
    caller_number = str(form.get("callerNumber", ""))
    recording_url = str(form.get("recordingUrl", ""))

    if recording_url:
        background_tasks.add_task(_process_voice_report, caller_number, recording_url)

    return _xml_response(f"<Say>{_CLOSING}</Say>")


async def _process_voice_report(caller_number: str, recording_url: str):
    """Same pipeline every other audio-capable channel uses, from here
    down this is not IVR-specific code."""
    from database.queries import get_patient_by_sms, save_adverse_event, log_communication
    from processing.audio_processor import transcribe_voice_note
    from intelligence.nigerian_language import process_nigerian_text
    from intelligence.tcm_herbs import detect_tcm_herbs
    from intelligence.agent_core import classify_adverse_event, calculate_deadline
    from intelligence.deduplication import check_duplicate
    from intelligence.pattern_detector import check_safety_signal

    patient = get_patient_by_sms(caller_number)
    if not patient:
        return  # already logged as unregistered in handle_call

    trial = patient.get("trials") or {}

    tr = await transcribe_voice_note(recording_url)
    transcript = tr.get("transcript", "")

    lp = process_nigerian_text(transcript)
    medicines = lp["traditional_medicines_detected"] + detect_tcm_herbs(transcript)

    cl = classify_adverse_event(
        clinical_summary=lp["processed_text"],
        patient_context={
            "trial_name": trial.get("trial_name"),
            "drug_name": trial.get("drug_name"),
            "last_dose_date": patient.get("last_dose_date"),
            "country": patient.get("country", "Nigeria"),
            "known_allergies": patient.get("known_allergies"),
        },
        traditional_medicines=medicines,
    )

    is_dup, _ = check_duplicate(
        patient_id=patient["id"], symptoms=cl.get("symptoms", []), hours_window=24
    )
    if is_dup:
        return

    dl = calculate_deadline(
        severity=cl.get("severity", "Mild"),
        country=patient.get("country", "Nigeria"),
        category=cl.get("category", "AE"),
    )

    saved = save_adverse_event({
        "patient_id": patient["id"],
        "trial_id": patient.get("trial_id"),
        "channel": "voice",
        "message_type": "audio",
        "original_message": transcript,
        "media_url": recording_url,
        "transcript": transcript,
        "symptoms": cl.get("symptoms", []),
        "severity": cl.get("severity", "Mild"),
        "urgency": cl.get("urgency", "Routine"),
        "category": cl.get("category", "AE"),
        "language_detected": lp["detected_language"],
        "ai_confidence": cl.get("confidence", 0),
        "ai_model_used": cl.get("model_used"),
        "trad_medicine_flag": len(medicines) > 0,
        "trad_medicine_type": ", ".join(m["name"] for m in medicines) if medicines else None,
        "draft_report": cl,
        "draft_patient_reply": cl.get("draft_patient_reply"),
        "status": "PENDING_APPROVAL",
        "regulatory_deadline": dl.get("deadline"),
        "drug_batch": trial.get("drug_batch_current"),
        "emotional_distress_flag": cl.get("emotional_distress_detected", False),
        "emotional_distress_notes": cl.get("emotional_distress_notes") or None,
    })

    if cl.get("severity") in ["Severe", "Life-threatening"]:
        from actions.notifications import notify_coordinator_urgent
        await notify_coordinator_urgent(patient, cl, trial)

    if cl.get("emotional_distress_detected"):
        from actions.notifications import notify_emotional_distress
        await notify_emotional_distress(patient, cl, trial)

    log_communication({
        "patient_id": patient["id"],
        "ae_id": saved["id"] if saved else None,
        "direction": "inbound",
        "channel": "voice",
        "message_content": transcript,
        "language_used": lp["detected_language"],
        "delivery_status": "received",
    })

    if patient.get("trial_id") and saved:
        signal = check_safety_signal(
            trial_id=patient["trial_id"],
            new_symptoms=cl.get("symptoms", []),
            drug_batch=trial.get("drug_batch_current"),
            new_ae_id=saved["id"],
        )
        if signal:
            from actions.notifications import notify_safety_signal
            await notify_safety_signal(signal, trial)