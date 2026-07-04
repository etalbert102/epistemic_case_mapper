from __future__ import annotations

import re
from collections import Counter
from typing import Any


def build_main_memo_obligation_ledger(
    *,
    scaffold: dict[str, Any],
    briefing_text: str,
    baseline_gap: dict[str, Any],
    source_coverage: dict[str, Any],
) -> dict[str, Any]:
    obligations = build_main_memo_obligation_plan(
        scaffold=scaffold,
        baseline_gap=baseline_gap,
        source_coverage=source_coverage,
    )
    evaluated = [_evaluate_obligation(obligation, briefing_text) for obligation in obligations]
    status_counts = Counter(str(row.get("status", "unknown")) for row in evaluated)
    missing = [row for row in evaluated if row.get("status") in {"missing_from_memo", "source_missing"}]
    stage_counts = Counter(str(row.get("stage_owner", "unknown")) for row in missing)
    return {
        "schema_id": "main_memo_obligation_ledger_v1",
        "method": "deterministic_required_obligation_selection_and_final_memo_text_presence_checks",
        "obligation_count": len(evaluated),
        "satisfied_count": status_counts.get("satisfied", 0),
        "missing_from_memo_count": status_counts.get("missing_from_memo", 0),
        "source_missing_count": status_counts.get("source_missing", 0),
        "status_counts": dict(status_counts),
        "missing_by_stage": dict(stage_counts),
        "top_missing_obligations": _top_missing(evaluated),
        "recommended_interventions": _recommended_interventions(stage_counts, status_counts),
        "obligations": evaluated,
    }


def build_main_memo_obligation_plan(
    *,
    scaffold: dict[str, Any],
    baseline_gap: dict[str, Any] | None = None,
    source_coverage: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Select map-derived obligations before prose is generated."""
    return _dedupe_obligations(
        [
            *_argument_model_obligations(scaffold),
            *_quantity_obligations(scaffold),
            *_evidence_family_obligations(scaffold),
            *_baseline_obligations(baseline_gap or {}, source_coverage or {}),
        ]
    )


def obligation_satisfied_by_text(obligation: dict[str, Any], text: str) -> bool:
    """Return whether prose carries an obligation without relying on final ledger state."""
    if obligation.get("status_override") == "source_missing":
        return True
    evaluated = _evaluate_obligation(obligation, text)
    return evaluated.get("status") == "satisfied"


def section_obligations_for_title(
    title: str,
    obligations: list[dict[str, Any]],
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    categories = _section_obligation_categories(title)
    eligible = [
        obligation
        for obligation in obligations
        if isinstance(obligation, dict)
        and str(obligation.get("stage_owner", "")) == "decision_synthesis"
        and str(obligation.get("category", "")) in categories
        and obligation.get("status_override") != "source_missing"
    ]
    ranked = sorted(
        eligible,
        key=lambda row: (
            categories.index(str(row.get("category", ""))) if str(row.get("category", "")) in categories else 99,
            -int(row.get("priority", 0)),
            str(row.get("obligation_id", "")),
        ),
    )
    first_page = title.strip().lower() == "decision brief"
    selected = _balanced_first_page_obligations(ranked, categories, limit=limit) if first_page else ranked[:limit]
    return [_compact_obligation_for_section(row, first_page_required=first_page) for row in selected]


def obligation_issues_for_text(obligations: list[dict[str, Any]], text: str, *, prefix: str) -> list[str]:
    issues: list[str] = []
    for obligation in obligations:
        if obligation_satisfied_by_text(obligation, text):
            continue
        issues.append(f"{prefix}: {obligation.get('obligation_id')} {str(obligation.get('statement', ''))[:90]}")
    return issues[:8]


def render_main_memo_obligation_ledger_markdown(ledger: dict[str, Any]) -> str:
    lines = [
        "# Main Memo Obligation Ledger",
        "",
        f"Schema: `{ledger.get('schema_id', 'unknown')}`",
        f"Obligations: `{ledger.get('obligation_count', 0)}`",
        f"Satisfied: `{ledger.get('satisfied_count', 0)}`",
        f"Missing from memo: `{ledger.get('missing_from_memo_count', 0)}`",
        f"Source missing: `{ledger.get('source_missing_count', 0)}`",
        "",
        "## Recommended Interventions",
        "",
    ]
    interventions = ledger.get("recommended_interventions", [])
    if interventions:
        lines.extend(f"- {item}" for item in interventions)
    else:
        lines.append("- No dominant obligation gap detected.")
    lines.extend(["", "## Top Missing Obligations", ""])
    missing = ledger.get("top_missing_obligations", [])
    if not missing:
        lines.append("No missing high-priority obligations.")
    for row in missing:
        lines.extend(
            [
                f"- `{row.get('obligation_id')}` {row.get('category')} / {row.get('stage_owner')}",
                f"  - Priority: `{row.get('priority')}`",
                f"  - Status: `{row.get('status')}`",
                f"  - Statement: {row.get('statement')}",
                f"  - Expected terms: {', '.join(str(term) for term in row.get('search_terms', [])[:6])}",
            ]
        )
    lines.extend(["", "## Status Counts", "", "```json", _compact_json(ledger.get("status_counts", {})), "```", ""])
    return "\n".join(lines).rstrip() + "\n"


def _section_obligation_categories(title: str) -> list[str]:
    lowered = title.strip().lower()
    if lowered == "decision brief":
        return ["quantitative_anchor", "strongest_support", "strongest_counterargument", "scope_boundary"]
    if "scope" in lowered or "exception" in lowered or "limit" in lowered:
        return ["scope_boundary", "strongest_counterargument", "decision_crux", "evidence_family_balance"]
    if "crux" in lowered:
        return ["decision_crux", "strongest_counterargument", "scope_boundary"]
    if "evidence" in lowered or "why" in lowered:
        return ["quantitative_anchor", "quantitative_depth", "strongest_support", "strongest_counterargument", "evidence_family_balance"]
    if "practical" in lowered:
        return ["strongest_support", "strongest_counterargument", "scope_boundary", "decision_crux"]
    return ["quantitative_anchor", "strongest_support", "strongest_counterargument", "scope_boundary", "decision_crux"]


def _balanced_first_page_obligations(
    obligations: list[dict[str, Any]],
    categories: list[str],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for category in categories:
        match = next((row for row in obligations if str(row.get("category", "")) == category and row not in selected), None)
        if match is not None:
            selected.append(match)
        if len(selected) >= limit:
            return selected
    return selected or obligations[:limit]


def _compact_obligation_for_section(obligation: dict[str, Any], *, first_page_required: bool) -> dict[str, Any]:
    return {
        "obligation_id": obligation.get("obligation_id"),
        "category": obligation.get("category"),
        "priority": obligation.get("priority"),
        "statement": obligation.get("statement"),
        "search_terms": _string_list(obligation.get("search_terms"))[:6],
        "reason": obligation.get("reason"),
        "first_page_required": first_page_required,
        "source_ids": _string_list(obligation.get("source_ids"))[:4],
        "claim_ids": _string_list(obligation.get("claim_ids"))[:4],
        "relation_ids": _string_list(obligation.get("relation_ids"))[:4],
        "quantity_ids": _string_list(obligation.get("quantity_ids"))[:4],
    }


def _argument_model_obligations(scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    argument_model = _dict(scaffold.get("argument_model"))
    specs = (
        ("quantitative_anchor", "decision_synthesis", "quantitative_anchors", 96, 8),
        ("strongest_counterargument", "decision_synthesis", "strongest_counterarguments", 88, 5),
        ("strongest_support", "decision_synthesis", "strongest_support", 82, 5),
        ("scope_boundary", "decision_synthesis", "scope_boundaries", 80, 6),
        ("decision_crux", "decision_synthesis", "cruxes", 74, 5),
    )
    obligations: list[dict[str, Any]] = []
    for category, stage, key, priority, limit in specs:
        rows = [row for row in argument_model.get(key, []) if isinstance(row, dict)]
        for index, row in enumerate(rows[:limit], start=1):
            obligations.append(
                _obligation(
                    obligation_id=f"{category}_{index:02d}",
                    category=category,
                    stage_owner=stage,
                    priority=priority - index,
                    statement=str(row.get("statement") or row.get("why_it_matters") or "").strip(),
                    search_terms=_terms_for_argument_item(row, scaffold),
                    source_ids=_string_list(row.get("source_ids")),
                    claim_ids=_string_list(row.get("claim_ids")),
                    relation_ids=_string_list(row.get("relation_ids")),
                    quantity_ids=_string_list(row.get("quantity_ids")),
                    reason=str(row.get("why_it_matters", "")).strip(),
                )
            )
    return obligations


def _quantity_obligations(scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    ledger = _dict(scaffold.get("quantity_ledger"))
    cards = [card for card in ledger.get("evidence_cards", []) if isinstance(card, dict)]
    obligations: list[dict[str, Any]] = []
    for index, card in enumerate(cards[:10], start=1):
        key_quantities = _string_list(card.get("key_quantities"))
        if not key_quantities:
            continue
        obligations.append(
            _obligation(
                obligation_id=f"quantity_card_{index:02d}",
                category="quantitative_depth",
                stage_owner="decision_synthesis",
                priority=86 - index,
                statement=str(card.get("claim") or card.get("interpretation_hint") or "; ".join(key_quantities)).strip(),
                search_terms=[*key_quantities[:6], str(card.get("source", "")), *_key_phrases(str(card.get("claim", "")))],
                source_ids=[],
                claim_ids=[str(card.get("claim_id", ""))] if str(card.get("claim_id", "")).strip() else [],
                relation_ids=[str(card.get("relation_id", ""))] if str(card.get("relation_id", "")).strip() else [],
                quantity_ids=[str(card.get("card_id", ""))] if str(card.get("card_id", "")).strip() else [],
                reason=str(card.get("interpretation_hint", "Quantitative evidence card should be considered for the main memo.")),
            )
        )
    return obligations


def _evidence_family_obligations(scaffold: dict[str, Any]) -> list[dict[str, Any]]:
    ledger = _dict(scaffold.get("evidence_weighting_ledger"))
    rows = [row for row in ledger.get("all_evidence", []) if isinstance(row, dict)]
    by_family: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        family = str(row.get("evidence_family", "general_evidence")).strip() or "general_evidence"
        by_family.setdefault(family, []).append(row)
    obligations: list[dict[str, Any]] = []
    for index, (family, family_rows) in enumerate(sorted(by_family.items()), start=1):
        ranked = sorted(family_rows, key=lambda row: (-int(row.get("score", 0)), str(row.get("claim_id", ""))))
        row = ranked[0]
        obligations.append(
            _obligation(
                obligation_id=f"evidence_family_{index:02d}_{_slug(family)}",
                category="evidence_family_balance",
                stage_owner="decision_synthesis",
                priority=66,
                statement=str(row.get("claim", "")).strip(),
                search_terms=[str(row.get("source", "")), family.replace("_", " "), *_key_phrases(str(row.get("claim", "")))],
                source_ids=[],
                claim_ids=[str(row.get("claim_id", ""))] if str(row.get("claim_id", "")).strip() else [],
                relation_ids=[],
                quantity_ids=[],
                reason=f"Representative high-weight row for evidence family `{family}`.",
            )
        )
    return obligations[:10]


def _baseline_obligations(baseline_gap: dict[str, Any], source_coverage: dict[str, Any]) -> list[dict[str, Any]]:
    if not baseline_gap.get("baseline_available"):
        return []
    source_missing = {_norm(term) for term in source_coverage.get("baseline_source_like_terms_absent", [])}
    obligations: list[dict[str, Any]] = []
    for index, term in enumerate(_clean_baseline_terms(baseline_gap.get("salient_baseline_terms_absent", []))[:16], start=1):
        norm = _norm(term)
        stage_owner = "source_coverage" if norm in source_missing else "decision_synthesis"
        status_override = "source_missing" if stage_owner == "source_coverage" else ""
        obligations.append(
            _obligation(
                obligation_id=f"baseline_concept_{index:02d}",
                category="baseline_comparison_concept",
                stage_owner=stage_owner,
                priority=92 - index,
                statement=f"Baseline concept absent from final memo: {term}",
                search_terms=[term],
                source_ids=[],
                claim_ids=[],
                relation_ids=[],
                quantity_ids=[],
                reason="Present in the comparison baseline but absent from the final memo.",
                status_override=status_override,
            )
        )
    return obligations


def _evaluate_obligation(obligation: dict[str, Any], briefing_text: str) -> dict[str, Any]:
    if obligation.get("status_override") == "source_missing":
        return {**obligation, "status": "source_missing", "matched_terms": []}
    matched = _matched_terms(_string_list(obligation.get("search_terms")), briefing_text)
    statement_overlap = _statement_overlap(str(obligation.get("statement", "")), briefing_text)
    satisfied = bool(matched) or statement_overlap >= 0.55
    return {
        **{key: value for key, value in obligation.items() if key != "status_override"},
        "status": "satisfied" if satisfied else "missing_from_memo",
        "matched_terms": matched[:8],
        "statement_overlap": round(statement_overlap, 3),
    }


def _terms_for_argument_item(row: dict[str, Any], scaffold: dict[str, Any]) -> list[str]:
    source_lookup = _dict(scaffold.get("source_display_names"))
    source_terms = [str(source_lookup.get(source_id, source_id)) for source_id in _string_list(row.get("source_ids"))]
    return [
        *_string_list(row.get("quantities"))[:8],
        *source_terms,
        *_key_phrases(str(row.get("statement", ""))),
        *_key_phrases(str(row.get("why_it_matters", ""))),
    ]


def _obligation(
    *,
    obligation_id: str,
    category: str,
    stage_owner: str,
    priority: int,
    statement: str,
    search_terms: list[str],
    source_ids: list[str],
    claim_ids: list[str],
    relation_ids: list[str],
    quantity_ids: list[str],
    reason: str,
    status_override: str = "",
) -> dict[str, Any]:
    return {
        "obligation_id": obligation_id,
        "category": category,
        "stage_owner": stage_owner,
        "priority": priority,
        "statement": _short_text(statement, 320),
        "search_terms": _clean_terms(search_terms)[:12],
        "source_ids": source_ids,
        "claim_ids": claim_ids,
        "relation_ids": relation_ids,
        "quantity_ids": quantity_ids,
        "reason": _short_text(reason, 220),
        "status_override": status_override,
    }


def _dedupe_obligations(obligations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    kept: list[dict[str, Any]] = []
    for row in sorted(obligations, key=lambda item: -int(item.get("priority", 0))):
        key = (str(row.get("category", "")), _norm(str(row.get("statement", "")))[:120])
        if key in seen:
            continue
        seen.add(key)
        kept.append(row)
    return kept[:60]


def _top_missing(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    missing = [row for row in rows if row.get("status") in {"missing_from_memo", "source_missing"}]
    return sorted(missing, key=lambda row: -int(row.get("priority", 0)))[:12]


def _recommended_interventions(stage_counts: Counter[str], status_counts: Counter[str]) -> list[str]:
    interventions: list[str] = []
    if status_counts.get("missing_from_memo", 0):
        interventions.append(
            "Add a main-memo synthesis coverage gate: every missing_from_memo obligation must be included, explicitly rejected, or marked appendix-only before accepting the memo."
        )
    if stage_counts.get("decision_synthesis", 0):
        interventions.append(
            "Strengthen section prompts with the missing decision_synthesis obligations as required first-page ingredients."
        )
    if stage_counts.get("source_coverage", 0):
        interventions.append(
            "Separate source_coverage gaps from synthesis failures so source collection limitations are not mistaken for model omission."
        )
    return interventions


def _matched_terms(terms: list[str], text: str) -> list[str]:
    normalized_text = _norm(text)
    matched: list[str] = []
    for term in terms:
        normalized = _norm(term)
        if not normalized or len(normalized) < 3:
            continue
        if normalized in normalized_text:
            matched.append(term)
    return matched


def _statement_overlap(statement: str, text: str) -> float:
    statement_terms = [term for term in _tokens(statement) if len(term) >= 4]
    if not statement_terms:
        return 0.0
    unique = sorted(set(statement_terms))
    text_terms = set(_tokens(text))
    return len([term for term in unique if term in text_terms]) / len(unique)


def _key_phrases(text: str) -> list[str]:
    phrases = {
        phrase
        for phrase in re.findall(r"\b[A-Z][A-Za-z0-9/-]{2,}(?:\s+[A-Z][A-Za-z0-9/-]{2,}){0,3}\b", text)
        if _useful_phrase(phrase)
    }
    phrases.update(re.findall(r"\b[A-Z][A-Za-z]{0,4}[A-Z0-9]\b(?:[-:/ ]*\d+(?:\.\d+)?)?", text))
    words = [word for word in re.findall(r"[A-Za-z0-9/%.-]+", text) if len(word) > 3]
    if len(words) >= 5:
        phrases.add(" ".join(words[:8]))
    return sorted(phrases, key=lambda item: (-len(item), item.lower()))[:8]


def _clean_terms(terms: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for term in terms:
        value = re.sub(r"\s+", " ", str(term)).strip(" -*`.,;:")
        if not value or len(value) < 3 or not _useful_phrase(value):
            continue
        normalized = _norm(value)
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(value)
    return cleaned


def _useful_phrase(value: str) -> bool:
    normalized = _norm(value)
    if not normalized:
        return False
    generic_singletons = {
        "a",
        "an",
        "and",
        "as",
        "central",
        "for",
        "from",
        "in",
        "of",
        "or",
        "the",
        "this",
        "with",
    }
    if normalized in generic_singletons:
        return False
    if len(normalized.split()) == 1 and len(normalized) < 4 and not re.search(r"\d", normalized):
        return False
    return True


def _clean_baseline_terms(raw_terms: Any) -> list[str]:
    terms = _string_list(raw_terms)
    blocked = {"bottom line for", "decision support synthesis", "follows from"}
    return [
        term
        for term in terms
        if "\n" not in term
        and _norm(term) not in blocked
        and not _norm(term).startswith("follows from")
    ]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip() and str(item).strip().lower() != "none"]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _norm(text: str) -> str:
    return " ".join(_tokens(text))


def _slug(text: str) -> str:
    slug = "_".join(_tokens(text))[:48]
    return slug or "unknown"


def _short_text(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 3].rstrip() + "..."


def _compact_json(value: Any) -> str:
    import json

    return json.dumps(value, indent=2, sort_keys=True)
