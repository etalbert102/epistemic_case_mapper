from __future__ import annotations

import re
from typing import Any


def quantity_signature(value: Any) -> str:
    text = str(value or "").lower()
    text = re.sub(r"[\u2000-\u200f,\s]+", " ", text)
    text = text.replace("confidence interval", "ci").replace("hazard ratio", "hr").replace("relative risk", "rr")
    return re.sub(r"[^a-z0-9.%/ <>=-]+", " ", text).strip()


def quantity_covered_by_text(value: Any, text: Any) -> bool:
    value_norm = quantity_signature(value)
    text_norm = quantity_signature(text)
    if not value_norm or not text_norm:
        return False
    if value_norm in text_norm:
        return True
    numbers = re.findall(r"\d+(?:\.\d+)?", value_norm)
    return bool(numbers) and all(number in text_norm for number in numbers[:2])


def likely_residual_quantity(value: Any, *, context_text: Any = "") -> bool:
    text = str(value or "").strip().lower()
    if not text or looks_like_audit_or_descriptor_quantity(text):
        return False
    if re.search(r"\b(?:hazard ratio|relative risk|risk ratio|odds ratio|hr|rr|or|confidence interval|ci)\b", text):
        return True
    if re.search(r"\b\d+(?:\.\d+)?\s*(?:mg|g|mcg|ml|l|units?|items?|servings?|doses?)\s*(?:/|per)\s*(?:day|week|month|year)\b", text):
        return True
    if re.search(r"\b(?:at least|less than|more than|up to)\s+[^.;,]*\b(?:unit|item|serving|dose|mg|g|mcg|ml|l)\b", text):
        return True
    if "%" in text:
        return bool(re.search(r"\b(?:risk|rate|mortality|effect|increase|decrease|reduction|absolute|relative)\b", text))
    context = str(context_text or "").lower()
    if re.search(r"\b\d+(?:\.\d+)?\b", text) and re.search(
        r"\b(?:risk|ratio|hazard|odds|mortality|disease|event|outcome|effect|measure|endpoint|rate|score|level|concentration|pressure)\b",
        context,
    ):
        return not re.search(r"\b(?:participants?|cohorts?|estimates?|events?|years?|months?|weeks?|days?)\b", text)
    return False


def looks_like_audit_or_descriptor_quantity(text: str) -> bool:
    if re.fullmatch(r"(?:19|20)\d{2}", text):
        return True
    if re.search(r"\b(?:participants?|person years?|events?|cohorts?|risk estimates?|studies|trials|articles|databases)\b", text):
        return True
    if re.search(r"\bi\s*2\s*=", text) or "heterogeneity" in text or re.search(r"\bp\s*(?:=|<|>|≤|>=|<=)", text):
        return True
    if re.search(r"\b\d+(?:\.\d+)?\s*(?:years?|months?|weeks?|days?)\b", text):
        return True
    return False
