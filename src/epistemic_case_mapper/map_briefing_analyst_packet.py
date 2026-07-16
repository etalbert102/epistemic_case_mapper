from __future__ import annotations

import re
from collections import Counter
from typing import Any

from epistemic_case_mapper.map_briefing_answer_frame import is_weak_answer_frame
from epistemic_case_mapper.map_briefing_analyst_decision_logic import analyst_decision_logic
from epistemic_case_mapper.map_briefing_analyst_decision_groups import build_groups_from_decision_model
from epistemic_case_mapper.map_briefing_analyst_quantity_binding import (
    build_analyst_quantity_binding_report,
    quantity_binding_quality_summary,
    quantity_bindings_for_group,
)
from epistemic_case_mapper.map_briefing_analyst_role_projection import (
    FOREGROUND_MEMO_USES,
    SECTION_BY_MEMO_USE,
    effective_memo_role as _effective_memo_role,
    memo_ready_role_for_group as _memo_ready_role_for_group,
    project_group_role as _project_group_role,
)
from epistemic_case_mapper.map_briefing_analyst_packet_helpers import (
    applicability_limits as _applicability_limits,
    clean_answer_text as _clean_answer_text,
    content_terms as _content_terms,
    first_group_text as _first_group_text,
    foreground_sections as _foreground_sections,
    ids_for_roles as _ids_for_roles,
    is_quantity_row as _is_quantity_row,
    ledger_ids as _ledger_ids,
    must_not_overstate as _must_not_overstate,
    synthesis_group_sections as _synthesis_group_sections,
    why_this_read as _why_this_read,
)
from epistemic_case_mapper.map_briefing_analyst_schemas import AnalystSynthesisPacket
from epistemic_case_mapper.map_briefing_canonical_decision_writer_packet import build_canonical_decision_writer_packet
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_memo_obligations import build_memo_obligation_packet
from epistemic_case_mapper.map_briefing_reader_packet_contract import build_memo_ready_decision_synthesis_contract
from epistemic_case_mapper.map_briefing_source_faithfulness import (
    source_faithfulness_warning_reason as _shared_source_faithfulness_warning_reason,
    source_faithfulness_warnings as _shared_source_faithfulness_warnings,
)
from epistemic_case_mapper.map_briefing_writer_packet import build_writer_packet
from epistemic_case_mapper.map_briefing_writer_guidance import compact_writer_guidance_for_model


def build_analyst_packet_bundle(
    *,
    packet: dict[str, Any],
    ledger: dict[str, Any],
    adjudication: dict[str, Any],
    decision_model: dict[str, Any] | None = None,
    memo_warning_packet: dict[str, Any] | None = None,
    refinement: dict[str, Any] | None = None,
    quantity_binding: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    packet = packet if isinstance(packet, dict) else {}
    ledger = ledger if isinstance(ledger, dict) else {}
    adjudication = adjudication if isinstance(adjudication, dict) else {}
    refinement = refinement if isinstance(refinement, dict) else {}
    warning_packet = memo_warning_packet if isinstance(memo_warning_packet, dict) else _dict(packet.get("memo_warning_packet"))
    ledger_by_id = {
        str(row.get("evidence_item_id") or ""): row
        for row in _list(ledger.get("rows"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }
    adjudication_rows = _sorted_adjudication_rows(adjudication)
    decision_model = decision_model if isinstance(decision_model, dict) else {}
    groups, group_accounting = build_groups_from_decision_model(decision_model, ledger_by_id)
    if not groups:
        groups, group_accounting = _build_groups(adjudication_rows, ledger_by_id)
    groups, adjudication_alignment = _align_groups_with_adjudication_roles(groups, adjudication_rows)
    if adjudication_alignment:
        group_accounting = dict(group_accounting)
        group_accounting["adjudication_role_alignment"] = adjudication_alignment
    groups, source_faithfulness_quarantine = _quarantine_source_faithfulness_conflicts(
        groups,
        _source_faithfulness_warnings(ledger, adjudication),
    )
    if source_faithfulness_quarantine:
        group_accounting = dict(group_accounting)
        group_accounting["source_faithfulness_quarantine"] = source_faithfulness_quarantine
    answer_frame = _build_answer_frame(packet, ledger, adjudication_rows, groups, refinement=refinement, decision_model=decision_model)
    synthesis_packet = _build_synthesis_packet(
        packet=packet,
        ledger=ledger,
        adjudication=adjudication,
        decision_model=decision_model,
        groups=groups,
        answer_frame=answer_frame,
        group_accounting=group_accounting,
        warning_packet=warning_packet,
        refinement=refinement,
    )
    quantity_binding_report = (
        quantity_binding
        if isinstance(quantity_binding, dict) and quantity_binding.get("schema_id") == "analyst_quantity_binding_report_v1"
        else build_analyst_quantity_binding_report(synthesis_packet=synthesis_packet, ledger=ledger)
    )
    quality = build_analyst_packet_quality_report(
        ledger=ledger,
        adjudication=adjudication,
        synthesis_packet=synthesis_packet,
        group_accounting=group_accounting,
        quantity_binding=quantity_binding_report,
    )
    memo_ready = _build_analyst_memo_ready_packet(
        packet=packet,
        synthesis_packet=synthesis_packet,
        warning_packet=_memo_facing_warning_packet(warning_packet, synthesis_packet),
        quality=quality,
        quantity_binding=quantity_binding_report,
    )
    return {
        "analyst_answer_frame": answer_frame,
        "analyst_evidence_groups": {
            "schema_id": "analyst_evidence_groups_v1",
            "group_count": len(groups),
            "groups": groups,
            "accounting": group_accounting,
        },
        "analyst_synthesis_packet": synthesis_packet,
        "analyst_quantity_binding_report": quantity_binding_report,
        "analyst_packet_quality_report": quality,
        "analyst_memo_ready_packet": memo_ready,
    }


def build_analyst_packet_quality_report(
    *,
    ledger: dict[str, Any],
    adjudication: dict[str, Any],
    synthesis_packet: dict[str, Any],
    group_accounting: dict[str, Any] | None = None,
    quantity_binding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ledger_ids = _ledger_ids(ledger)
    adjudicated_ids = {
        str(row.get("evidence_item_id") or "")
        for row in _list(adjudication.get("rows"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }
    covered_ids = {
        evidence_id
        for section in _synthesis_group_sections(synthesis_packet)
        for group in _list(synthesis_packet.get(section))
        if isinstance(group, dict)
        for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
    }
    accounted_ids = set(_string_list(_dict(synthesis_packet.get("evidence_accounting_summary")).get("accounted_evidence_item_ids")))
    missing_from_adjudication = sorted(set(ledger_ids) - adjudicated_ids)
    missing_from_packet_accounting = sorted(set(ledger_ids) - accounted_ids)
    issues = [
        *(["missing_adjudication_rows"] if missing_from_adjudication else []),
        *(["missing_packet_accounting"] if missing_from_packet_accounting else []),
        *(["no_primary_reasoning_chain"] if not _list(synthesis_packet.get("primary_reasoning_chain")) else []),
        *(["no_counterweight_or_scope"] if not _list(synthesis_packet.get("main_counterweights")) and not _list(synthesis_packet.get("scope_and_applicability")) else []),
    ]
    source_faithfulness_warnings = _source_faithfulness_warnings(ledger, adjudication)
    return {
        "schema_id": "analyst_packet_quality_report_v1",
        "status": "ready" if not issues and not source_faithfulness_warnings else "warning",
        "ledger_row_count": len(ledger_ids),
        "adjudicated_row_count": len(adjudicated_ids),
        "packet_accounted_row_count": len(accounted_ids),
        "foreground_group_count": sum(len(_list(synthesis_packet.get(section))) for section in _foreground_sections()),
        "background_group_count": len(_list(synthesis_packet.get("background_context"))),
        "covered_evidence_item_count": len(covered_ids),
        "quantity_binding": quantity_binding_quality_summary(quantity_binding or {}),
        "missing_from_adjudication": missing_from_adjudication,
        "missing_from_packet_accounting": missing_from_packet_accounting,
        "source_faithfulness_warning_count": len(source_faithfulness_warnings),
        "source_faithfulness_warnings": source_faithfulness_warnings,
        "group_accounting": group_accounting or {},
        "issues": [*issues, *(["source_faithfulness_warnings_present"] if source_faithfulness_warnings else [])],
    }


def _build_groups(adjudication_rows: list[dict[str, Any]], ledger_by_id: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    group_by_evidence_id: dict[str, str] = {}
    deferred_covered: list[dict[str, Any]] = []
    grouped_quantity_rows: list[str] = []
    for row in adjudication_rows:
        evidence_id = str(row.get("evidence_item_id") or "").strip()
        if not evidence_id:
            continue
        memo_use = str(row.get("memo_use") or "")
        ledger_row = ledger_by_id.get(evidence_id, {})
        if memo_use in {"covered_by_group", "not_decision_relevant"}:
            deferred_covered.append(row)
            continue
        if _is_quantity_row(ledger_row):
            target = _quantity_target_group(row, ledger_row, groups)
            if target is not None:
                _merge_quantity_into_group(target, row, ledger_row)
                target["covered_evidence_item_ids"] = _dedupe([*target.get("covered_evidence_item_ids", []), evidence_id])
                group_by_evidence_id[evidence_id] = str(target.get("group_id") or "")
                grouped_quantity_rows.append(evidence_id)
                continue
        group = _group_from_row(len(groups) + 1, row, ledger_row)
        groups.append(group)
        group_by_evidence_id[evidence_id] = str(group.get("group_id") or "")
    for row in deferred_covered:
        _attach_deferred_row(row, ledger_by_id, groups, group_by_evidence_id)
    return groups, {
        "schema_id": "analyst_group_accounting_v1",
        "method": "row_adjudication_grouping",
        "grouped_quantity_row_ids": grouped_quantity_rows,
        "group_count": len(groups),
        "covered_evidence_item_ids": _dedupe(
            [
                evidence_id
                for group in groups
                for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
            ]
        ),
        "foreground_group_count": sum(1 for group in groups if group.get("memo_role") in FOREGROUND_MEMO_USES),
    }


def _quarantine_source_faithfulness_conflicts(
    groups: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    warnings_by_id = {
        str(warning.get("evidence_item_id") or ""): warning
        for warning in warnings
        if isinstance(warning, dict) and str(warning.get("evidence_item_id") or "").strip()
    }
    if not warnings_by_id:
        return groups, {}
    revised = []
    quarantined = []
    for group in groups:
        if not isinstance(group, dict):
            revised.append(group)
            continue
        evidence_ids = _string_list(group.get("covered_evidence_item_ids"))
        group_warnings = [warnings_by_id[evidence_id] for evidence_id in evidence_ids if evidence_id in warnings_by_id]
        if not group_warnings or str(group.get("memo_role") or "") != "load_bearing_primary_support":
            revised.append(group)
            continue
        replacement_role = _quarantine_replacement_role(group_warnings)
        updated = dict(group)
        updated["memo_role"] = replacement_role
        updated["answer_relation"] = _quarantine_replacement_answer_relation(group_warnings, str(group.get("answer_relation") or ""))
        updated["effect_on_final_answer"] = _quarantine_replacement_effect(group_warnings, str(group.get("effect_on_final_answer") or ""))
        updated["conflict_note"] = _short_text(
            "Source-faithfulness warning: this evidence cannot serve as primary support until the source-bottom-line conflict is resolved.",
            320,
        )
        updated["rationale"] = _short_text(
            " ".join(
                part
                for part in (
                    str(group.get("rationale") or ""),
                    "Routed away from primary support because source bottom-line polarity conflicts with the assigned answer role.",
                )
                if part
            ),
            420,
        )
        revised.append(updated)
        quarantined.append(
            {
                "group_id": str(group.get("group_id") or ""),
                "from_memo_role": "load_bearing_primary_support",
                "to_memo_role": replacement_role,
                "evidence_item_ids": [warning.get("evidence_item_id") for warning in group_warnings],
                "warning_reasons": _dedupe([str(warning.get("warning") or "") for warning in group_warnings if warning.get("warning")]),
            }
        )
    return revised, {
        "schema_id": "source_faithfulness_quarantine_v1",
        "quarantined_group_count": len(quarantined),
        "quarantined_groups": quarantined,
    } if quarantined else {}


def _quarantine_replacement_role(warnings: list[dict[str, Any]]) -> str:
    reasons = {str(warning.get("warning") or "") for warning in warnings}
    if "source_bottom_line_increased_risk_but_row_supports_neutral_or_beneficial_answer" in reasons:
        return "load_bearing_counterweight"
    return "needs_human_or_model_review"


def _quarantine_replacement_answer_relation(warnings: list[dict[str, Any]], current: str) -> str:
    reasons = {str(warning.get("warning") or "") for warning in warnings}
    if "source_bottom_line_increased_risk_but_row_supports_neutral_or_beneficial_answer" in reasons:
        return "challenges_answer"
    return current if current and current != "supports_answer" else "uncertain_relation"


def _quarantine_replacement_effect(warnings: list[dict[str, Any]], current: str) -> str:
    reasons = {str(warning.get("warning") or "") for warning in warnings}
    if "source_bottom_line_increased_risk_but_row_supports_neutral_or_beneficial_answer" in reasons:
        return "weakens current_best_answer"
    return current if current and not current.startswith("supports ") else "explains tension"


def _align_groups_with_adjudication_roles(
    groups: list[dict[str, Any]],
    adjudication_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    adjudication_by_id = {
        str(row.get("evidence_item_id") or ""): row
        for row in adjudication_rows
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    }
    revised = []
    aligned = []
    for group in groups:
        if not isinstance(group, dict):
            revised.append(group)
            continue
        evidence_ids = _string_list(group.get("covered_evidence_item_ids"))
        repaired_rows = [
            adjudication_by_id[evidence_id]
            for evidence_id in evidence_ids
            if _is_source_faithfulness_repaired_row(adjudication_by_id.get(evidence_id, {}))
        ]
        if not repaired_rows:
            revised.append(group)
            continue
        updated = dict(group)
        updated["memo_role"] = "load_bearing_counterweight"
        updated["answer_relation"] = "challenges_answer"
        updated["effect_on_final_answer"] = "weakens current_best_answer"
        updated["proposition"] = _short_text(
            "This evidence should bound or challenge the current answer because source-level bottom lines conflict with using it as primary support.",
            620,
        )
        updated["conflict_note"] = _short_text(
            "Aligned with source-faithfulness-repaired adjudication rows: "
            + "; ".join(str(row.get("evidence_item_id") or "") for row in repaired_rows),
            320,
        )
        updated["rationale"] = _short_text(
            " ".join(
                part
                for part in (
                    str(group.get("rationale") or ""),
                    "The group role follows repaired adjudication labels rather than support-shaped relation wording.",
                )
                if part
            ),
            420,
        )
        revised.append(updated)
        aligned.append(
            {
                "group_id": str(group.get("group_id") or ""),
                "evidence_item_ids": [str(row.get("evidence_item_id") or "") for row in repaired_rows],
                "to_memo_role": "load_bearing_counterweight",
                "reason": "source_faithfulness_repaired_adjudication",
            }
        )
    return revised, {
        "schema_id": "adjudication_role_alignment_v1",
        "aligned_group_count": len(aligned),
        "aligned_groups": aligned,
    } if aligned else {}


def _is_source_faithfulness_repaired_row(row: dict[str, Any]) -> bool:
    if not isinstance(row, dict):
        return False
    if str(row.get("memo_use") or "") != "load_bearing_counterweight":
        return False
    if str(row.get("answer_relation") or "") != "challenges_answer":
        return False
    return "Source-faithfulness repair" in str(row.get("source_weight_note") or "") or "source-bottom-line conflict" in str(
        row.get("misuse_warning") or ""
    )


def _build_answer_frame(
    packet: dict[str, Any],
    ledger: dict[str, Any],
    adjudication_rows: list[dict[str, Any]],
    groups: list[dict[str, Any]],
    *,
    refinement: dict[str, Any],
    decision_model: dict[str, Any],
) -> dict[str, Any]:
    support_ids = _ids_for_roles(adjudication_rows, {"load_bearing_primary_support", "quantitative_anchor"}, limit=8)
    counter_ids = _ids_for_roles(adjudication_rows, {"load_bearing_counterweight"}, limit=5)
    scope_ids = _ids_for_roles(adjudication_rows, {"scope_or_applicability"}, limit=5)
    crux_ids = _ids_for_roles(adjudication_rows, {"decision_crux"}, limit=5)
    direct_answer = _clean_answer_text(_dict(packet.get("answer_frame")).get("default_answer")) or _clean_answer_text(
        _dict(packet.get("answer_spine")).get("default_read")
    )
    question = str(ledger.get("decision_question") or packet.get("decision_question") or "").strip()
    if not direct_answer or is_weak_answer_frame(direct_answer, question=question):
        direct_answer = _why_this_read(groups)
    model_answer = str(decision_model.get("direct_answer") or "").strip()
    if model_answer and not is_weak_answer_frame(model_answer, question=question):
        direct_answer = _short_text(model_answer, 420)
    refined_answer = str(refinement.get("direct_answer") or "").strip()
    if refined_answer and not is_weak_answer_frame(refined_answer, question=question):
        direct_answer = _short_text(refined_answer, 420)
    return {
        "schema_id": "analyst_answer_frame_v1",
        "decision_question": question,
        "direct_answer": direct_answer,
        "confidence": str(decision_model.get("confidence") or _dict(packet.get("answer_frame")).get("confidence") or "not_specified"),
        "why_this_read": _short_text(str(refinement.get("answer_rationale") or decision_model.get("overall_rationale") or ""), 620) or _why_this_read(groups),
        "strongest_counterargument": _first_group_text(groups, "load_bearing_counterweight"),
        "why_counterargument_does_or_does_not_change_answer": "Weigh the main counterweight against the primary support rather than listing both as independent facts.",
        "scope": _first_group_text(groups, "scope_or_applicability"),
        "what_would_change_the_answer": _first_group_text(groups, "decision_crux"),
        "must_not_overstate": _must_not_overstate(groups),
        "supporting_evidence_item_ids": support_ids,
        "counterweight_evidence_item_ids": counter_ids,
        "scope_evidence_item_ids": _dedupe([*scope_ids, *crux_ids]),
    }


def _build_synthesis_packet(
    *,
    packet: dict[str, Any],
    ledger: dict[str, Any],
    adjudication: dict[str, Any],
    decision_model: dict[str, Any],
    groups: list[dict[str, Any]],
    answer_frame: dict[str, Any],
    group_accounting: dict[str, Any],
    warning_packet: dict[str, Any],
    refinement: dict[str, Any],
) -> dict[str, Any]:
    warning_obligations = _warning_obligations(refinement, warning_packet)
    result = {
        "schema_id": "analyst_synthesis_packet_v1",
        "decision_question": str(ledger.get("decision_question") or packet.get("decision_question") or "").strip(),
        "bottom_line": str(answer_frame.get("direct_answer") or "").strip(),
        "primary_reasoning_chain": _groups_for(groups, "load_bearing_primary_support", limit=8),
        "main_counterweights": _groups_for(groups, "load_bearing_counterweight", limit=6),
        "decision_cruxes": _groups_for(groups, "decision_crux", limit=6),
        "scope_and_applicability": _groups_for(groups, "scope_or_applicability", limit=6),
        "quantitative_anchors": _groups_for(groups, "quantitative_anchor", limit=8),
        "background_context": _background_groups(groups, limit=10),
        "must_not_overstate": _dedupe(_string_list(answer_frame.get("must_not_overstate"))),
        "warnings_to_address": _warnings_to_address(warning_packet, adjudication, warning_obligations=warning_obligations),
        "warning_obligations": warning_obligations,
        "argument_plan": _argument_plan(refinement, groups, warning_obligations, decision_model=decision_model),
        "decision_logic": analyst_decision_logic(_merged_refinement(refinement, decision_model), answer_frame, groups, warning_obligations),
        "writer_guidance_packet": _dict(packet.get("writer_guidance_packet")),
        "source_notes": _source_notes(packet),
        "evidence_accounting_summary": _evidence_accounting_summary(ledger, adjudication, groups, group_accounting),
    }
    return AnalystSynthesisPacket.model_validate(result).model_dump()


def _build_analyst_memo_ready_packet(
    *,
    packet: dict[str, Any],
    synthesis_packet: dict[str, Any],
    warning_packet: dict[str, Any],
    quality: dict[str, Any],
    quantity_binding: dict[str, Any],
) -> dict[str, Any]:
    evidence_items = []
    mandatory_group_ids = _mandatory_group_ids(synthesis_packet)
    writer_guidance_packet = _dict(packet.get("writer_guidance_packet")) or _dict(synthesis_packet.get("writer_guidance_packet"))
    for section in _synthesis_group_sections(synthesis_packet):
        for group in _list(synthesis_packet.get(section)):
            if not isinstance(group, dict):
                continue
            evidence_items.append(
                _memo_ready_item_from_group(
                    len(evidence_items) + 1,
                    group,
                    must_use=str(group.get("group_id") or "") in mandatory_group_ids,
                    quantity_bindings=quantity_bindings_for_group(quantity_binding, str(group.get("group_id") or "")),
                )
            )
    for obligation in _list(synthesis_packet.get("warning_obligations")):
        if isinstance(obligation, dict) and str(obligation.get("memo_action") or "") != "not_needed_for_memo":
            evidence_items.append(_memo_ready_item_from_warning_obligation(len(evidence_items) + 1, obligation))
    memo_ready = {
        "schema_id": "memo_ready_packet_v1",
        "method": "analyst_adjudicated_packet_adapter",
        "decision_question": synthesis_packet.get("decision_question"),
        "answer_spine": {
            "default_read": synthesis_packet.get("bottom_line"),
            "confidence": _dict(packet.get("answer_frame")).get("confidence", "not_specified"),
            "synthesis_strategy": "Write from the compact analyst synthesis packet; background evidence is accounted for but not mandatory prose.",
        },
        "source_trail": _memo_ready_source_trail(packet, evidence_items),
        "memo_warning_packet": warning_packet,
        "memo_obligations": build_memo_obligation_packet(evidence_items, warning_packet, writer_guidance_packet),
        "analyst_synthesis_packet": synthesis_packet,
        "analyst_argument_plan": synthesis_packet.get("argument_plan", []),
        "analyst_decision_logic": synthesis_packet.get("decision_logic", {}),
        "writer_guidance_packet": writer_guidance_packet,
        "compact_writer_guidance": compact_writer_guidance_for_model(writer_guidance_packet),
        "analyst_quantity_binding_report": quantity_binding,
        "analyst_packet_quality_report": quality,
        "evidence_items": evidence_items,
    }
    writer_packet = build_writer_packet(memo_ready)
    memo_ready["writer_packet"] = writer_packet
    memo_ready["writer_packet_quality_report"] = writer_packet.get("writer_packet_quality_report", {})
    memo_ready["decision_synthesis_contract"] = build_memo_ready_decision_synthesis_contract(memo_ready)
    memo_ready["canonical_decision_writer_packet"] = canonical = build_canonical_decision_writer_packet(memo_ready)
    memo_ready["canonical_decision_writer_packet_quality_report"] = canonical.get("quality_report", {})
    return memo_ready


def _memo_ready_source_trail(packet: dict[str, Any], evidence_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_lookup = _source_metadata_lookup(packet)
    rows_by_key: dict[str, dict[str, Any]] = {}
    for item in evidence_items:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "context").strip() or "context"
        for source_ref in _source_refs_for_item(item):
            metadata = _lookup_source_metadata(source_lookup, source_ref)
            key = _source_row_key(metadata, source_ref)
            if not key:
                continue
            row = rows_by_key.setdefault(
                key,
                {
                    "source_id": metadata.get("source_id") or source_ref,
                    "source_label": metadata.get("source_label") or source_ref,
                    "display_label": metadata.get("display_label") or "",
                    "citation_label": metadata.get("citation_label") or "",
                    "source_url": metadata.get("source_url") or "",
                    "used_for": [],
                    "appears_in_packet": True,
                },
            )
            row["used_for"] = _dedupe([*row.get("used_for", []), role])
    return [
        _drop_empty(row)
        for row in sorted(
            rows_by_key.values(),
            key=lambda row: (str(row.get("source_label") or ""), str(row.get("source_id") or "")),
        )
    ]


def _source_metadata_lookup(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for row in _list(packet.get("source_trail")):
        if not isinstance(row, dict):
            continue
        metadata = {
            "source_id": str(row.get("source_id") or row.get("id") or "").strip(),
            "source_label": str(row.get("source_label") or row.get("label") or row.get("citation_label") or row.get("display_label") or "").strip(),
            "display_label": str(row.get("display_label") or "").strip(),
            "citation_label": str(row.get("citation_label") or "").strip(),
            "source_url": str(row.get("source_url") or row.get("url") or "").strip(),
        }
        for alias in _source_aliases(metadata):
            lookup[_source_key(alias)] = metadata
    return lookup


def _source_refs_for_item(item: dict[str, Any]) -> list[str]:
    return _dedupe(
        [
            *_string_list(item.get("source_ids")),
            *_string_list(item.get("source_labels")),
            str(item.get("source_label") or "").strip(),
        ]
    )


def _lookup_source_metadata(lookup: dict[str, dict[str, Any]], source_ref: str) -> dict[str, str]:
    return lookup.get(_source_key(source_ref), {})

def _source_row_key(metadata: dict[str, Any], source_ref: str) -> str:
    return _source_key(str(metadata.get("source_id") or metadata.get("source_label") or source_ref or ""))


def _source_aliases(metadata: dict[str, Any]) -> list[str]:
    return _dedupe(
        [
            str(metadata.get("source_id") or ""),
            str(metadata.get("source_label") or ""),
            str(metadata.get("display_label") or ""),
            str(metadata.get("citation_label") or ""),
            str(metadata.get("source_url") or ""),
        ]
    )


def _source_key(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in (None, "", [], {})}


def _mandatory_group_ids(synthesis_packet: dict[str, Any]) -> set[str]:
    groups = [
        *(_list(synthesis_packet.get("primary_reasoning_chain"))[:4]),
        *(_list(synthesis_packet.get("main_counterweights"))[:3]),
        *(_list(synthesis_packet.get("scope_and_applicability"))[:3]),
        *(_list(synthesis_packet.get("decision_cruxes"))[:3]),
    ]
    return {
        str(group.get("group_id") or "")
        for group in groups
        if isinstance(group, dict) and not _weak_group_proposition(str(group.get("proposition") or ""))
    }


def _memo_ready_item_from_group(
    index: int,
    group: dict[str, Any],
    *,
    must_use: bool,
    quantity_bindings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    memo_role = str(group.get("source_memo_role") or group.get("memo_role") or "")
    reader_role = _memo_ready_role_for_group(group)
    source_labels = _string_list(group.get("source_labels"))
    proposition = str(group.get("proposition") or "")
    quantities = [
        _memo_ready_quantity_from_binding(binding)
        for binding in (quantity_bindings or [])
        if isinstance(binding, dict) and str(binding.get("value") or "").strip()
    ]
    claim = _reader_claim_with_key_quantities(proposition, [row["value"] for row in quantities])
    return {
        "item_id": f"analyst_item_{index:03d}",
        "role": reader_role,
        "source_memo_role": memo_role,
        "answer_relation": str(group.get("answer_relation") or "").strip(),
        "target_answer_option": str(group.get("target_answer_option") or "").strip(),
        "effect_on_final_answer": str(group.get("effect_on_final_answer") or "").strip(),
        "tension_type": str(group.get("tension_type") or "").strip(),
        "reader_claim": claim,
        "source_label": source_labels[0] if source_labels else "",
        "source_labels": source_labels,
        "source_ids": _string_list(group.get("source_ids")),
        "quantities": quantities,
        "lineage": {"analyst_group_id": group.get("group_id"), "evidence_item_ids": group.get("covered_evidence_item_ids", [])},
        "quantity_binding_lineage": [
            {
                "candidate_id": binding.get("candidate_id"),
                "source_evidence_item_id": binding.get("source_evidence_item_id"),
                "binding_source": binding.get("binding_source"),
                "binding_confidence": binding.get("binding_confidence"),
                "deterministic_warnings": binding.get("deterministic_warnings", []),
            }
            for binding in (quantity_bindings or [])
            if isinstance(binding, dict)
        ],
        "decision_relevance": group.get("rationale"),
        "caveat": "; ".join(_string_list(group.get("applicability_limits"))),
        "source_appraisal": group.get("source_appraisal") if isinstance(group.get("source_appraisal"), dict) else {},
        "source_use_warnings": _string_list(group.get("source_use_warnings")),
        "allowed_wording": group.get("allowed_wording") if isinstance(group.get("allowed_wording"), dict) else {},
        "must_use": must_use,
    }


def _memo_ready_quantity_from_binding(binding: dict[str, Any]) -> dict[str, str]:
    return _drop_empty(
        {
            "value": str(binding.get("value") or "").strip(),
            "interpretation": str(binding.get("interpretation") or "").strip(),
            "source_evidence_item_id": str(binding.get("source_evidence_item_id") or "").strip(),
            "source_labels": _string_list(binding.get("source_labels")),
            "binding_confidence": str(binding.get("binding_confidence") or "").strip(),
        }
    )


def _memo_ready_item_from_warning_obligation(index: int, obligation: dict[str, Any]) -> dict[str, Any]:
    action = str(obligation.get("memo_action") or "")
    severity = str(obligation.get("severity") or "")
    source_labels = _string_list(obligation.get("source_labels"))
    role = "strongest_counterweight" if action == "incorporate_as_counterweight" else "scope_boundary" if action == "bound_scope_or_confidence" or severity == "critical" else "context_only"
    return {
        "item_id": f"analyst_warning_item_{index:03d}",
        "role": role,
        "reader_claim": str(obligation.get("obligation") or "").strip(),
        "source_label": source_labels[0] if source_labels else "",
        "source_labels": source_labels,
        "source_ids": [],
        "quantities": [],
        "lineage": {"warning_id": obligation.get("warning_id")},
        "decision_relevance": obligation.get("rationale"),
        "caveat": obligation.get("rationale"),
        "must_use": action in {"incorporate_as_counterweight", "bound_scope_or_confidence"} or severity == "critical",
    }


def _reader_claim_with_key_quantities(claim: str, quantities: list[str]) -> str:
    claim = claim.strip()
    if not claim or not quantities:
        return claim
    already_present = [quantity for quantity in quantities if quantity.lower() in claim.lower()]
    missing = [quantity for quantity in quantities if quantity not in already_present]
    if not missing:
        return claim
    return _short_text(f"{claim} Key quantitative anchors: {'; '.join(missing)}.", 700)


def _weak_group_proposition(text: str) -> bool:
    stripped = " ".join(str(text or "").split())
    if not stripped:
        return True
    if stripped.count(";") >= 5 and len(stripped.split()) <= 24:
        return True
    lowered = stripped.lower()
    if lowered.startswith(("keywords:", "mesh terms:", "cardiovascular diseases;")):
        return True
    return False


def _source_faithfulness_warnings(ledger: dict[str, Any], adjudication: dict[str, Any]) -> list[dict[str, Any]]:
    return _shared_source_faithfulness_warnings(ledger, adjudication)


def _source_faithfulness_warning_reason(ledger_row: dict[str, Any], adjudication_row: dict[str, Any]) -> str:
    return _shared_source_faithfulness_warning_reason(ledger_row, adjudication_row)


def _group_from_row(index: int, adjudication_row: dict[str, Any], ledger_row: dict[str, Any]) -> dict[str, Any]:
    evidence_id = str(adjudication_row.get("evidence_item_id") or "")
    memo_use = str(adjudication_row.get("memo_use") or "needs_human_or_model_review")
    source_labels = _string_list(ledger_row.get("source_labels"))
    quantity_values = _dedupe([*_string_list(ledger_row.get("quantity_values")), *_string_list(adjudication_row.get("quantity_values"))])
    return {
        "group_id": f"analyst_group_{index:03d}",
        "proposition": _short_text(str(ledger_row.get("claim") or adjudication_row.get("rationale") or evidence_id), 520),
        "memo_role": memo_use if memo_use in SECTION_BY_MEMO_USE else "needs_human_or_model_review",
        "answer_relation": str(adjudication_row.get("answer_relation") or "").strip(),
        "target_answer_option": _short_text(str(adjudication_row.get("target_answer_option") or ""), 220),
        "effect_on_final_answer": _short_text(str(adjudication_row.get("effect_on_final_answer") or ""), 260),
        "tension_type": str(adjudication_row.get("tension_type") or "").strip(),
        "importance_rank": int(adjudication_row.get("importance_rank", 100) or 100),
        "covered_evidence_item_ids": [evidence_id],
        "source_ids": _dedupe([*_string_list(ledger_row.get("source_ids")), *_string_list(adjudication_row.get("source_ids"))]),
        "source_labels": source_labels,
        "source_bottom_lines": _list(ledger_row.get("source_bottom_lines"))[:6],
        "source_bottom_line_signals": _string_list(ledger_row.get("source_bottom_line_signals"))[:6],
        "source_appraisal": ledger_row.get("source_appraisal") if isinstance(ledger_row.get("source_appraisal"), dict) else {},
        "source_use_warnings": _string_list(ledger_row.get("source_use_warnings")),
        "allowed_wording": ledger_row.get("allowed_wording") if isinstance(ledger_row.get("allowed_wording"), dict) else {},
        "quantity_values": quantity_values,
        "applicability_limits": _applicability_limits(memo_use, ledger_row, adjudication_row),
        "rationale": _short_text(str(adjudication_row.get("rationale") or ledger_row.get("why_it_matters") or "Adjudicated as relevant to the decision."), 320),
        "conflict_note": "",
    }


def _attach_deferred_row(
    row: dict[str, Any],
    ledger_by_id: dict[str, dict[str, Any]],
    groups: list[dict[str, Any]],
    group_by_evidence_id: dict[str, str],
) -> None:
    evidence_id = str(row.get("evidence_item_id") or "")
    targets = _string_list(row.get("covered_by"))
    for target in targets:
        group_id = group_by_evidence_id.get(target, target if target.startswith("analyst_group_") else "")
        group = next((candidate for candidate in groups if str(candidate.get("group_id") or "") == group_id), None)
        if group is None:
            continue
        group["covered_evidence_item_ids"] = _dedupe([*group.get("covered_evidence_item_ids", []), evidence_id])
        _merge_quantity_into_group(group, row, ledger_by_id.get(evidence_id, {}))
        return
    if str(row.get("memo_use") or "") == "covered_by_group":
        group = _group_from_row(len(groups) + 1, {**row, "memo_use": "background_only"}, ledger_by_id.get(evidence_id, {}))
        group["rationale"] = _short_text(str(row.get("rationale") or "Marked covered, but no valid target group was available."), 320)
        groups.append(group)


def _quantity_target_group(
    adjudication_row: dict[str, Any],
    ledger_row: dict[str, Any],
    groups: list[dict[str, Any]],
) -> dict[str, Any] | None:
    source_ids = set(_string_list(ledger_row.get("source_ids")) or _string_list(adjudication_row.get("source_ids")))
    quantity_values = set(_string_list(ledger_row.get("quantity_values")) or _string_list(adjudication_row.get("quantity_values")))
    if not source_ids and not quantity_values:
        return None
    for group in groups:
        if group.get("memo_role") not in {"load_bearing_primary_support", "load_bearing_counterweight", "scope_or_applicability", "decision_crux"}:
            continue
        group_sources = set(_string_list(group.get("source_ids")))
        group_quantities = set(_string_list(group.get("quantity_values")))
        if (source_ids and source_ids & group_sources) or (quantity_values and quantity_values & group_quantities):
            return group
    return None


def _merge_quantity_into_group(group: dict[str, Any], adjudication_row: dict[str, Any], ledger_row: dict[str, Any]) -> None:
    group["quantity_values"] = _dedupe(
        [
            *_string_list(group.get("quantity_values")),
            *_string_list(ledger_row.get("quantity_values")),
            *_string_list(adjudication_row.get("quantity_values")),
        ]
    )


def _evidence_accounting_summary(
    ledger: dict[str, Any],
    adjudication: dict[str, Any],
    groups: list[dict[str, Any]],
    group_accounting: dict[str, Any],
) -> dict[str, Any]:
    ledger_ids = _ledger_ids(ledger)
    adjudication_rows = [row for row in _list(adjudication.get("rows")) if isinstance(row, dict)]
    foreground_ids = {
        evidence_id
        for group in groups
        if group.get("memo_role") in FOREGROUND_MEMO_USES
        for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
    }
    accounted_ids = {
        evidence_id
        for group in groups
        for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
    }
    accounted_ids.update(_string_list(group_accounting.get("accounted_evidence_item_ids")))
    explicitly_downgraded_ids = {
        str(row.get("evidence_item_id") or "")
        for row in adjudication_rows
        if str(row.get("memo_use") or "") == "not_decision_relevant" and str(row.get("evidence_item_id") or "").strip()
    }
    explicitly_downgraded_ids.update(_string_list(group_accounting.get("explicitly_downgraded_evidence_item_ids")))
    accounted_ids.update(explicitly_downgraded_ids)
    return {
        "ledger_row_count": len(ledger_ids),
        "adjudicated_row_count": len({str(row.get("evidence_item_id") or "") for row in adjudication_rows}),
        "memo_use_counts": dict(Counter(str(row.get("memo_use") or "unknown") for row in adjudication_rows)),
        "accounted_evidence_item_ids": sorted(accounted_ids),
        "foreground_evidence_item_ids": sorted(foreground_ids),
        "background_or_downgraded_evidence_item_ids": sorted(set(accounted_ids) - foreground_ids),
        "explicitly_downgraded_evidence_item_ids": sorted(explicitly_downgraded_ids),
        "unaccounted_evidence_item_ids": sorted(set(ledger_ids) - accounted_ids),
        "group_accounting": group_accounting,
    }


def _warnings_to_address(
    warning_packet: dict[str, Any],
    adjudication: dict[str, Any],
    *,
    warning_obligations: list[dict[str, Any]],
) -> list[str]:
    if warning_obligations:
        return _dedupe(
            [
                _short_text(str(row.get("obligation") or ""), 280)
                for row in warning_obligations
                if str(row.get("memo_action") or "") != "not_needed_for_memo" and str(row.get("obligation") or "").strip()
            ]
        )
    warning_rows = [
        row
        for row in _list(adjudication.get("rows"))
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").startswith("warning:")
    ]
    warnings = []
    for row in warning_rows:
        text = str(row.get("rationale") or "").strip()
        if text:
            warnings.append(text)
    for warning in _list(warning_packet.get("warnings")):
        if isinstance(warning, dict) and warning.get("claim"):
            warnings.append(str(warning.get("claim")))
    return _dedupe([_short_text(warning, 280) for warning in warnings if warning.strip()])


def _warning_obligations(refinement: dict[str, Any], warning_packet: dict[str, Any]) -> list[dict[str, Any]]:
    by_id = {
        str(row.get("warning_id") or ""): row
        for row in _list(warning_packet.get("warnings"))
        if isinstance(row, dict) and str(row.get("warning_id") or "").strip()
    }
    rows = []
    for obligation in _list(refinement.get("warning_obligations")):
        if not isinstance(obligation, dict):
            continue
        warning_id = str(obligation.get("warning_id") or "").strip()
        if warning_id not in by_id:
            continue
        source_labels = _string_list(obligation.get("source_labels")) or _string_list(by_id[warning_id].get("source_labels"))
        rows.append(
            {
                "warning_id": warning_id,
                "memo_action": str(obligation.get("memo_action") or "bound_scope_or_confidence"),
                "obligation": _short_text(str(obligation.get("obligation") or by_id[warning_id].get("claim") or ""), 360),
                "rationale": _short_text(str(obligation.get("rationale") or ""), 260),
                "source_labels": source_labels,
                "key_terms": _string_list(obligation.get("key_terms"))[:8],
                "severity": by_id[warning_id].get("severity"),
            }
        )
    return rows


def _argument_plan(
    refinement: dict[str, Any],
    groups: list[dict[str, Any]],
    warning_obligations: list[dict[str, Any]],
    *,
    decision_model: dict[str, Any],
) -> list[dict[str, Any]]:
    refined = [row for row in _list(refinement.get("argument_plan")) if isinstance(row, dict)]
    if refined:
        return [_normalize_argument_plan_step(index + 1, row) for index, row in enumerate(refined)]
    model_plan = [row for row in _list(decision_model.get("argument_plan")) if isinstance(row, dict)]
    if model_plan:
        return [_normalize_argument_plan_step(index + 1, row) for index, row in enumerate(model_plan)]
    return _deterministic_argument_plan(groups, warning_obligations)


def _merged_refinement(refinement: dict[str, Any], decision_model: dict[str, Any]) -> dict[str, Any]:
    if not decision_model:
        return refinement
    decision_logic = _dict(decision_model.get("decision_logic"))
    merged = {
        "direct_answer": decision_model.get("direct_answer"),
        "answer_rationale": decision_model.get("overall_rationale"),
        "decision_logic": decision_logic,
        "argument_plan": decision_model.get("argument_plan", []),
    }
    return {**merged, **refinement}


def _normalize_argument_plan_step(index: int, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "step_id": str(row.get("step_id") or f"step_{index:02d}"),
        "section": str(row.get("section") or "Decision-Relevant Evidence"),
        "writing_goal": _short_text(str(row.get("writing_goal") or ""), 360),
        "required_points": [_short_text(point, 260) for point in _string_list(row.get("required_points"))[:6]],
        "evidence_item_ids": _string_list(row.get("evidence_item_ids"))[:12],
        "source_labels": _string_list(row.get("source_labels"))[:8],
        "transition_from_previous": _short_text(str(row.get("transition_from_previous") or ""), 220),
    }


def _deterministic_argument_plan(groups: list[dict[str, Any]], warning_obligations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    steps = []
    for step_id, section, roles, goal in (
        ("answer_and_support", "Decision Brief", {"load_bearing_primary_support"}, "State the direct answer and summarize the main support."),
        ("counterweight_and_weighting", "Why This Is the Best Current Read", {"load_bearing_counterweight"}, "Acknowledge the strongest counterweight and explain how it bounds the answer."),
        ("cruxes", "What Could Change the Answer", {"decision_crux"}, "Explain what evidence would change the answer."),
        ("scope", "Decision-Relevant Evidence", {"scope_or_applicability"}, "State the population and applicability boundaries."),
    ):
        selected = [group for group in groups if _effective_memo_role(group) in roles][:4]
        if not selected:
            continue
        steps.append(
            {
                "step_id": step_id,
                "section": section,
                "writing_goal": goal,
                "required_points": [_short_text(str(group.get("proposition") or ""), 260) for group in selected if group.get("proposition")],
                "evidence_item_ids": [
                    evidence_id
                    for group in selected
                    for evidence_id in _string_list(group.get("covered_evidence_item_ids"))
                ][:12],
                "source_labels": list(
                    dict.fromkeys(
                        source
                        for group in selected
                        for source in _string_list(group.get("source_labels"))
                    )
                )[:8],
                "transition_from_previous": "Integrate this step with the previous reasoning rather than listing it as a separate fact.",
            }
        )
    actionable = [row for row in warning_obligations if row.get("memo_action") != "not_needed_for_memo"]
    if actionable:
        steps.append(
            {
                "step_id": "warning_bounds",
                "section": "Decision-Relevant Evidence",
                "writing_goal": "Use warning obligations as scope, context, or confidence bounds.",
                "required_points": [_short_text(str(row.get("obligation") or ""), 260) for row in actionable[:4]],
                "evidence_item_ids": [str(row.get("warning_id") or "") for row in actionable[:4]],
                "source_labels": list(dict.fromkeys(source for row in actionable for source in _string_list(row.get("source_labels"))))[:8],
                "transition_from_previous": "Use these obligations to calibrate the answer.",
            }
        )
    return steps


def _memo_facing_warning_packet(warning_packet: dict[str, Any], synthesis_packet: dict[str, Any]) -> dict[str, Any]:
    obligations = {
        str(row.get("warning_id") or ""): row
        for row in _list(synthesis_packet.get("warning_obligations"))
        if isinstance(row, dict) and str(row.get("warning_id") or "").strip()
    }
    if not obligations:
        return warning_packet
    warnings = []
    for warning in _list(warning_packet.get("warnings")):
        if not isinstance(warning, dict):
            continue
        obligation = obligations.get(str(warning.get("warning_id") or ""))
        if not obligation:
            warnings.append(warning)
            continue
        action = str(obligation.get("memo_action") or "")
        if action == "not_needed_for_memo":
            continue
        claim = str(obligation.get("obligation") or warning.get("claim") or "").strip()
        anchor_text = " ".join([claim, " ".join(_string_list(obligation.get("key_terms")))])
        warnings.append(
            {
                **warning,
                "claim": claim,
                "anchor_terms": _content_terms(anchor_text)[:10],
                "expected_memo_action": action or warning.get("expected_memo_action"),
                "repair_instruction": str(obligation.get("rationale") or warning.get("repair_instruction") or ""),
                "source_labels": _string_list(obligation.get("source_labels")) or _string_list(warning.get("source_labels")),
            }
        )
    return {
        **warning_packet,
        "warnings": warnings,
        "actionable_warning_count": len(warnings),
        "critical_warning_count": sum(1 for row in warnings if row.get("severity") == "critical"),
        "moderate_warning_count": sum(1 for row in warnings if row.get("severity") == "moderate"),
        "method": f"{warning_packet.get('method', 'memo_warning_packet')}_with_analyst_obligations",
    }


def _source_notes(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for source in _list(packet.get("source_trail")):
        if not isinstance(source, dict):
            continue
        label = str(source.get("source_label") or source.get("label") or "").strip()
        rows.append(
            {
                "source_id": source.get("source_id") or source.get("id") or label,
                "source_label": label,
                "source_url": source.get("source_url") or source.get("url") or "",
            }
        )
    return rows


def _sorted_adjudication_rows(adjudication: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in _list(adjudication.get("rows")) if isinstance(row, dict)]
    return sorted(rows, key=lambda row: (int(row.get("importance_rank", 100) or 100), str(row.get("evidence_item_id") or "")))


def _groups_for(groups: list[dict[str, Any]], memo_use: str, *, limit: int) -> list[dict[str, Any]]:
    return [_project_group_role(group, memo_use) for group in groups if _effective_memo_role(group) == memo_use][:limit]


def _background_groups(groups: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    return [
        _project_group_role(group, _effective_memo_role(group))
        for group in groups
        if _effective_memo_role(group) in {"mechanism_or_context", "background_only", "needs_human_or_model_review"}
    ][:limit]
