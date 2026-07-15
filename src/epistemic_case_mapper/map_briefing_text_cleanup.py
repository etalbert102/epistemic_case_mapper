from __future__ import annotations

import re


def replace_internal_reader_phrases(text: str) -> str:
    replacements = {
        "mapped support": "available evidence",
        "map-backed read": "evidence-based read",
        "map-backed default": "best-supported default",
        "decision role": "function in the decision",
        "load-bearing map distinction": "important distinction",
        "preserved as a load-bearing map distinction": "important for interpreting the recommendation",
        "not specified": "not established by this packet",
        "full map-backed detail": "full source-grounded detail",
    }
    cleaned = text
    for phrase, replacement in replacements.items():
        cleaned = re.sub(re.escape(phrase), replacement, cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\((?:sc|ec|spine)_?\d{3,}\)", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(?:sc|ec|spine)_?\d{3,}\b", "source-backed evidence", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\byou really cannot\b", "it is difficult to", cleaned, flags=re.IGNORECASE)
    person_group = r"(?:participants|people|those|adults|children|individuals|patients|respondents|workers|population|group|subgroup|cohort)"
    return re.sub(
        rf"\b({person_group}\b[^.\n;:]{{0,140}}?)\s+WHO\s+(were|was|are|is|had|have|do|does|did|may|might|should|could|can|would)\b",
        lambda match: f"{match.group(1)} who {match.group(2)}",
        cleaned,
        flags=re.IGNORECASE,
    )


def reader_facing_sufficiency_limit(status: str) -> str:
    if status == "usable_with_named_gaps":
        return (
            "Where the current source packet lacks a decision-relevant evidence slot, "
            "the memo treats that absence as a named evidence gap rather than as negative evidence."
        )
    if status == "sufficient_for_scaffolded_briefing":
        return (
            "The current source packet is strong enough to organize a bounded briefing, "
            "while leaving the wider evidence base open."
        )
    return (
        "The current source packet has enough structure to name the relevant limits, "
        "with unresolved gaps kept explicit until source-backed evidence fills them."
    )


def reader_facing_unresolved_slot(slot: str) -> str:
    return f"The current map does not cleanly establish the decision-relevant {_label(slot)}."


def reader_facing_unresolved_family(family: str) -> str:
    return f"The current map does not cleanly establish {_label(family)} evidence."


def reader_facing_unresolved_source_category(category: str) -> str:
    if category.startswith("decision_slot:"):
        return reader_facing_unresolved_slot(category.split(":", 1)[1])
    if category.startswith("evidence_family:"):
        return reader_facing_unresolved_family(category.split(":", 1)[1])
    return f"The current source packet does not cleanly establish {_label(category)}."


def _label(value: str) -> str:
    return value.replace("_", " ").replace(":", ": ")
