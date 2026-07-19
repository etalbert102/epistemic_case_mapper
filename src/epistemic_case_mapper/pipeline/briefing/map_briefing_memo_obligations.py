from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_writer_guidance import writer_guidance_memo_obligations


def build_memo_obligation_packet(
    evidence_items: list[dict[str, Any]],
    memo_warning_packet: dict[str, Any] | None = None,
    writer_guidance_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build writer-facing obligations from audit-facing evidence records."""

    obligations: list[dict[str, Any]] = []
    for item in evidence_items:
        if not isinstance(item, dict) or not item.get("must_use"):
            continue
        obligation = _obligation_from_evidence_item(len(obligations) + 1, item)
        if obligation:
            obligations.append(obligation)
    for warning in _list((memo_warning_packet or {}).get("warnings")):
        if not isinstance(warning, dict):
            continue
        obligation = _obligation_from_warning(len(obligations) + 1, warning)
        if obligation:
            obligations.append(obligation)
    obligations.extend(writer_guidance_memo_obligations(writer_guidance_packet, start_index=len(obligations) + 1))
    return {
        "schema_id": "memo_obligations_v1",
        "method": "decision_obligations_from_memo_ready_items_source_warnings_and_writer_guidance",
        "required_count": sum(1 for row in obligations if row.get("required")),
        "optional_count": sum(1 for row in obligations if not row.get("required")),
        "obligations": obligations,
        "guidance": [
            "Use required obligations to preserve decision-relevant reasoning in natural prose.",
            "Use optional obligations only when they improve scope, calibration, or reader auditability.",
            "Keep the full evidence packet available for audit even when the memo compresses low-value detail.",
        ],
    }


def required_memo_obligations(packet: dict[str, Any]) -> list[dict[str, Any]]:
    obligations = _memo_obligations(packet)
    return [row for row in obligations if row.get("required")]


def all_memo_obligations(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return _memo_obligations(packet)


def _memo_obligations(packet: dict[str, Any]) -> list[dict[str, Any]]:
    payload = packet.get("memo_obligations") if isinstance(packet, dict) else {}
    rows = _list(payload.get("obligations")) if isinstance(payload, dict) else []
    return [row for row in rows if isinstance(row, dict)]


def _obligation_from_evidence_item(index: int, item: dict[str, Any]) -> dict[str, Any]:
    role = str(item.get("role") or "").strip()
    source_labels = _source_labels(item)
    source_ids = _source_ids(item)
    claim = _sanitize_claim(str(item.get("reader_claim") or "").strip())
    if not claim:
        return {}
    obligation_type = {
        "strongest_support": "must_weigh_support",
        "quantitative_anchor": "must_interpret_quantity",
        "strongest_counterweight": "must_weigh_counterweight",
        "scope_boundary": "must_bound_scope",
        "decision_crux": "must_address_crux",
    }.get(role, "optional_context")
    quantities = _load_bearing_quantities(item)
    statement = _obligation_statement(role, claim)
    validation_terms = _validation_terms(role, claim, statement)
    evidence_item_ids = _dedupe([str(item.get("item_id") or "").strip()])
    return {
        "obligation_id": f"memo_obligation_{index:03d}",
        "obligation_type": obligation_type,
        "required": obligation_type != "optional_context",
        "role": role,
        "statement": statement,
        "prose_instruction": _prose_instruction(role),
        "why_it_matters": _why_it_matters(role, item),
        "source_labels": source_labels,
        "source_label": source_labels[0] if source_labels else "",
        "source_ids": source_ids,
        "quantities": quantities,
        "evidence_item_ids": evidence_item_ids,
        "acceptable_expression": _acceptable_expression(
            role,
            claim,
            source_ids=source_ids,
            quantities=quantities,
            validation_terms=validation_terms,
        ),
        "validation_mode": "scope_signal" if role == "scope_boundary" else "claim_terms",
        "validation_terms": validation_terms,
        "audit_claim": claim,
    }


def _obligation_from_warning(index: int, warning: dict[str, Any]) -> dict[str, Any]:
    severity = str(warning.get("severity") or "").strip().lower()
    quantities = [
        {"value": value, "interpretation": "source-warning quantity"}
        for value in _string_list(warning.get("quantity_values"))
    ]
    required = severity == "critical" or bool(quantities)
    claim = _sanitize_claim(str(warning.get("claim") or "").strip())
    if not claim:
        return {}
    return {
        "obligation_id": f"memo_obligation_{index:03d}",
        "obligation_type": "must_weigh_omitted_evidence" if required else "optional_context",
        "required": required,
        "role": "source_warning",
        "statement": claim if required else f"Use this context only if it changes scope, confidence, or reader auditability: {claim}",
        "prose_instruction": (
            "Incorporate if it changes the decision read; otherwise use it as a limitation."
            if required
            else "Use this only when it improves the decision read."
        ),
        "why_it_matters": str(warning.get("why_it_matters") or warning.get("decision_relevance") or "").strip(),
        "source_labels": _string_list(warning.get("source_labels")),
        "source_label": _first(_string_list(warning.get("source_labels"))),
        "source_ids": _string_list(warning.get("source_ids")),
        "quantities": quantities,
        "warning_ids": [str(warning.get("warning_id") or "")],
        "acceptable_expression": _acceptable_expression(
            "source_warning",
            claim,
            source_ids=_string_list(warning.get("source_ids")),
            quantities=quantities,
            validation_terms=_dedupe([*_string_list(warning.get("anchor_terms")), *_content_terms(claim)[:6]])[:10],
        ),
        "validation_mode": "claim_terms",
        "validation_terms": _dedupe([*_string_list(warning.get("anchor_terms")), *_content_terms(claim)[:6]])[:10],
        "audit_claim": claim,
    }


def _obligation_statement(role: str, claim: str) -> str:
    if role == "scope_boundary":
        return "Bound the answer's applicability using this source-backed scope boundary."
    if role == "decision_crux":
        return f"Evaluate this decision crux with calibrated language: {claim}"
    if role == "strongest_counterweight":
        return f"Weigh this counterweight against the default answer: {claim}"
    if role == "quantitative_anchor":
        return f"Interpret this load-bearing quantity for the decision: {claim}"
    if role == "strongest_support":
        return f"Use this as load-bearing support for the default answer: {claim}"
    return f"Use this context only if it improves the decision read: {claim}"


def _prose_instruction(role: str) -> str:
    if role == "scope_boundary":
        return "State the practical boundary or population/scope limitation when it changes the decision."
    if role == "decision_crux":
        return "Name the uncertainty or distinction that could change the answer."
    if role == "strongest_counterweight":
        return "Give the counterweight its force, then explain whether it changes the answer."
    if role == "quantitative_anchor":
        return "Use the quantity to calibrate strength of claim rather than as a bare statistic."
    if role == "strongest_support":
        return "Connect the support directly to the answer."
    return "Use only if it improves the reader's decision."


def _why_it_matters(role: str, item: dict[str, Any]) -> str:
    explicit = str(item.get("decision_relevance") or item.get("memo_inclusion_rationale") or item.get("include_reason") or "").strip()
    if explicit:
        return explicit
    if role == "scope_boundary":
        return "Prevents the memo from applying the answer outside the supported population, dose, endpoint, or evidence type."
    if role == "strongest_counterweight":
        return "Keeps the memo from sounding stronger than the evidence supports."
    if role == "quantitative_anchor":
        return "Calibrates the strength, magnitude, or uncertainty of the answer."
    if role == "decision_crux":
        return "Identifies what could change the decision."
    if role == "strongest_support":
        return "Supplies load-bearing support for the best current answer."
    return "Adds context only if it changes interpretation, confidence, or practical use."


def _acceptable_expression(
    role: str,
    claim: str,
    *,
    source_ids: list[str],
    quantities: list[dict[str, Any]],
    validation_terms: list[str],
) -> dict[str, Any]:
    return {
        "must_attach_to_claim": True,
        "required_terms_or_equivalents": validation_terms[:8],
        "required_source_ids": source_ids,
        "required_quantity_values": [str(quantity.get("value") or "").strip() for quantity in quantities if str(quantity.get("value") or "").strip()],
        "semantic_job": _prose_instruction(role),
        "claim_to_preserve": claim,
    }


def _sanitize_claim(claim: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(claim or "")).strip()
    cleaned = re.sub(r"\bcrux\s+for\b", "as it relates to", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bprimary driver\b", "potentially important driver", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bconsistently neutralized\b", "qualified", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bbyproduct of\b", "partly explained by", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\binherent property of\b", "effect unique to", cleaned, flags=re.IGNORECASE)
    return cleaned


def _validation_terms(role: str, claim: str, statement: str) -> list[str]:
    if role == "scope_boundary":
        return ["scope", "applies", "apply", "population", "subgroup", "boundary", "condition", "without", "history"]
    return _dedupe([*_content_terms(claim)[:8], *_content_terms(statement)[:4]])[:10]


def _load_bearing_quantities(item: dict[str, Any]) -> list[dict[str, Any]]:
    role = str(item.get("role") or "")
    if role == "scope_boundary":
        return []
    rows = []
    for quantity in _list(item.get("quantities")):
        if not isinstance(quantity, dict):
            continue
        value = str(quantity.get("value") or "").strip()
        if value:
            rows.append(
                {
                    "value": value,
                    "interpretation": str(quantity.get("interpretation") or "").strip(),
                    "retention_phrase": str(quantity.get("retention_phrase") or "").strip(),
                    "source_ids": _dedupe(
                        [
                            *_string_list(quantity.get("source_ids")),
                            *_string_list(_dict(quantity.get("assertion_bundle")).get("source_ids")),
                        ]
                    ),
                    "source_labels": _string_list(quantity.get("source_labels")) or _string_list(quantity.get("source_label")),
                    "quantity_role": str(quantity.get("quantity_role") or "").strip(),
                    "quantity_id": str(quantity.get("quantity_id") or "").strip(),
                    "source_evidence_item_id": str(quantity.get("source_evidence_item_id") or "").strip(),
                    "memo_use": str(quantity.get("memo_use") or "").strip(),
                    "must_retain": bool(quantity.get("must_retain")) if "must_retain" in quantity else None,
                    "analyst_quantity_relevance": quantity.get("analyst_quantity_relevance") if isinstance(quantity.get("analyst_quantity_relevance"), dict) else {},
                }
            )
    return rows


def _source_labels(item: dict[str, Any]) -> list[str]:
    return _dedupe([*_string_list(item.get("source_labels")), str(item.get("source_label") or "").strip()])


def _source_ids(item: dict[str, Any]) -> list[str]:
    return _dedupe(
        [
            *_string_list(item.get("source_ids")),
            *[
                source_id
                for quantity in _list(item.get("quantities"))
                if isinstance(quantity, dict)
                for source_id in _string_list(quantity.get("source_ids"))
            ],
            *[
                source_id
                for quantity in _list(item.get("quantities"))
                if isinstance(quantity, dict)
                for source_id in _string_list(_dict(quantity.get("assertion_bundle")).get("source_ids"))
            ],
        ]
    )


def _content_terms(text: str) -> list[str]:
    stop = {
        "about",
        "after",
        "against",
        "answer",
        "associated",
        "between",
        "claim",
        "decision",
        "evidence",
        "from",
        "into",
        "that",
        "their",
        "this",
        "using",
        "with",
        "without",
    }
    terms = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}", str(text).lower()):
        if token not in stop:
            terms.append(token)
    return _dedupe(terms)


def _first(values: list[str]) -> str:
    return values[0] if values else ""
