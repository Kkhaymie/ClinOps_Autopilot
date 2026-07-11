# backend/intelligence/nigerian_language.py
"""
Lightweight Nigerian-language pre-processing for inbound adverse-event text.

This runs *before* the message reaches the AI classifier (agent_core). It:
  1. Detects which script/language the report is likely in (Nigerian Pidgin,
     Yoruba, Igbo, Hausa, or plain English) using keyword matching — a fast,
     dependency-free heuristic. The LLM prompt in agent_core already
     understands these languages directly, so this is a hint, not a
     translation step. Also flags Arabic-script text (see
     _contains_arabic_script), likely Hausa written in Ajami script, common
     in Northern Nigeria, so it gets routed to the AI classifier with the
     right expectation rather than silently misread as plain Arabic.
  2. Scans for mentions of common Nigerian traditional/herbal remedies
     (Agbo, Zobo, Nzu, Akanwu, etc.), since these can interact with trial
     drugs and must be flagged for the coordinator.
  3. Returns a normalized "processed_text" that's safe to hand straight to
     classify_adverse_event().

Called from: main.py (physical letter OCR flow), channels/whatsapp_cloud.py,
channels/email_receiver.py, channels/telegram_receiver.py.
"""

import re
from typing import List, TypedDict


class TraditionalMedicine(TypedDict):
    name: str
    risk: str          # "HIGH" | "MODERATE" | "LOW"
    note: str


class ProcessedText(TypedDict):
    processed_text: str
    original_text: str
    detected_language: str
    language_signals: List[str]
    traditional_medicines_detected: List[TraditionalMedicine]
    has_high_risk_medicine: bool


# ---------------------------------------------------------------------------
# Keyword banks
# ---------------------------------------------------------------------------

# Common Nigerian Pidgin / local-language markers. Not exhaustive — just
# enough to flag "this report is likely not plain English" for routing and
# to nudge the LLM prompt/reviewer.
_LANGUAGE_MARKERS = {
    "Nigerian Pidgin": [
        "abeg", "wetin", "dey", "una", "wahala", "sabi", "no dey",
        "e don", "make i", "i no fit", "body dey", "e dey pain",
    ],
    "Yoruba": [
        "mo n", "won ni", "ara mi", "aisan", "oogun", "iba", "ile iwosan",
    ],
    "Igbo": [
        "adighi", "aru m", "oria", "ogwu", "ana m", "biko",
    ],
    "Hausa": [
        "ina ji", "jikina", "magani", "asibiti", "rashin lafiya", "ba na",
    ],
}

# Traditional/herbal remedies referenced in patient reports. Risk levels
# reflect the general concern that these are unregulated, potentially
# hepatotoxic, or may mask/mimic AE symptoms (drug interaction risk), not a
# clinical determination — the coordinator/PI still makes the final call.
_TRADITIONAL_MEDICINES: List[TraditionalMedicine] = [
    {"name": "Agbo", "risk": "HIGH",
     "note": "Herbal decoction; unregulated dosing, possible hepatotoxicity and drug interactions."},
    {"name": "Zobo", "risk": "LOW",
     "note": "Hibiscus drink; generally low risk but can affect blood pressure/potassium."},
    {"name": "Nzu", "risk": "HIGH",
     "note": "Edible clay/kaolin; can impair drug absorption and cause heavy-metal exposure."},
    {"name": "Akanwu", "risk": "MODERATE",
     "note": "Potash (potassium carbonate); electrolyte disturbance risk, especially in pregnancy."},
    {"name": "Dogonyaro", "risk": "MODERATE",
     "note": "Neem-based remedy; hepatotoxicity risk with prolonged use."},
    {"name": "Alligator pepper", "risk": "LOW",
     "note": "Culinary/ceremonial use; low clinical risk in typical amounts."},
    {"name": "Bitter kola", "risk": "LOW",
     "note": "Common chewed remedy; may have mild stimulant/anticoagulant effects."},
    {"name": "Ogogoro", "risk": "MODERATE",
     "note": "Local distilled spirit; interacts with many trial drugs, hepatotoxic in excess."},
]


_ARABIC_SCRIPT_PATTERN = re.compile(
    r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]"
)


def _contains_arabic_script(text: str, threshold: float = 0.15) -> bool:
    """
    True if a meaningful fraction of the text is Arabic-script characters.

    This is a Unicode code-point range check, deterministic, not a
    vocabulary guess, so unlike keyword matching it doesn't depend on
    having a verified word list. It flags Arabic-script text generally;
    it does NOT distinguish Ajami (Hausa written in Arabic script) from
    actual Arabic, that distinction needs linguistic judgement this
    function isn't making. In this system's context (a Nigerian trial
    site), Arabic-script SMS/WhatsApp text is far more likely to be
    Ajami-Hausa than Arabic proper, so callers should treat it as a
    "probably Ajami" signal and let the AI classifier, which has much
    broader multilingual training than a keyword list, make the actual
    read.
    """
    if not text:
        return False
    arabic_chars = len(_ARABIC_SCRIPT_PATTERN.findall(text))
    letters = len(re.findall(r"\w", text, re.UNICODE))
    if letters == 0:
        return False
    return (arabic_chars / letters) >= threshold


def _detect_script(text: str) -> tuple:
    """Return (best_guess_language, matched_signal_phrases).

    Uses word-boundary matching, not plain substring matching, a short
    marker like "una" shouldn't match inside an unrelated word. Checks
    for Arabic script first, since keyword matching against the Latin-
    script marker lists wouldn't apply to it anyway.
    """
    if _contains_arabic_script(text):
        return "Arabic script (Ajami-Hausa likely)", ["arabic-script-detected"]

    lowered = text.lower()
    matches_by_lang = {}
    for lang, markers in _LANGUAGE_MARKERS.items():
        hits = [m for m in markers if re.search(r"\b" + re.escape(m) + r"\b", lowered)]
        if hits:
            matches_by_lang[lang] = hits

    if not matches_by_lang:
        return "English", []

    best_lang = max(matches_by_lang, key=lambda l: len(matches_by_lang[l]))
    return best_lang, matches_by_lang[best_lang]


def _detect_traditional_medicines(text: str) -> List[TraditionalMedicine]:
    lowered = text.lower()
    found = []
    for med in _TRADITIONAL_MEDICINES:
        pattern = r"\b" + re.escape(med["name"].lower()) + r"\b"
        if re.search(pattern, lowered):
            found.append(med)
    return found


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def process_nigerian_text(text: str) -> ProcessedText:
    """
    Pre-process an inbound patient/proxy report before AI classification.

    Args:
        text: raw transcript/body from any channel (WhatsApp, SMS, Telegram,
              email, or OCR'd physical letter).

    Returns:
        dict matching ProcessedText — always returns a well-formed result,
        even for empty/None input, so callers can safely index into it.
    """
    text = text or ""
    cleaned = _normalize_whitespace(text)

    language, signals = _detect_script(cleaned)
    medicines = _detect_traditional_medicines(cleaned)
    has_high_risk = any(m["risk"] == "HIGH" for m in medicines)

    return {
        "processed_text": cleaned,
        "original_text": text,
        "detected_language": language,
        "language_signals": signals,
        "traditional_medicines_detected": medicines,
        "has_high_risk_medicine": has_high_risk,
    }