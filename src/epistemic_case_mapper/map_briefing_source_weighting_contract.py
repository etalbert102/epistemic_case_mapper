from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    norm as _norm,
    short_text as _short_text,
    string_list as _string_list,
)


LANE_ROLE = {
    "primary_answer_drivers": "drives_answer",
    "counterweight_sources": "bounds_answer",
    "quantitative_calibrators": "calibrates_magnitude",
    "scope_boundary_sources": "sets_scope",
    "contextual_sources": "contextualizes",
}

ROLE_ORDER = {
    "drives_answer": 0,
    "bounds_answer": 1,
    "calibrates_magnitude": 2,
    "sets_scope": 3,
    "contextualizes": 4,
}


def build_source_weighting_contract(canonical_packet: dict[str, Any]) -> dict[str, Any]:
    """Compile source hierarchy and source-local judgments into a section contract."""

    packet = canonical_packet if isinstance(canonical_packet, dict) else {}
    hierarchy = _dict(packet.get("source_hierarchy"))
    judgments = _source_judgments_by_id(packet.get("source_weight_judgments"))
    language = _language_contracts_by_source(packet.get("evidence_language_contracts"))
    lane_cards = _lane_cards(_dict(hierarchy.get("lanes")))
    rows = _contract_rows(hierarchy, judgments=judgments, language=language, lane_cards=lane_cards)
    missing_sources = _missing_sources(packet, rows)
    return {
        "schema_id": "source_weighting_contract_v1",
        "decision_question": packet.get("decision_question"),
        "hierarchy_thesis": hierarchy.get("hierarchy_thesis", ""),
        "source_count": len(rows),
        "roles_present": _dedupe(row["role"] for row in rows if row.get("role")),
        "sources": rows,
        "lane_cards": lane_cards,
        "report": {
            "schema_id": "source_weighting_contract_report_v1",
            "status": "ready" if rows and not missing_sources else "warning" if rows else "empty",
            "source_count": len(rows),
            "missing_source_ids": missing_sources,
            "role_counts": _role_counts(rows),
            "issues": ["missing_memo_facing_sources"] if missing_sources else [],
        },
    }


def build_source_weighting_section_packet(reader_packet: dict[str, Any]) -> dict[str, Any]:
    packet = reader_packet if isinstance(reader_packet, dict) else {}
    contract = _dict(packet.get("source_weighting_contract"))
    if not _list(contract.get("sources")):
        return {}
    return _drop_empty(
        {
            "schema_id": "source_weighting_section_packet_v1",
            "section": "How to Weight the Evidence",
            "writing_job": "Explain how to weight the source base before reading the detailed evidence argument.",
            "decision_question": packet.get("decision_question"),
            "current_read": _current_read(packet),
            "confidence": _dict(packet.get("balanced_answer_frame")).get("confidence"),
            "hierarchy_thesis": contract.get("hierarchy_thesis"),
            "source_role_groups": _role_groups(_list(contract.get("sources"))),
            "lane_cards": contract.get("lane_cards"),
            "required_points": [
                "State which sources carry the answer.",
                "State which sources bound, calibrate, scope, or contextualize the answer.",
                "Explain why the limiting sources narrow or calibrate the answer rather than simply overturning it.",
                "Name source-type or design caveats only where they change how confidently the reader should use the source.",
            ],
            "validation_contract": {
                "roles_to_cover": _dedupe(row.get("role") for row in _list(contract.get("sources")) if row.get("role")),
                "source_ids_to_account_for": _dedupe(
                    source_id for row in _list(contract.get("sources")) for source_id in _string_list(row.get("source_ids"))
                ),
            },
        }
    )


def build_source_weighting_flow_audit(canonical_packet: dict[str, Any], reader_packet: dict[str, Any] | None = None) -> dict[str, Any]:
    canonical = canonical_packet if isinstance(canonical_packet, dict) else {}
    reader = reader_packet if isinstance(reader_packet, dict) else {}
    contract = _dict(canonical.get("source_weighting_contract")) or build_source_weighting_contract(canonical)
    section_packet = _dict(reader.get("source_weighting_section_packet"))
    source_section_has_evidence_context = bool(_list(section_packet.get("evidence_context")))
    return {
        "schema_id": "source_weighting_flow_audit_v1",
        "status": "ready" if contract.get("source_count", 0) else "warning",
        "canonical_has_source_hierarchy": bool(_dict(canonical.get("source_hierarchy"))),
        "canonical_has_source_weight_judgments": bool(_list(canonical.get("source_weight_judgments"))),
        "canonical_has_source_weighting_contract": bool(_list(contract.get("sources"))),
        "reader_has_source_weighting_contract": bool(_list(_dict(reader.get("source_weighting_contract")).get("sources"))),
        "section_packet_has_full_evidence_context": source_section_has_evidence_context,
        "section_packet_role_count": len(_list(section_packet.get("source_role_groups"))),
        "contract_report": contract.get("report", {}),
        "issues": ["source_weighting_section_still_has_full_evidence_context"] if source_section_has_evidence_context else [],
    }


def build_source_weighting_fidelity_report(memo: str, packet: dict[str, Any]) -> dict[str, Any]:
    contract = _dict(packet.get("source_weighting_contract")) or _dict(
        _dict(packet.get("canonical_decision_writer_packet")).get("source_weighting_contract")
    )
    if not _list(contract.get("sources")) and _dict(packet.get("canonical_decision_writer_packet")):
        contract = build_source_weighting_contract(_dict(packet.get("canonical_decision_writer_packet")))
    sources = [row for row in _list(contract.get("sources")) if isinstance(row, dict)]
    section = _source_weighting_section(memo)
    statuses = [_role_status(section, role, sources) for role in _dedupe(row.get("role") for row in sources if row.get("role"))]
    source_statuses = [_source_status(section, row) for row in sources]
    issues = [
        *[row for row in statuses if not row["covered"]],
        *[row for row in source_statuses if not row["covered"]],
    ]
    flattened = _looks_flattened(section, statuses=statuses)
    if flattened:
        issues.append({"issue_type": "flattened_source_weighting", "reason": "section mentions sources but not enough source role distinctions"})
    return {
        "schema_id": "source_weighting_fidelity_report_v1",
        "status": "ready" if not issues else "warning",
        "report_mode": "report_only",
        "source_weighting_section_found": bool(section.strip()),
        "role_statuses": statuses,
        "source_statuses": source_statuses,
        "issue_count": len(issues),
        "issues": issues,
    }


def _contract_rows(
    hierarchy: dict[str, Any],
    *,
    judgments: dict[str, dict[str, Any]],
    language: dict[str, list[dict[str, Any]]],
    lane_cards: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    accounting = [row for row in _list(hierarchy.get("source_accounting")) if isinstance(row, dict)]
    if not accounting and judgments:
        accounting = [{"source_id": source_id, "primary_lane": _lane_from_role(row.get("main_use"))} for source_id, row in judgments.items()]
    rows = []
    for account in accounting:
        source_id = str(account.get("source_id") or "").strip()
        if not source_id:
            continue
        judgment = judgments.get(source_id, {})
        role = LANE_ROLE.get(str(account.get("primary_lane") or ""), str(judgment.get("main_use") or "contextualizes"))
        rows.append(
            _drop_empty(
                {
                    "source_ids": [source_id],
                    "source_id": source_id,
                    "citation_key": source_id,
                    "source_slug": account.get("source_slug") or account.get("original_source_id"),
                    "role": role,
                    "source_type": judgment.get("source_type"),
                    "role_rationale": _short_text(account.get("rationale") or judgment.get("why_weight_this_way"), 700),
                    "memo_weight_sentence": _short_text(judgment.get("memo_weight_sentence"), 700),
                    "supported_claims": _supported_claims(source_id, lane_cards, judgment),
                    "cannot_support": _cannot_support(judgment),
                    "confidence_effect": judgment.get("confidence_effect"),
                    "linked_evidence_item_ids": _dedupe(
                        [
                            *_string_list(judgment.get("evidence_item_ids")),
                            *[
                                evidence_id
                                for card in lane_cards
                                if source_id in _string_list(card.get("source_ids"))
                                for evidence_id in _string_list(card.get("evidence_item_ids"))
                            ],
                        ]
                    ),
                    "source_appraisal_caveats": _source_caveats(source_id, language, judgment),
                }
            )
        )
    return sorted(rows, key=lambda row: (ROLE_ORDER.get(str(row.get("role")), 99), str(row.get("source_id"))))


def _lane_cards(lanes: dict[str, Any]) -> list[dict[str, Any]]:
    cards = []
    for lane, rows in lanes.items():
        role = LANE_ROLE.get(str(lane), str(lane))
        for index, row in enumerate(_list(rows), start=1):
            if not isinstance(row, dict):
                continue
            cards.append(
                _drop_empty(
                    {
                        "lane": lane,
                        "role": role,
                        "card_id": f"{lane}_{index:02d}",
                        "source_ids": _string_list(row.get("source_ids")),
                        "evidence_item_ids": _string_list(row.get("evidence_item_ids")),
                        "role_description": _short_text(row.get("role"), 360),
                        "rationale": _short_text(row.get("rationale"), 600),
                    }
                )
            )
    return cards


def _role_groups(sources: list[Any]) -> list[dict[str, Any]]:
    groups = []
    for role in sorted({str(row.get("role")) for row in sources if isinstance(row, dict) and row.get("role")}, key=lambda item: ROLE_ORDER.get(item, 99)):
        rows = [row for row in sources if isinstance(row, dict) and row.get("role") == role]
        groups.append(
            {
                "role": role,
                "writing_job": _role_writing_job(role),
                "sources": [
                    {
                        key: row.get(key)
                        for key in (
                            "source_ids",
                            "citation_key",
                            "source_slug",
                            "source_type",
                            "role_rationale",
                            "memo_weight_sentence",
                            "supported_claims",
                            "cannot_support",
                            "confidence_effect",
                            "linked_evidence_item_ids",
                            "source_appraisal_caveats",
                        )
                        if row.get(key) not in (None, "", [], {})
                    }
                    for row in rows
                ],
            }
        )
    return groups


def _role_writing_job(role: str) -> str:
    return {
        "drives_answer": "Explain why these sources carry the default answer.",
        "bounds_answer": "Explain how these sources narrow, weaken, or cap the answer.",
        "calibrates_magnitude": "Use these sources for quantities, thresholds, or practical dose limits.",
        "sets_scope": "Use these sources to state who or what the answer applies to.",
        "contextualizes": "Use these sources to explain mechanism, comparison, or interpretation without overstating them as primary support.",
    }.get(role, "Explain this source role in plain language.")


def _source_judgments_by_id(value: Any) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in _list(value):
        if not isinstance(row, dict):
            continue
        for source_id in _string_list(row.get("source_ids")):
            rows[source_id] = row
    return rows


def _language_contracts_by_source(value: Any) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for row in _list(value):
        if not isinstance(row, dict):
            continue
        for source_id in _string_list(row.get("source_ids")):
            rows.setdefault(source_id, []).append(row)
    return rows


def _supported_claims(source_id: str, lane_cards: list[dict[str, Any]], judgment: dict[str, Any]) -> list[str]:
    claims = [
        str(card.get("role_description") or card.get("rationale") or "").strip()
        for card in lane_cards
        if source_id in _string_list(card.get("source_ids"))
    ]
    claims.append(str(judgment.get("memo_weight_sentence") or "").strip())
    return [_short_text(row, 420) for row in _dedupe(claims) if row][:4]


def _cannot_support(judgment: dict[str, Any]) -> list[str]:
    rows = [*_string_list(judgment.get("what_not_to_use_it_for"))]
    if limit := str(judgment.get("reader_facing_limit") or "").strip():
        rows.append(limit)
    return [_short_text(row, 360) for row in _dedupe(rows) if row][:4]


def _source_caveats(source_id: str, language: dict[str, list[dict[str, Any]]], judgment: dict[str, Any]) -> list[str]:
    rows = []
    for contract in language.get(source_id, []):
        rows.extend(_string_list(contract.get("calibration_basis")))
        if rule := str(contract.get("wording_rule") or "").strip():
            rows.append(rule)
    if limit := str(judgment.get("reader_facing_limit") or "").strip():
        rows.append(limit)
    return [_short_text(row, 260) for row in _dedupe(rows) if row][:5]


def _missing_sources(packet: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
    accounted = {str(row.get("source_id") or "") for row in rows}
    source_ids = {
        source_id
        for source in _list(packet.get("citation_registry"))
        if isinstance(source, dict)
        for source_id in _string_list(source.get("source_id"))
    }
    if not source_ids:
        source_ids = {
            source_id
            for row in _list(packet.get("source_weight_judgments"))
            if isinstance(row, dict)
            for source_id in _string_list(row.get("source_ids"))
        }
    return sorted(source_id for source_id in source_ids if source_id and source_id not in accounted)


def _role_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        role = str(row.get("role") or "unknown")
        counts[role] = counts.get(role, 0) + 1
    return counts


def _lane_from_role(role: Any) -> str:
    value = str(role or "").strip()
    for lane, mapped in LANE_ROLE.items():
        if mapped == value:
            return lane
    return "contextual_sources"


def _current_read(packet: dict[str, Any]) -> str:
    balanced = _dict(packet.get("balanced_answer_frame"))
    bluf = _dict(packet.get("bluf_contract"))
    answer = _dict(packet.get("answer_frame"))
    skeleton = _dict(answer.get("skeleton"))
    return str(bluf.get("recommended_read") or balanced.get("best_current_read") or skeleton.get("direct_answer") or "").strip()


def _source_weighting_section(memo: str) -> str:
    match = re.search(r"(?ims)^##\s+How to Weight the Evidence\s*(.*?)(?=^##\s+|\Z)", str(memo or ""))
    return match.group(1).strip() if match else ""


def _role_status(section: str, role: str, sources: list[dict[str, Any]]) -> dict[str, Any]:
    role_sources = [row for row in sources if row.get("role") == role]
    source_ids = [source_id for row in role_sources for source_id in _string_list(row.get("source_ids"))]
    role_terms = _role_terms(role)
    covered = any(_contains(section, term) for term in role_terms) and any(_contains(section, source_id) for source_id in source_ids)
    return {
        "issue_type": "missing_source_weight_role",
        "role": role,
        "covered": covered,
        "source_ids": source_ids,
        "role_terms": role_terms,
    }


def _source_status(section: str, row: dict[str, Any]) -> dict[str, Any]:
    source_ids = _string_list(row.get("source_ids"))
    covered = any(_contains(section, source_id) for source_id in source_ids)
    return {
        "issue_type": "missing_source_weight_source",
        "role": row.get("role"),
        "source_ids": source_ids,
        "covered": covered,
    }


def _role_terms(role: str) -> list[str]:
    return {
        "drives_answer": ["carry", "drives", "primary", "load-bearing", "main support"],
        "bounds_answer": ["bound", "limit", "counterweight", "narrows", "does not overturn"],
        "calibrates_magnitude": ["calibrat", "magnitude", "threshold", "dose", "quantity"],
        "sets_scope": ["scope", "applies", "population", "boundary"],
        "contextualizes": ["context", "interpret", "mechanism", "explain"],
    }.get(role, [role.replace("_", " ")])


def _looks_flattened(section: str, *, statuses: list[dict[str, Any]]) -> bool:
    if not section.strip():
        return False
    covered_roles = sum(1 for row in statuses if row.get("covered"))
    citation_count = len(re.findall(r"\[[^\]]+\]", section))
    return citation_count >= 3 and covered_roles <= 1


def _contains(text: str, needle: str) -> bool:
    return _norm(needle) in _norm(text)


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}
