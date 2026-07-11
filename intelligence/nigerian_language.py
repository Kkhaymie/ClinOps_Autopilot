# backend/intelligence/nigerian_language.py
"""
Nigerian language processing utilities.

Pipeline: expand SMS abbreviations -> detect language -> detect
traditional medicines -> normalise Pidgin symptom phrases into
clinical terms. Run on every incoming message before AI classification.
"""

import re
from typing import Dict, List

# ── PIDGIN SYMPTOM TABLE ──────────────────────────────────────────
PIDGIN_MAP: Dict[str, str] = {
    "body dey hot": "fever",
    "my body dey hot": "fever",
    "body hot": "fever",
    "head dey pain": "headache",
    "my head dey pain me": "headache",
    "head dey do me": "headache",
    "belle dey turn": "nausea",
    "tummy dey turn": "nausea",
    "stomach dey turn": "nausea",
    "dey purge": "diarrhea",
    "running stomach": "diarrhea",
    "heart dey do gbim gbim": "palpitations",
    "gbim gbim": "palpitations",
    "heart dey beat fast": "palpitations",
    "heart dey do somehow": "palpitations",
    "body dey shake": "tremors",
    "dey shake": "tremors",
    "i no fit sleep": "insomnia",
    "no fit sleep": "insomnia",
    "eye don red": "conjunctivitis",
    "eye red red": "conjunctivitis",
    "e dey pain me for chest": "chest pain",
    "chest dey pain me": "chest pain",
    "piss don change colour": "urine discolouration",
    "leg don swell": "peripheral oedema",
    "ankle don swell": "peripheral oedema",
    "i dey scratch my body": "pruritus",
    "body dey itch": "pruritus",
    "body dey do me somehow": "malaise",
    "body dey do me": "malaise",
    "i no sabi wetin dey happen": "confusion",
    "i dey confuse": "confusion",
    "i no fit stand up": "severe weakness",
    "i no fit waka": "inability to walk",
    "waist dey pain me": "lower back pain",
    "back dey pain me": "lower back pain",
    "i no fit breathe": "dyspnoea",
    "breathing anyhow": "dyspnoea",
    "mouth don dry": "dry mouth",
    "i dey vomit": "vomiting",
    "dey vomit": "vomiting",
    "dey feel dizzy": "dizziness",
    "head dey turn": "dizziness",
    "rash dey my body": "skin rash",
    "my skin don red": "skin erythema",
    "e dey woss": "worsening symptoms",
    "i no fit chop": "anorexia",
    "no wan chop": "anorexia",
}

# ── SMS ABBREVIATION EXPANDER ─────────────────────────────────────
SMS_ABBR: Dict[str, str] = {
    r"\bd\b": "the",
    r"\bnt\b": "not",
    r"\bfln\b": "feeling",
    r"\btab\b": "tablet",
    r"\bmed\b": "medication",
    r"\bdoc\b": "doctor",
    r"\bdr\b": "doctor",
    r"\bsx\b": "symptoms",
    r"\bb4\b": "before",
    r"\b2day\b": "today",
    r"\b4rm\b": "from",
    r"\baftr\b": "after",
    r"\bwel\b": "well",
    r"\bplz\b": "please",
    r"\bpls\b": "please",
    r"\bu\b": "you",
    r"\bur\b": "your",
    r"\br\b": "are",
    r"\bwt\b": "with",
    r"\btmrw\b": "tomorrow",
    r"\bnite\b": "night",
    r"\bmrng\b": "morning",
    r"\bbt\b": "but",
}

# ── TRADITIONAL MEDICINE DATABASE ────────────────────────────────
TRAD_MEDICINES: Dict[str, dict] = {
    # Nigerian — HIGH risk
    "agbo jedi-jedi": {
        "risk": "HIGH", "type": "agbo_jedi_jedi",
        "action": "IMMEDIATE_FLAG",
        "interactions": ["anticoagulants", "cardiac drugs", "hepatotoxic drugs"],
    },
    "agbo jedi jedi": {
        "risk": "HIGH", "type": "agbo_jedi_jedi",
        "action": "IMMEDIATE_FLAG",
        "interactions": ["anticoagulants", "cardiac drugs"],
    },
    "agbo": {
        "risk": "HIGH", "type": "agbo_generic",
        "action": "IMMEDIATE_FLAG",
        "interactions": ["anticoagulants", "antihypertensives"],
    },
    "zobo": {
        "risk": "HIGH", "type": "zobo",
        "action": "FLAG_AND_REPORT",
        "interactions": ["antihypertensives", "chloroquine"],
    },
    "hibiscus drink": {
        "risk": "HIGH", "type": "zobo",
        "action": "FLAG_AND_REPORT",
        "interactions": ["antihypertensives"],
    },
    "nzu": {
        "risk": "HIGH", "type": "nzu",
        "action": "IMMEDIATE_FLAG",
        "interactions": ["all drugs — binds in GI tract"],
    },
    "white clay": {
        "risk": "HIGH", "type": "nzu",
        "action": "IMMEDIATE_FLAG",
        "interactions": ["all drugs — binds in GI tract"],
    },
    "calabash chalk": {
        "risk": "HIGH", "type": "nzu",
        "action": "IMMEDIATE_FLAG",
        "interactions": ["all drugs — binds in GI tract"],
    },
    # Nigerian — MODERATE risk
    "akanwu": {
        "risk": "MODERATE", "type": "akanwu",
        "action": "FLAG_AND_REPORT",
        "interactions": ["nephrotoxic drugs", "alters gastric pH"],
    },
    "kaun": {
        "risk": "MODERATE", "type": "akanwu",
        "action": "FLAG_AND_REPORT",
        "interactions": ["nephrotoxic drugs"],
    },
    "potash": {
        "risk": "MODERATE", "type": "akanwu",
        "action": "FLAG_AND_REPORT",
        "interactions": ["nephrotoxic drugs"],
    },
    "bitter leaf": {
        "risk": "MODERATE", "type": "bitter_leaf",
        "action": "FLAG_AND_REPORT",
        "interactions": ["antidiabetic", "antimalarial"],
    },
    "tete leaves": {
        "risk": "MODERATE", "type": "tete",
        "action": "FLAG_AND_REPORT",
        "interactions": ["anticoagulants", "antidiabetic"],
    },
    "african spinach": {
        "risk": "MODERATE", "type": "tete",
        "action": "FLAG_AND_REPORT",
        "interactions": ["anticoagulants"],
    },
    # Nigerian — LOW-MODERATE risk
    "kola nut": {
        "risk": "LOW-MODERATE", "type": "kola_nut",
        "action": "LOG_AND_MONITOR",
        "interactions": ["MAO inhibitors", "stimulants"],
    },
    "kolanut": {
        "risk": "LOW-MODERATE", "type": "kola_nut",
        "action": "LOG_AND_MONITOR",
        "interactions": ["MAO inhibitors", "stimulants"],
    },
    # Nigerian — UNKNOWN
    "dawanaki": {
        "risk": "UNKNOWN", "type": "dawanaki",
        "action": "FLAG_URGENT_IDENTIFICATION",
        "interactions": ["unknown — needs identification"],
    },
    # Asian — HIGH risk
    "starfruit": {
        "risk": "HIGH", "type": "starfruit",
        "action": "IMMEDIATE_FLAG",
        "interactions": ["nephrotoxic drugs", "renal patients"],
    },
    "carambola": {
        "risk": "HIGH", "type": "starfruit",
        "action": "IMMEDIATE_FLAG",
        "interactions": ["nephrotoxic drugs"],
    },
    "belimbing": {
        "risk": "HIGH", "type": "starfruit",
        "action": "IMMEDIATE_FLAG",
        "interactions": ["nephrotoxic drugs"],
    },
    "grapefruit": {
        "risk": "HIGH", "type": "grapefruit",
        "action": "FLAG_AND_REPORT",
        "interactions": ["CYP3A4 substrate drugs"],
    },
    # TCM — MODERATE risk
    "dan shen": {
        "risk": "MODERATE", "type": "tcm_dan_shen",
        "action": "FLAG_AND_REPORT",
        "interactions": ["anticoagulants", "cardiac drugs"],
    },
    "ginseng": {
        "risk": "MODERATE", "type": "tcm_ginseng",
        "action": "FLAG_AND_REPORT",
        "interactions": ["anticoagulants", "antidiabetic"],
    },
}

# ── LANGUAGE DETECTION MARKERS ────────────────────────────────────
# Kept as module-level constants (rather than inline in detect_language)
# so they're easy to extend/tune without touching the scoring logic.
_LANGUAGE_MARKERS: Dict[str, List[str]] = {
    "Nigerian Pidgin": [
        "dey", "no be", "wetin", "abi", "na", "sabi",
        "wahala", "gbim", "somehow", "anyhow", "oya",
    ],
    "Yoruba": [
        "dokita", "ara", "ọwọ", "pẹlẹ", "ẹ jọ",
        "ẹsẹ", "mo", "wa", "ọ", "ẹ",
    ],
    "Igbo": [
        "ụkwụ", "nke", "ya", "dị", "maka",
        "ọ", "ị", "ụ", "gwa", "biko",
    ],
    "Hausa": [
        "dai", "kuma", "zafi", "ciwon", "kai",
        "jikin", "ina", "tare", "mai", "wanda",
    ],
    "Singlish": [
        "lah", "leh", "meh", "lor", "hor",
        "liddat", "shiok", "alamak", "confirm",
    ],
    "French": [
        "depuis", "depuis hier", "depuis ce matin",
        "je", "douleur", "mal", "médicament",
    ],
}
# Marker sets checked against the lowercased text (safe for latin-script langs).
_LOWERCASE_LANGUAGES = {"Nigerian Pidgin", "Hausa", "Singlish", "French"}
# Marker sets checked against the original-case text (diacritics/scripts
# where lowercasing could break matching).
_ORIGINAL_CASE_LANGUAGES = {"Yoruba", "Igbo"}

_ENGLISH_BASELINE_SCORE = 3


def expand_sms_abbreviations(text: str) -> str:
    """Expand common SMS shorthand (e.g. 'u', 'b4', 'tmrw') into full words."""
    for pattern, replacement in SMS_ABBR.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def normalise_pidgin(text: str) -> str:
    """Replace known Pidgin symptom phrases with bracketed clinical tags."""
    text_lower = text.lower()
    for expr, clinical in PIDGIN_MAP.items():
        if expr in text_lower:
            text_lower = text_lower.replace(expr, f"[SYMPTOM:{clinical}]")
    return text_lower


def detect_traditional_medicines(text: str) -> List[dict]:
    """Scan text for known traditional/herbal medicine mentions and their risk info."""
    text_lower = text.lower()
    found = []
    for name, info in TRAD_MEDICINES.items():
        if name in text_lower:
            found.append({
                "name": name,
                "risk": info["risk"],
                "type": info["type"],
                "action": info["action"],
                "known_interactions": info.get("interactions", []),
            })
    return found


def detect_language(text: str) -> str:
    """
    Score text against marker word lists for each supported language and
    return the best match, defaulting to English if nothing scores above 0.

    Note: the original Arabic marker list contained corrupted/unparseable
    literals and has been dropped rather than silently matching nothing.
    If Arabic detection is needed, supply a clean marker list of Arabic
    words/phrases here.
    """
    text_lower = text.lower()
    scores: Dict[str, int] = {"English": _ENGLISH_BASELINE_SCORE}

    for language, markers in _LANGUAGE_MARKERS.items():
        haystack = text_lower if language in _LOWERCASE_LANGUAGES else text
        scores[language] = sum(1 for marker in markers if marker in haystack)

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "English"


def process_nigerian_text(text: str) -> dict:
    """
    Master function — run all Nigerian language processing.
    Call this on every incoming message before AI classification.
    """
    expanded = expand_sms_abbreviations(text)
    language = detect_language(expanded)
    medicines = detect_traditional_medicines(expanded)
    normalised = normalise_pidgin(expanded)

    return {
        "original_text": text,
        "processed_text": normalised,
        "detected_language": language,
        "traditional_medicines_detected": medicines,
        "has_high_risk_medicine": any(m["risk"] == "HIGH" for m in medicines),
    }
