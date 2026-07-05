from __future__ import annotations

from typing import Any


def model_briefing_scaffold(scaffold: dict[str, Any]) -> dict[str, Any]:
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    evidence_ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
    compact_ledger = {
        "family_counts": evidence_ledger.get("family_counts", {}),
        "decision_concept_counts": evidence_ledger.get("decision_concept_counts", {}),
        "weight_counts": evidence_ledger.get("weight_counts", {}),
        "top_evidence_by_section": _compact_top_evidence_sections(evidence_ledger.get("top_evidence_by_section", {})),
        "notes": evidence_ledger.get("notes", []),
    }
    compact_decision_model = {
        key: decision_model.get(key)
        for key in (
            "default_answer",
            "decision_slots",
            "missing_decision_slots",
            "evidence_families",
            "main_reasons",
            "strongest_counterarguments",
            "tension_resolutions",
            "practical_recommendations",
            "what_would_change_answer",
            "prose_requirements",
        )
    }
    return {
        "quality_status": scaffold.get("quality_status"),
        "quality_score": scaffold.get("quality_score"),
        "confidence_cap": scaffold.get("confidence_cap"),
        "briefing_contract": _model_safe_value(scaffold.get("briefing_contract")),
        "decision_frame": _model_safe_value(scaffold.get("decision_frame")),
        "decision_model": _model_safe_value(compact_decision_model),
        "graph_synthesis_packet": _model_safe_value(scaffold.get("graph_synthesis_packet")),
        "decision_synthesis_model": _model_safe_value(scaffold.get("decision_synthesis_model")),
        "argument_model": _model_safe_value(scaffold.get("argument_model")),
        "decision_argument_artifacts": _model_safe_value(scaffold.get("decision_argument_artifacts")),
        "evidence_compression_table": _model_safe_value(scaffold.get("evidence_compression_table")),
        "concept_evidence_packets": _model_concept_evidence_packets(scaffold.get("concept_evidence_packets")),
        "map_sufficiency_report": _model_safe_value(scaffold.get("map_sufficiency_report")),
        "briefing_plan": _model_safe_value(scaffold.get("briefing_plan")),
        "evidence_weighting_ledger": compact_ledger,
        "quantitative_anchors": _model_safe_value(scaffold.get("quantitative_anchors", [])[:10]),
        "quantitative_evidence_cards": _model_safe_value(scaffold.get("quantitative_evidence_cards", [])[:10]),
        "quantity_ledger_summary": {
            "quantity_count": scaffold.get("quantity_ledger", {}).get("quantity_count"),
            "quantitative_card_count": scaffold.get("quantity_ledger", {}).get("quantitative_card_count"),
            "type_counts": scaffold.get("quantity_ledger", {}).get("type_counts", {}),
        },
        "evidence_roles_for_deterministic_attachment": _model_safe_value(scaffold.get("evidence_roles")),
        "crux_candidates": _model_safe_value(scaffold.get("crux_candidates")),
        "refined_cruxes": _model_safe_value(scaffold.get("refined_cruxes")),
        "quality_issues": _model_safe_value(scaffold.get("quality_issues")),
    }


def _model_safe_value(value: Any) -> Any:
    if isinstance(value, dict):
        skipped = {
            "raw_claim",
            "raw_rationale",
            "excerpt",
            "supporting_excerpts",
            "context",
            "context_window",
            "source_anchor",
            "source_anchor_a",
            "source_anchor_b",
            "source_claim_support_excerpt",
            "target_claim_support_excerpt",
            "search_terms",
        }
        return {
            str(key): _model_safe_value(item)
            for key, item in value.items()
            if str(key) not in skipped and not _model_omits_field(str(key), item)
        }
    if isinstance(value, list):
        return [_model_safe_value(item) for item in value if not _model_omits_item(item)]
    if isinstance(value, str):
        return _compressed_claim_text(value, {})
    return value


def _model_omits_item(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    if item.get("appendix_only"):
        return True
    if str(item.get("evidence_use", "")).startswith("appendix"):
        return True
    if _is_study_scale_only_item(item):
        return True
    eligibility = item.get("eligibility", {}) if isinstance(item.get("eligibility"), dict) else {}
    return bool(eligibility.get("appendix_only"))


def _model_omits_field(key: str, item: Any) -> bool:
    return key == "quantitative_anchor" and _is_study_scale_quantity_text(str(item))


def _is_study_scale_only_item(item: dict[str, Any]) -> bool:
    evidence_type = str(item.get("evidence_type") or item.get("evidence_use") or "").strip().lower()
    if evidence_type != "study scale or follow-up context":
        return False
    quantities = item.get("quantities", [])
    quantity_text = " ".join(str(value) for value in quantities) if isinstance(quantities, list) else str(quantities)
    has_effect_signal = any(
        marker in quantity_text.lower()
        for marker in ("hr", "rr", "or ", "risk ratio", "hazard ratio", "confidence interval", "95% ci", "p=")
    )
    return not has_effect_signal


def _is_study_scale_quantity_text(text: str) -> bool:
    lower = text.lower()
    has_context_quantity = any(marker in lower for marker in ("participants", "subjects", "patients", "people", "years", "months"))
    has_effect_signal = any(
        marker in lower
        for marker in ("hr", "rr", "or ", "risk ratio", "hazard ratio", "confidence interval", "95% ci", "p=", "p <")
    )
    return has_context_quantity and not has_effect_signal


def _compact_top_evidence_sections(value: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(value, dict):
        return {}
    compact: dict[str, list[dict[str, Any]]] = {}
    for section, rows in value.items():
        compact_rows: list[dict[str, Any]] = []
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict) or _model_omits_item(row):
                continue
            noise = row.get("noise", {}) if isinstance(row.get("noise"), dict) else {}
            compact_rows.append(
                {
                    "claim_id": row.get("claim_id"),
                    "section": row.get("section"),
                    "weight": row.get("weight"),
                    "score": row.get("score"),
                    "source": row.get("source"),
                    "evidence_family": row.get("evidence_family"),
                    "decision_concepts": row.get("decision_concepts", []),
                    "noise_kind": noise.get("kind", "none"),
                    "claim": _compressed_claim_text(str(row.get("claim", "")), noise),
                }
            )
        compact[str(section)] = compact_rows[:6]
    return compact


def _model_concept_evidence_packets(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    compact_packets: list[dict[str, Any]] = []
    for packet in value.get("packets", []) if isinstance(value.get("packets"), list) else []:
        if not isinstance(packet, dict):
            continue
        compact_packets.append(
            {
                "concept": packet.get("concept"),
                "label": packet.get("label"),
                "synthesis_job": packet.get("synthesis_job"),
                "must_surface_terms": packet.get("must_surface_terms", []),
                "rows": [
                    {
                        "claim_id": row.get("claim_id"),
                        "source": row.get("source"),
                        "weight": row.get("weight"),
                        "claim": row.get("claim"),
                        "why_it_matters": row.get("why_it_matters"),
                    }
                    for row in packet.get("rows", [])[:3]
                    if isinstance(row, dict) and not _model_omits_item(row)
                ],
            }
        )
    return {
        "schema_id": value.get("schema_id"),
        "method": value.get("method"),
        "packets": compact_packets[:8],
    }


def _compressed_claim_text(claim: str, noise: dict[str, Any]) -> str:
    kind = str(noise.get("kind", "none"))
    if kind == "boilerplate_disclosure":
        return "The source includes extensive disclosures; treat this as source context, not substantive evidence."
    if kind == "publisher_or_license_boilerplate":
        return "The source includes publisher, license, or metadata boilerplate; do not use it as substantive evidence."
    return _short_text(claim, max_chars=260)


def _short_text(text: str, *, max_chars: int) -> str:
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip(" ,.;") + "..."
