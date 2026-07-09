from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from epistemic_case_mapper.map_briefing_packet_eligibility import (
    decision_relevance_assessment,
    packet_candidate_eligibility,
    question_content_terms,
    question_overlap_count,
)
from epistemic_case_mapper.map_briefing_packet_sufficiency import (
    build_packet_sufficiency_report,
)
from epistemic_case_mapper.map_briefing_packet_coverage import build_packet_coverage_report
from epistemic_case_mapper.map_briefing_packet_model_view import packet_summary_for_model
from epistemic_case_mapper.map_briefing_section_views import build_section_views
from epistemic_case_mapper.map_briefing_answer_frame import normalize_answer_frame
from epistemic_case_mapper.map_briefing_decision_problem import (
    build_candidate_answer_set,
    build_decision_problem_report,
)
from epistemic_case_mapper.map_briefing_decision_obligations import build_decision_obligation_graph
from epistemic_case_mapper.map_briefing_decision_slots import build_decision_slot_inventory
from epistemic_case_mapper.map_briefing_evidence_answer_matrix import build_evidence_answer_matrix
from epistemic_case_mapper.map_briefing_packet_budget import (
    build_packet_budget_allocation_report,
    build_packet_compression_report,
)
from epistemic_case_mapper.map_briefing_source_evidence_graph import build_source_evidence_graph
from epistemic_case_mapper.map_briefing_source_bottom_lines import (
    source_bottom_line_candidates as _source_bottom_line_candidates,
)
from epistemic_case_mapper.map_briefing_top_quantity_candidates import build_top_quantity_anchor_candidates
from epistemic_case_mapper.map_briefing_vertical_slice_report import build_decision_model_vertical_slice_report


ROLE_ORDER = (
    "strongest_support",
    "counterweight",
    "scope_boundary",
    "decision_crux",
    "quantitative_anchor",
    "mechanism",
    "context",
)

CRITICAL_IMPORTANCE = {"critical", "high"}


def build_decision_briefing_packet_bundle(scaffold: dict[str, Any], *, question: str) -> dict[str, dict[str, Any]]:
    """Build the packet-first synthesis interface from existing scaffold artifacts.

    The packet is deliberately assembled before model critique/refinement. It
    records a broad candidate inventory, then emits sufficiency telemetry so
    lossy trimming is visible rather than hidden inside prose generation.
    """

    candidate_pool = _candidate_pool(scaffold, question=question)
    source_trail = _source_trail(scaffold, candidate_pool)
    bundles = _trimmed_bundles(candidate_pool)
    retain_ledger = _must_retain_ledger(scaffold, bundles)
    section_views = build_section_views(bundles, retain_ledger)
    answer_frame, answer_frame_report = _answer_frame(scaffold, question=question)
    decision_problem = build_decision_problem_report(scaffold, question=question)
    candidate_answers = build_candidate_answer_set(scaffold, question=question)
    source_evidence_graph = build_source_evidence_graph(scaffold)
    decision_obligations = build_decision_obligation_graph(
        question=question or str(scaffold.get("question", "")),
        decision_problem_report=decision_problem,
        candidate_answer_set=candidate_answers,
        source_evidence_graph=source_evidence_graph,
    )
    evidence_answer_matrix = build_evidence_answer_matrix(
        candidate_answer_set=candidate_answers,
        decision_obligation_graph=decision_obligations,
        source_evidence_graph=source_evidence_graph,
    )
    evidence_answer_matrix_quality_report = (
        evidence_answer_matrix.get("quality_report", {})
        if isinstance(evidence_answer_matrix.get("quality_report"), dict)
        else {}
    )
    decision_slots = build_decision_slot_inventory(
        decision_obligation_graph=decision_obligations,
        evidence_answer_matrix=evidence_answer_matrix,
    )
    budget_report = build_packet_budget_allocation_report(
        candidate_answer_set=candidate_answers,
        decision_slot_inventory=decision_slots,
        evidence_answer_matrix=evidence_answer_matrix,
    )
    compression_report = build_packet_compression_report(
        decision_slot_inventory=decision_slots,
        evidence_answer_matrix=evidence_answer_matrix,
    )
    packet = {
        "schema_id": "decision_briefing_packet_v1",
        "decision_question": question or str(scaffold.get("question", "")),
        "answer_frame": answer_frame,
        "decision_problem_report": decision_problem,
        "candidate_answer_set": candidate_answers,
        "source_evidence_graph": source_evidence_graph,
        "decision_obligation_graph": decision_obligations,
        "evidence_answer_matrix": evidence_answer_matrix,
        "evidence_answer_matrix_quality_report": evidence_answer_matrix_quality_report,
        "decision_slots": decision_slots,
        "packet_budget_allocation_report": budget_report,
        "packet_compression_report": compression_report,
        "must_retain_ledger": retain_ledger,
        "evidence_bundles": bundles,
        "section_views": section_views,
        "source_trail": source_trail,
        "coverage_report": build_packet_coverage_report(candidate_pool, bundles, retain_ledger, source_trail),
    }
    vertical_slice_report = build_decision_model_vertical_slice_report(packet)
    packet["decision_model_vertical_slice_report"] = vertical_slice_report
    sufficiency = build_packet_sufficiency_report(packet, candidate_pool=candidate_pool)
    report = _packet_builder_report(candidate_pool, packet, sufficiency)
    return {
        "decision_briefing_packet": packet,
        "answer_frame_normalization_report": answer_frame_report,
        "decision_problem_report": decision_problem,
        "candidate_answer_set": candidate_answers,
        "source_evidence_graph": source_evidence_graph,
        "decision_obligation_graph": decision_obligations,
        "evidence_answer_matrix": evidence_answer_matrix,
        "evidence_answer_matrix_quality_report": evidence_answer_matrix_quality_report,
        "decision_slots": decision_slots,
        "packet_budget_allocation_report": budget_report,
        "packet_compression_report": compression_report,
        "decision_model_vertical_slice_report": vertical_slice_report,
        "packet_sufficiency_report": sufficiency,
        "decision_briefing_packet_report": report,
    }


def _candidate_pool(scaffold: dict[str, Any], *, question: str = "") -> list[dict[str, Any]]:
    source_by_claim = _source_cards_by_claim(scaffold)
    source_by_id = {
        str(card.get("source_card_id")): card
        for card in _cards(scaffold.get("source_evidence_cards"))
        if str(card.get("source_card_id", "")).strip()
    }
    pool: list[dict[str, Any]] = []
    question_terms = question_content_terms(question or str(scaffold.get("question", "")))
    for card in _cards(scaffold.get("candidate_evidence_cards")):
        card_id = str(card.get("candidate_card_id", "")).strip()
        claim_ids = _string_list(card.get("claim_ids"))
        source_cards = _source_cards_for_candidate(card, source_by_claim, source_by_id)
        source_ids = _dedupe(
            [
                *_string_list(card.get("source_ids")),
                *[str(source.get("source_id", "")) for source in source_cards if source.get("source_id")],
            ]
        )
        source_labels = _source_labels(scaffold, source_ids, fallback=_string_list(card.get("source_titles")))
        quantity_values = _dedupe(
            [
                *_string_list(card.get("quantity_values")),
                *[
                    quantity
                    for source in source_cards
                    for quantity in _string_list(source.get("quantity_values"))
                ],
            ]
        )
        role = _decision_role(card, quantity_values=quantity_values)
        source_excerpt = _best_source_excerpt(card, source_cards)
        claim_text = _short_text(str(card.get("claim", "")), 420)
        pool.append(
            _drop_empty(
                {
                    "pool_id": f"pool_{len(pool)+1:04d}",
                    "candidate_card_id": card_id,
                    "source_card_ids": _dedupe(
                        [
                            *_string_list(card.get("source_card_ids")),
                            *[str(source.get("source_card_id", "")) for source in source_cards if source.get("source_card_id")],
                        ]
                    ),
                    "claim_ids": claim_ids,
                    "source_ids": source_ids,
                    "source_labels": source_labels,
                    "claim": claim_text,
                    "source_excerpt": _short_text(source_excerpt, 520),
                    "decision_role": role,
                    "decision_polarity": str(card.get("decision_polarity") or ""),
                    "raw_roles": _dedupe([str(card.get("role", "")), *_string_list(card.get("evidence_roles"))]),
                    "quantity_values": quantity_values[:8],
                    "limitations": _string_list(card.get("limitations"))[:6],
                    "section_candidates": _string_list(card.get("section_candidates"))[:8],
                    "decision_relevance_score": int(card.get("decision_relevance_score", 0) or 0),
                    "quality": card.get("quality"),
                    "inclusion_recommendation": card.get("inclusion_recommendation"),
                    "anchor_confidence": card.get("anchor_confidence"),
                    "why_it_matters": _short_text(str(card.get("inclusion_reason", "")), 240),
                    "limits": _candidate_limits(card),
                    "directionality": _directionality_for_role(role),
                    "source_grounded": bool(source_cards) or str(card.get("anchor_confidence", "")).lower() not in {"", "missing"},
                    "pretrim_kind": "candidate_evidence_card",
                    "question_overlap_count": question_overlap_count(str(card.get("claim", "")), question_terms),
                    "decision_relevance_assessment": decision_relevance_assessment(
                        " ".join([claim_text, source_excerpt]),
                        question_terms=question_terms,
                        decision_role=role,
                    ),
                }
            )
        )
    pool.extend(_source_bottom_line_candidates(scaffold, len(pool), question_terms=question_terms))
    pool.extend(_argument_item_candidates(scaffold, len(pool), question_terms=question_terms))
    pool.extend(_quantity_card_candidates(scaffold, len(pool), question_terms=question_terms))
    pool.extend(
        build_top_quantity_anchor_candidates(
            _top_quantity_anchor_groups(scaffold),
            offset=len(pool),
            question_terms=question_terms,
        )
    )
    return _dedupe_pool(pool)


def _source_cards_by_claim(scaffold: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    by_claim: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for card in _cards(scaffold.get("source_evidence_cards")):
        for claim_id in _string_list(card.get("claim_ids")):
            by_claim[claim_id].append(card)
    return by_claim


def _source_cards_for_candidate(
    card: dict[str, Any],
    source_by_claim: dict[str, list[dict[str, Any]]],
    source_by_id: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_card_id in _string_list(card.get("source_card_ids")):
        if source_card_id in source_by_id:
            rows.append(source_by_id[source_card_id])
    for claim_id in _string_list(card.get("claim_ids")):
        rows.extend(source_by_claim.get(claim_id, []))
    return _dedupe_dicts(rows, key_fields=("source_card_id", "source_id", "source_quote_or_excerpt"))


def _argument_item_candidates(scaffold: dict[str, Any], offset: int, *, question_terms: list[str] | None = None) -> list[dict[str, Any]]:
    argument = _dict(scaffold.get("argument_model"))
    source_by_claim = _source_cards_by_claim(scaffold)
    quantity_by_id = _quantity_rows_by_id(scaffold)
    specs = [
        ("strongest_support", "strongest_support", 9),
        ("counterweight", "strongest_counterarguments", 9),
        ("scope_boundary", "scope_boundaries", 8),
        ("decision_crux", "cruxes", 7),
        ("quantitative_anchor", "quantitative_anchors", 9),
    ]
    rows: list[dict[str, Any]] = []
    for role, key, base_score in specs:
        for item in [row for row in argument.get(key, []) if isinstance(row, dict)][:8]:
            claim_ids = _string_list(item.get("claim_ids"))[:8]
            quantity_ids = _string_list(item.get("quantity_ids"))[:8]
            quantities = _string_list(item.get("quantities"))[:8]
            if role == "quantitative_anchor" and not quantities:
                continue
            source_ids = _source_ids_for_argument_item(scaffold, item, source_by_claim=source_by_claim, quantity_by_id=quantity_by_id)
            statement = _short_text(str(item.get("statement", "")), 420)
            rows.append(
                _drop_empty(
                    {
                        "pool_id": f"pool_{offset+len(rows)+1:04d}",
                        "candidate_card_id": "",
                        "claim_ids": claim_ids,
                        "source_ids": source_ids,
                        "source_labels": _source_labels(scaffold, source_ids, fallback=_string_list(item.get("sources"))),
                        "relation_ids": _string_list(item.get("relation_ids"))[:8],
                        "quantity_ids": quantity_ids,
                        "claim": statement,
                        "decision_role": role,
                        "raw_roles": [key],
                        "quantity_values": quantities,
                        "limitations": _string_list(item.get("limitations"))[:6],
                        "decision_relevance_score": base_score,
                        "quality": item.get("weight"),
                        "why_it_matters": _short_text(str(item.get("why_it_matters", "")), 260),
                        "limits": _string_list(item.get("limitations"))[:6],
                        "directionality": _directionality_for_role(role),
                        "source_grounded": bool(source_ids or claim_ids),
                        "pretrim_kind": f"argument_model.{key}",
                        "question_overlap_count": question_overlap_count(str(item.get("statement", "")), question_terms or []),
                        "decision_relevance_assessment": decision_relevance_assessment(
                            statement,
                            question_terms=question_terms or [],
                            decision_role=role,
                        ),
                    }
                )
            )
    return rows


def _quantity_card_candidates(scaffold: dict[str, Any], offset: int, *, question_terms: list[str] | None = None) -> list[dict[str, Any]]:
    ledger = _dict(scaffold.get("quantity_ledger"))
    rows: list[dict[str, Any]] = []
    for card in [row for row in ledger.get("evidence_cards", []) if isinstance(row, dict)][:18]:
        quantities = _dedupe([*_string_list(card.get("key_quantities")), *_string_list(card.get("effect_estimates"))])
        if not quantities:
            continue
        source_ids = _source_ids_for_quantity_row(scaffold, card)
        if not source_ids and _is_relation_rationale_source(card):
            continue
        claim_text = _short_text(str(card.get("claim", "")), 420)
        context_text = _short_text(str(card.get("context", "")), 520)
        rows.append(
            _drop_empty(
                {
                    "pool_id": f"pool_{offset+len(rows)+1:04d}",
                    "candidate_card_id": str(card.get("atomic_evidence_card_id", "")),
                    "claim_ids": [str(card.get("claim_id", ""))] if str(card.get("claim_id", "")).strip() else [],
                    "quantity_ids": [str(card.get("card_id", ""))] if str(card.get("card_id", "")).strip() else [],
                    "source_ids": source_ids,
                    "source_labels": _source_labels(scaffold, source_ids, fallback=_string_list(card.get("source"))),
                    "claim": claim_text,
                    "source_excerpt": context_text,
                    "decision_role": "quantitative_anchor",
                    "raw_roles": ["quantity_ledger.evidence_cards"],
                    "quantity_values": quantities[:8],
                    "decision_relevance_score": min(10, max(7, int(card.get("card_score", 0) or 0) // 4)),
                    "quality": card.get("evidence_use"),
                    "why_it_matters": _short_text(str(card.get("interpretation_hint") or card.get("evidence_use") or ""), 260),
                    "limits": _string_list(card.get("limitations"))[:6],
                    "directionality": str(card.get("direction") or "quantitative_anchor"),
                    "source_grounded": bool(source_ids),
                    "pretrim_kind": "quantity_ledger.evidence_card",
                    "question_overlap_count": max(
                        question_overlap_count(str(card.get("claim", "")), question_terms or []),
                        question_overlap_count(str(card.get("context", "")), question_terms or []),
                    ),
                    "decision_relevance_assessment": decision_relevance_assessment(
                        " ".join([claim_text, context_text]),
                        question_terms=question_terms or [],
                        decision_role="quantitative_anchor",
                    ),
                }
            )
        )
    return rows


def _trimmed_bundles(candidate_pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidate_pool:
        eligibility = packet_candidate_eligibility(row)
        if not eligibility["main_memo_eligible"] and row.get("pretrim_kind") != "source_bottom_line":
            continue
        retained = dict(row)
        retained["packet_eligibility"] = eligibility
        by_role[str(retained.get("decision_role") or "context")].append(retained)
    budgets = {
        "strongest_support": 8,
        "counterweight": 8,
        "scope_boundary": 6,
        "decision_crux": 6,
        "quantitative_anchor": 8,
        "mechanism": 4,
        "context": 4,
    }
    selected: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for row in sorted((row for rows in by_role.values() for row in rows if row.get("pretrim_kind") == "source_bottom_line"), key=_candidate_rank):
        key = _candidate_identity(row)
        if key not in seen_keys:
            seen_keys.add(key)
            selected.append(row)
    source_bottom_line_count = len(selected)
    for role in ROLE_ORDER:
        for row in sorted(by_role.get(role, []), key=_candidate_rank)[: budgets.get(role, 4)]:
            if row.get("pretrim_kind") == "source_bottom_line":
                continue
            key = _candidate_identity(row)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            selected.append(row)
    selected = selected[:source_bottom_line_count] + sorted(selected[source_bottom_line_count:], key=_candidate_rank)[: max(0, 42 - source_bottom_line_count)]
    return [_bundle_from_candidate(index, row) for index, row in enumerate(selected, start=1)]


def _bundle_from_candidate(index: int, row: dict[str, Any]) -> dict[str, Any]:
    role = str(row.get("decision_role") or "context")
    return _drop_empty(
        {
            "bundle_id": f"bundle_{index:03d}",
            "decision_role": role,
            "claim": row.get("claim"),
            "source_ids": _string_list(row.get("source_ids"))[:8],
            "source_labels": _string_list(row.get("source_labels"))[:8],
            "candidate_card_ids": _string_list(row.get("candidate_card_id"))[:4],
            "source_card_ids": _string_list(row.get("source_card_ids"))[:8],
            "claim_ids": _string_list(row.get("claim_ids"))[:8],
            "relation_ids": _string_list(row.get("relation_ids"))[:8],
            "quantity_ids": _string_list(row.get("quantity_ids"))[:8],
            "quantity_values": _string_list(row.get("quantity_values"))[:8],
            "why_it_matters": row.get("why_it_matters") or _default_why_it_matters(role),
            "limits": _string_list(row.get("limits")) or _string_list(row.get("limitations")),
            "directionality": row.get("directionality") or _directionality_for_role(role),
            "section_use": _section_use_for_role(role),
            "section_targets": _section_targets_for_row(row, role),
            "weight": _bundle_weight(row),
            "quality": row.get("quality"),
            "evidence_track": row.get("evidence_track"),
            "source_summary_decision_role": row.get("source_summary_decision_role"),
            "source_summary_directionality": row.get("source_summary_directionality"),
            "source_excerpt": row.get("source_excerpt"),
            "source_grounded": bool(row.get("source_grounded")),
            "pretrim_pool_id": row.get("pool_id"),
            "pretrim_kind": row.get("pretrim_kind"),
            "eligibility": row.get("packet_eligibility"),
            "decision_relevance_assessment": row.get("decision_relevance_assessment"),
        }
    )


def _must_retain_ledger(scaffold: dict[str, Any], bundles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for bundle in bundles:
        role = str(bundle.get("decision_role") or "")
        importance = _importance_for_bundle(bundle)
        if importance not in CRITICAL_IMPORTANCE:
            continue
        rows.append(_retain_item(len(rows) + 1, bundle, importance=importance))
    for quantity_group in _top_quantity_anchor_groups(scaffold):
        if _quantity_group_already_retained(quantity_group, rows):
            continue
        rows.append(_retain_quantity_group_item(len(rows) + 1, quantity_group))
    return _dedupe_dicts(rows, key_fields=("statement", "decision_role", "required_terms"))[:28]


def _retain_item(index: int, bundle: dict[str, Any], *, importance: str) -> dict[str, Any]:
    quantity_limit = 12 if bundle.get("decision_role") == "quantitative_anchor" else 6
    required_terms = _dedupe(
        [
            *_string_list(bundle.get("quantity_values"))[:quantity_limit],
            *_string_list(bundle.get("source_labels"))[:3],
            *_key_phrases(str(bundle.get("claim", "")))[:4],
        ]
    )
    return _drop_empty(
        {
            "item_id": f"retain_{index:03d}",
            "decision_role": bundle.get("decision_role"),
            "statement": _short_text(str(bundle.get("claim", "")), 320),
            "required_terms": required_terms[:10],
            "source_ids": _string_list(bundle.get("source_ids"))[:8],
            "claim_ids": _string_list(bundle.get("claim_ids"))[:8],
            "relation_ids": _string_list(bundle.get("relation_ids"))[:8],
            "quantity_ids": _string_list(bundle.get("quantity_ids"))[:8],
            "bundle_ids": _string_list(bundle.get("bundle_id")),
            "importance": importance,
            "section_targets": _string_list(bundle.get("section_targets"))[:4],
            "omission_policy": "must_include" if importance == "critical" else "warn_if_missing",
            "why_it_matters": _short_text(str(bundle.get("why_it_matters", "")), 220),
        }
    )


def _retain_quantity_group_item(index: int, quantity_group: dict[str, Any]) -> dict[str, Any]:
    quantities = _string_list(quantity_group.get("quantity_values"))
    return _drop_empty(
        {
            "item_id": f"retain_{index:03d}",
            "decision_role": "quantitative_anchor",
            "statement": _short_text(str(quantity_group.get("claim", "")), 320),
            "required_terms": _dedupe([*quantities, *_key_phrases(str(quantity_group.get("claim", "")))])[:10],
            "source_ids": _string_list(quantity_group.get("source_ids"))[:8],
            "source_labels": _string_list(quantity_group.get("source_labels"))[:4],
            "claim_ids": _string_list(quantity_group.get("claim_ids"))[:4],
            "quantity_ids": _string_list(quantity_group.get("quantity_ids"))[:8],
            "quantity_values": quantities[:8],
            "importance": "critical",
            "section_targets": ["Evidence Carrying the Conclusion"],
            "omission_policy": "must_include",
            "why_it_matters": "Top quantitative anchor from the quantity ledger.",
        }
    )


def _source_trail(scaffold: dict[str, Any], candidate_pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_lookup = _dict(scaffold.get("source_display_names"))
    source_urls = _dict(scaffold.get("source_urls"))
    citation_labels = _dict(scaffold.get("source_citation_labels"))
    used_for: dict[str, set[str]] = defaultdict(set)
    for row in candidate_pool:
        for source_id in _string_list(row.get("source_ids")):
            used_for[source_id].add(str(row.get("decision_role") or "context"))
    for source_id in source_lookup:
        used_for.setdefault(str(source_id), set())
    rows = []
    for source_id, roles in sorted(used_for.items(), key=lambda item: (0 if item[1] else 1, _source_label(scaffold, item[0]))):
        rows.append(
            {
                "source_id": source_id,
                "source_label": _source_label(scaffold, source_id),
                "display_label": str(source_lookup.get(source_id) or "").strip(),
                "citation_label": str(citation_labels.get(source_id) or "").strip(),
                "source_url": str(source_urls.get(source_id) or "").strip(),
                "used_for": sorted(role for role in roles if role),
                "appears_in_packet": bool(roles),
            }
        )
    return rows


def _packet_builder_report(candidate_pool: list[dict[str, Any]], packet: dict[str, Any], sufficiency: dict[str, Any]) -> dict[str, Any]:
    bundles = [row for row in packet.get("evidence_bundles", []) if isinstance(row, dict)]
    eligibility = [packet_candidate_eligibility(row) for row in candidate_pool]
    suppressed = [row for row in eligibility if not row["main_memo_eligible"]]
    suppressed_reason_counts = Counter(reason for row in suppressed for reason in row.get("reasons", []))
    warning_counts = Counter(warning for row in eligibility for warning in row.get("warnings", []))
    return {
        "schema_id": "decision_briefing_packet_report_v1",
        "method": "broad_candidate_inventory_then_decision_role_trimming",
        "candidate_pool_count": len(candidate_pool),
        "bundle_count": len(bundles),
        "must_retain_count": len(packet.get("must_retain_ledger", [])),
        "section_view_count": len(packet.get("section_views", [])),
        "main_memo_suppressed_candidate_count": len(suppressed),
        "main_memo_suppressed_reason_counts": dict(sorted(suppressed_reason_counts.items())),
        "main_memo_warning_counts": dict(sorted(warning_counts.items())),
        "pretrim_kind_counts": dict(Counter(str(row.get("pretrim_kind", "unknown")) for row in candidate_pool)),
        "bundle_role_counts": dict(Counter(str(row.get("decision_role", "unknown")) for row in bundles)),
        "sufficiency_status": sufficiency.get("status"),
        "issues": sufficiency.get("issues", []),
    }


def _answer_frame(scaffold: dict[str, Any], *, question: str) -> tuple[dict[str, Any], dict[str, Any]]:
    return normalize_answer_frame(
        canonical_decision_spine=_dict(scaffold.get("canonical_decision_spine")),
        argument_model=_dict(scaffold.get("argument_model")),
        question=question or str(scaffold.get("question", "")),
    )


def _top_quantity_anchor_rows(scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    ledger = _dict(scaffold.get("quantity_ledger"))
    return [row for row in ledger.get("top_quantitative_anchors", []) if isinstance(row, dict)][:12]


def _top_quantity_anchor_groups(scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    order: list[tuple[str, str]] = []
    for row in _top_quantity_anchor_rows(scaffold):
        quantity_text = str(row.get("quantity_text") or row.get("quantity") or "").strip()
        claim = str(row.get("claim") or "").strip()
        if not quantity_text or not claim:
            continue
        source_ids = _source_ids_for_quantity_row(scaffold, row)
        source_labels = _source_labels(scaffold, source_ids, fallback=_string_list(row.get("source")))
        key = ("|".join(_string_list(row.get("claim_id")) or [claim]), "|".join(source_ids or source_labels or _string_list(row.get("source"))))
        if key not in grouped:
            order.append(key)
            grouped[key] = {"claim": claim, "claim_ids": _string_list(row.get("claim_id")), "source_ids": source_ids, "source_labels": source_labels, "quantity_values": [], "quantity_ids": []}
        grouped[key]["quantity_values"] = _dedupe([*grouped[key]["quantity_values"], quantity_text])
        grouped[key]["quantity_ids"] = _dedupe([*grouped[key]["quantity_ids"], *_string_list(row.get("quantity_id"))])
    return [grouped[key] for key in order if grouped[key].get("quantity_values")]


def _quantity_group_already_retained(quantity_group: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    terms = {_norm(term) for row in rows for term in _string_list(row.get("required_terms"))}
    return bool(quantities := [_norm(quantity) for quantity in _string_list(quantity_group.get("quantity_values"))]) and all(quantity in terms for quantity in quantities)


def _quantity_rows_by_id(scaffold: dict[str, Any]) -> dict[str, dict[str, Any]]:
    ledger = _dict(scaffold.get("quantity_ledger"))
    rows = {}
    for key in ("evidence_cards", "top_quantitative_anchors"):
        for row in ledger.get(key, []) if isinstance(ledger.get(key), list) else []:
            if not isinstance(row, dict):
                continue
            for row_id in _string_list(row.get("card_id")) + _string_list(row.get("quantity_id")):
                rows[row_id] = row
    return rows


def _source_ids_for_argument_item(
    scaffold: dict[str, Any],
    item: dict[str, Any],
    *,
    source_by_claim: dict[str, list[dict[str, Any]]],
    quantity_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    source_ids = _string_list(item.get("source_ids"))[:8]
    if source_ids:
        return source_ids
    resolved: list[str] = []
    for claim_id in _string_list(item.get("claim_ids")):
        for source_card in source_by_claim.get(claim_id, []):
            resolved.extend(_string_list(source_card.get("source_id")))
    for quantity_id in _string_list(item.get("quantity_ids")):
        quantity_row = quantity_by_id.get(quantity_id, {})
        resolved.extend(_source_ids_for_quantity_row(scaffold, quantity_row))
    return _dedupe(resolved)[:8]


def _source_ids_for_quantity_row(scaffold: dict[str, Any], row: dict[str, Any]) -> list[str]:
    explicit = _dedupe([*_string_list(row.get("source_id")), *_string_list(row.get("source_ids"))])
    if explicit:
        return explicit
    source_text = str(row.get("source") or row.get("source_title") or "").strip()
    if not source_text:
        return []
    display = _dict(scaffold.get("source_display_names"))
    citation = _dict(scaffold.get("source_citation_labels"))
    matches = [
        source_id
        for source_id, label in {**display, **citation}.items()
        if _norm(str(label)) == _norm(source_text)
    ]
    if matches:
        return _dedupe([str(source_id) for source_id in matches])
    if source_text in display or source_text in citation:
        return [source_text]
    return []


def _is_relation_rationale_source(row: dict[str, Any]) -> bool:
    return _norm(str(row.get("source") or row.get("source_title") or "")) == "relation rationale"


def _candidate_rank(row: dict[str, Any]) -> tuple[int, int, int, str]:
    role_rank = {
        "quantitative_anchor": 0,
        "counterweight": 1,
        "strongest_support": 2,
        "scope_boundary": 3,
        "decision_crux": 4,
        "mechanism": 5,
        "context": 6,
    }.get(str(row.get("decision_role", "")), 7)
    grounded = 0 if row.get("source_grounded") else 1
    return (role_rank, -_candidate_priority(row), grounded, str(row.get("pool_id", "")))


def _candidate_priority(row: dict[str, Any]) -> int:
    try:
        score = int(row.get("decision_relevance_score", 0) or 0)
    except (TypeError, ValueError):
        score = 0
    if row.get("quantity_values"):
        score += 1
    if row.get("decision_role") in {"counterweight", "quantitative_anchor"}:
        score += 1
    if not row.get("source_grounded"):
        score -= 2
    return max(0, min(10, score))


def _bundle_weight(row: dict[str, Any]) -> str:
    priority = _candidate_priority(row)
    if priority >= 9:
        return "high"
    if priority >= 7:
        return "medium"
    return "low"


def _importance_for_bundle(bundle: dict[str, Any]) -> str:
    if bundle.get("decision_role") == "quantitative_anchor" or bundle.get("weight") == "high":
        return "critical"
    if bundle.get("decision_role") in {"counterweight", "scope_boundary", "decision_crux"}:
        return "high"
    return "medium"


def _candidate_identity(row: dict[str, Any]) -> str:
    pretrim_kind = str(row.get("pretrim_kind", ""))
    if pretrim_kind.startswith("argument_model."):
        claim_ids = _string_list(row.get("claim_ids"))
        if claim_ids:
            return f"{pretrim_kind}:claim_ids:{'|'.join(claim_ids)}"
        return f"{pretrim_kind}:{_norm(str(row.get('claim', '')))[:120]}"
    for key in ("candidate_card_id", "claim_ids", "source_card_ids"):
        values = _string_list(row.get(key))
        if values:
            return f"{key}:{'|'.join(values)}"
    return _norm(str(row.get("claim", "")))[:120]


def _decision_role(card: dict[str, Any], *, quantity_values: list[str]) -> str:
    polarity = str(card.get("decision_polarity") or "").strip().lower()
    if polarity in {"supports_current_answer", "support", "supports"}:
        return "strongest_support"
    if polarity in {"challenges_current_answer", "challenge", "challenges", "counterweight", "counter"}:
        return "counterweight"
    if polarity in {"scopes_current_answer", "scope", "scopes", "scope_boundary"}:
        return "scope_boundary"
    text = " ".join((str(card.get("role", "")), " ".join(_string_list(card.get("evidence_roles"))), " ".join(_string_list(card.get("scope_tags"))))).lower()
    if any(term in text for term in ("counter", "challenge", "conflict", "tension", "contrary")):
        return "counterweight"
    if any(term in text for term in ("scope", "boundary", "exception", "limit", "population", "subgroup", "comparator")):
        return "scope_boundary"
    if any(term in text for term in ("crux", "decision-changing")):
        return "decision_crux"
    if quantity_values:
        return "quantitative_anchor"
    if any(term in text for term in ("mechanism", "proxy", "biomarker")):
        return "mechanism"
    labels = {token for token in re.split(r"[^a-zA-Z0-9_]+", text) if token}
    if labels & {"support", "supports", "strongest_support", "main_text"}:
        return "strongest_support"
    return "context"


def _directionality_for_role(role: str) -> str:
    return {
        "strongest_support": "supports",
        "counterweight": "challenges",
        "scope_boundary": "scopes",
        "decision_crux": "in_tension",
        "quantitative_anchor": "quantifies",
        "mechanism": "explains_or_proxies",
    }.get(role, "contextualizes")


def _section_use_for_role(role: str) -> str:
    return {
        "strongest_support": "Use as load-bearing support for the current read.",
        "counterweight": "Use as the strongest contrary or limiting evidence.",
        "scope_boundary": "Use to bound where the answer travels.",
        "decision_crux": "Use to state what would change the answer.",
        "quantitative_anchor": "Use as a concrete numerical anchor.",
        "mechanism": "Use as mechanism or proxy evidence without over-weighting it.",
    }.get(role, "Use only as context if it clarifies the decision.")


def _section_targets_for_row(row: dict[str, Any], role: str) -> list[str]:
    explicit = _string_list(row.get("section_candidates"))
    if explicit:
        return explicit[:4]
    return _default_sections_for_role(role)


def _default_sections_for_role(role: str) -> list[str]:
    if role in {"strongest_support", "quantitative_anchor", "mechanism"}:
        return ["Evidence Carrying the Conclusion"]
    if role == "counterweight":
        return ["Why This Read", "Decision Cruxes"]
    if role == "scope_boundary":
        return ["Practical Scope and Exceptions"]
    if role == "decision_crux":
        return ["Decision Cruxes"]
    return ["Why This Read"]


def _default_why_it_matters(role: str) -> str:
    return {
        "strongest_support": "This is load-bearing support for the current read.",
        "counterweight": "This bounds or weakens the current read.",
        "scope_boundary": "This determines where the answer applies.",
        "decision_crux": "This identifies a point that could change the decision.",
        "quantitative_anchor": "This provides a numerical anchor for the decision.",
        "mechanism": "This explains a possible mechanism or proxy path.",
    }.get(role, "This provides contextual evidence for the decision.")


def _best_source_excerpt(card: dict[str, Any], source_cards: list[dict[str, Any]]) -> str:
    for source in source_cards:
        text = str(source.get("source_quote_or_excerpt", "")).strip()
        if text:
            return text
    return str(card.get("source_excerpt") or card.get("claim") or "")


def _candidate_limits(card: dict[str, Any]) -> list[str]:
    limits = _string_list(card.get("limitations"))
    if card.get("fragment_risk"):
        limits.append("fragment_risk")
    if card.get("off_question_risk"):
        limits.append("off_question_risk")
    if card.get("anchor_confidence") == "missing":
        limits.append("missing_source_anchor")
    return _dedupe(limits)[:6]


def _cards(report: Any) -> list[dict[str, Any]]:
    data = report if isinstance(report, dict) else {}
    return [card for card in data.get("cards", []) if isinstance(card, dict)]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _source_labels(scaffold: dict[str, Any], source_ids: list[str], *, fallback: list[str] | None = None) -> list[str]:
    labels = [_source_label(scaffold, source_id) for source_id in source_ids]
    labels = [label for label in labels if label]
    if not labels and fallback:
        labels = fallback
    return _dedupe(labels)


def _source_label(scaffold: dict[str, Any], source_id: str) -> str:
    citation = _dict(scaffold.get("source_citation_labels"))
    display = _dict(scaffold.get("source_display_names"))
    return str(citation.get(source_id) or display.get(source_id) or source_id).strip()


def _key_phrases(text: str) -> list[str]:
    words = [word for word in re.findall(r"[A-Za-z0-9][A-Za-z0-9.\-/%]*", text) if len(word) > 2]
    phrases = []
    for size in (4, 3):
        for index in range(0, max(0, len(words) - size + 1)):
            phrase = " ".join(words[index : index + size])
            if len(phrase) >= 12:
                phrases.append(phrase)
            if len(phrases) >= 8:
                return _dedupe(phrases)
    return _dedupe(words[:8])


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        key = _norm(text)
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _dedupe_dicts(rows: list[dict[str, Any]], *, key_fields: tuple[str, ...]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        key_parts: list[str] = []
        for field in key_fields:
            key_parts.extend(_string_list(row.get(field)))
        key = _norm("|".join(key_parts) or str(row))
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _dedupe_pool(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = _candidate_identity(row)
        if not key:
            continue
        current = by_key.get(key)
        if current is None or _candidate_richness(row) > _candidate_richness(current):
            by_key[key] = row
    return list(by_key.values())


def _candidate_richness(row: dict[str, Any]) -> tuple[int, int, int, int, int, int, int, int, str]:
    return (
        1 if row.get("protected_candidate") else 0,
        1 if row.get("decision_role") == "quantitative_anchor" else 0,
        len(_string_list(row.get("quantity_values"))),
        1 if row.get("source_grounded") else 0,
        len(_string_list(row.get("source_ids"))) + len(_string_list(row.get("source_labels"))),
        len(_string_list(row.get("source_excerpt"))),
        _candidate_priority(row),
        len(str(row.get("claim", ""))),
        str(row.get("pretrim_kind", "")),
    )


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", [], {}, None)}


def _short_text(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9.]+", " ", str(text).lower()).strip()
