from __future__ import annotations

import re
from typing import Any


QUANTITY_PATTERNS: tuple[tuple[str, str], ...] = (
    ("confidence_interval", r"\b(?:95\s*%\s*)?(?:CI|confidence interval)\s*[:=]?\s*[\[(]?\s*[-+]?\d+(?:\.\d+)?\s*(?:-|–|—|to)\s*[-+]?\d+(?:\.\d+)?\s*[\])]?\b"),
    ("effect_size", r"\b(?:HR|RR|OR|IRR|SMD|MD|ARR|ARD|hazard ratio|relative risk|risk ratio|odds ratio|mean difference|risk difference|β|beta)\s*(?:=|of|was|:)?\s*[-+]?\d+(?:\.\d+)?\b"),
    ("p_value", r"\b[Pp]\s*(?:=|<|>|≤|≥|<=|>=)\s*0?\.\d+\b"),
    ("sample_size", r"\b(?:n\s*=\s*)?\d[\d,\s]{1,12}\s+(?:participants|subjects|adults|patients|people|events|cases|cohorts|studies|trials|risk estimates)\b"),
    ("duration", r"\b\d+(?:\.\d+)?\s*(?:days?|weeks?|months?|years?|yrs?|y)\b"),
    ("exposure_threshold", r"\b(?:up to|at least|at most|less than|more than|around|approximately|about|>|<|≤|≥|>=|<=)?\s*(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten)\s*[A-Za-z%/.-]{0,18}\s*(?:/|per)\s*(?:day|week|month|year|d|wk|mo|yr)\b"),
    ("biomarker_or_mean_change", r"(?:[-+−]\s*)?\d+(?:\.\d+)?\s*(?:mg/dL|mmol/L|mmHg|µg/mL|ug/mL|ng/mL|g/day|mg/day|g/week|mg/week)\b"),
    ("percentage", r"\b\d+(?:\.\d+)?\s*%"),
    ("year_or_date", r"\b(?:19|20)\d{2}(?:\s*[–-]\s*(?:19|20)\d{2})?\b"),
)

TYPE_PRIORITY = {
    "effect_size": 12,
    "confidence_interval": 11,
    "p_value": 10,
    "sample_size": 9,
    "exposure_threshold": 8,
    "biomarker_or_mean_change": 8,
    "duration": 6,
    "percentage": 5,
    "year_or_date": 1,
}


def build_quantity_ledger(candidate_map: dict[str, Any], source_lookup: dict[str, str], *, question: str = "") -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for claim in _claims(candidate_map):
        rows.extend(_quantity_rows_for_claim(claim, source_lookup, question))
    for relation in _relations(candidate_map):
        rows.extend(_quantity_rows_for_relation(relation, question))
    rows = _dedupe_quantity_rows(rows)
    rows = sorted(rows, key=lambda row: (-int(row.get("relevance_score", 0)), str(row.get("source", "")), str(row.get("claim_id", ""))))
    cards = build_quantitative_evidence_cards(rows)
    type_counts: dict[str, int] = {}
    for row in rows:
        type_counts[str(row.get("quantity_type", ""))] = type_counts.get(str(row.get("quantity_type", "")), 0) + 1
    return {
        "schema_id": "quantity_ledger_v1",
        "method": "mechanical_regex_quantity_extraction_from_map_claims_excerpts_and_relations",
        "quantity_count": len(rows),
        "quantitative_card_count": len(cards),
        "type_counts": type_counts,
        "top_quantitative_anchors": top_quantity_anchors(rows),
        "evidence_cards": cards,
        "quantities": rows,
    }


def top_quantity_anchors(rows_or_ledger: Any, *, limit: int = 12) -> list[dict[str, Any]]:
    rows = rows_or_ledger.get("quantities", []) if isinstance(rows_or_ledger, dict) else rows_or_ledger
    usable = [row for row in rows if isinstance(row, dict) and row.get("quantity_type") != "year_or_date"]
    ranked = [
        row
        for _index, row in sorted(
            enumerate(usable),
            key=lambda pair: (-int(pair[1].get("relevance_score", 0)), pair[0]),
        )
    ]
    selected = _diverse_quantity_anchors(ranked, limit)
    return [
        {
            "quantity_text": row.get("quantity_text"),
            "quantity_type": row.get("quantity_type"),
            "source": row.get("source"),
            "claim_id": row.get("claim_id"),
            "claim": row.get("claim"),
            "context_window": row.get("context_window"),
            "relevance_score": row.get("relevance_score"),
        }
        for row in selected
    ]


def quantity_ledger_markdown(ledger: dict[str, Any], *, limit: int = 30) -> list[str]:
    rows = [row for row in ledger.get("quantities", []) if isinstance(row, dict)]
    cards = [card for card in ledger.get("evidence_cards", []) if isinstance(card, dict)]
    if not rows and not cards:
        return ["## Quantitative Evidence Ledger", "", "No quantities were mechanically extracted from the current map packet."]
    lines = [
        "## Quantitative Evidence Ledger",
        "",
        "Mechanically extracted quantities are shown for auditability. The main memo should use these selectively rather than treating every number as load-bearing.",
        "",
    ]
    if cards:
        lines.extend(_quantity_card_markdown(cards[: min(12, limit)]))
        lines.append("")
    lines.extend(
        [
            "### Raw Extracted Quantities",
            "",
            "| Quantity | Type | Source | Context |",
            "|---|---|---|---|",
        ]
    )
    for row in rows[:limit]:
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(str(value))
                for value in (
                    row.get("quantity_text", ""),
                    str(row.get("quantity_type", "")).replace("_", " "),
                    row.get("source", ""),
                    row.get("context_window", ""),
                )
            )
            + " |"
        )
    return lines


def build_quantitative_evidence_cards(rows: list[dict[str, Any]], *, limit: int = 18) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for row in rows:
        if row.get("quantity_type") == "year_or_date":
            continue
        key = (str(row.get("source_id", "")), str(row.get("claim_id", "")), str(row.get("relation_id", "")))
        groups.setdefault(key, []).append(row)
    cards = [_quantity_card(index, group) for index, group in enumerate(groups.values(), start=1)]
    ranked = sorted(cards, key=lambda card: (-int(card.get("card_score", 0)), str(card.get("source", "")), str(card.get("claim_id", ""))))
    return _diverse_quantity_cards(ranked, limit)


def _quantity_card_markdown(cards: list[dict[str, Any]]) -> list[str]:
    lines = [
        "### Quantitative Evidence Cards",
        "",
        "| Use | Key quantities | Source | Interpretation |",
        "|---|---|---|---|",
    ]
    for card in cards:
        lines.append(
            "| "
            + " | ".join(
                _markdown_cell(str(value))
                for value in (
                    card.get("evidence_use", ""),
                    "; ".join(card.get("key_quantities", [])),
                    card.get("source", ""),
                    card.get("interpretation_hint", ""),
                )
            )
            + " |"
        )
    return lines


def _quantity_card(index: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = sorted(rows, key=lambda row: (-int(row.get("relevance_score", 0)), TYPE_PRIORITY.get(str(row.get("quantity_type", "")), 0)))
    best = ordered[0] if ordered else {}
    by_type = {quantity_type: _unique(row.get("quantity_text", "") for row in ordered if row.get("quantity_type") == quantity_type) for quantity_type, _ in QUANTITY_PATTERNS}
    key_quantities = _card_key_quantities(by_type)
    return {
        "card_id": f"qc{index:04d}",
        "claim_id": best.get("claim_id"),
        "relation_id": best.get("relation_id"),
        "source": best.get("source"),
        "role": best.get("role"),
        "claim": _short_text(str(best.get("claim", "")), 300),
        "evidence_use": _evidence_use(ordered),
        "direction": _dominant_direction(ordered),
        "key_quantities": key_quantities,
        "effect_estimates": by_type.get("effect_size", [])[:4],
        "uncertainty_intervals": by_type.get("confidence_interval", [])[:4],
        "p_values": by_type.get("p_value", [])[:3],
        "sample_or_event_counts": by_type.get("sample_size", [])[:4],
        "dose_or_exposure": by_type.get("exposure_threshold", [])[:4],
        "duration": by_type.get("duration", [])[:3],
        "biomarker_or_mean_change": by_type.get("biomarker_or_mean_change", [])[:4],
        "context": _short_text(str(best.get("context_window", "")), 420),
        "interpretation_hint": _interpretation_hint(by_type, ordered),
        "card_score": max((int(row.get("relevance_score", 0)) for row in ordered), default=0) + _card_bonus(by_type),
    }


def _card_key_quantities(by_type: dict[str, list[str]]) -> list[str]:
    ordered: list[str] = []
    for quantity_type in ("effect_size", "confidence_interval", "p_value", "sample_size", "exposure_threshold", "duration", "biomarker_or_mean_change"):
        ordered.extend(by_type.get(quantity_type, [])[:2])
    return ordered[:8]


def _evidence_use(rows: list[dict[str, Any]]) -> str:
    context = " ".join(str(row.get("context_window", "")) for row in rows).lower()
    types = {str(row.get("quantity_type", "")) for row in rows}
    if "subgroup" in context or "restricted" in context or re.search(r"\b(?:patients|participants|people|subjects|adults)\s+with\s+(?:a\s+)?(?:high|low|elevated|prior|baseline|pre-existing|specific)\b", context):
        return "subgroup estimate"
    if "biomarker_or_mean_change" in types or any(marker in context for marker in ("biomarker", "concentration", "marker", "surrogate")):
        return "biomarker or surrogate estimate"
    if "effect_size" in types and any(marker in context for marker in ("risk", "mortality", "event", "endpoint", "outcome")):
        return "outcome estimate"
    if "sample_size" in types or "duration" in types:
        return "study scale or follow-up context"
    if "exposure_threshold" in types:
        return "dose or exposure boundary"
    return "quantitative context"


def _interpretation_hint(by_type: dict[str, list[str]], rows: list[dict[str, Any]]) -> str:
    effect = (by_type.get("effect_size") or [""])[0]
    interval = (by_type.get("confidence_interval") or [""])[0]
    null = _null_value_for_effect(effect)
    bounds = _interval_bounds(interval)
    if effect and bounds and null is not None:
        if bounds[0] <= null <= bounds[1]:
            return f"{effect} with {interval}; interval includes the usual null value, so treat as uncertain."
        if bounds[0] > null:
            return f"{effect} with {interval}; interval is above the usual null value."
        if bounds[1] < null:
            return f"{effect} with {interval}; interval is below the usual null value."
    direction = _dominant_direction(rows)
    if effect:
        return f"{effect}; direction from source context: {direction.replace('_', ' ')}."
    if by_type.get("sample_size"):
        return "Describes study scale; use for evidential weight, not as an effect estimate."
    if by_type.get("exposure_threshold"):
        return "Describes a dose or exposure boundary; use to define scope."
    return "Use as quantitative context, not as a standalone conclusion."


def _card_bonus(by_type: dict[str, list[str]]) -> int:
    bonus = 0
    if by_type.get("effect_size") and by_type.get("confidence_interval"):
        bonus += 4
    if by_type.get("sample_size"):
        bonus += 2
    if by_type.get("exposure_threshold"):
        bonus += 1
    return bonus


def _diverse_quantity_cards(cards: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    source_counts: dict[str, int] = {}
    for card in cards:
        source = str(card.get("source", ""))
        if source_counts.get(source, 0) >= 4:
            continue
        selected.append(card)
        source_counts[source] = source_counts.get(source, 0) + 1
        if len(selected) >= limit:
            return selected
    for card in cards:
        if card not in selected:
            selected.append(card)
        if len(selected) >= limit:
            break
    return selected


def _unique(values: Any) -> list[str]:
    seen: set[str] = set()
    kept: list[str] = []
    for value in values:
        cleaned = re.sub(r"\s+", " ", str(value)).strip()
        key = cleaned.lower()
        if cleaned and key not in seen:
            seen.add(key)
            kept.append(cleaned)
    return kept


def _dominant_direction(rows: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    for row in rows:
        direction = str(row.get("direction", "unspecified"))
        counts[direction] = counts.get(direction, 0) + 1
    if not counts:
        return "unspecified"
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _null_value_for_effect(effect: str) -> float | None:
    lowered = effect.lower()
    if any(marker in lowered for marker in ("rr", "or", "hr", "irr", "risk ratio", "relative risk", "odds ratio", "hazard ratio")):
        return 1.0
    if any(marker in lowered for marker in ("md", "smd", "arr", "ard", "difference", "beta", "β")):
        return 0.0
    return None


def _interval_bounds(interval: str) -> tuple[float, float] | None:
    numbers = [float(match) for match in re.findall(r"[-+]?\d+(?:\.\d+)?", interval)]
    if len(numbers) < 2:
        return None
    return (min(numbers[-2:]), max(numbers[-2:]))


def _short_text(text: str, max_chars: int) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 3].rstrip(" ,.;") + "..."


def _context_window(text: str, start: int, end: int, *, max_chars: int = 360) -> str:
    left = _sentence_left(text, start)
    right = _sentence_right(text, end)
    if right - left > max_chars:
        radius = max_chars // 2
        left = _word_left(text, max(0, start - radius))
        right = _word_right(text, min(len(text), end + radius))
    window = text[left:right].strip(" ,;")
    return re.sub(r"\s+", " ", window)


def _sentence_left(text: str, start: int) -> int:
    boundaries = [text.rfind(marker, 0, start) for marker in (". ", "? ", "! ")]
    boundary = max(boundaries)
    return boundary + 2 if boundary >= 0 else 0


def _sentence_right(text: str, end: int) -> int:
    candidates = [text.find(marker, end) for marker in (". ", "? ", "! ")]
    candidates = [candidate + 1 for candidate in candidates if candidate >= 0]
    return min(candidates) if candidates else len(text)


def _word_left(text: str, left: int) -> int:
    if left <= 0:
        return 0
    while left < len(text) and not text[left - 1].isspace():
        left += 1
    return min(left, len(text))


def _word_right(text: str, right: int) -> int:
    if right >= len(text):
        return len(text)
    while right > 0 and right < len(text) and not text[right].isspace():
        right -= 1
    return right if right > 0 else min(len(text), right)


def _markdown_cell(text: str) -> str:
    return re.sub(r"\s+", " ", text).replace("|", "\\|").strip()


def _quantity_rows_for_claim(claim: dict[str, Any], source_lookup: dict[str, str], question: str) -> list[dict[str, Any]]:
    claim_id = str(claim.get("claim_id", "")).strip()
    source_id = str(claim.get("source_id", "")).strip()
    source = source_lookup.get(source_id, source_id)
    base = {
        "claim_id": claim_id,
        "source_id": source_id,
        "source": source,
        "claim": str(claim.get("claim", "")).strip(),
        "role": claim.get("role"),
    }
    rows: list[dict[str, Any]] = []
    for field in ("claim", "excerpt"):
        rows.extend(_extract_quantities(str(claim.get(field, "")), base, field, question))
    for item in claim.get("supporting_excerpts", []) if isinstance(claim.get("supporting_excerpts"), list) else []:
        if isinstance(item, dict):
            rows.extend(_extract_quantities(str(item.get("excerpt", "")), base, "supporting_excerpt", question))
    return rows


def _quantity_rows_for_relation(relation: dict[str, Any], question: str) -> list[dict[str, Any]]:
    base = {
        "claim_id": "",
        "source_id": "",
        "source": "relation rationale",
        "relation_id": relation.get("relation_id"),
        "claim": str(relation.get("rationale", "")).strip(),
        "role": relation.get("relation_type"),
    }
    return _extract_quantities(str(relation.get("rationale", "")), base, "relation_rationale", question)


def _extract_quantities(text: str, base: dict[str, Any], field: str, question: str) -> list[dict[str, Any]]:
    cleaned = re.sub(r"\s+", " ", text).strip()
    if not cleaned:
        return []
    rows: list[dict[str, Any]] = []
    occupied: list[tuple[int, int]] = []
    for quantity_type, pattern in QUANTITY_PATTERNS:
        for match in re.finditer(pattern, cleaned, flags=re.IGNORECASE):
            span = match.span()
            if any(not (span[1] <= left or span[0] >= right) for left, right in occupied):
                continue
            occupied.append(span)
            context = _context_window(cleaned, span[0], span[1])
            quantity_text = re.sub(r"\s+", " ", match.group(0)).strip()
            rows.append(
                {
                    **base,
                    "field": field,
                    "quantity_type": quantity_type,
                    "quantity_text": quantity_text,
                    "context_window": context,
                    "direction": _direction_from_context(context),
                    "relevance_score": _relevance_score(quantity_type, quantity_text, context, base, question),
                }
            )
    return rows


def _relevance_score(quantity_type: str, quantity_text: str, context: str, base: dict[str, Any], question: str) -> int:
    score = TYPE_PRIORITY.get(quantity_type, 1)
    lowered = context.lower()
    if any(marker in lowered for marker in ("risk", "mortality", "outcome", "event", "endpoint", "association", "associated")):
        score += 4
    if any(marker in lowered for marker in ("subgroup", "patients", "participants", "cohort", "trial", "meta-analysis", "systematic review")):
        score += 2
    if any(marker in lowered for marker in ("confidence interval", "95% ci", " ci ", "p ")):
        score += 2
    if str(base.get("role", "")) in {"crux", "scope_limit", "conclusion_support"}:
        score += 2
    score += min(4, len(set(_terms(question)) & set(_terms(context))))
    if quantity_type == "year_or_date" and not any(marker in lowered for marker in ("follow", "guideline", "trial", "cohort")):
        score -= 3
    if len(quantity_text) <= 1:
        score -= 2
    return score


def _direction_from_context(context: str) -> str:
    lowered = context.lower()
    if any(marker in lowered for marker in ("not associated", "no association", "no significant", "neutral", "null")):
        return "neutral_or_null"
    if any(marker in lowered for marker in ("lower", "reduced", "decreased", "inverse")):
        return "lower_or_reduced"
    if any(marker in lowered for marker in ("higher", "increased", "elevated", "positive association")):
        return "higher_or_increased"
    return "unspecified"


def _dedupe_quantity_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str]] = set()
    kept: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("claim_id", "")),
            str(row.get("source_id", "")),
            str(row.get("quantity_type", "")),
            re.sub(r"\s+", " ", str(row.get("quantity_text", "")).lower()).strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        row["quantity_id"] = f"q{len(kept) + 1:04d}"
        kept.append(row)
    return kept


def _diverse_quantity_anchors(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    selected_ids: set[int] = set()
    source_counts: dict[str, int] = {}
    claim_counts: dict[str, int] = {}
    source_cap = max(2, limit // 4)
    claim_cap = 2
    for row in rows:
        source = str(row.get("source", ""))
        claim_id = str(row.get("claim_id", ""))
        if source_counts.get(source, 0) >= source_cap or (claim_id and claim_counts.get(claim_id, 0) >= claim_cap):
            continue
        _select_quantity_anchor(row, selected, selected_ids, source_counts, claim_counts)
        if len(selected) >= limit:
            return selected
    for row in rows:
        if id(row) not in selected_ids:
            _select_quantity_anchor(row, selected, selected_ids, source_counts, claim_counts)
        if len(selected) >= limit:
            break
    return selected


def _select_quantity_anchor(
    row: dict[str, Any],
    selected: list[dict[str, Any]],
    selected_ids: set[int],
    source_counts: dict[str, int],
    claim_counts: dict[str, int],
) -> None:
    selected.append(row)
    selected_ids.add(id(row))
    source = str(row.get("source", ""))
    claim_id = str(row.get("claim_id", ""))
    source_counts[source] = source_counts.get(source, 0) + 1
    if claim_id:
        claim_counts[claim_id] = claim_counts.get(claim_id, 0) + 1


def _claims(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    claims = candidate_map.get("claims", [])
    return [claim for claim in claims if isinstance(claim, dict)] if isinstance(claims, list) else []


def _relations(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    relations = candidate_map.get("relations", [])
    return [relation for relation in relations if isinstance(relation, dict)] if isinstance(relations, list) else []


def _terms(text: str) -> list[str]:
    stop = {"the", "and", "that", "this", "with", "from", "into", "than", "when", "where", "which", "should"}
    return [term for term in re.findall(r"[a-z0-9]+", text.lower()) if len(term) >= 4 and term not in stop]
