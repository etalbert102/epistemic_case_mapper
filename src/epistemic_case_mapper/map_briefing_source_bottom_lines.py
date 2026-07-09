from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_packet_eligibility import question_overlap_count


def build_source_bottom_line_cards(prioritized_map: dict[str, Any], scaffold: dict[str, Any]) -> dict[str, Any]:
    source_lookup = scaffold.get("source_display_names", {}) if isinstance(scaffold.get("source_display_names"), dict) else {}
    rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for claim in prioritized_map.get("claims", []) if isinstance(prioritized_map.get("claims"), list) else []:
        if not isinstance(claim, dict):
            continue
        source_card = claim.get("whole_doc_source_card") if isinstance(claim.get("whole_doc_source_card"), dict) else {}
        bottom_line = str(claim.get("source_bottom_line") or source_card.get("source_bottom_line") or "").strip()
        source_id = str(claim.get("source_id") or "").strip()
        if not bottom_line or not source_id:
            continue
        key = (source_id, bottom_line)
        if key in seen:
            continue
        seen.add(key)
        rows.append(
            {
                "source_bottom_line_id": f"sbl{len(rows)+1:04d}",
                "source_id": source_id,
                "source_label": str(source_lookup.get(source_id) or source_id),
                "claim_ids": [str(claim.get("claim_id"))] if claim.get("claim_id") else [],
                "source_bottom_line": bottom_line,
                "decision_importance_level": str(claim.get("decision_importance_level") or ""),
                "decision_function": str(claim.get("decision_function") or source_card.get("source_card_role") or ""),
                "decision_polarity": str(claim.get("decision_polarity") or source_card.get("decision_polarity") or ""),
                "source_card_role": str(source_card.get("source_card_role") or ""),
            }
        )
    return {
        "schema_id": "source_bottom_line_cards_v1",
        "card_count": len(rows),
        "cards": rows,
    }


def source_bottom_line_candidates(
    scaffold: dict[str, Any],
    offset: int,
    *,
    question_terms: list[str] | None = None,
) -> list[dict[str, Any]]:
    report = scaffold.get("source_bottom_line_cards", {}) if isinstance(scaffold.get("source_bottom_line_cards"), dict) else {}
    rows: list[dict[str, Any]] = []
    for card in report.get("cards", []) if isinstance(report.get("cards"), list) else []:
        if not isinstance(card, dict):
            continue
        bottom_line = str(card.get("source_bottom_line") or "").strip()
        source_id = str(card.get("source_id") or "").strip()
        if not bottom_line or not source_id:
            continue
        role = _source_bottom_line_decision_role(card)
        importance = str(card.get("decision_importance_level") or "").lower()
        score = {"critical": 10, "high": 9, "medium": 7}.get(importance, 7)
        rows.append(
            _drop_empty(
                {
                    "pool_id": f"pool_{offset+len(rows)+1:04d}",
                    "candidate_card_id": str(card.get("source_bottom_line_id") or f"source_bottom_line:{source_id}"),
                    "claim_ids": _string_list(card.get("claim_ids"))[:8],
                    "source_ids": [source_id],
                    "source_labels": _source_labels(scaffold, [source_id], fallback=_string_list(card.get("source_label"))),
                    "claim": _short_text(bottom_line, 420),
                    "source_excerpt": _short_text(bottom_line, 520),
                    "decision_role": role,
                    "raw_roles": ["source_bottom_line", *_source_bottom_line_role_hints(card)],
                    "decision_polarity": str(card.get("decision_polarity") or ""),
                    "decision_relevance_score": score,
                    "quality": "source_summary",
                    "inclusion_recommendation": "main_text",
                    "why_it_matters": "Source-level bottom line; use to keep the packet faithful to the source's overall contribution.",
                    "directionality": _directionality_for_role(role),
                    "source_grounded": True,
                    "pretrim_kind": "source_bottom_line",
                    "question_overlap_count": question_overlap_count(bottom_line, question_terms or []),
                }
            )
        )
    return rows


def _source_bottom_line_role_hints(card: dict[str, Any]) -> list[str]:
    text = " ".join(
        str(card.get(key) or "")
        for key in ("decision_polarity", "role", "evidence_role")
    ).lower()
    hints: list[str] = []
    if any(term in text for term in ("supports_current_answer", "strongest_support", "support")):
        hints.append("support")
    if any(term in text for term in ("challenges_current_answer", "counter", "challenge", "conflict", "tension", "contrary")):
        hints.append("counterweight")
    if any(term in text for term in ("scopes_current_answer", "scope", "boundary", "exception", "limit", "population", "subgroup")):
        hints.append("scope")
    return hints or ["context"]


def _source_bottom_line_decision_role(card: dict[str, Any]) -> str:
    return _decision_role_fallback(card)


def _decision_role_fallback(card: dict[str, Any]) -> str:
    polarity = str(card.get("decision_polarity") or "").strip().lower()
    if polarity in {"supports_current_answer", "support", "supports"}:
        return "strongest_support"
    if polarity in {"challenges_current_answer", "challenge", "challenges", "counterweight", "counter"}:
        return "counterweight"
    if polarity in {"scopes_current_answer", "scope", "scopes", "scope_boundary"}:
        return "scope_boundary"
    text = " ".join(
        [
            "source_bottom_line",
            " ".join(_source_bottom_line_role_hints(card)),
        ]
    ).lower()
    if any(term in text for term in ("counter", "challenge", "conflict", "tension", "contrary")):
        return "counterweight"
    if any(term in text for term in ("scope", "boundary", "exception", "limit", "population", "subgroup", "comparator")):
        return "scope_boundary"
    if any(term in text for term in ("crux", "decision-changing")):
        return "decision_crux"
    if any(term in text for term in ("support", "conclusion", "main_text")):
        return "strongest_support"
    return "context"


def _first_signal_position(text: str, signals: tuple[str, ...]) -> int:
    positions = [text.find(signal) for signal in signals if signal in text]
    return min(positions) if positions else -1


def _directionality_for_role(role: str) -> str:
    return {
        "strongest_support": "supports",
        "counterweight": "challenges",
        "scope_boundary": "scopes",
        "decision_crux": "in_tension",
        "quantitative_anchor": "quantifies",
        "mechanism": "explains_or_proxies",
    }.get(role, "contextualizes")


def _source_labels(scaffold: dict[str, Any], source_ids: list[str], *, fallback: list[str] | None = None) -> list[str]:
    citation = scaffold.get("source_citation_labels", {}) if isinstance(scaffold.get("source_citation_labels"), dict) else {}
    display = scaffold.get("source_display_names", {}) if isinstance(scaffold.get("source_display_names"), dict) else {}
    labels = [str(citation.get(source_id) or display.get(source_id) or source_id).strip() for source_id in source_ids]
    labels = [label for label in labels if label]
    if not labels and fallback:
        labels = fallback
    return _dedupe(labels)


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        key = re.sub(r"\s+", " ", text.lower()).strip()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", [], {}, None)}


def _short_text(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 1].rstrip() + "..."
