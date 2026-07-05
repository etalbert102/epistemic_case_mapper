from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.main_memo_obligations import build_main_memo_obligation_plan
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.synthesis_uplift_packet import _parse_json


GLOBAL_MEMO_SECTIONS = [
    "Decision Brief",
    "Practical Read",
    "Why This Read",
    "Evidence Carrying the Conclusion",
    "Practical Scope and Exceptions",
    "Decision Cruxes",
    "Limits of the Current Map",
]

GLOBAL_MEMO_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "bottom_line_narrative": {"type": "string"},
        "reader_strategy": {"type": "string"},
        "section_plans": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section": {"type": "string"},
                    "thesis": {"type": "string"},
                    "target_words": {"type": "integer"},
                    "owned_obligation_ids": {"type": "array", "items": {"type": "string"}},
                    "owned_evidence_roles": {"type": "array", "items": {"type": "string"}},
                    "cross_reference_only": {"type": "array", "items": {"type": "string"}},
                    "omit_or_appendix": {"type": "array", "items": {"type": "string"}},
                    "transition_goal": {"type": "string"},
                },
                "required": ["section", "thesis", "target_words"],
            },
        },
        "compression_priorities": {"type": "array", "items": {"type": "string"}},
        "do_not_repeat": {"type": "array", "items": {"type": "string"}},
        "style_rules": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["bottom_line_narrative", "section_plans"],
}


def build_global_memo_plan(
    scaffold: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    obligations = build_main_memo_obligation_plan(scaffold=scaffold)
    prompt = build_global_memo_plan_prompt(scaffold, obligations)
    if backend.strip() == "prompt":
        plan = deterministic_global_memo_plan(scaffold, obligations, status="deterministic_prompt_backend")
        validation = validate_global_memo_plan(plan, obligations)
        return {"plan": plan, "prompt": prompt, "raw": "", "validation": validation}
    result = run_model_backend(
        prompt,
        backend,
        timeout_seconds=backend_timeout,
        max_retries=backend_retries,
        response_schema=GLOBAL_MEMO_PLAN_SCHEMA,
    )
    payload = _parse_json(result.text)
    if not isinstance(payload, dict):
        plan = deterministic_global_memo_plan(scaffold, obligations, status="deterministic_parse_fallback")
        plan["model_error"] = "global memo plan model output was not valid JSON"
    else:
        plan = normalize_global_memo_plan(payload, scaffold, obligations)
    validation = validate_global_memo_plan(plan, obligations)
    if validation["status"] != "passes":
        plan = repair_global_memo_plan(plan, scaffold, obligations)
        validation = validate_global_memo_plan(plan, obligations)
    return {"plan": plan, "prompt": prompt, "raw": result.text, "validation": validation}


def build_global_memo_plan_prompt(scaffold: dict[str, Any], obligations: list[dict[str, Any]]) -> str:
    packet = {
        "question": scaffold.get("question"),
        "decision_synthesis_model": _compact_decision_synthesis(scaffold.get("decision_synthesis_model", {})),
        "argument_model": _compact_argument_model(scaffold.get("argument_model", {})),
        "graph_summary": _compact_graph_packet(scaffold.get("graph_synthesis_packet", {})),
        "main_memo_obligations": [_compact_obligation(row) for row in obligations[:16]],
        "allowed_sections": GLOBAL_MEMO_SECTIONS,
    }
    return (
        "Create a global plan for a source-grounded decision-support memo.\n"
        "Your job is memo architecture, not new evidence. Do not add facts.\n"
        "Assign each required obligation to at most one owning section. Use cross-reference guidance for facts mentioned elsewhere.\n"
        "Keep the executive memo concise: target about 1200-1500 words before appendix.\n"
        "Return only JSON with fields: bottom_line_narrative, reader_strategy, section_plans, compression_priorities, do_not_repeat, style_rules.\n"
        "Each section_plans item must include: section, thesis, target_words, owned_obligation_ids, owned_evidence_roles, cross_reference_only, omit_or_appendix, transition_goal.\n\n"
        "Planning packet:\n"
        + json.dumps(packet, indent=2, ensure_ascii=False)
    )


def deterministic_global_memo_plan(
    scaffold: dict[str, Any],
    obligations: list[dict[str, Any]],
    *,
    status: str = "deterministic_fallback",
) -> dict[str, Any]:
    owned = _fallback_obligation_owners(obligations)
    sections = []
    for section in GLOBAL_MEMO_SECTIONS:
        sections.append(
            {
                "section": section,
                "thesis": _fallback_section_thesis(section, scaffold),
                "target_words": _fallback_target_words(section),
                "owned_obligation_ids": owned.get(section, []),
                "owned_evidence_roles": _fallback_roles(section),
                "cross_reference_only": _fallback_cross_references(section),
                "omit_or_appendix": ["source-level detail not needed for this section"],
                "transition_goal": _fallback_transition(section),
            }
        )
    return {
        "schema_id": "global_memo_plan_v1",
        "method": status,
        "status": status,
        "bottom_line_narrative": _fallback_bottom_line(scaffold),
        "reader_strategy": "Give the answer first, then show why the evidence supports a scoped read, what would change it, and where the map remains limited.",
        "section_plans": sections,
        "compression_priorities": [
            "State each major evidence role once in its owning section.",
            "Prefer one integrated paragraph over lists of isolated claims.",
            "Move source-level detail and repeated quantities to the appendix.",
        ],
        "do_not_repeat": [
            "Do not repeat the same full claim across multiple sections.",
            "Do not restate source titles when a short cross-reference is enough.",
            "Do not render internal ownership or validation metadata.",
        ],
        "style_rules": [
            "Use plain analytic prose.",
            "Avoid internal map terminology unless naming a map limitation.",
            "Use calibrated language for uncertain or conflicting evidence.",
        ],
    }


def normalize_global_memo_plan(
    payload: dict[str, Any],
    scaffold: dict[str, Any],
    obligations: list[dict[str, Any]],
) -> dict[str, Any]:
    fallback = deterministic_global_memo_plan(scaffold, obligations)
    section_lookup = {
        str(row.get("section", "")).strip(): row
        for row in payload.get("section_plans", [])
        if isinstance(row, dict)
    }
    sections: list[dict[str, Any]] = []
    for fallback_section in fallback["section_plans"]:
        section = str(fallback_section["section"])
        model_row = section_lookup.get(section, {})
        sections.append(
            {
                "section": section,
                "thesis": _short_text(str(model_row.get("thesis") or fallback_section["thesis"]), 260),
                "target_words": _bounded_int(model_row.get("target_words"), fallback_section["target_words"], 60, 320),
                "owned_obligation_ids": _string_list(model_row.get("owned_obligation_ids")),
                "owned_evidence_roles": _string_list(model_row.get("owned_evidence_roles")) or fallback_section["owned_evidence_roles"],
                "cross_reference_only": _string_list(model_row.get("cross_reference_only"))[:8],
                "omit_or_appendix": _string_list(model_row.get("omit_or_appendix"))[:8],
                "transition_goal": _short_text(str(model_row.get("transition_goal") or fallback_section["transition_goal"]), 220),
            }
        )
    plan = {
        "schema_id": "global_memo_plan_v1",
        "method": "model_global_plan_with_deterministic_validation",
        "status": "model_generated",
        "bottom_line_narrative": _short_text(str(payload.get("bottom_line_narrative") or fallback["bottom_line_narrative"]), 420),
        "reader_strategy": _short_text(str(payload.get("reader_strategy") or fallback["reader_strategy"]), 420),
        "section_plans": sections,
        "compression_priorities": _string_list(payload.get("compression_priorities"))[:8] or fallback["compression_priorities"],
        "do_not_repeat": _string_list(payload.get("do_not_repeat"))[:8] or fallback["do_not_repeat"],
        "style_rules": _string_list(payload.get("style_rules"))[:8] or fallback["style_rules"],
    }
    return repair_global_memo_plan(plan, scaffold, obligations)


def repair_global_memo_plan(
    plan: dict[str, Any],
    scaffold: dict[str, Any],
    obligations: list[dict[str, Any]],
) -> dict[str, Any]:
    fallback = deterministic_global_memo_plan(scaffold, obligations)
    valid_ids = {str(row.get("obligation_id", "")) for row in obligations if row.get("obligation_id")}
    seen: set[str] = set()
    sections: list[dict[str, Any]] = []
    by_section = {row["section"]: row for row in fallback["section_plans"]}
    for row in plan.get("section_plans", []) if isinstance(plan.get("section_plans"), list) else []:
        if not isinstance(row, dict):
            continue
        section = str(row.get("section", "")).strip()
        if section not in GLOBAL_MEMO_SECTIONS:
            continue
        owned = []
        for item in _string_list(row.get("owned_obligation_ids")):
            if item in valid_ids and item not in seen:
                owned.append(item)
                seen.add(item)
        repaired = {**by_section[section], **row, "section": section, "owned_obligation_ids": owned}
        repaired["target_words"] = _bounded_int(repaired.get("target_words"), by_section[section]["target_words"], 60, 320)
        sections.append(repaired)
    present = {row["section"] for row in sections}
    for section in GLOBAL_MEMO_SECTIONS:
        if section not in present:
            sections.append(by_section[section])
    missing_ids = [item for item in valid_ids if item and item not in seen]
    fallback_owners = _fallback_obligation_owners(obligations)
    for obligation_id in sorted(missing_ids):
        owner = _owner_for_obligation_id(obligation_id, obligations, fallback_owners)
        for row in sections:
            if row["section"] == owner:
                row.setdefault("owned_obligation_ids", []).append(obligation_id)
                break
    repaired_plan = dict(plan)
    repaired_plan["section_plans"] = sections
    repaired_plan.setdefault("schema_id", "global_memo_plan_v1")
    return repaired_plan


def validate_global_memo_plan(plan: dict[str, Any], obligations: list[dict[str, Any]]) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    sections = [row for row in plan.get("section_plans", []) if isinstance(row, dict)] if isinstance(plan.get("section_plans"), list) else []
    section_names = [str(row.get("section", "")).strip() for row in sections]
    for section in GLOBAL_MEMO_SECTIONS:
        if section not in section_names:
            issues.append({"issue_type": "missing_section_plan", "section": section, "severity": "error"})
    valid_ids = {str(row.get("obligation_id", "")) for row in obligations if row.get("obligation_id")}
    assigned: list[str] = []
    for row in sections:
        for item in _string_list(row.get("owned_obligation_ids")):
            if item not in valid_ids:
                issues.append({"issue_type": "unknown_obligation_id", "obligation_id": item, "section": row.get("section"), "severity": "warning"})
            assigned.append(item)
        target = _bounded_int(row.get("target_words"), 0, 0, 10_000)
        if target > 340:
            issues.append({"issue_type": "section_budget_too_large", "section": row.get("section"), "target_words": target, "severity": "warning"})
    duplicates = sorted(item for item in set(assigned) if assigned.count(item) > 1)
    for item in duplicates:
        issues.append({"issue_type": "duplicate_obligation_owner", "obligation_id": item, "severity": "error"})
    missing = sorted(item for item in valid_ids if item and item not in assigned)
    for item in missing:
        issues.append({"issue_type": "unassigned_obligation", "obligation_id": item, "severity": "error"})
    total_words = sum(_bounded_int(row.get("target_words"), 0, 0, 10_000) for row in sections)
    if total_words > 1650:
        issues.append({"issue_type": "memo_budget_too_large", "target_words": total_words, "severity": "warning"})
    fatal = any(issue["severity"] == "error" for issue in issues)
    return {
        "schema_id": "global_memo_plan_validation_v1",
        "status": "needs_repair" if fatal else "passes_with_warnings" if issues else "passes",
        "issue_count": len(issues),
        "issues": issues,
        "section_count": len(sections),
        "assigned_obligation_count": len(set(assigned) & valid_ids),
        "required_obligation_count": len(valid_ids),
        "target_word_count": total_words,
    }


def section_plan_for_title(scaffold: dict[str, Any], title: str) -> dict[str, Any]:
    plan = scaffold.get("global_memo_plan", {}) if isinstance(scaffold.get("global_memo_plan"), dict) else {}
    for row in plan.get("section_plans", []) if isinstance(plan.get("section_plans"), list) else []:
        if isinstance(row, dict) and str(row.get("section", "")).strip().lower() == title.strip().lower():
            return row
    return {}


def _compact_decision_synthesis(value: Any) -> dict[str, Any]:
    synthesis = value if isinstance(value, dict) else {}
    return {
        "bottom_line": synthesis.get("bottom_line", {}),
        "evidence_lines": _limit_rows(synthesis.get("evidence_lines"), 6),
        "central_tensions": _limit_rows(synthesis.get("central_tensions"), 4),
        "scope_boundaries": _limit_rows(synthesis.get("scope_boundaries"), 5),
        "cruxes": _limit_rows(synthesis.get("cruxes"), 5),
    }


def _compact_argument_model(value: Any) -> dict[str, Any]:
    model = value if isinstance(value, dict) else {}
    return {
        "proposed_answer": model.get("proposed_answer"),
        "confidence": model.get("confidence"),
        "strongest_support": _limit_rows(model.get("strongest_support"), 4),
        "strongest_counterarguments": _limit_rows(model.get("strongest_counterarguments"), 4),
        "quantitative_anchors": _limit_rows(model.get("quantitative_anchors"), 5),
        "scope_boundaries": _limit_rows(model.get("scope_boundaries"), 5),
    }


def _compact_graph_packet(value: Any) -> dict[str, Any]:
    packet = value if isinstance(value, dict) else {}
    return {
        "graph_summary": packet.get("graph_summary", {}),
        "central_tensions": _limit_rows(packet.get("central_tensions"), 3),
        "load_bearing_claims": _limit_rows(packet.get("load_bearing_claims"), 5),
        "bridge_claims": _limit_rows(packet.get("bridge_claims"), 3),
    }


def _compact_obligation(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "obligation_id": row.get("obligation_id"),
        "category": row.get("category"),
        "priority": row.get("priority"),
        "statement": _short_text(str(row.get("statement", "")), 220),
        "claim_ids": _string_list(row.get("claim_ids")),
        "quantity_ids": _string_list(row.get("quantity_ids")),
    }


def _fallback_obligation_owners(obligations: list[dict[str, Any]]) -> dict[str, list[str]]:
    owned: dict[str, list[str]] = {section: [] for section in GLOBAL_MEMO_SECTIONS}
    for row in obligations:
        obligation_id = str(row.get("obligation_id", "")).strip()
        if obligation_id:
            owned[_fallback_owner(row)].append(obligation_id)
    return owned


def _fallback_owner(row: dict[str, Any]) -> str:
    category = str(row.get("category", "")).lower()
    if category in {"practical_action", "practical_recommendation"}:
        return "Practical Read"
    if category in {"scope_boundary", "implementation_constraint"}:
        return "Practical Scope and Exceptions"
    if category in {"decision_crux"}:
        return "Decision Cruxes"
    if category in {"known_gap", "quality_issue", "missing_evidence"}:
        return "Limits of the Current Map"
    if category in {"strongest_support", "strongest_counterargument", "quantitative_anchor", "evidence_family_balance"}:
        return "Evidence Carrying the Conclusion"
    return "Why This Read"


def _owner_for_obligation_id(obligation_id: str, obligations: list[dict[str, Any]], fallback_owners: dict[str, list[str]]) -> str:
    for section, ids in fallback_owners.items():
        if obligation_id in ids:
            return section
    for row in obligations:
        if str(row.get("obligation_id", "")) == obligation_id:
            return _fallback_owner(row)
    return "Evidence Carrying the Conclusion"


def _fallback_section_thesis(section: str, scaffold: dict[str, Any]) -> str:
    if section == "Decision Brief":
        return _fallback_bottom_line(scaffold)
    return {
        "Practical Read": "Translate the bottom-line read into concrete, scoped practical implications.",
        "Why This Read": "Explain the reasoning path that connects the most important evidence to the bottom line.",
        "Evidence Carrying the Conclusion": "Integrate the load-bearing support, counterevidence, quantities, and method limits.",
        "Practical Scope and Exceptions": "Name the population, dose, comparator, and implementation boundaries.",
        "Decision Cruxes": "State the concrete uncertainties that would change the answer.",
        "Limits of the Current Map": "Name what the map does not establish and where confidence should remain bounded.",
    }.get(section, "Write a concise source-grounded section.")


def _fallback_bottom_line(scaffold: dict[str, Any]) -> str:
    synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    bottom = synthesis.get("bottom_line", {}) if isinstance(synthesis.get("bottom_line"), dict) else {}
    current = str(bottom.get("current_read") or bottom.get("classification") or "").strip()
    return current or "Give a calibrated, scoped answer based on the mapped evidence."


def _fallback_target_words(section: str) -> int:
    return {
        "Decision Brief": 120,
        "Practical Read": 190,
        "Why This Read": 220,
        "Evidence Carrying the Conclusion": 270,
        "Practical Scope and Exceptions": 220,
        "Decision Cruxes": 180,
        "Limits of the Current Map": 170,
    }.get(section, 160)


def _fallback_roles(section: str) -> list[str]:
    return {
        "Decision Brief": ["bottom_line", "confidence", "top_evidence", "top_caveat"],
        "Practical Read": ["practical_recommendation", "implementation_constraint"],
        "Why This Read": ["reasoning_path", "central_tension"],
        "Evidence Carrying the Conclusion": ["support", "counterevidence", "quantities", "method_limits"],
        "Practical Scope and Exceptions": ["population", "dose", "comparator", "subgroup"],
        "Decision Cruxes": ["decision_changing_uncertainty"],
        "Limits of the Current Map": ["missing_evidence", "quality_issue", "scope_limit"],
    }.get(section, [])


def _fallback_cross_references(section: str) -> list[str]:
    if section in {"Why This Read", "Decision Cruxes", "Limits of the Current Map"}:
        return ["source-level evidence details", "full quantitative details"]
    if section == "Practical Read":
        return ["methodological details", "secondary quantities"]
    return []


def _fallback_transition(section: str) -> str:
    return {
        "Decision Brief": "Orient the reader to the answer before evidence details.",
        "Practical Read": "Move from answer to implications.",
        "Why This Read": "Move from implications to reasoning.",
        "Evidence Carrying the Conclusion": "Move from reasoning to evidence weight.",
        "Practical Scope and Exceptions": "Move from evidence to boundaries.",
        "Decision Cruxes": "Move from boundaries to what would change the answer.",
        "Limits of the Current Map": "Close by bounding confidence and completeness.",
    }.get(section, "")


def _limit_rows(value: Any, limit: int) -> list[Any]:
    return value[:limit] if isinstance(value, list) else []


def _bounded_int(value: Any, fallback: int, low: int, high: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = fallback
    return max(low, min(high, number))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _short_text(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned if len(cleaned) <= max_chars else cleaned[: max_chars - 3].rstrip(" ,.;") + "..."
