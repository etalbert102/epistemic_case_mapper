from __future__ import annotations

import re
from collections import Counter, defaultdict
from typing import Any

from epistemic_case_mapper.map_briefing_packet_sufficiency import (
    build_packet_sufficiency_report,
    packet_quantity_retention,
)


SECTION_ORDER = [
    "Decision Brief",
    "Why This Read",
    "Evidence Carrying the Conclusion",
    "Practical Read",
    "Practical Scope and Exceptions",
    "Decision Cruxes",
    "Limits of the Current Map",
]

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

    candidate_pool = _candidate_pool(scaffold)
    source_trail = _source_trail(scaffold, candidate_pool)
    bundles = _trimmed_bundles(candidate_pool)
    retain_ledger = _must_retain_ledger(scaffold, bundles)
    section_views = _section_views(scaffold, bundles, retain_ledger)
    packet = {
        "schema_id": "decision_briefing_packet_v1",
        "decision_question": question or str(scaffold.get("question", "")),
        "answer_frame": _answer_frame(scaffold),
        "must_retain_ledger": retain_ledger,
        "evidence_bundles": bundles,
        "section_views": section_views,
        "source_trail": source_trail,
        "coverage_report": _packet_coverage_report(candidate_pool, bundles, retain_ledger, source_trail),
    }
    sufficiency = build_packet_sufficiency_report(packet, candidate_pool=candidate_pool)
    report = _packet_builder_report(candidate_pool, packet, sufficiency)
    return {
        "decision_briefing_packet": packet,
        "packet_sufficiency_report": sufficiency,
        "decision_briefing_packet_report": report,
    }


def packet_summary_for_model(packet: dict[str, Any], *, max_bundles: int = 18) -> dict[str, Any]:
    """Return a compact, model-facing view for critique/refinement/writing."""

    bundles = [row for row in packet.get("evidence_bundles", []) if isinstance(row, dict)]
    return {
        "schema_id": "decision_briefing_packet_model_view_v1",
        "decision_question": packet.get("decision_question"),
        "answer_frame": packet.get("answer_frame", {}),
        "must_retain_ledger": packet.get("must_retain_ledger", [])[:18],
        "evidence_bundles": bundles[:max_bundles],
        "section_views": packet.get("section_views", []),
        "source_trail": packet.get("source_trail", [])[:24],
        "coverage_report": packet.get("coverage_report", {}),
    }


def _candidate_pool(scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    source_by_claim = _source_cards_by_claim(scaffold)
    source_by_id = {
        str(card.get("source_card_id")): card
        for card in _cards(scaffold.get("source_evidence_cards"))
        if str(card.get("source_card_id", "")).strip()
    }
    pool: list[dict[str, Any]] = []
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
                    "claim": _short_text(str(card.get("claim", "")), 420),
                    "source_excerpt": _short_text(source_excerpt, 520),
                    "decision_role": role,
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
                }
            )
        )
    pool.extend(_argument_item_candidates(scaffold, len(pool)))
    pool.extend(_quantity_card_candidates(scaffold, len(pool)))
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


def _argument_item_candidates(scaffold: dict[str, Any], offset: int) -> list[dict[str, Any]]:
    argument = _dict(scaffold.get("argument_model"))
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
            rows.append(
                _drop_empty(
                    {
                        "pool_id": f"pool_{offset+len(rows)+1:04d}",
                        "candidate_card_id": "",
                        "claim_ids": _string_list(item.get("claim_ids"))[:8],
                        "source_ids": _string_list(item.get("source_ids"))[:8],
                        "source_labels": _source_labels(scaffold, _string_list(item.get("source_ids"))[:8]),
                        "relation_ids": _string_list(item.get("relation_ids"))[:8],
                        "quantity_ids": _string_list(item.get("quantity_ids"))[:8],
                        "claim": _short_text(str(item.get("statement", "")), 420),
                        "decision_role": role,
                        "raw_roles": [key],
                        "quantity_values": _string_list(item.get("quantities"))[:8],
                        "limitations": _string_list(item.get("limitations"))[:6],
                        "decision_relevance_score": base_score,
                        "quality": item.get("weight"),
                        "why_it_matters": _short_text(str(item.get("why_it_matters", "")), 260),
                        "limits": _string_list(item.get("limitations"))[:6],
                        "directionality": _directionality_for_role(role),
                        "source_grounded": bool(_string_list(item.get("source_ids")) or _string_list(item.get("claim_ids"))),
                        "pretrim_kind": f"argument_model.{key}",
                    }
                )
            )
    return rows


def _quantity_card_candidates(scaffold: dict[str, Any], offset: int) -> list[dict[str, Any]]:
    ledger = _dict(scaffold.get("quantity_ledger"))
    rows: list[dict[str, Any]] = []
    for card in [row for row in ledger.get("evidence_cards", []) if isinstance(row, dict)][:18]:
        quantities = _dedupe([*_string_list(card.get("key_quantities")), *_string_list(card.get("effect_estimates"))])
        rows.append(
            _drop_empty(
                {
                    "pool_id": f"pool_{offset+len(rows)+1:04d}",
                    "candidate_card_id": str(card.get("atomic_evidence_card_id", "")),
                    "claim_ids": [str(card.get("claim_id", ""))] if str(card.get("claim_id", "")).strip() else [],
                    "quantity_ids": [str(card.get("card_id", ""))] if str(card.get("card_id", "")).strip() else [],
                    "source_ids": _string_list(card.get("source_id")),
                    "source_labels": _source_labels(scaffold, _string_list(card.get("source_id"))),
                    "claim": _short_text(str(card.get("claim", "")), 420),
                    "source_excerpt": _short_text(str(card.get("context", "")), 520),
                    "decision_role": "quantitative_anchor",
                    "raw_roles": ["quantity_ledger.evidence_cards"],
                    "quantity_values": quantities[:8],
                    "decision_relevance_score": min(10, max(7, int(card.get("card_score", 0) or 0) // 4)),
                    "quality": card.get("evidence_use"),
                    "why_it_matters": _short_text(str(card.get("interpretation_hint") or card.get("evidence_use") or ""), 260),
                    "limits": _string_list(card.get("limitations"))[:6],
                    "directionality": str(card.get("direction") or "quantitative_anchor"),
                    "source_grounded": True,
                    "pretrim_kind": "quantity_ledger.evidence_card",
                }
            )
        )
    return rows


def _trimmed_bundles(candidate_pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_role: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in candidate_pool:
        by_role[str(row.get("decision_role") or "context")].append(row)
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
    for role in ROLE_ORDER:
        for row in sorted(by_role.get(role, []), key=_candidate_rank)[: budgets.get(role, 4)]:
            key = _candidate_identity(row)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            selected.append(row)
    selected = sorted(selected, key=_candidate_rank)[:42]
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
            "source_excerpt": row.get("source_excerpt"),
            "source_grounded": bool(row.get("source_grounded")),
            "pretrim_pool_id": row.get("pool_id"),
            "pretrim_kind": row.get("pretrim_kind"),
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
    for quantity in _top_quantity_anchor_rows(scaffold):
        if _quantity_already_retained(quantity, rows):
            continue
        rows.append(_retain_quantity_item(len(rows) + 1, quantity, scaffold))
    return _dedupe_dicts(rows, key_fields=("statement", "decision_role", "required_terms"))[:28]


def _retain_item(index: int, bundle: dict[str, Any], *, importance: str) -> dict[str, Any]:
    required_terms = _dedupe(
        [
            *_string_list(bundle.get("quantity_values"))[:6],
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


def _retain_quantity_item(index: int, quantity: dict[str, Any], scaffold: dict[str, Any]) -> dict[str, Any]:
    source_ids = _string_list(quantity.get("source"))
    return _drop_empty(
        {
            "item_id": f"retain_{index:03d}",
            "decision_role": "quantitative_anchor",
            "statement": _short_text(str(quantity.get("claim", "")), 320),
            "required_terms": _dedupe([str(quantity.get("quantity_text", "")), *_key_phrases(str(quantity.get("claim", "")))])[:10],
            "source_ids": source_ids,
            "source_labels": _source_labels(scaffold, source_ids),
            "claim_ids": _string_list(quantity.get("claim_id"))[:4],
            "quantity_ids": _string_list(quantity.get("quantity_id"))[:4],
            "importance": "critical",
            "section_targets": ["Evidence Carrying the Conclusion"],
            "omission_policy": "must_include",
            "why_it_matters": "Top quantitative anchor from the quantity ledger.",
        }
    )


def _section_views(scaffold: dict[str, Any], bundles: list[dict[str, Any]], retain_ledger: list[dict[str, Any]]) -> list[dict[str, Any]]:
    bundles_by_id = {str(row.get("bundle_id")): row for row in bundles}
    by_section: dict[str, dict[str, list[str]]] = {
        title: {"primary_bundle_ids": [], "contrast_bundle_ids": [], "boundary_bundle_ids": [], "context_bundle_ids": [], "must_retain_item_ids": []}
        for title in SECTION_ORDER
    }
    for bundle in bundles:
        bundle_id = str(bundle.get("bundle_id"))
        for section in _string_list(bundle.get("section_targets")) or _default_sections_for_role(str(bundle.get("decision_role", ""))):
            slot = _section_slot_for_role(str(bundle.get("decision_role", "")))
            if section not in by_section:
                by_section[section] = {"primary_bundle_ids": [], "contrast_bundle_ids": [], "boundary_bundle_ids": [], "context_bundle_ids": [], "must_retain_item_ids": []}
            by_section[section][slot].append(bundle_id)
    for item in retain_ledger:
        for section in _string_list(item.get("section_targets")) or ["Evidence Carrying the Conclusion"]:
            if section not in by_section:
                by_section[section] = {"primary_bundle_ids": [], "contrast_bundle_ids": [], "boundary_bundle_ids": [], "context_bundle_ids": [], "must_retain_item_ids": []}
            by_section[section]["must_retain_item_ids"].append(str(item.get("item_id")))
    views = []
    for title, rows in by_section.items():
        view = {
            "section": title,
            "section_job": _section_job(title),
            "primary_bundle_ids": _dedupe(rows["primary_bundle_ids"])[:8],
            "contrast_bundle_ids": _dedupe(rows["contrast_bundle_ids"])[:5],
            "boundary_bundle_ids": _dedupe(rows["boundary_bundle_ids"])[:5],
            "context_bundle_ids": _dedupe(rows["context_bundle_ids"])[:4],
            "must_retain_item_ids": _dedupe(rows["must_retain_item_ids"])[:8],
        }
        if any(view[key] for key in ("primary_bundle_ids", "contrast_bundle_ids", "boundary_bundle_ids", "context_bundle_ids", "must_retain_item_ids")):
            views.append(view)
    return views


def _source_trail(scaffold: dict[str, Any], candidate_pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_lookup = _dict(scaffold.get("source_display_names"))
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
                "used_for": sorted(role for role in roles if role),
                "appears_in_packet": bool(roles),
            }
        )
    return rows


def _packet_coverage_report(
    candidate_pool: list[dict[str, Any]],
    bundles: list[dict[str, Any]],
    retain_ledger: list[dict[str, Any]],
    source_trail: list[dict[str, Any]],
) -> dict[str, Any]:
    retained_ids = _retained_candidate_ids(bundles)
    high_priority_omitted = [
        row
        for row in candidate_pool
        if _candidate_priority(row) >= 7
        and row.get("candidate_card_id")
        and str(row.get("candidate_card_id")) not in retained_ids
        and "appendix" not in str(row.get("inclusion_recommendation", "")).lower()
    ]
    return {
        "candidate_pool_count": len(candidate_pool),
        "evidence_bundle_count": len(bundles),
        "must_retain_count": len(retain_ledger),
        "high_priority_omitted_count": len(high_priority_omitted),
        "source_label_missing_count": sum(1 for row in source_trail if not row.get("source_label")),
        "quantity_missing_count": len(packet_quantity_retention({"must_retain_ledger": retain_ledger}, candidate_pool)["missing_top_quantities"]),
        "warnings": _dedupe(
            [
                *([ "high_priority_omitted_after_trimming" ] if high_priority_omitted else []),
                *([ "no_must_retain_items" ] if not retain_ledger else []),
                *([ "no_evidence_bundles" ] if not bundles else []),
            ]
        ),
    }


def _packet_builder_report(candidate_pool: list[dict[str, Any]], packet: dict[str, Any], sufficiency: dict[str, Any]) -> dict[str, Any]:
    bundles = [row for row in packet.get("evidence_bundles", []) if isinstance(row, dict)]
    return {
        "schema_id": "decision_briefing_packet_report_v1",
        "method": "broad_candidate_inventory_then_decision_role_trimming",
        "candidate_pool_count": len(candidate_pool),
        "bundle_count": len(bundles),
        "must_retain_count": len(packet.get("must_retain_ledger", [])),
        "section_view_count": len(packet.get("section_views", [])),
        "pretrim_kind_counts": dict(Counter(str(row.get("pretrim_kind", "unknown")) for row in candidate_pool)),
        "bundle_role_counts": dict(Counter(str(row.get("decision_role", "unknown")) for row in bundles)),
        "sufficiency_status": sufficiency.get("status"),
        "issues": sufficiency.get("issues", []),
    }


def _answer_frame(scaffold: dict[str, Any]) -> dict[str, Any]:
    spine = _dict(scaffold.get("canonical_decision_spine"))
    default = _dict(spine.get("default_answer"))
    argument = _dict(scaffold.get("argument_model"))
    proposed = argument.get("proposed_answer")
    if isinstance(proposed, dict):
        current_read = str(proposed.get("current_read") or proposed.get("classification") or default.get("claim") or "")
    else:
        current_read = str(proposed or default.get("claim") or "")
    return _drop_empty(
        {
            "default_answer": _short_text(current_read, 420),
            "confidence": str(spine.get("confidence") or argument.get("confidence") or "medium"),
            "scope": _short_text(" ".join(_string_list(default.get("limits"))), 260),
            "main_uncertainty": _short_text(" ".join(_string_list(argument.get("confidence_reasons"))), 260),
        }
    )


def _top_quantity_anchor_rows(scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    ledger = _dict(scaffold.get("quantity_ledger"))
    return [row for row in ledger.get("top_quantitative_anchors", []) if isinstance(row, dict)][:12]


def _quantity_already_retained(quantity: dict[str, Any], rows: list[dict[str, Any]]) -> bool:
    terms = {_norm(term) for row in rows for term in _string_list(row.get("required_terms"))}
    return _norm(str(quantity.get("quantity_text", ""))) in terms


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
    for key in ("candidate_card_id", "claim_ids", "source_card_ids"):
        values = _string_list(row.get(key))
        if values:
            return f"{key}:{'|'.join(values)}"
    return _norm(str(row.get("claim", "")))[:120]


def _retained_candidate_ids(bundles: list[dict[str, Any]]) -> set[str]:
    return {
        card_id
        for bundle in bundles
        for card_id in _string_list(bundle.get("candidate_card_ids"))
        if card_id
    }


def _decision_role(card: dict[str, Any], *, quantity_values: list[str]) -> str:
    text = " ".join([str(card.get("role", "")), " ".join(_string_list(card.get("evidence_roles"))), " ".join(_string_list(card.get("scope_tags"))), str(card.get("inclusion_reason", ""))]).lower()
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
    if any(term in text for term in ("support", "conclusion", "main_text")):
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


def _section_slot_for_role(role: str) -> str:
    if role == "counterweight":
        return "contrast_bundle_ids"
    if role == "scope_boundary":
        return "boundary_bundle_ids"
    if role == "context":
        return "context_bundle_ids"
    return "primary_bundle_ids"


def _section_job(title: str) -> str:
    if title == "Decision Brief":
        return "State the answer, confidence, and central reason."
    if title == "Why This Read":
        return "Explain the reasoning path and most important tension."
    if title == "Evidence Carrying the Conclusion":
        return "Identify the evidence doing the most work and its quantitative anchors."
    if title == "Practical Read":
        return "Translate the answer into decision-relevant practical implications."
    if title == "Practical Scope and Exceptions":
        return "Bound the answer and name exceptions or population limits."
    if title == "Decision Cruxes":
        return "Name what would change the answer."
    if title == "Limits of the Current Map":
        return "Name missing evidence and robustness limits."
    return "Use packet evidence to advance this section's distinct decision function."


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
    result = []
    seen: set[str] = set()
    for row in rows:
        key = _candidate_identity(row)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", [], {}, None)}


def _short_text(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9.]+", " ", str(text).lower()).strip()
