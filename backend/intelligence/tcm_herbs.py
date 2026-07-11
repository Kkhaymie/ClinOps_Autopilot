# backend/intelligence/tcm_herbs.py
"""
Traditional Chinese Medicine herb-drug interaction detection, Singapore
context (Scenario 12).

Every entry below is sourced from NCCIH (NIH) or a peer-reviewed
cardiovascular herb-interaction review, not general knowledge, herb-drug
interactions are pharmacological claims, and getting one wrong here is a
different order of risk than getting a vocabulary word wrong. This is
deliberately a short, conservative list: only herbs where I found a
specific, repeated, documented interaction, not everything that showed up
in a search. Sources are noted inline per entry so a clinician can verify
or expand this without re-researching from scratch.

Separate from nigerian_language.py's traditional-medicine list (that one's
Nigeria-specific); this one runs unconditionally alongside it, same as
that one does, since restricting by patient.country adds a stale-data
failure mode for no real benefit — a Nigerian patient mentioning "ginseng"
by name is already a low false-positive-risk keyword regardless of
country.

NOT covered here, and deliberately not attempted: HSA's list of herbal
PRODUCTS found to be adulterated with hidden pharmaceutical ingredients
(e.g. the 2023 D'sihat Herba Gout & Sendi alert). That's a different
problem, a dynamic, changing list of specific commercial product names,
not stable herb pharmacology, and belongs in a periodically-refreshed
HSA-alert feed, not a hardcoded list that goes stale the day it ships.
"""

import re
from typing import List, TypedDict


class TCMHerb(TypedDict):
    name: str
    risk: str  # "HIGH" | "MODERATE" | "LOW"
    note: str


_TCM_HERBS = [
    {
        "name": "Ginseng (Ren Shen)",
        "match": ["ginseng", "ren shen", "renshen"],
        "risk": "MODERATE",
        "note": (
            "Documented case report of reduced warfarin anticoagulant effect "
            "(INR dropped from 3-4 to 1.5). Uncertain interaction with calcium "
            "channel blockers, statins, and blood glucose control. "
            "Source: NCCIH; Cleveland Clinic Pharmacotherapy Update case report."
        ),
    },
    {
        "name": "Dan Shen / Red Sage (Salvia miltiorrhiza)",
        "match": ["dan shen", "danshen", "red sage", "salvia miltiorrhiza"],
        "risk": "MODERATE",
        "note": (
            "Commonly used for cardiovascular conditions, listed among herbs "
            "with cardiovascular interaction potential. Evidence on drug-"
            "metabolism (CYP) interaction is mixed, minimal effect shown for "
            "aqueous extract in a 2024 review, but cardiac-drug overlap "
            "warrants caution given how it's typically used. "
            "Source: PMC2831618; PMC12675451."
        ),
    },
    {
        "name": "Licorice root / Gan Cao (Glycyrrhiza)",
        "match": ["licorice", "liquorice", "gan cao", "gancao", "glycyrrhiza"],
        "risk": "HIGH",
        "note": (
            "Can cause hypokalemia (low potassium), which increases digoxin "
            "toxicity risk and can itself cause arrhythmia/palpitations. "
            "Directly relevant to any cardiac-symptom report. "
            "Source: PMC12641511 (TCM cardiovascular metabolites review)."
        ),
    },
    {
        "name": "Green tea (high-dose/extract)",
        "match": ["green tea extract", "green tea", "camellia sinensis"],
        "risk": "LOW",
        "note": (
            "At high doses, shown to reduce blood levels/effectiveness of "
            "nadolol (a beta-blocker). Worth flagging for patients on "
            "beta-blockers reporting reduced symptom control, low risk at "
            "ordinary dietary intake. Source: NCCIH herb-drug interactions digest."
        ),
    },
    {
        "name": "St. John's Wort",
        "match": ["st john's wort", "st johns wort", "saint john's wort", "hypericum"],
        "risk": "HIGH",
        "note": (
            "Not actually TCM, a Western herb, but common across Singapore's "
            "communities so included here. Strongly induces CYP3A4 drug "
            "metabolism, reduces effectiveness of many drugs including "
            "warfarin and statins. Source: NCCIH; PMC12641511."
        ),
    },
]


def detect_tcm_herbs(text: str) -> List[TCMHerb]:
    if not text:
        return []
    lowered = text.lower()
    found: List[TCMHerb] = []
    for herb in _TCM_HERBS:
        for alias in herb["match"]:
            if re.search(r"\b" + re.escape(alias) + r"\b", lowered):
                found.append({"name": herb["name"], "risk": herb["risk"], "note": herb["note"]})
                break  # one match per herb is enough, don't double-count aliases
    return found