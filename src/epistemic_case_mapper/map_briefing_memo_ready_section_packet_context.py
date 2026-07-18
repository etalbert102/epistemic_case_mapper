from __future__ import annotations

from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import string_list as _string_list
from epistemic_case_mapper.map_briefing_source_bound_evidence import quantity_binding_rows


def section_writing_packets(
    packet: dict[str, Any],
    *,
    compact_spine_step: Any,
    compact_source_judgment: Any,
) -> list[dict[str, Any]]:
    spine = _dict(packet.get("evidence_weighted_argument_spine"))
    steps = [compact_spine_step(row) for row in _list(spine.get("steps")) if isinstance(row, dict)]
    steps_by_id = {str(row.get("step_id") or ""): row for row in steps if row.get("step_id")}
    evidence_by_id = _evidence_by_id(packet)
    requirements = section_retention_requirements(packet)
    source_judgments = [compact_source_judgment(row) for row in _list(packet.get("source_weight_judgments")) if isinstance(row, dict)]
    packets = []
    for section in _list(spine.get("section_plan")):
        if not isinstance(section, dict):
            continue
        section_name = str(section.get("section") or "").strip()
        owned_steps = [steps_by_id[step_id] for step_id in _string_list(section.get("owned_step_ids")) if step_id in steps_by_id]
        section_requirements = [row for row in requirements if row.get("primary_section") == section_name]
        evidence_ids = _dedupe(
            [
                *_string_list(section.get("owned_evidence_item_ids")),
                *[evidence_id for step in owned_steps for evidence_id in _string_list(step.get("evidence_item_ids"))],
                *[
                    evidence_id
                    for requirement in section_requirements
                    for evidence_id in _string_list(requirement.get("evidence_item_ids"))
                ],
            ]
        )
        evidence_rows = [evidence_by_id[evidence_id] for evidence_id in evidence_ids if evidence_id in evidence_by_id]
        if not evidence_rows and _section_id_from_heading(section_name) == "practical_implication":
            evidence_rows = _practical_evidence_rows(packet)
        source_ids = _dedupe(
            [
                *[source_id for step in owned_steps for source_id in _string_list(step.get("source_ids"))],
                *[source_id for row in evidence_rows for source_id in _string_list(row.get("source_ids"))],
                *[source_id for row in section_requirements for source_id in _string_list(row.get("source_ids"))],
            ]
        )
        binding_rows = quantity_binding_rows(packet, source_ids=source_ids) if source_ids else []
        packets.append(
            _drop_empty(
                {
                    "section": section_name,
                    "writing_job": section.get("writing_job"),
                    "argument_steps": owned_steps,
                    "required_points": section.get("must_include_points"),
                    "retention_requirements": section_requirements,
                    "evidence_context": evidence_rows,
                    "quantity_binding_context": binding_rows[:12],
                    "source_weighting": [
                        row
                        for row in source_judgments
                        if any(source_id in _string_list(row.get("source_ids")) for source_id in source_ids)
                    ],
                }
            )
        )
    return packets


def section_retention_requirements(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in _list(packet.get("mandatory_retention_checklist")):
        if not isinstance(row, dict):
            continue
        rows.append(_compact_retention_requirement(row))
    return rows


def compact_memo_ready_row(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "item_id": row.get("item_id"),
            "role": row.get("role"),
            "answer_relation": row.get("answer_relation"),
            "reader_evidence_role": row.get("reader_evidence_role"),
            "memo_function": row.get("memo_function"),
            "claim": row.get("claim") or row.get("statement"),
            "source_ids": row.get("source_ids") or ([row.get("source_id")] if row.get("source_id") else None),
            "quantities": row.get("quantities"),
            "source_excerpt": row.get("source_excerpt"),
            "decision_relevance": row.get("decision_relevance"),
            "caveat": row.get("caveat"),
            "importance_rank": row.get("importance_rank"),
        }
    )


def _evidence_by_id(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    rows = []
    rows.extend(compact_memo_ready_row(row) for row in _list(packet.get("priority_evidence")) if isinstance(row, dict))
    rows.extend(compact_memo_ready_row(row) for row in _list(packet.get("counterweight_dispositions")) if isinstance(row, dict))
    rows.extend(compact_memo_ready_row(row) for row in _list(packet.get("scope_boundaries")) if isinstance(row, dict))
    rows.extend(compact_memo_ready_row(row) for row in _list(packet.get("decision_cruxes")) if isinstance(row, dict))
    inventory = _dict(packet.get("organized_evidence_inventory"))
    for lane_rows in _dict(inventory.get("lanes")).values():
        rows.extend(compact_memo_ready_row(row) for row in _list(lane_rows) if isinstance(row, dict))
    by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        item_id = str(row.get("item_id") or "").strip()
        if item_id and item_id not in by_id:
            by_id[item_id] = row
    return by_id


def _practical_evidence_rows(packet: dict[str, Any]) -> list[dict[str, Any]]:
    inventory = _dict(packet.get("organized_evidence_inventory"))
    lanes = _dict(inventory.get("lanes"))
    candidates = []
    for lane in ("interpretive_context", "scope_and_applicability"):
        for row in _list(lanes.get(lane)):
            if isinstance(row, dict) and _practical_row_eligible(row, lane=lane):
                candidates.append(compact_memo_ready_row(row))
    return _dedupe_rows(candidates, "item_id")[:6]


def _practical_row_eligible(row: dict[str, Any], *, lane: str) -> bool:
    relation = str(row.get("answer_relation") or "").strip()
    role = str(row.get("role") or "").strip()
    obligation = str(row.get("obligation_level") or "").strip()
    if relation in {"off_question", "not_relevant", "not_decision_relevant", "uncertain_relation"}:
        return False
    if obligation in {"optional_context", "off_question", "not_relevant"}:
        return False
    if lane == "interpretive_context":
        return relation in {"contextualizes_answer", "supports_answer", "bounds_scope"} or role in {"mechanism_or_explanation", "context_only"}
    if lane == "scope_and_applicability":
        return relation in {"contextualizes_answer", "bounds_scope"} and role == "scope_boundary"
    return False


def _compact_retention_requirement(row: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "requirement_id": row.get("obligation_id") or row.get("item_id"),
            "primary_section": _retention_requirement_section(row),
            "role": row.get("role") or row.get("obligation_type"),
            "statement": row.get("statement") or row.get("claim"),
            "source_ids": row.get("source_ids") or ([row.get("source_id")] if row.get("source_id") else None),
            "quantities": row.get("quantities"),
            "evidence_item_ids": row.get("evidence_item_ids"),
            "prose_instruction": row.get("prose_instruction"),
        }
    )


def _retention_requirement_section(row: dict[str, Any]) -> str:
    role = str(row.get("role") or row.get("obligation_type") or "").lower()
    text = str(row.get("statement") or row.get("claim") or row.get("prose_instruction") or "").lower()
    if any(token in role for token in ("counter", "boundary", "scope", "crux", "limit", "risk")):
        return "What Could Change or Bound the Answer"
    if any(token in text for token in ("subgroup", "scope", "bound", "risk factor", "exception", "threshold", "high-risk")):
        return "What Could Change or Bound the Answer"
    if any(token in role for token in ("practical", "application", "implementation")):
        return "Practical Implication"
    if any(token in text for token in ("practical", "application", "implementation", "advice", "recommend", "replacement", "action", "translate")):
        return "Practical Implication"
    if "bottom" in role or "answer" in role:
        return "Bottom Line"
    return "Why This Is the Best Current Read"


def _section_id_from_heading(heading: str) -> str:
    text = str(heading or "").lower()
    if "bottom" in text:
        return "bottom_line"
    if "weight" in text:
        return "source_weighting"
    if "change" in text or "bound" in text or "counter" in text:
        return "counterweights"
    if "practical" in text or "implication" in text:
        return "practical_implication"
    return "answer_evidence"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        marker = str(value or "").strip()
        if marker and marker not in seen:
            seen.add(marker)
            result.append(marker)
    return result


def _dedupe_rows(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for row in rows:
        marker = str(row.get(key) or "")
        if not marker or marker in seen:
            continue
        seen.add(marker)
        deduped.append(row)
    return deduped
