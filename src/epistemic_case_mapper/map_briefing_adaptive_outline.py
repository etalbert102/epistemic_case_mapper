from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)


SECTION_ORDER = ("bottom_line", "answer_evidence", "counterweights", "source_weighting", "practical_implication")


def build_adaptive_memo_outline(writer_interface: dict[str, Any]) -> dict[str, Any]:
    """Build a compact, case-adaptive memo plan from existing writer-interface judgments."""

    interface = writer_interface if isinstance(writer_interface, dict) else {}
    raw_cards = _must_write_cards(interface)
    cards, merge_report = _merge_must_write_cards(raw_cards)
    section_ids = _selected_section_ids(interface, cards)
    return {
        "schema_id": "adaptive_memo_outline_v1",
        "method": "deterministic_projection_from_answer_roles_retention_obligations_and_source_appraisal",
        "decision_question": interface.get("decision_question"),
        "outline_policy": [
            "Use this as the section plan for synthesis.",
            "Satisfy each must_write_card in natural prose rather than as a checklist.",
            "Merge related cards in the same paragraph when they share a source, claim family, or quantity interpretation.",
        ],
        "sections": [_section(section_id, interface, cards) for section_id in section_ids],
        "must_write_cards": cards,
        "merge_report": merge_report,
        "section_selection_summary": _section_selection_summary(interface, raw_cards, cards, section_ids),
    }


def _selected_section_ids(interface: dict[str, Any], cards: list[dict[str, Any]]) -> list[str]:
    section_ids = ["bottom_line", "answer_evidence"]
    if _has_counterweight_context(interface, cards):
        section_ids.append("counterweights")
    if _needs_source_weighting(interface, cards):
        section_ids.append("source_weighting")
    section_ids.append("practical_implication")
    return [section_id for section_id in SECTION_ORDER if section_id in section_ids]


def _section(section_id: str, interface: dict[str, Any], cards: list[dict[str, Any]]) -> dict[str, Any]:
    titles = _title_set(interface)
    section_cards = [card for card in cards if card.get("section_id") == section_id]
    goals = {
        "bottom_line": "Answer the decision question directly, then state confidence and the main boundary on the answer.",
        "answer_evidence": "Explain the evidence that carries the current answer and interpret load-bearing quantities.",
        "counterweights": "Give counterweights, scope boundaries, and cruxes their force, then explain how they bound or could change the answer.",
        "source_weighting": "Explain how source quality, directness, or measurement limits should calibrate the read.",
        "practical_implication": "Translate the answer into decision-relevant action, monitoring, or next-step implications.",
    }
    return {
        "section_id": section_id,
        "title": titles.get(section_id, section_id.replace("_", " ").title()),
        "writing_goal": goals[section_id],
        "must_write_card_ids": [card["card_id"] for card in section_cards],
    }


def _title_set(interface: dict[str, Any]) -> dict[str, str]:
    question = str(interface.get("decision_question") or "").lower()
    if any(term in question for term in ("what should", "believe", "current read", "how should", "interpret")):
        return {
            "bottom_line": "Current Read",
            "answer_evidence": "Evidence Carrying the Read",
            "counterweights": "What Could Change or Bound the Read",
            "source_weighting": "How to Weight the Evidence",
            "practical_implication": "How to Use This Read",
        }
    return {
        "bottom_line": "Decision Brief",
        "answer_evidence": "Evidence Carrying the Decision",
        "counterweights": "What Could Change the Decision",
        "source_weighting": "How to Weight the Evidence",
        "practical_implication": "Practical Implications",
    }


def _must_write_cards(interface: dict[str, Any]) -> list[dict[str, Any]]:
    evidence_by_id = {
        str(item.get("item_id") or ""): item
        for item in _list(interface.get("decision_evidence_table")) + _list(interface.get("rescued_context_table"))
        if isinstance(item, dict) and str(item.get("item_id") or "").strip()
    }
    cards = []
    for index, obligation in enumerate(_list(interface.get("retention_checklist")), start=1):
        if not isinstance(obligation, dict):
            continue
        source_rows = [evidence_by_id.get(item_id, {}) for item_id in _string_list(obligation.get("evidence_item_ids"))]
        source_rows = [row for row in source_rows if isinstance(row, dict) and row]
        source_labels = _dedupe(
            [
                *[label for row in source_rows for label in _source_labels(row)],
                *_source_labels(obligation),
            ]
        )
        statement = _card_statement(obligation, source_rows)
        if not statement:
            continue
        section_id = _section_for_obligation(obligation, source_rows)
        quantities = _quantities_to_keep_together(obligation, source_rows)
        cards.append(
            {
                "card_id": f"must_write_{index:03d}",
                "section_id": section_id,
                "obligation_ids": _dedupe(_string_list(obligation.get("obligation_id"))),
                "obligation_types": _dedupe(_string_list(obligation.get("obligation_type"))),
                "roles": _dedupe(
                    [
                        str(obligation.get("role") or "").strip(),
                        *[str(row.get("role") or "").strip() for row in source_rows],
                    ]
                ),
                "source_labels": source_labels,
                "statement": _short_text(statement, 520),
                "prose_instruction": _short_text(str(obligation.get("prose_instruction") or ""), 280),
                "quantities_to_keep_together": quantities,
                "evidence_item_ids": _dedupe(_string_list(obligation.get("evidence_item_ids"))),
                "decision_relevance": _short_text(
                    " ".join(str(row.get("decision_relevance") or "").strip() for row in source_rows),
                    420,
                ),
            }
        )
    return cards


def _card_statement(obligation: dict[str, Any], source_rows: list[dict[str, Any]]) -> str:
    source_claim = " ".join(str(row.get("claim") or "").strip() for row in source_rows if str(row.get("claim") or "").strip())
    statement = str(obligation.get("statement") or "").strip()
    return source_claim or statement


def _section_for_obligation(obligation: dict[str, Any], source_rows: list[dict[str, Any]]) -> str:
    roles = {str(obligation.get("role") or "").strip(), *[str(row.get("role") or "").strip() for row in source_rows]}
    types = {str(obligation.get("obligation_type") or "").strip()}
    relations = {str(row.get("answer_relation") or "").strip() for row in source_rows}
    if roles.intersection({"strongest_counterweight", "scope_boundary", "decision_crux", "source_warning"}):
        return "counterweights"
    if types.intersection({"must_weigh_counterweight", "must_bound_scope", "must_address_crux", "must_weigh_omitted_evidence"}):
        return "counterweights"
    if "challenges_answer" in relations or "bounds_scope" in relations or "identifies_crux" in relations:
        return "counterweights"
    if _guidance_suggests_source_weighting(obligation, source_rows):
        return "source_weighting"
    if roles.intersection({"strongest_support", "quantitative_anchor"}) or types.intersection(
        {"must_weigh_support", "must_interpret_quantity"}
    ):
        return "answer_evidence"
    return "practical_implication"


def _guidance_suggests_source_weighting(obligation: dict[str, Any], source_rows: list[dict[str, Any]]) -> bool:
    if str(obligation.get("role") or "") != "critique_writer_guidance":
        return False
    text = " ".join(
        [
            str(obligation.get("statement") or ""),
            str(obligation.get("prose_instruction") or ""),
            *[str(row.get("source_appraisal_note") or "") for row in source_rows],
        ]
    ).lower()
    return any(
        term in text
        for term in (
            "source",
            "study",
            "measurement",
            "directness",
            "causal",
            "confound",
            "appraisal",
            "quality",
            "outcome",
            "biomarker",
        )
    )


def _quantities_to_keep_together(obligation: dict[str, Any], source_rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    for quantity in _list(obligation.get("quantities")):
        if isinstance(quantity, dict):
            value = str(quantity.get("value") or "").strip()
            interpretation = str(quantity.get("interpretation") or "").strip()
        else:
            value = str(quantity or "").strip()
            interpretation = ""
        if value:
            rows.append({"value": value, "interpretation": interpretation})
    for item in source_rows:
        for quantity in _list(item.get("quantities")):
            if not isinstance(quantity, dict):
                continue
            value = str(quantity.get("value") or "").strip()
            if value:
                rows.append({"value": value, "interpretation": str(quantity.get("interpretation") or "").strip()})
    deduped = []
    seen = set()
    for row in rows:
        key = (row["value"].lower(), row["interpretation"].lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _merge_must_write_cards(cards: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    passthrough = []
    for card in cards:
        key = _merge_key(card)
        if not key:
            passthrough.append(card)
            continue
        grouped.setdefault(key, []).append(card)
    merged = []
    groups = []
    for rows in grouped.values():
        if len(rows) == 1:
            merged.append(rows[0])
            continue
        row = _merged_card(rows)
        merged.append(row)
        groups.append(
            {
                "card_ids": [card["card_id"] for card in rows],
                "merged_card_id": row["card_id"],
                "source_labels": row["source_labels"],
                "section_id": row["section_id"],
            }
        )
    result = sorted([*passthrough, *merged], key=lambda card: (SECTION_ORDER.index(card["section_id"]), card["card_id"]))
    for index, card in enumerate(result, start=1):
        card["card_id"] = f"must_write_{index:03d}"
    return result, {
        "input_card_count": len(cards),
        "merged_card_count": len(result),
        "merged_groups": groups,
    }


def _merge_key(card: dict[str, Any]) -> tuple[str, str, str] | None:
    section = str(card.get("section_id") or "").strip()
    source_key = "|".join(sorted(_source_labels(card)))
    family = _claim_family_key(str(card.get("statement") or ""))
    if not section or not source_key or not family:
        return None
    return (section, source_key, family)


def _merged_card(cards: list[dict[str, Any]]) -> dict[str, Any]:
    base = dict(cards[0])
    statements = _dedupe([str(card.get("statement") or "").strip() for card in cards])
    base.update(
        {
            "card_id": str(cards[0].get("card_id") or ""),
            "obligation_ids": _dedupe([value for card in cards for value in _string_list(card.get("obligation_ids"))]),
            "obligation_types": _dedupe([value for card in cards for value in _string_list(card.get("obligation_types"))]),
            "roles": _dedupe([value for card in cards for value in _string_list(card.get("roles"))]),
            "source_labels": _dedupe([value for card in cards for value in _source_labels(card)]),
            "statement": _short_text(" / ".join(statements), 780),
            "must_write_points": statements,
            "quantities_to_keep_together": _merge_quantities(cards),
            "evidence_item_ids": _dedupe([value for card in cards for value in _string_list(card.get("evidence_item_ids"))]),
            "decision_relevance": _short_text(
                " ".join(str(card.get("decision_relevance") or "").strip() for card in cards), 520
            ),
        }
    )
    return base


def _merge_quantities(cards: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows = []
    seen = set()
    for card in cards:
        for row in _list(card.get("quantities_to_keep_together")):
            if not isinstance(row, dict):
                continue
            value = str(row.get("value") or "").strip()
            interpretation = str(row.get("interpretation") or "").strip()
            key = (value.lower(), interpretation.lower())
            if value and key not in seen:
                seen.add(key)
                rows.append({"value": value, "interpretation": interpretation})
    return rows


def _claim_family_key(text: str) -> str:
    terms = [
        term
        for term in re.findall(r"[a-z][a-z0-9_-]{3,}", str(text).lower())
        if term not in _STOPWORDS
    ]
    return " ".join(_dedupe(terms)[:7])


def _has_counterweight_context(interface: dict[str, Any], cards: list[dict[str, Any]]) -> bool:
    return any(card.get("section_id") == "counterweights" for card in cards) or any(
        _list(interface.get(key)) for key in ("counterweights_and_disposition", "scope_boundaries", "decision_cruxes")
    )


def _needs_source_weighting(interface: dict[str, Any], cards: list[dict[str, Any]]) -> bool:
    if any(card.get("section_id") == "source_weighting" for card in cards):
        return True
    return any(
        _list(row.get("source_use_warnings"))
        or _list(row.get("interpretation_caveats"))
        or _dict(row.get("allowed_wording"))
        or str(row.get("decision_directness") or "") in {"partial", "indirect"}
        for row in _list(interface.get("source_appraisal_summary"))
        if isinstance(row, dict)
    )


def _section_selection_summary(
    interface: dict[str, Any],
    raw_cards: list[dict[str, Any]],
    cards: list[dict[str, Any]],
    section_ids: list[str],
) -> dict[str, Any]:
    return {
        "selected_section_ids": section_ids,
        "raw_must_write_card_count": len(raw_cards),
        "must_write_card_count": len(cards),
        "source_weighting_included": "source_weighting" in section_ids,
        "counterweights_included": "counterweights" in section_ids,
        "quantity_card_count": sum(1 for card in cards if _list(card.get("quantities_to_keep_together"))),
        "source_appraisal_row_count": len(_list(interface.get("source_appraisal_summary"))),
    }


def _source_labels(item: dict[str, Any]) -> list[str]:
    return _dedupe([*_string_list(item.get("source_labels")), str(item.get("source_label") or "").strip()])


_STOPWORDS = {
    "about",
    "against",
    "answer",
    "applicability",
    "because",
    "claim",
    "decision",
    "default",
    "evidence",
    "interpret",
    "load-bearing",
    "quantity",
    "source-backed",
    "support",
    "using",
    "weigh",
    "with",
}
