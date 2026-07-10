# backend/intelligence/agent_core.py
"""
AI-powered adverse event classification.

Routes to a local Ollama model in development (saves API credits) or
Mistral in production. Both paths return a normalized classification
dict; on any failure, _fallback() returns a safe manual-review payload
instead of raising.
"""

import json
import os
from datetime import datetime, timedelta
from typing import List, Optional

from dotenv import load_dotenv
from mistralai import Mistral

load_dotenv()

mistral = Mistral(api_key=os.getenv("MISTRAL_API_KEY"))
USE_LOCAL = os.getenv("ENVIRONMENT", "development") == "development"

SYSTEM = """You are ClinOps Autopilot — a clinical trial adverse event
classification specialist. You understand Nigerian Pidgin, Yoruba, Igbo,
Hausa, Singlish, Arabic, and Japanese symptom descriptions.
You know Nigerian traditional medicines (Agbo, Zobo, Nzu, Akanwu).
You always return valid JSON only. Never add explanation outside JSON."""


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def classify_adverse_event(
    clinical_summary: str,
    patient_context: dict,
    traditional_medicines: Optional[List[dict]] = None,
) -> dict:
    if USE_LOCAL:
        return _classify_ollama(clinical_summary, patient_context, traditional_medicines)
    return _classify_mistral(clinical_summary, patient_context, traditional_medicines)


# ---------------------------------------------------------------------------
# Model backends
# ---------------------------------------------------------------------------

def _classify_mistral(summary: str, ctx: dict, medicines: Optional[List[dict]]) -> dict:
    trad_alert = ""
    if medicines:
        high = [m for m in medicines if m["risk"] == "HIGH"]
        if high:
            names = [m["name"] for m in high]
            trad_alert = (
                f"\n⚠ HIGH-RISK TRADITIONAL MEDICINES DETECTED: {names}. "
                f"Elevate severity. Flag drug interaction risk."
            )

    prompt = f"""Classify this clinical trial adverse event.

PATIENT CONTEXT:
- Trial drug: {ctx.get('drug_name', 'Unknown')}
- Last dose: {ctx.get('last_dose_date', 'Unknown')}
- Country: {ctx.get('country', 'Nigeria')}
- Allergies: {ctx.get('known_allergies', 'None')}{trad_alert}

PATIENT REPORT:
{summary}

Return ONLY this JSON:
{{
  "symptoms": ["list", "of", "symptoms"],
  "severity": "Mild|Moderate|Severe|Life-threatening",
  "urgency": "Routine|Same-day|Urgent|Emergency",
  "category": "AE|SAE|Protocol-Deviation|Inquiry|Non-reportable",
  "confidence": 85,
  "causality": "Probable|Possible|Unlikely|Unrelated",
  "trad_medicine_interaction_risk": "None|Low|Moderate|High|Critical",
  "cultural_flags": [],
  "estimated_onset": "approximate time since symptoms started",
  "draft_patient_reply": "Reply message to send to patient",
  "coordinator_action": "What coordinator should do next",
  "regulatory_deadline_trigger": true,
  "emotional_distress_detected": false,
  "emotional_distress_notes": "brief note on tone/content suggesting distress, empty string if none"
}}"""

    try:
        response = mistral.chat.complete(
            model="mistral-large-latest",
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=800,
        )
        raw = _clean_json(response.choices[0].message.content.strip())
        result = json.loads(raw)
        result["model_used"] = "mistral-large-latest"
        return result
    except Exception as e:
        return _fallback(str(e))


def _classify_ollama(summary: str, ctx: dict, medicines: Optional[List[dict]]) -> dict:
    """Use local Ollama during development — saves Mistral credits."""
    try:
        import ollama

        prompt = f"""Classify adverse event. Return JSON only.
Drug: {ctx.get('drug_name', 'Unknown')}
Report: {summary}

JSON:
{{
  "symptoms": [],
  "severity": "Mild",
  "urgency": "Routine",
  "category": "AE",
  "confidence": 70,
  "causality": "Possible",
  "trad_medicine_interaction_risk": "None",
  "cultural_flags": [],
  "estimated_onset": "Unknown",
  "draft_patient_reply": "Thank you. We have received your report.",
  "coordinator_action": "Review and approve",
  "regulatory_deadline_trigger": true,
  "emotional_distress_detected": false,
  "emotional_distress_notes": ""
}}"""

        response = ollama.chat(
            model="llama3.2",
            messages=[
                {"role": "system", "content": "Clinical AE classifier. JSON only."},
                {"role": "user", "content": prompt},
            ],
        )
        raw = _clean_json(response["message"]["content"])
        result = json.loads(raw)
        result["model_used"] = "ollama-llama3.2"
        return result
    except Exception as e:
        return _fallback(str(e))


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _clean_json(text: str) -> str:
    """Strip markdown code-fences (```json ... ```) that models sometimes wrap JSON in."""
    text = text.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:]
            part = part.strip()
            if part.startswith("{"):
                return part
    return text


def _fallback(error: str) -> dict:
    """Safe default returned when AI classification fails for any reason."""
    return {
        "symptoms": ["Manual review required"],
        "severity": "Moderate",
        "urgency": "Same-day",
        "category": "AE",
        "confidence": 0,
        "causality": "Unknown",
        "trad_medicine_interaction_risk": "Unknown",
        "cultural_flags": ["AI classification failed"],
        "estimated_onset": "Unknown",
        "draft_patient_reply": (
            "Thank you for your message. We have received your report "
            "and will follow up with you shortly."
        ),
        "coordinator_action": (
            "MANUAL REVIEW REQUIRED — AI classification failed. "
            "Please review original message."
        ),
        "regulatory_deadline_trigger": True,
        "emotional_distress_detected": False,
        "emotional_distress_notes": "",
        "model_used": "fallback",
        "error": error,
    }


# ---------------------------------------------------------------------------
# Regulatory deadline calculation
# ---------------------------------------------------------------------------

_REGULATORY_RULES = {
    "Nigeria": {
        "body": "NAFDAC",
        "Life-threatening": timedelta(hours=24),
        "SAE": timedelta(days=7),
        "Severe": timedelta(days=7),
        "Moderate": timedelta(days=15),
        "Mild": timedelta(days=15),
    },
    "Singapore": {
        "body": "HSA",
        "Life-threatening": timedelta(days=7),
        "SAE": timedelta(days=15),
        "Severe": timedelta(days=15),
        "Moderate": timedelta(days=30),
        "Mild": timedelta(days=30),
    },
    "India": {
        "body": "CDSCO",
        "Life-threatening": timedelta(days=7),
        "SAE": timedelta(days=14),
        "Severe": timedelta(days=14),
        "Moderate": timedelta(days=30),
        "Mild": timedelta(days=30),
    },
    "Japan": {
        "body": "PMDA",
        "Life-threatening": timedelta(days=7),
        "SAE": timedelta(days=15),
        "Severe": timedelta(days=15),
        "Moderate": timedelta(days=30),
        "Mild": timedelta(days=30),
    },
}

# Categories that were never a reportable adverse event in the first
# place, a regulatory clock shouldn't start for these. Fix #3.
_NON_REPORTABLE_CATEGORIES = {"Non-reportable", "Inquiry"}


def calculate_deadline(
    severity: str,
    country: str,
    category: str,
    base_time: Optional[datetime] = None,
) -> dict:
    if category in _NON_REPORTABLE_CATEGORIES:
        return {
            "regulatory_body": None,
            "deadline": None,
            "hours_total": None,
            "is_urgent": False,
        }

    if not base_time:
        base_time = datetime.now()

    country_rules = _REGULATORY_RULES.get(country, _REGULATORY_RULES["Nigeria"])
    effective = "SAE" if category == "SAE" else severity
    delta = country_rules.get(effective, timedelta(days=15))
    deadline = base_time + delta

    return {
        "regulatory_body": country_rules["body"],
        "deadline": deadline.isoformat(),
        "hours_total": delta.total_seconds() / 3600,
        "is_urgent": delta.total_seconds() / 3600 <= 48,
    }
