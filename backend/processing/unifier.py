# backend/processing/unifier.py
"""
Normalizes output from the type-specific processors (audio, image, video)
into one consistent shape before it reaches the AI classifier.

Every channel handler used to branch on message_type itself and call the
right processor inline, duplicating the same logic four times with small
inconsistencies (e.g. WhatsApp's image handling merged the caption in a
slightly different order than Telegram's). This is now the one place that
happens; channel handlers should call unify_message() instead of importing
the processors directly.
"""

from typing import List, Optional, TypedDict


class UnifiedContent(TypedDict):
    content: str                        # text to feed the classifier as clinical_summary
    transcript: Optional[str]           # raw speech transcript, if audio/video had any
    visible_symptoms: List[str]         # from image/video vision analysis
    trad_medicine_hints: List[str]      # traditional medicine names spotted in images/video
    severity_indication: Optional[str]  # "Mild|Moderate|Severe|None", from image analysis only
    success: bool                       # False if the underlying processor failed


def _empty(content: str, success: bool = True) -> UnifiedContent:
    return {
        "content": content,
        "transcript": None,
        "visible_symptoms": [],
        "trad_medicine_hints": [],
        "severity_indication": None,
        "success": success,
    }


async def unify_message(
    message_type: str,
    body: str = "",
    media_url: Optional[str] = None,
    auth_header: Optional[str] = None,
) -> UnifiedContent:
    """
    Given a channel-agnostic (message_type, body/caption, media_url), run
    whichever processor applies and return one consistent shape.

    auth_header: only needed for WhatsApp Cloud API media URLs, which
    require a bearer token to download. Telegram file paths and Cloudinary
    URLs don't need it, pass None.
    """
    if message_type == "text" or not media_url:
        return _empty(body)

    if message_type == "audio":
        from processing.audio_processor import transcribe_voice_note
        tr = await transcribe_voice_note(media_url, auth_header)
        transcript = tr.get("transcript") or ""
        result = _empty(transcript or body, success=tr.get("success", False))
        result["transcript"] = transcript or None
        return result

    if message_type == "image":
        from processing.image_processor import analyse_symptom_image
        an = await analyse_symptom_image(media_url, auth_header)
        description = an.get("medical_description", "")
        content = (description + " " + body).strip() or body
        result = _empty(content, success=an.get("success", False))
        result["visible_symptoms"] = an.get("visible_symptoms", [])
        result["trad_medicine_hints"] = an.get("traditional_medicines_detected", [])
        result["severity_indication"] = an.get("severity_indication")
        return result

    if message_type == "video":
        from processing.video_processor import process_video_message
        vr = await process_video_message(media_url, auth_header)
        symptoms: List[str] = []
        for frame in vr.get("visual_analysis", []) or []:
            symptoms += frame.get("analysis", {}).get("symptoms_visible", [])
        result = _empty(vr.get("merged_clinical_summary", body), success=vr.get("success", False))
        result["transcript"] = vr.get("audio_transcript")
        result["visible_symptoms"] = list(set(symptoms))
        return result

    # document, or any future type without a dedicated processor: fall
    # back to whatever text/caption came with it rather than failing
    return _empty(body)