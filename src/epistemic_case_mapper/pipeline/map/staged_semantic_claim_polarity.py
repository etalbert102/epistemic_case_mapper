from __future__ import annotations

import re


def claim_polarity(text: str) -> str:
    normalized = f" {re.sub(r'\s+', ' ', text.lower())} "
    if _has_any(
        normalized,
        " no association ",
        " not associated ",
        " no clear association ",
        " no clear effect ",
        " no difference ",
        " unchanged ",
        " near null ",
        " null result ",
    ):
        return "null_or_no_clear_association"
    beneficial = _has_any(
        normalized,
        " lower risk ",
        " reduced risk ",
        " decreased risk ",
        " protective ",
        " beneficial ",
        " improved ",
    ) or bool(
        re.search(r"\b(?:lower|reduced|decreased)\b.{0,40}\b(?:risk|mortality|events?|outcomes?)\b", normalized)
    )
    harmful = _has_any(
        normalized,
        " higher risk ",
        " increased risk ",
        " higher mortality ",
        " increased mortality ",
        " harmful ",
        " adverse effect ",
        " adverse effects ",
        " concern ",
    ) or bool(
        re.search(r"\b(?:higher|increased|elevated)\b.{0,40}\b(?:risk|mortality|events?|outcomes?)\b", normalized)
    )
    if beneficial and not harmful:
        return "beneficial_or_lower"
    if harmful and not beneficial:
        return "harmful_or_concern"
    return "mixed"


def _has_any(text: str, *markers: str) -> bool:
    return any(marker in text for marker in markers)
