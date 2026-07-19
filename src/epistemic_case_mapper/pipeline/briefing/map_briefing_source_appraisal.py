from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_appraisal_policy import (
    allowed_wording_from_flags as _allowed_wording_from_flags,
    claim_use_context as _claim_use_context,
    declared_document_type as _declared_document_type,
    document_flags as _document_flags,
    document_type as _document_type,
    endpoint_kind as _endpoint_kind,
    evidence_proximity as _evidence_proximity,
    interpretation_caveats as _interpretation_caveats,
    more_restrictive_use as _more_restrictive_use,
    recommended_use as _recommended_use,
    source_use_warnings as _source_use_warnings,
)
from epistemic_case_mapper.model_backends import model_parallelism, run_model_backend, run_parallel


class SourceInterpretationCaveat(BaseModel):
    model_config = ConfigDict(extra="forbid")

    caveat_type: str
    explanation: str
    basis: Literal["excerpt", "metadata", "not_found", "model_uncertain"] = "model_uncertain"
    evidence_excerpt: str = ""
    affected_claim_types: list[str] = Field(default_factory=list)
    downstream_handling: str = ""
    review_required: bool = False


class SourceCaveatAppraisal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    document_type: Literal[
        "empirical_study",
        "evidence_synthesis",
        "guidance_or_advisory",
        "contextual_summary",
        "legal_or_regulatory",
        "dataset_or_record",
        "mixed_or_unknown",
    ] = "mixed_or_unknown"
    evidence_proximity: Literal["primary", "synthesis", "guidance", "summary", "official_record", "unknown"] = "unknown"
    decision_directness: Literal["direct", "partial", "indirect", "unknown"] = "unknown"
    recommended_use: Literal[
        "load_bearing_ok",
        "load_bearing_with_qualification",
        "corroborate_or_bound",
        "decision_context_or_corroboration",
        "background_or_context",
        "human_review_needed",
    ] = "human_review_needed"
    caveat_summary: str = ""
    interpretation_caveats: list[SourceInterpretationCaveat] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    independence_caveats: list[str] = Field(default_factory=list)
    claim_scope_limits: list[str] = Field(default_factory=list)
    suspicious_flags: list[str] = Field(default_factory=list)


class SourceCaveatAppraisalOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    appraisals: list[SourceCaveatAppraisal] = Field(default_factory=list)


def build_source_appraisal_report(
    *,
    source_evidence_cards: dict[str, Any],
    evidence_quality_report: dict[str, Any],
    source_caveat_appraisal_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cards = [card for card in _list(source_evidence_cards.get("cards")) if isinstance(card, dict)]
    quality_components = evidence_quality_report.get("quality_components", {})
    if not isinstance(quality_components, dict):
        quality_components = {}
    cards_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        source_id = str(card.get("source_id") or "").strip()
        if source_id:
            cards_by_source[source_id].append(card)
    appraisals = [
        _source_appraisal(source_id, source_cards, quality_components=quality_components)
        for source_id, source_cards in sorted(cards_by_source.items())
    ]
    appraisals = _merge_model_appraisals(appraisals, source_caveat_appraisal_report or {})
    missing_appraisal_count = sum(1 for card in cards if not str(card.get("source_id") or "").strip())
    issues = [
        *(["no_source_cards_available"] if not cards else []),
        *(["source_cards_missing_source_id"] if missing_appraisal_count else []),
    ]
    return {
        "schema_id": "source_appraisal_report_v1",
        "method": "generic_source_use_appraisal_from_cards_and_quality_components",
        "status": "ready" if not issues else "warning",
        "source_count": len(appraisals),
        "card_count": len(cards),
        "missing_appraisal_count": missing_appraisal_count,
        "appraisals": appraisals,
        "appraisal_by_source_id": {str(row.get("source_id")): row for row in appraisals if row.get("source_id")},
        "issues": issues,
    }


def run_source_caveat_appraisal(
    *,
    source_evidence_cards: dict[str, Any],
    evidence_quality_report: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    packets = build_source_appraisal_packets(
        source_evidence_cards=source_evidence_cards,
        evidence_quality_report=evidence_quality_report,
    )
    if backend.strip() == "prompt":
        report = _deterministic_caveat_report(packets, status="prompt_backend_scaffold")
        return {
            "source_appraisal_packets": {"schema_id": "source_appraisal_packets_v1", "packets": packets},
            "source_caveat_appraisal_report": report,
            "source_caveat_appraisal_run_report": _run_report(
                "prompt_backend_scaffold",
                report,
                backend=backend,
                backend_timeout=backend_timeout,
            ),
        }
    results = run_parallel(
        packets,
        lambda packet: _run_single_source_caveat_appraisal(
            packet,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
        ),
        max_workers=_source_appraisal_parallelism(backend),
    )
    valid_appraisals = [row["appraisal"] for row in results if row.get("valid") and isinstance(row.get("appraisal"), dict)]
    fallback_appraisals = [
        _deterministic_model_appraisal(packet, status="backend_error_or_invalid_fallback")
        for packet, result in zip(packets, results)
        if not result.get("valid")
    ]
    report = {
        "schema_id": "source_caveat_appraisal_report_v1",
        "status": "accepted_with_fallbacks" if fallback_appraisals else "accepted",
        "method": "bounded_source_packet_llm_caveat_appraisal",
        "backend": backend,
        "source_count": len(packets),
        "valid_appraisal_count": len(valid_appraisals),
        "fallback_appraisal_count": len(fallback_appraisals),
        "appraisals": [*valid_appraisals, *fallback_appraisals],
        "per_source_reports": results,
        "issues": _dedupe([issue for row in results for issue in _string_list(row.get("issues"))]),
    }
    return {
        "source_appraisal_packets": {"schema_id": "source_appraisal_packets_v1", "packets": packets},
        "source_caveat_appraisal_report": report,
        "source_caveat_appraisal_run_report": _run_report(report["status"], report, backend=backend, backend_timeout=backend_timeout),
    }


def build_source_appraisal_packets(
    *,
    source_evidence_cards: dict[str, Any],
    evidence_quality_report: dict[str, Any],
) -> list[dict[str, Any]]:
    cards = [card for card in _list(source_evidence_cards.get("cards")) if isinstance(card, dict)]
    quality = evidence_quality_report.get("quality_components", {})
    quality = quality if isinstance(quality, dict) else {}
    by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        source_id = str(card.get("source_id") or "").strip()
        if source_id:
            by_source[source_id].append(card)
    return [
        _source_packet(source_id, source_cards, quality_components=quality)
        for source_id, source_cards in sorted(by_source.items())
    ]


def appraisal_for_sources(source_appraisal_report: dict[str, Any], source_refs: list[str]) -> dict[str, Any]:
    report = source_appraisal_report if isinstance(source_appraisal_report, dict) else {}
    lookup = _appraisal_lookup(report)
    all_appraisals = _appraisal_rows(report)
    appraisals = []
    for ref in source_refs:
        key = _source_key(ref)
        if key in lookup:
            appraisals.append(lookup[key])
            continue
        fuzzy = _fuzzy_appraisal_match(str(ref), all_appraisals)
        if fuzzy:
            appraisals.append(fuzzy)
    appraisals = _dedupe_appraisals(appraisals)
    if not appraisals:
        return {
            "status": "missing",
            "source_appraisal_ids": [],
            "document_types": [],
            "recommended_uses": [],
            "decision_directness": "unknown",
            "allowed_wording": _allowed_wording_from_flags({"missing_appraisal"}),
            "source_use_warnings": ["source_appraisal_missing"],
        }
    flags = {flag for row in appraisals for flag in _string_list(row.get("appraisal_flags"))}
    recommended_uses = _dedupe([str(row.get("recommended_use") or "") for row in appraisals if row.get("recommended_use")])
    directness_values = _dedupe([str(row.get("decision_directness") or "") for row in appraisals if row.get("decision_directness")])
    warnings = _dedupe([warning for row in appraisals for warning in _string_list(row.get("source_use_warnings"))])
    caveats = _dedupe([caveat for row in appraisals for caveat in _string_list(row.get("interpretation_caveats"))])
    return {
        "status": "ready",
        "source_appraisal_ids": _dedupe([str(row.get("source_appraisal_id") or "") for row in appraisals if row.get("source_appraisal_id")]),
        "document_types": _dedupe([str(row.get("document_type") or "") for row in appraisals if row.get("document_type")]),
        "evidence_proximity": _dedupe([str(row.get("evidence_proximity") or "") for row in appraisals if row.get("evidence_proximity")]),
        "recommended_uses": recommended_uses,
        "decision_directness": _least_direct(directness_values),
        "allowed_wording": _allowed_wording_from_flags(flags),
        "source_use_warnings": warnings,
        "interpretation_caveats": caveats[:8],
    }


def attach_source_appraisal_to_rows(rows: list[dict[str, Any]], source_appraisal_report: dict[str, Any]) -> None:
    report = source_appraisal_report if isinstance(source_appraisal_report, dict) else {}
    if not report:
        return
    for row in rows:
        if not isinstance(row, dict):
            continue
        existing = row.get("source_appraisal") if isinstance(row.get("source_appraisal"), dict) else {}
        if existing.get("status") == "ready":
            continue
        source_refs = _dedupe([*_string_list(row.get("source_ids")), *_string_list(row.get("source_labels"))])
        appraisal = appraisal_for_sources(report, source_refs)
        if appraisal.get("status") != "ready":
            continue
        row["source_appraisal"] = appraisal
        row["source_use_warnings"] = _string_list(appraisal.get("source_use_warnings"))
        row["allowed_wording"] = appraisal.get("allowed_wording") if isinstance(appraisal.get("allowed_wording"), dict) else {}


def build_source_appraisal_decision_grade_report(writer_packet: dict[str, Any]) -> dict[str, Any]:
    units = [unit for unit in _list(writer_packet.get("evidence_units")) if isinstance(unit, dict)]
    appraised = [unit for unit in units if isinstance(unit.get("source_appraisal"), dict) and unit["source_appraisal"].get("status") == "ready"]
    warnings = [warning for unit in units for warning in _string_list(unit.get("source_use_warnings"))]
    allowed = [unit.get("allowed_wording") for unit in units if isinstance(unit.get("allowed_wording"), dict)]
    causal_restricted = sum(1 for row in allowed if row.get("causal_language_allowed") is False)
    contextualized = sum(
        1
        for warning in warnings
        if warning in {
            "association_not_causation",
            "indirect_endpoint",
            "guidance_not_independent_empirical_evidence",
            "context_not_primary_evidence",
        }
    )
    source_use_limited = sum(1 for warning in warnings if warning.startswith("recommended_use_") or warning == "quality_limit")
    issues = [
        *(["no_source_appraised_units"] if units and not appraised else []),
        *(["no_calibration_warnings"] if units and not warnings else []),
    ]
    return {
        "schema_id": "source_appraisal_decision_grade_report_v1",
        "status": "improved_decision_grade_scaffold" if appraised and (causal_restricted or contextualized or source_use_limited) else "no_visible_appraisal_uplift",
        "evidence_unit_count": len(units),
        "source_appraised_unit_count": len(appraised),
        "causal_restricted_unit_count": causal_restricted,
        "calibration_warning_count": len(warnings),
        "decision_grade_handles": {
            "association_language_handles": warnings.count("association_not_causation"),
            "indirect_endpoint_handles": warnings.count("indirect_endpoint"),
            "guidance_context_handles": warnings.count("guidance_not_independent_empirical_evidence"),
            "context_not_primary_handles": warnings.count("context_not_primary_evidence"),
            "source_use_limit_handles": source_use_limited,
        },
        "issues": issues,
    }


def _source_packet(source_id: str, cards: list[dict[str, Any]], *, quality_components: dict[str, Any]) -> dict[str, Any]:
    manifest_metadata = _first_metadata(cards)
    independence_caveats = _dedupe(
        [
            *_string_list(manifest_metadata.get("independence_caveats")),
            *[caveat for card in cards for caveat in _string_list(card.get("independence_caveats"))],
        ]
    )
    snippets = []
    for card in cards[:10]:
        card_id = str(card.get("source_card_id") or "")
        quality = quality_components.get(card_id, {}) if isinstance(quality_components.get(card_id), dict) else {}
        snippets.append(
            _drop_empty(
                {
                    "source_card_id": card_id,
                    "excerpt": _short_text(str(card.get("source_quote_or_excerpt") or ""), 900),
                    "evidence_type": str(card.get("evidence_type") or ""),
                    "outcome_or_endpoint": str(card.get("outcome_or_endpoint") or ""),
                    "decision_relevance_score": card.get("decision_relevance_score"),
                    "anchor_confidence": card.get("anchor_confidence"),
                    "quality_component": quality,
                    "limitations": _string_list(card.get("limitations"))[:5],
                    "quantity_values": _string_list(card.get("quantity_values"))[:6],
                    "source_metadata": card.get("source_metadata") if isinstance(card.get("source_metadata"), dict) else {},
                }
            )
        )
    return {
        "schema_id": "source_appraisal_packet_v1",
        "source_id": source_id,
        "source_label": _first_text(cards, "source_title") or source_id,
        "source_metadata": manifest_metadata,
        "independence_caveats": independence_caveats[:8],
        "card_count": len(cards),
        "packet_scope": "source_cards_bounded",
        "cards": snippets,
    }


def _run_single_source_caveat_appraisal(
    packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    prompt = build_source_caveat_appraisal_prompt(packet)
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        return {
            "source_id": packet.get("source_id"),
            "valid": False,
            "status": "backend_error",
            "prompt": prompt,
            "raw": "",
            "issues": [str(exc)],
        }
    payload = _extract_json(result.text)
    parse = _parse_source_caveat_payload(payload, expected_source_id=str(packet.get("source_id") or ""))
    return {
        "source_id": packet.get("source_id"),
        "valid": parse["valid"],
        "status": parse["status"],
        "prompt": prompt,
        "raw": result.text,
        "appraisal": parse.get("appraisal", {}),
        "issues": parse.get("issues", []),
    }


def build_source_caveat_appraisal_prompt(packet: dict[str, Any]) -> str:
    contract = {
        "appraisals": [
            {
                "source_id": packet.get("source_id"),
                "document_type": "empirical_study | evidence_synthesis | guidance_or_advisory | contextual_summary | legal_or_regulatory | dataset_or_record | mixed_or_unknown",
                "evidence_proximity": "primary | synthesis | guidance | summary | official_record | unknown",
                "decision_directness": "direct | partial | indirect | unknown",
                "recommended_use": "load_bearing_ok | load_bearing_with_qualification | corroborate_or_bound | decision_context_or_corroboration | background_or_context | human_review_needed",
                "caveat_summary": "one sentence",
                "interpretation_caveats": [
                    {
                        "caveat_type": "method_limit | source_role | directness | independence | transparency | scope | other",
                        "explanation": "brief source-grounded explanation",
                        "basis": "excerpt | metadata | not_found | model_uncertain",
                        "evidence_excerpt": "short excerpt or empty when basis is not_found/model_uncertain",
                        "affected_claim_types": ["claim type"],
                        "downstream_handling": "how memo should use this source",
                        "review_required": False,
                    }
                ],
                "missing_information": ["missing transparency or method detail"],
                "independence_caveats": ["correlation or double-counting caution"],
                "claim_scope_limits": ["population/setting/endpoint limit"],
                "suspicious_flags": [],
            }
        ]
    }
    return (
        "You are appraising one source for decision-ready evidence use.\n"
        "Judge how claims from this source may be used for later decision analysis.\n"
        "Use only the supplied manifest metadata, independence caveats, source-card excerpts, and quality components. If information is absent, mark it as not_found or unknown.\n"
        "Return strict JSON matching this shape:\n"
        f"{json.dumps(contract, indent=2)}\n\n"
        "Source appraisal packet:\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}\n"
    )


def _parse_source_caveat_payload(payload: Any, *, expected_source_id: str) -> dict[str, Any]:
    try:
        parsed = SourceCaveatAppraisalOutput.model_validate(payload).model_dump()
    except ValidationError as exc:
        return {"valid": False, "status": "schema_invalid", "issues": [str(exc)]}
    matches = [row for row in _list(parsed.get("appraisals")) if str(row.get("source_id") or "") == expected_source_id]
    if not matches:
        return {"valid": False, "status": "missing_expected_source", "issues": [f"missing_source_id:{expected_source_id}"]}
    appraisal = _canonical_model_appraisal(matches[0])
    return {"valid": True, "status": "accepted", "appraisal": appraisal, "issues": []}


def _canonical_model_appraisal(row: dict[str, Any]) -> dict[str, Any]:
    caveats = [caveat for caveat in _list(row.get("interpretation_caveats")) if isinstance(caveat, dict)]
    return {
        "source_id": row.get("source_id"),
        "document_type": row.get("document_type"),
        "evidence_proximity": row.get("evidence_proximity"),
        "decision_directness": row.get("decision_directness"),
        "recommended_use": row.get("recommended_use"),
        "caveat_summary": _short_text(str(row.get("caveat_summary") or ""), 360),
        "interpretation_caveats": [_short_text(str(c.get("explanation") or ""), 260) for c in caveats if c.get("explanation")][:8],
        "claim_scope_limits": _string_list(row.get("claim_scope_limits"))[:8],
        "missing_information": _string_list(row.get("missing_information"))[:8],
        "independence_caveats": _string_list(row.get("independence_caveats"))[:6],
        "suspicious_flags": _string_list(row.get("suspicious_flags"))[:6],
        "model_appraised": True,
    }


def _deterministic_caveat_report(packets: list[dict[str, Any]], *, status: str) -> dict[str, Any]:
    appraisals = [_deterministic_model_appraisal(packet, status=status) for packet in packets]
    return {
        "schema_id": "source_caveat_appraisal_report_v1",
        "status": status,
        "method": "deterministic_scaffold_from_source_appraisal_packets",
        "source_count": len(packets),
        "valid_appraisal_count": len(appraisals),
        "fallback_appraisal_count": len(appraisals),
        "appraisals": appraisals,
        "per_source_reports": [
            {"source_id": packet.get("source_id"), "valid": True, "status": status, "issues": []}
            for packet in packets
        ],
        "issues": [],
    }


def _deterministic_model_appraisal(packet: dict[str, Any], *, status: str) -> dict[str, Any]:
    source_id = str(packet.get("source_id") or "")
    source_card_report = {
        "cards": [
            {
                "source_card_id": card.get("source_card_id"),
                "source_id": source_id,
                "source_title": packet.get("source_label"),
                "source_quote_or_excerpt": card.get("excerpt"),
                "evidence_type": card.get("evidence_type"),
                "outcome_or_endpoint": card.get("outcome_or_endpoint"),
                "anchor_confidence": card.get("anchor_confidence"),
                "decision_relevance_score": card.get("decision_relevance_score"),
                "limitations": card.get("limitations", []),
                "source_metadata": packet.get("source_metadata", {}),
                "independence_caveats": packet.get("independence_caveats", []),
            }
            for card in _list(packet.get("cards"))
            if isinstance(card, dict)
        ]
    }
    quality = {
        "quality_components": {
            str(card.get("source_card_id") or ""): card.get("quality_component")
            for card in _list(packet.get("cards"))
            if isinstance(card, dict) and isinstance(card.get("quality_component"), dict)
        }
    }
    base = build_source_appraisal_report(source_evidence_cards=source_card_report, evidence_quality_report=quality)["appraisals"]
    row = dict(base[0]) if base else {"source_id": source_id}
    row["model_appraised"] = False
    row["model_appraisal_status"] = status
    return row


def _merge_model_appraisals(appraisals: list[dict[str, Any]], report: dict[str, Any]) -> list[dict[str, Any]]:
    model_by_source = {
        str(row.get("source_id") or ""): row
        for row in _list(report.get("appraisals"))
        if isinstance(row, dict) and str(row.get("source_id") or "").strip()
    }
    if not model_by_source:
        return appraisals
    merged = []
    for appraisal in appraisals:
        source_id = str(appraisal.get("source_id") or "")
        model = model_by_source.get(source_id)
        merged.append(_merge_single_model_appraisal(appraisal, model) if model else appraisal)
    return merged


def _merge_single_model_appraisal(base: dict[str, Any], model: dict[str, Any]) -> dict[str, Any]:
    flags = set(_string_list(base.get("appraisal_flags")))
    flags.update(_model_flags(model))
    directness = str(model.get("decision_directness") or base.get("decision_directness") or "unknown")
    recommended = _more_restrictive_use(
        str(base.get("recommended_use") or _recommended_use(flags, directness)),
        str(model.get("recommended_use") or ""),
    )
    declared_source_type = str(base.get("declared_source_type") or "")
    return {
        **base,
        "document_type": base.get("document_type") if declared_source_type else model.get("document_type") or base.get("document_type"),
        "evidence_proximity": model.get("evidence_proximity") or base.get("evidence_proximity"),
        "decision_directness": directness,
        "recommended_use": recommended,
        "claim_use_context": _claim_use_context(recommended),
        "appraisal_flags": sorted(flags),
        "interpretation_caveats": _dedupe([*_string_list(base.get("interpretation_caveats")), *_string_list(model.get("interpretation_caveats"))])[:12],
        "source_use_warnings": _source_use_warnings(flags, recommended),
        "allowed_wording": _allowed_wording_from_flags(flags),
        "model_appraised": bool(model.get("model_appraised")),
        "model_caveat_summary": model.get("caveat_summary", ""),
        "model_claim_scope_limits": _string_list(model.get("claim_scope_limits"))[:8],
        "model_missing_information": _string_list(model.get("missing_information"))[:8],
        "model_independence_caveats": _string_list(model.get("independence_caveats"))[:6],
    }


def _source_appraisal(
    source_id: str,
    cards: list[dict[str, Any]],
    *,
    quality_components: dict[str, Any],
) -> dict[str, Any]:
    title = _first_text(cards, "source_title") or source_id
    manifest_metadata = _first_metadata(cards)
    declared_source_type = str(
        manifest_metadata.get("source_type")
        or _first_text(cards, "declared_source_type")
        or ""
    ).strip()
    provenance_level = str(
        manifest_metadata.get("provenance_level")
        or _first_text(cards, "provenance_level")
        or "unspecified"
    ).strip()
    evidence_role = str(
        manifest_metadata.get("evidence_role")
        or _first_text(cards, "evidence_role")
        or "unspecified"
    ).strip()
    independence_caveats = _dedupe(
        [
            *_string_list(manifest_metadata.get("independence_caveats")),
            *[caveat for card in cards for caveat in _string_list(card.get("independence_caveats"))],
        ]
    )
    evidence_text = " ".join(
        [
            source_id,
            title,
            *[str(card.get("evidence_type") or "") for card in cards],
            *[str(card.get("source_quote_or_excerpt") or "") for card in cards],
        ]
    ).lower()
    endpoint_text = " ".join(str(card.get("outcome_or_endpoint") or "") for card in cards).lower()
    limitation_values = _dedupe([limit for card in cards for limit in _string_list(card.get("limitations"))])
    quality_rows = [
        quality_components.get(str(card.get("source_card_id") or ""), {})
        for card in cards
        if isinstance(quality_components.get(str(card.get("source_card_id") or "")), dict)
    ]
    directness_values = [str(row.get("directness") or "") for row in quality_rows if row.get("directness")]
    quality_values = [str(row.get("overall") or "") for row in quality_rows if row.get("overall")]
    anchor_values = [str(card.get("anchor_confidence") or "missing") for card in cards]
    role_values = [str(card.get("supports_challenges_or_scopes") or "") for card in cards if card.get("supports_challenges_or_scopes")]
    document_type = _declared_document_type(declared_source_type) if declared_source_type else _document_type(evidence_text)
    evidence_proximity = _evidence_proximity(document_type)
    endpoint_kind = _endpoint_kind(endpoint_text)
    flags = set(_document_flags(document_type, endpoint_kind, evidence_text))
    if independence_caveats:
        flags.add("independence_not_established")
    if manifest_metadata and provenance_level in {"unspecified", "local_note", "synthetic_note"}:
        flags.add("provenance_not_decision_grade")
    if bool(manifest_metadata.get("needs_upgrade")):
        flags.add("source_needs_upgrade")
    if "narrative" in declared_source_type.lower() or "scoping" in declared_source_type.lower():
        flags.add("secondary_or_scoping_review")
    if any(value == "missing" for value in anchor_values):
        flags.add("anchor_limit")
    if limitation_values:
        flags.add("explicit_limitations")
    if any(value in {"weak", "indirect", "unknown"} for value in quality_values):
        flags.add("quality_limit")
    decision_directness = _least_direct(directness_values)
    if endpoint_kind in {"surrogate", "proxy"} and decision_directness == "direct":
        decision_directness = "partial"
    recommended_use = _recommended_use(flags, decision_directness)
    return {
        "source_appraisal_id": f"sa_{_slug(source_id)}",
        "source_id": source_id,
        "source_label": title,
        "declared_source_type": declared_source_type,
        "provenance_level": provenance_level,
        "evidence_role": evidence_role,
        "manifest_metadata": manifest_metadata,
        "independence_caveats": independence_caveats,
        "source_card_ids": [str(card.get("source_card_id") or "") for card in cards if card.get("source_card_id")],
        "document_type": document_type,
        "evidence_proximity": evidence_proximity,
        "decision_directness": decision_directness,
        "endpoint_kind": endpoint_kind,
        "recommended_use": recommended_use,
        "claim_use_context": _claim_use_context(recommended_use),
        "appraisal_flags": sorted(flags),
        "interpretation_caveats": _dedupe([*_interpretation_caveats(flags), *independence_caveats]),
        "source_use_warnings": _source_use_warnings(flags, recommended_use),
        "allowed_wording": _allowed_wording_from_flags(flags),
        "observed_roles": sorted(set(role_values)),
        "quality_component_counts": dict(Counter(quality_values)),
        "anchor_component_counts": dict(Counter(anchor_values)),
        "limitation_examples": limitation_values[:6],
    }


def _first_metadata(cards: list[dict[str, Any]]) -> dict[str, Any]:
    for card in cards:
        value = card.get("source_metadata")
        if isinstance(value, dict) and value:
            return dict(value)
    return {}


def _model_flags(model: dict[str, Any]) -> set[str]:
    flags: set[str] = set()
    recommended = str(model.get("recommended_use") or "")
    directness = str(model.get("decision_directness") or "")
    document_type = str(model.get("document_type") or "")
    caveat_text = " ".join(
        [
            str(model.get("caveat_summary") or ""),
            " ".join(_string_list(model.get("interpretation_caveats"))),
            " ".join(_string_list(model.get("claim_scope_limits"))),
            " ".join(_string_list(model.get("missing_information"))),
        ]
    ).lower()
    if directness == "indirect":
        flags.add("quality_limit")
    if recommended in {"corroborate_or_bound", "background_or_context", "decision_context_or_corroboration", "human_review_needed"}:
        flags.add("quality_limit")
    if document_type == "guidance_or_advisory":
        flags.add("guidance_not_independent_empirical_evidence")
    if document_type == "contextual_summary":
        flags.add("context_not_primary_evidence")
    if "association" in caveat_text or "confound" in caveat_text or "causal" in caveat_text:
        flags.add("association_not_causation")
    if "surrogate" in caveat_text or "biomarker" in caveat_text or "indirect endpoint" in caveat_text:
        flags.add("indirect_endpoint")
    if "scope" in caveat_text or "population" in caveat_text or "applicability" in caveat_text:
        flags.add("scope_sensitive")
    if "independ" in caveat_text or "double count" in caveat_text:
        flags.add("synthesis_depends_on_included_sources")
        flags.add("independence_not_established")
    return flags


def _least_direct(values: list[str]) -> str:
    order = {"indirect": 0, "partial": 1, "direct": 2}
    normalized = [value for value in values if value in order]
    if not normalized:
        return "unknown"
    return min(normalized, key=lambda value: order[value])


def _appraisal_lookup(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup = {}
    for row in _appraisal_rows(report):
        aliases = [row.get("source_id"), row.get("source_label")]
        aliases.extend(str(row.get("source_id") or "").replace("_", " ").split())
        for key in aliases:
            if str(key or "").strip():
                lookup[_source_key(str(key))] = row
    return lookup


def _appraisal_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in _list(report.get("appraisals")) if isinstance(row, dict)]
    by_source = report.get("appraisal_by_source_id")
    if isinstance(by_source, dict):
        rows.extend(row for row in by_source.values() if isinstance(row, dict))
    return _dedupe_appraisals(rows)


def _fuzzy_appraisal_match(source_ref: str, appraisals: list[dict[str, Any]]) -> dict[str, Any] | None:
    ref_terms = _label_terms(source_ref)
    if not ref_terms:
        return None
    best: tuple[float, dict[str, Any] | None] = (0.0, None)
    for appraisal in appraisals:
        labels = [str(appraisal.get("source_id") or ""), str(appraisal.get("source_label") or "")]
        terms = set().union(*[_label_terms(label) for label in labels])
        if not terms:
            continue
        score = len(ref_terms & terms) / max(1, min(len(ref_terms), len(terms)))
        if score > best[0]:
            best = (score, appraisal)
    return best[1] if best[0] >= 0.45 else None


def _dedupe_appraisals(appraisals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    seen = set()
    for appraisal in appraisals:
        key = str(appraisal.get("source_id") or appraisal.get("source_label") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        rows.append(appraisal)
    return rows


def _label_terms(label: str) -> set[str]:
    stop = {
        "and", "the", "for", "with", "from", "study", "review", "source", "evidence",
        "risk", "dietary", "consumption", "association", "associations",
    }
    return {
        term
        for term in re.findall(r"[a-z0-9]+", str(label or "").lower())
        if len(term) > 2 and term not in stop
    }


def _extract_json(raw: str) -> Any:
    text = str(raw or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        try:
            return json.loads(fenced.group(1).strip())
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return {}


def _source_appraisal_parallelism(backend: str) -> int:
    return min(model_parallelism(backend), 2) if backend.strip().startswith("ollama:") else model_parallelism(backend)


def _run_report(status: str, report: dict[str, Any], *, backend: str, backend_timeout: int | None) -> dict[str, Any]:
    return {
        "schema_id": "source_caveat_appraisal_run_report_v1",
        "status": status,
        "backend": backend,
        "live_enrichment_required": backend.strip() != "prompt",
        "backend_timeout_seconds": backend_timeout,
        "source_count": report.get("source_count", 0),
        "valid_appraisal_count": report.get("valid_appraisal_count", 0),
        "fallback_appraisal_count": report.get("fallback_appraisal_count", 0),
        "issue_count": len(_list(report.get("issues"))),
        "issues": _string_list(report.get("issues"))[:20],
    }


def _first_text(cards: list[dict[str, Any]], key: str) -> str:
    for card in cards:
        value = str(card.get(key) or "").strip()
        if value:
            return value
    return ""


def _source_key(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", str(value or "").strip()).strip("_").lower()
    return _short_text(slug or "source", 80)


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}
