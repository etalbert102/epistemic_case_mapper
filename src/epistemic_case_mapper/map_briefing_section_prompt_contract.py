from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_slots import _rewrite_mentions_anchor_row
from epistemic_case_mapper.map_briefing_section_input_compiler import (
    compact_main_memo_obligations,
    compile_model_section_packet,
)


def model_facing_section_contract(contract: dict[str, Any]) -> dict[str, Any]:
    model_packet = compile_model_section_packet(str(contract.get("heading", "")), contract)
    model_contract = {
        "heading": contract.get("heading"),
        "confidence": contract.get("confidence"),
        "requires_confidence": contract.get("requires_confidence"),
        "model_section_packet": model_packet,
        "validation_obligations": _model_facing_validation_obligations(contract),
        "section_job": contract.get("section_job"),
        "has_obligations": contract.get("has_obligations"),
        "style": contract.get("style", []),
    }
    return {key: value for key, value in model_contract.items() if value not in ({}, [], "", None)}


def _model_facing_validation_obligations(contract: dict[str, Any]) -> dict[str, Any]:
    obligations = {
        "required_evidence": _model_facing_required_evidence(contract.get("required_evidence")),
        "required_gaps": contract.get("required_gaps", []),
        "required_cruxes": _model_facing_required_cruxes(contract.get("required_cruxes")),
        "required_main_memo_obligations": compact_main_memo_obligations(
            contract.get("required_main_memo_obligations", [])
        ),
        "practical_actions": _model_facing_practical_actions(contract),
        "min_decision_changing_cruxes": contract.get("min_decision_changing_cruxes"),
    }
    return {key: value for key, value in obligations.items() if value not in ({}, [], "", None)}


def model_facing_section_markdown(markdown: str, contract: dict[str, Any]) -> str:
    text = markdown
    for row in contract.get("owned_elsewhere_evidence", []) if isinstance(contract.get("owned_elsewhere_evidence"), list) else []:
        if not isinstance(row, dict) or not _text_mentions_owned_elsewhere(text, row):
            continue
        policy = row.get("reference_policy", {}) if isinstance(row.get("reference_policy"), dict) else {}
        owner = str(policy.get("owner_section", "")).strip() or "the owning section"
        slot = str(row.get("slot", "evidence")).strip() or "evidence"
        replacement = "" if policy.get("reference_style") == "do_not_repeat" else f"{slot} evidence is handled in {owner}."
        text = _replace_matching_sentences(text, row, replacement)
    return text.strip() or markdown


def _model_facing_required_evidence(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in value if isinstance(value, list) else []:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "slot": row.get("slot"),
                "claim": row.get("claim"),
                "source": row.get("source"),
                "anchor_terms": row.get("anchor_terms", []),
                "instruction": "This section owns this evidence and may explain it fully.",
            }
        )
    return rows


def _replace_matching_sentences(text: str, row: dict[str, Any], replacement: str) -> str:
    parts = []
    for sentence in _split_sentences_preserving_lines(text):
        if _text_mentions_owned_elsewhere(sentence, row):
            if replacement:
                parts.append(replacement)
        else:
            parts.append(sentence)
    return "\n".join(part for part in parts if part.strip())


def _split_sentences_preserving_lines(text: str) -> list[str]:
    chunks: list[str] = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith(("#", "-", "*", "|")):
            chunks.append(line)
        else:
            chunks.extend(part.strip() for part in re.split(r"(?<=[.!?])\s+", line) if part.strip())
    return chunks


def _model_facing_required_cruxes(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in value if isinstance(value, list) else []:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "crux": row.get("crux"),
                "why_it_matters": row.get("why_it_matters"),
                "current_read": row.get("current_read"),
                "would_change_if": row.get("would_change_if"),
            }
        )
    return rows


def _model_facing_practical_actions(contract: dict[str, Any]) -> list[str]:
    actions: list[str] = []
    for action in contract.get("practical_actions", []) if isinstance(contract.get("practical_actions"), list) else []:
        text = str(action).strip()
        if text and not _mentions_owned_elsewhere_evidence(text, contract):
            actions.append(text)
    return actions[:4]


def _mentions_owned_elsewhere_evidence(text: str, contract: dict[str, Any]) -> bool:
    for row in contract.get("owned_elsewhere_evidence", []) if isinstance(contract.get("owned_elsewhere_evidence"), list) else []:
        if isinstance(row, dict) and _text_mentions_owned_elsewhere(text, row):
            return True
    return False


def _text_mentions_owned_elsewhere(text: str, row: dict[str, Any]) -> bool:
    if _rewrite_mentions_anchor_row(text, row):
        return True
    haystack_terms = _terms(text)
    if not haystack_terms:
        return False
    claim_terms = _terms(str(row.get("claim", "")))
    anchor_terms = _terms(" ".join(str(term) for term in row.get("anchor_terms", []) if str(term).strip())) if isinstance(row.get("anchor_terms"), list) else set()
    distinctive = (claim_terms | anchor_terms) - _GENERIC_SECTION_TERMS
    if len(haystack_terms & distinctive) >= 2:
        return True
    return bool(haystack_terms & _HIGH_SIGNAL_TERMS & distinctive)


def _terms(text: str) -> set[str]:
    return {term for term in re.findall(r"[a-z0-9]{4,}", str(text).lower())}


_HIGH_SIGNAL_TERMS = {
    "diabetes",
    "mortality",
    "stroke",
    "cancer",
    "cohort",
    "randomized",
    "trial",
    "processed",
    "unprocessed",
}


_GENERIC_SECTION_TERMS = {
    "associated",
    "association",
    "cardiovascular",
    "consumption",
    "disease",
    "evidence",
    "higher",
    "intake",
    "intervention",
    "interventions",
    "practical",
    "recommendation",
    "risk",
    "section",
}
