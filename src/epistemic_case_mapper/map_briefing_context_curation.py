from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.map_briefing_context_reports import (
    build_evidence_quality_report,
    build_source_evidence_cards,
    build_source_sufficiency_report,
)
from epistemic_case_mapper.map_briefing_context_schemas import (
    CandidateEvidenceCardsReport,
    MemoArgumentSpineReport,
    SectionReasoningCardsReport,
    SourceCoverageReport,
    SourceMapReconciliationReport,
)


SECTION_TITLES = [
    "Decision Brief",
    "Why This Read",
    "Evidence Carrying the Conclusion",
    "Practical Read",
    "Practical Scope and Exceptions",
    "Decision Cruxes",
    "Limits of the Current Map",
]


def build_decision_ready_context_bundle(
    prioritized_map: dict[str, Any],
    *,
    scaffold: dict[str, Any],
    question: str,
    source_lookup: dict[str, str],
) -> dict[str, Any]:
    source_urls = scaffold.get("source_urls", {}) if isinstance(scaffold.get("source_urls"), dict) else {}
    source_cards = build_source_evidence_cards(prioritized_map, source_lookup=source_lookup, source_urls=source_urls)
    sufficiency = build_source_sufficiency_report(
        decision_question=question,
        source_evidence_cards=source_cards,
        scaffold=scaffold,
    )
    quality = build_evidence_quality_report(source_cards)
    reconciliation = build_source_map_reconciliation(prioritized_map, source_cards)
    candidates = build_candidate_evidence_cards(
        source_evidence_cards=source_cards,
        source_map_reconciliation=reconciliation,
        evidence_quality_report=quality,
        question=question,
    )
    spine = build_memo_argument_spine(
        candidate_evidence_cards=candidates,
        source_sufficiency_report=sufficiency,
        question=question,
    )
    section_cards = build_section_reasoning_cards(spine, candidates)
    coverage = build_source_coverage_report(
        source_evidence_cards=source_cards,
        candidate_evidence_cards=candidates,
        source_map_reconciliation=reconciliation,
        section_reasoning_cards=section_cards,
    )
    return {
        "source_evidence_cards": source_cards,
        "source_sufficiency_report": sufficiency,
        "evidence_quality_report": quality,
        "source_map_reconciliation": reconciliation,
        "candidate_evidence_cards": candidates,
        "memo_argument_spine": spine,
        "section_reasoning_cards": section_cards,
        "source_coverage_report": coverage,
    }


def build_source_map_reconciliation(candidate_map: dict[str, Any], source_evidence_cards: dict[str, Any]) -> dict[str, Any]:
    cards = [card for card in source_evidence_cards.get("cards", []) if isinstance(card, dict)]
    cards_by_claim = _cards_by_claim(cards)
    rows: list[dict[str, Any]] = []
    for claim in _claims(candidate_map):
        claim_id = str(claim.get("claim_id", "")).strip()
        claim_text = _claim_text(claim)
        matched = cards_by_claim.get(claim_id, []) if claim_id else []
        match_type = "claim_id" if matched else "none"
        if not matched:
            matched = _source_overlap_cards(claim, claim_text, cards)
            match_type = "source_overlap" if matched else "none"
        anchors = {str(card.get("anchor_confidence") or "missing") for card in matched}
        status = "source_backed" if anchors - {"missing"} else "weakly_backed" if matched else "unbacked"
        issues = [] if status == "source_backed" else [f"claim_{status}"]
        rows.append(
            {
                "claim_id": claim_id,
                "claim_text": _shorten(claim_text, 280),
                "source_card_ids": [str(card.get("source_card_id", "")) for card in matched if card.get("source_card_id")],
                "source_ids": _dedupe([str(card.get("source_id", "")) for card in matched if card.get("source_id")]),
                "status": status,
                "match_type": match_type,
                "issues": issues,
            }
        )
    report = SourceMapReconciliationReport(
        claim_count=len(rows),
        source_backed_count=sum(1 for row in rows if row["status"] == "source_backed"),
        weakly_backed_count=sum(1 for row in rows if row["status"] == "weakly_backed"),
        unbacked_count=sum(1 for row in rows if row["status"] == "unbacked"),
        rows=rows,
        issues=[] if rows else ["no_claims_to_reconcile"],
    )
    return report.model_dump()


def build_candidate_evidence_cards(
    *,
    source_evidence_cards: dict[str, Any],
    source_map_reconciliation: dict[str, Any],
    evidence_quality_report: dict[str, Any],
    question: str,
) -> dict[str, Any]:
    question_terms = _content_terms(question)
    quality = evidence_quality_report.get("quality_components", {}) if isinstance(evidence_quality_report.get("quality_components"), dict) else {}
    backed_claims = _backed_claim_ids(source_map_reconciliation)
    cards: list[dict[str, Any]] = []
    for index, source_card in enumerate(source_evidence_cards.get("cards", []), start=1):
        if not isinstance(source_card, dict):
            continue
        source_card_id = str(source_card.get("source_card_id", ""))
        quality_row = quality.get(source_card_id, {}) if isinstance(quality.get(source_card_id), dict) else {}
        score = _candidate_score(source_card, quality_row, question_terms)
        role = _candidate_role(source_card)
        claim_ids = _string_list(source_card.get("claim_ids"))
        appendix_only = _appendix_only(source_card, score, quality_row, backed_claims, claim_ids)
        cards.append(
            {
                "candidate_card_id": f"ec{index:04d}",
                "source_card_ids": [source_card_id] if source_card_id else [],
                "claim_ids": claim_ids,
                "source_ids": _string_list(source_card.get("source_id")),
                "source_titles": _string_list(source_card.get("source_title")),
                "claim": _shorten(str(source_card.get("source_quote_or_excerpt", "")), 300),
                "source_excerpt": _shorten(str(source_card.get("source_quote_or_excerpt", "")), 500),
                "role": role,
                "decision_relevance_score": score,
                "quality": str(quality_row.get("overall") or "unknown"),
                "inclusion_recommendation": "appendix_only" if appendix_only else "main_text" if score >= 7 else "supporting_context",
                "inclusion_reason": _inclusion_reason(source_card, role, score, quality_row),
                "section_candidates": _section_candidates(role),
                "quantity_values": _string_list(source_card.get("quantity_values")),
                "limitations": _string_list(source_card.get("limitations")),
                "anchor_confidence": str(source_card.get("anchor_confidence") or "missing"),
                "off_question_risk": score < 4,
                "fragment_risk": bool(source_card.get("fragment_risk") or source_card.get("boilerplate_risk")),
            }
        )
    report = CandidateEvidenceCardsReport(
        card_count=len(cards),
        main_text_count=sum(1 for card in cards if card["inclusion_recommendation"] == "main_text"),
        appendix_only_count=sum(1 for card in cards if card["inclusion_recommendation"] == "appendix_only"),
        cards=cards,
        issues=[] if cards else ["no_candidate_evidence_cards"],
    )
    return report.model_dump()


def build_memo_argument_spine(
    *,
    candidate_evidence_cards: dict[str, Any],
    source_sufficiency_report: dict[str, Any],
    question: str,
) -> dict[str, Any]:
    cards = _usable_cards(candidate_evidence_cards)
    status = _spine_status(source_sufficiency_report, cards)
    items = [_spine_item("answer", _answer_statement(status, question), [], 0)]
    for role in ("support", "counterweight", "scope", "quantity"):
        for card in _top_role_cards(cards, role, limit=2):
            items.append(_spine_item(role, str(card.get("claim", "")), [card], int(card.get("decision_relevance_score", 0))))
    for missing in _string_list(source_sufficiency_report.get("missing_source_categories"))[:4]:
        items.append(_spine_item("limitation", f"The provided source set is missing {missing.replace('_', ' ')}.", [], 0))
    load_bearing = _dedupe([card["candidate_card_id"] for card in cards[:8] if card.get("candidate_card_id")])
    report = MemoArgumentSpineReport(
        decision_question=question,
        status=status,
        answer_frame=_answer_statement(status, question),
        source_sufficiency_status=str(source_sufficiency_report.get("status") or ""),
        load_bearing_candidate_card_ids=load_bearing,
        items=items,
        issues=[] if cards else ["no_usable_candidate_cards_for_argument_spine"],
    )
    return report.model_dump()


def build_section_reasoning_cards(
    memo_argument_spine: dict[str, Any],
    candidate_evidence_cards: dict[str, Any],
) -> dict[str, Any]:
    cards = _usable_cards(candidate_evidence_cards)
    groups = {role: _top_role_cards(cards, role, limit=8) for role in ("support", "counterweight", "scope", "quantity", "limitation", "context")}
    sections = [_section_reasoning(title, groups, cards, memo_argument_spine) for title in SECTION_TITLES]
    if any(section["context_status"] == "not_synthesis_ready" for section in sections):
        status = "not_synthesis_ready"
    elif any(section["context_status"] == "warning" for section in sections):
        status = "warning"
    else:
        status = "ready"
    report = SectionReasoningCardsReport(
        status=status,
        sections=sections,
        issues=[section["exception_reason"] for section in sections if section.get("exception_reason")],
    )
    return report.model_dump()


def build_source_coverage_report(
    *,
    source_evidence_cards: dict[str, Any],
    candidate_evidence_cards: dict[str, Any],
    source_map_reconciliation: dict[str, Any],
    section_reasoning_cards: dict[str, Any],
) -> dict[str, Any]:
    assigned = _assigned_candidate_ids(section_reasoning_cards)
    candidates = [card for card in candidate_evidence_cards.get("cards", []) if isinstance(card, dict)]
    omitted = [
        str(card.get("candidate_card_id"))
        for card in candidates
        if int(card.get("decision_relevance_score", 0)) >= 7
        and card.get("inclusion_recommendation") != "appendix_only"
        and str(card.get("candidate_card_id")) not in assigned
    ]
    unbacked = [
        str(row.get("claim_id"))
        for row in source_map_reconciliation.get("rows", [])
        if isinstance(row, dict) and row.get("status") == "unbacked" and row.get("claim_id")
    ]
    appendix_only = [str(card.get("candidate_card_id")) for card in candidates if card.get("inclusion_recommendation") == "appendix_only"]
    issues = []
    if omitted:
        issues.append("high_relevance_candidate_cards_not_assigned_to_sections")
    if unbacked:
        issues.append("generated_claims_without_source_backing")
    return SourceCoverageReport(
        total_source_card_count=int(source_evidence_cards.get("source_card_count") or 0),
        candidate_card_count=len(candidates),
        assigned_main_card_count=len(assigned),
        omitted_high_relevance_card_ids=omitted[:20],
        unbacked_claim_ids=unbacked[:20],
        appendix_only_card_ids=appendix_only[:30],
        issues=issues,
    ).model_dump()


def _section_reasoning(
    title: str,
    groups: dict[str, list[dict[str, Any]]],
    all_cards: list[dict[str, Any]],
    spine: dict[str, Any],
) -> dict[str, Any]:
    owned = _cards_for_section(title, groups)
    if title == "Decision Brief":
        owned = []
    owned = _expand_to_budget(owned, all_cards, minimum=3, maximum=7) if owned else []
    refs = [card for card in all_cards if card not in owned][:4]
    status, exception = _section_status(title, owned, all_cards)
    return {
        "section": title,
        "section_thesis": _section_thesis(title, spine, owned),
        "decision_move": _decision_move(title),
        "owned_cards": [_model_card(card, title) for card in owned],
        "reference_only_cards": [_model_card(card, title, reference=True) for card in refs],
        "do_not_use_cards": [str(card.get("candidate_card_id")) for card in all_cards if card not in owned and card not in refs][:12],
        "excluded_near_miss_cards": [_near_miss_card(card) for card in all_cards if card not in owned][:5],
        "context_status": status,
        "exception_reason": exception,
    }


def _cards_for_section(title: str, groups: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    key = title.lower()
    if "why this read" in key:
        return _merge_cards(groups["support"][:2], groups["counterweight"][:1], groups["scope"][:1])
    if "evidence carrying" in key:
        return _merge_cards(groups["support"][:3], groups["quantity"][:2], groups["counterweight"][:2])
    if "practical read" in key:
        return _merge_cards(groups["support"][:2], groups["scope"][:3], groups["counterweight"][:1])
    if "scope" in key or "exception" in key:
        return _merge_cards(groups["scope"][:4], groups["counterweight"][:2])
    if "crux" in key:
        return _merge_cards(groups["counterweight"][:2], groups["scope"][:2], groups["quantity"][:1])
    if "limit" in key:
        return _merge_cards(groups["limitation"][:3], groups["context"][:2], groups["counterweight"][:2])
    return []


def _model_card(card: dict[str, Any], section: str, *, reference: bool = False) -> dict[str, Any]:
    role = str(card.get("role") or "context")
    return {
        "candidate_card_id": card.get("candidate_card_id"),
        "source_card_ids": _string_list(card.get("source_card_ids")),
        "claim_ids": _string_list(card.get("claim_ids")),
        "source_ids": _string_list(card.get("source_ids")),
        "source": ", ".join(_string_list(card.get("source_titles")) or _string_list(card.get("source_ids"))),
        "claim": card.get("claim"),
        "source_excerpt": card.get("source_excerpt"),
        "intended_role": "reference context" if reference else role,
        "reason_for_inclusion": _reason_for_section(section, role, reference),
        "quality": card.get("quality"),
        "quantity_values": _string_list(card.get("quantity_values")),
        "limitations": _string_list(card.get("limitations")),
        "use": "Briefly reference only." if reference else "This section may explain this evidence fully.",
    }


def _candidate_score(card: dict[str, Any], quality: dict[str, Any], question_terms: set[str]) -> int:
    base = int(card.get("decision_relevance_score") or 0)
    text = str(card.get("source_quote_or_excerpt") or "")
    overlap = min(3, len(question_terms & _content_terms(text)))
    anchor_bonus = 1 if card.get("anchor_confidence") != "missing" else -2
    quality_bonus = {"usable": 2, "weak": 0, "unknown": -1, "indirect": -2}.get(str(quality.get("overall") or ""), 0)
    return max(0, min(10, base + overlap + anchor_bonus + quality_bonus))


def _appendix_only(card: dict[str, Any], score: int, quality: dict[str, Any], backed_claims: set[str], claim_ids: list[str]) -> bool:
    if card.get("fragment_risk") or card.get("boilerplate_risk"):
        return True
    if card.get("anchor_confidence") == "missing":
        return True
    if claim_ids and not any(claim_id in backed_claims for claim_id in claim_ids):
        return True
    return score < 3 or quality.get("overall") == "indirect"


def _candidate_role(card: dict[str, Any]) -> str:
    role = str(card.get("supports_challenges_or_scopes") or "").lower()
    if "challenge" in role:
        return "counterweight"
    if "scope" in role:
        return "scope"
    if card.get("quantity_values"):
        return "quantity"
    if _string_list(card.get("limitations")):
        return "limitation"
    return "support" if "support" in role else "context"


def _section_candidates(role: str) -> list[str]:
    if role == "counterweight":
        return ["Why This Read", "Evidence Carrying the Conclusion", "Decision Cruxes"]
    if role == "scope":
        return ["Practical Scope and Exceptions", "Decision Cruxes", "Practical Read"]
    if role == "quantity":
        return ["Evidence Carrying the Conclusion", "Decision Cruxes"]
    if role == "limitation":
        return ["Limits of the Current Map", "Practical Scope and Exceptions"]
    return ["Why This Read", "Evidence Carrying the Conclusion", "Practical Read"]


def _spine_item(role: str, statement: str, cards: list[dict[str, Any]], score: int) -> dict[str, Any]:
    return {
        "spine_id": f"spine_{role}_{abs(hash(statement)) % 100000:05d}",
        "role": role,
        "statement": _shorten(statement, 320),
        "candidate_card_ids": [str(card.get("candidate_card_id")) for card in cards if card.get("candidate_card_id")],
        "source_card_ids": _dedupe([sid for card in cards for sid in _string_list(card.get("source_card_ids"))]),
        "source_ids": _dedupe([sid for card in cards for sid in _string_list(card.get("source_ids"))]),
        "decision_relevance_score": score,
    }


def _top_role_cards(cards: list[dict[str, Any]], role: str, *, limit: int) -> list[dict[str, Any]]:
    role_cards = [card for card in cards if card.get("role") == role]
    if role == "quantity":
        role_cards = [card for card in cards if card.get("quantity_values") or card.get("role") == "quantity"]
    return sorted(role_cards, key=lambda card: int(card.get("decision_relevance_score", 0)), reverse=True)[:limit]


def _usable_cards(report: dict[str, Any]) -> list[dict[str, Any]]:
    cards = [card for card in report.get("cards", []) if isinstance(card, dict)]
    usable = [card for card in cards if card.get("inclusion_recommendation") != "appendix_only"]
    return sorted(usable, key=lambda card: int(card.get("decision_relevance_score", 0)), reverse=True)


def _spine_status(sufficiency: dict[str, Any], cards: list[dict[str, Any]]) -> str:
    if not cards or sufficiency.get("status") == "insufficient_source_set":
        return "insufficient"
    if sufficiency.get("bounded_answer_required"):
        return "bounded"
    return "ready"


def _answer_statement(status: str, question: str) -> str:
    if status == "ready":
        return f"The provided documents contain enough source-backed evidence to answer: {question}"
    if status == "bounded":
        return f"The memo should answer {question} as a bounded read over the provided documents."
    return f"The current source set is not sufficient to answer {question} without explicit caveats."


def _section_thesis(title: str, spine: dict[str, Any], owned: list[dict[str, Any]]) -> str:
    if title == "Decision Brief":
        return str(spine.get("answer_frame") or "State the bounded answer and confidence.")
    if owned:
        focus = _section_focus_phrase(owned)
        if "why this read" in title.lower():
            return f"Explain why the answer follows from {focus}."
        if "scope" in title.lower() or "exception" in title.lower():
            return f"Name the practical boundaries implied by {focus}."
        if "evidence carrying" in title.lower():
            return f"Show how {focus} carries or weakens the conclusion."
        if "limit" in title.lower():
            return f"Bound the memo by the uncertainties visible in {focus}."
        return f"Translate {focus} into the section's decision implication."
    return f"{title} should explain the limits of what the current source packet can support."


def _section_focus_phrase(owned: list[dict[str, Any]]) -> str:
    roles = _dedupe([str(card.get("role") or "context").replace("_", " ") for card in owned])[:3]
    snippets = [_claim_noun_phrase(str(card.get("claim", ""))) for card in owned[:2]]
    snippets = [snippet for snippet in snippets if snippet]
    if snippets and roles:
        return f"{', '.join(roles)} evidence on {'; '.join(snippets)}"
    if snippets:
        return "; ".join(snippets)
    return ", ".join(roles) + " evidence" if roles else "the owned evidence"


def _claim_noun_phrase(claim: str) -> str:
    cleaned = _shorten(claim, 110).strip(" .")
    if not cleaned:
        return ""
    return cleaned[0].lower() + cleaned[1:]


def _decision_move(title: str) -> str:
    moves = {
        "Decision Brief": "Give the answer, confidence, and strongest caveat.",
        "Why This Read": "Explain the reasoning path from evidence to answer.",
        "Evidence Carrying the Conclusion": "Show which evidence carries the conclusion and which evidence weakens it.",
        "Practical Read": "Translate the evidence into practical implications under stated conditions.",
        "Practical Scope and Exceptions": "Name where the answer travels and where it should not.",
        "Decision Cruxes": "Identify conditions that would change the answer.",
        "Limits of the Current Map": "Bound the memo to what the current documents establish.",
    }
    return moves.get(title, "Synthesize assigned evidence for this section.")


def _section_status(title: str, owned: list[dict[str, Any]], all_cards: list[dict[str, Any]]) -> tuple[str, str]:
    if title == "Decision Brief":
        return "ready", "opening section generated from accepted body sections"
    if 3 <= len(owned) <= 7:
        return "ready", ""
    if owned:
        return "warning", "owned card count outside default 3-7 budget because the source packet is sparse"
    if all_cards:
        return "warning", "section has no owned cards and must rely on reference context"
    return "not_synthesis_ready", "no usable source-backed cards available"


def _reason_for_section(section: str, role: str, reference: bool) -> str:
    if reference:
        return f"This card gives cross-section context for {section}; do not restate it fully."
    return f"This {role} card is assigned to {section} because it bears on that section's decision move."


def _near_miss_card(card: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_card_id": card.get("candidate_card_id"),
        "role": card.get("role"),
        "reason_excluded": "lower priority than the owned cards for this section",
    }


def _expand_to_budget(cards: list[dict[str, Any]], all_cards: list[dict[str, Any]], *, minimum: int, maximum: int) -> list[dict[str, Any]]:
    selected = _merge_cards(cards)
    for card in all_cards:
        if len(selected) >= minimum:
            break
        if card not in selected:
            selected.append(card)
    return selected[:maximum]


def _merge_cards(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for card in group:
            card_id = str(card.get("candidate_card_id", ""))
            if card_id and card_id not in seen:
                seen.add(card_id)
                merged.append(card)
    return merged


def _cards_by_claim(cards: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_claim: dict[str, list[dict[str, Any]]] = {}
    for card in cards:
        for claim_id in _string_list(card.get("claim_ids")):
            by_claim.setdefault(claim_id, []).append(card)
    return by_claim


def _source_overlap_cards(claim: dict[str, Any], claim_text: str, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_id = str(claim.get("source_id") or "").strip()
    claim_terms = _content_terms(claim_text)
    matched = []
    for card in cards:
        if source_id and str(card.get("source_id") or "") != source_id:
            continue
        if len(claim_terms & _content_terms(str(card.get("source_quote_or_excerpt") or ""))) >= 3:
            matched.append(card)
    return matched[:3]


def _backed_claim_ids(reconciliation: dict[str, Any]) -> set[str]:
    return {
        str(row.get("claim_id"))
        for row in reconciliation.get("rows", [])
        if isinstance(row, dict) and row.get("status") != "unbacked" and row.get("claim_id")
    }


def _assigned_candidate_ids(section_cards: dict[str, Any]) -> set[str]:
    assigned: set[str] = set()
    for section in section_cards.get("sections", []) if isinstance(section_cards.get("sections"), list) else []:
        if not isinstance(section, dict):
            continue
        for card in section.get("owned_cards", []) if isinstance(section.get("owned_cards"), list) else []:
            if isinstance(card, dict) and card.get("candidate_card_id"):
                assigned.add(str(card["candidate_card_id"]))
    return assigned


def _inclusion_reason(card: dict[str, Any], role: str, score: int, quality: dict[str, Any]) -> str:
    source = str(card.get("source_title") or card.get("source_id") or "source")
    return f"{source} provides {role} evidence with relevance {score}/10 and quality {quality.get('overall', 'unknown')}."


def _claims(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    claims = candidate_map.get("claims", [])
    return [claim for claim in claims if isinstance(claim, dict)] if isinstance(claims, list) else []


def _claim_text(claim: dict[str, Any]) -> str:
    return str(claim.get("claim") or claim.get("text") or claim.get("proposition") or "").strip()


def _content_terms(text: str) -> set[str]:
    stop = {"about", "after", "against", "between", "could", "from", "have", "into", "should", "than", "that", "their", "there", "this", "what", "when", "where", "which", "with", "would"}
    return {token for token in re.findall(r"[a-z0-9]{4,}", str(text).lower()) if token not in stop}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        key = item.lower()
        if key and key not in seen:
            seen.add(key)
            result.append(item)
    return result


def _shorten(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned if len(cleaned) <= limit else cleaned[: max(0, limit - 3)].rstrip(" ,.;") + "..."
