# backend/processing/image_processor.py
import os
import base64
import json
import httpx
from mistralai import Mistral
from dotenv import load_dotenv

load_dotenv()

mistral = Mistral(api_key=os.getenv("MISTRAL_API_KEY", ""))

IMAGE_PROMPT = """You are a clinical trial medical image analyst.
Analyse this patient-submitted image. Return ONLY valid JSON:
{
  "image_type": "symptom_photo|handwriting|medication|food|other",
  "medical_description": "detailed clinical description of what you see",
  "visible_symptoms": ["symptom1", "symptom2"],
  "severity_indication": "Mild|Moderate|Severe|None",
  "handwriting_text": "transcribe any text visible exactly as written",
  "handwriting_language": "English|Arabic|Yoruba|Igbo|Hausa|Hindi|None",
  "traditional_medicines_detected": ["name if packaging visible"],
  "food_risks_detected": ["starfruit|grapefruit|zobo|bitter_leaf|kola_nut"],
  "confidence": 85
}"""

OCR_PROMPT = """You are a handwriting OCR specialist for clinical letters.
CRITICAL RULES:
- Arabic: process RIGHT-TO-LEFT, handle cursive letterforms, preserve diacritics
- Yoruba: PRESERVE ALL TONAL MARKS exactly (è, ó, ẹ, ọ) — they change word meanings
- Hausa Ajami: this is Arabic script writing Hausa — transliterate then translate
- Hindi/Devanagari: handle conjunct consonants correctly
- Do NOT guess words you cannot read — mark them as [unclear]

Return ONLY valid JSON:
{
  "script_detected": "English|Arabic|Yoruba|Igbo|Hausa-Ajami|Hindi|Chinese|Other",
  "transcribed_text": "exact transcription preserving ALL diacritics and marks",
  "translated_to_english": "English translation if not already English",
  "letter_date_mentioned": "date if stated in letter, else null",
  "medical_content": "summary of any symptoms or medical content mentioned",
  "overall_confidence": 85,
  "low_confidence_words": ["word1", "word2"],
  "reading_direction": "LTR|RTL"
}"""


async def _load_image_as_b64(url: str,
                               auth_header: str = None) -> tuple:
    """Download image and convert to base64."""
    headers = {}
    if auth_header:
        headers["Authorization"] = auth_header

    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(url, follow_redirects=True, headers=headers)

    ct    = r.headers.get("content-type", "image/jpeg")
    media = "image/png" if "png" in ct else "image/jpeg"
    b64   = base64.b64encode(r.content).decode()
    return b64, media


def _call_pixtral(b64: str, media: str, prompt: str) -> dict:
    """Send image to Mistral Pixtral vision model."""
    r = mistral.chat.complete(
        model="pixtral-large-latest",
        messages=[{
            "role": "user",
            "content": [
                {"type": "image_url",
                 "image_url": f"data:{media};base64,{b64}"},
                {"type": "text", "text": prompt}
            ]
        }]
    )
    raw = r.choices[0].message.content.strip()
    # Strip markdown fences if present
    if "```" in raw:
        parts = raw.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                raw = part
                break
    return json.loads(raw)


async def analyse_symptom_image(url: str,
                                 auth_header: str = None) -> dict:
    """
    Analyse a photo sent by a patient.
    Detects symptoms, traditional medicines, food risks.
    auth_header: pass when URL is from Meta/WhatsApp Cloud API.
    """
    try:
        b64, media = await _load_image_as_b64(url, auth_header)
        result = _call_pixtral(b64, media, IMAGE_PROMPT)
        result["success"] = True
        return result
    except Exception as e:
        print(f"analyse_symptom_image error: {e}")
        return {
            "success":                      False,
            "error":                        str(e),
            "image_type":                   "unknown",
            "medical_description":          "Image analysis failed",
            "visible_symptoms":             [],
            "severity_indication":          "Unknown",
            "confidence":                   0,
            "traditional_medicines_detected": [],
            "food_risks_detected":          []
        }


async def perform_handwriting_ocr(url: str,
                                   declared_language: str = None,
                                   auth_header: str = None) -> dict:
    """
    Perform OCR on a handwritten letter image.
    Handles English, Arabic RTL, Yoruba tonal, Hausa Ajami,
    Igbo, Hindi Devanagari, Chinese characters.
    """
    try:
        b64, media = await _load_image_as_b64(url, auth_header)
        prompt = OCR_PROMPT
        if declared_language:
            prompt = f"The letter is declared to be in {declared_language}.\n" + prompt

        result = _call_pixtral(b64, media, prompt)
        result["success"] = True

        # Determine processing route based on confidence
        conf = result.get("overall_confidence", 0)
        result["routing"] = (
            "AUTO_PROCESS"       if conf >= 85 else
            "COORDINATOR_VERIFY" if conf >= 60 else
            "MANUAL_REQUIRED"
        )
        return result

    except Exception as e:
        print(f"perform_handwriting_ocr error: {e}")
        return {
            "success":            False,
            "error":              str(e),
            "transcribed_text":   None,
            "overall_confidence": 0,
            "routing":            "MANUAL_REQUIRED"
        }
