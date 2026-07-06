from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any

from epistemic_case_mapper.map_briefing_context_schemas import (
    EvidenceQualityReport,
    SectionContextAcceptanceReport,
    SectionContextAcceptanceRow,
    SourceEvidenceCardReport,
    SourceSufficiencyReport,
)


def build_source_evidence_cards(
    candidate_map: dict[str, Any],
    *,
    source_lookup: dict[str, str],
    source_urls: dict[str, str] | None = None,
) -> dict[str, Any]:
    source_urls = source_urls or {}
    cards: list[dict[str, Any]] = []
    for index, claim in enumerate(_claims(candidate_map), start=1):
        text = _claim_text(claim)
        source_id = str(claim.get("source_id", "")).strip()
        excerpt = _excerpt_for_claim(claim, text)
        anchor_confidence = _anchor_confidence(claim, excerpt)
        source_card = {
            "source_card_id": f"sc{index:04d}",
            "source_id": source_id,
            "source_title": source_lookup.get(source_id, source_id),
            "source_url": str(source_urls.get(source_id, "")).strip(),
            "source_span": _source_span(claim),
            "source_quote_or_excerpt": excerpt,
            "span_hash": str(claim.get("source_text_hash") or claim.get("excerpt_hash") or _stable_hash(excerpt)),
            "anchor_confidence": anchor_confidence,
            "decision_relevance_score": _int_value(claim.get("decision_relevance_score") or claim.get("relevance_score") or claim.get("score")),
            "endpoint_match": str(claim.get("endpoint_fit") or claim.get("endpoint_match") or "unknown"),
            "population_match": str(claim.get("population_fit") or claim.get("population_match") or "unknown"),
            "exposure_or_intervention": "",
            "comparator": "",
            "outcome_or_endpoint": str(claim.get("endpoint_type") or ""),
            "evidence_type": str(claim.get("evidence_family") or claim.get("claim_type") or "unspecified"),
            "quantity_values": _string_list(claim.get("quantity_values") or claim.get("quantities")),
            "limitations": _limitations_for_claim(claim),
            "supports_challenges_or_scopes": _role_for_claim(claim),
            "fragment_risk": _has_noise(claim, "fragment"),
            "boilerplate_risk": _has_noise(claim, "boilerplate"),
            "claim_ids": [str(claim.get("claim_id", "")).strip()] if str(claim.get("claim_id", "")).strip() else [],
        }
        cards.append(source_card)
    anchored = sum(1 for card in cards if card.get("anchor_confidence") != "missing")
    report = SourceEvidenceCardReport(
        source_card_count=len(cards),
        anchored_card_count=anchored,
        missing_anchor_count=len(cards) - anchored,
        cards=cards,
        issues=[] if cards else ["no_claims_available_for_source_evidence_cards"],
    )
    return report.model_dump()


def build_source_sufficiency_report(
    *,
    decision_question: str,
    source_evidence_cards: dict[str, Any],
    scaffold: dict[str, Any],
) -> dict[str, Any]:
    cards = [card for card in source_evidence_cards.get("cards", []) if isinstance(card, dict)]
    question_terms = _content_terms(decision_question)
    role_counts = Counter(str(card.get("supports_challenges_or_scopes") or "uncategorized") for card in cards)
    direct_cards = [
        card
        for card in cards
        if _directness_score(question_terms, str(card.get("source_quote_or_excerpt", ""))) >= 2
        or _int_value(card.get("decision_relevance_score")) >= 6
    ]
    anchored_cards = [card for card in cards if card.get("anchor_confidence") != "missing"]
    quantity_cards = [card for card in cards if card.get("quantity_values")]
    sufficiency = scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}
    missing = _generic_missing_categories(
        cards=cards,
        direct_cards=direct_cards,
        anchored_cards=anchored_cards,
        role_counts=role_counts,
        quantity_cards=quantity_cards,
        existing_sufficiency=sufficiency,
    )
    if not cards or not anchored_cards or "direct_answer_evidence" in missing:
        status = "insufficient_source_set"
    elif missing:
        status = "sufficient_for_bounded_answer"
    else:
        status = "sufficient_for_decision_ready_answer"
    report = SourceSufficiencyReport(
        status=status,
        decision_question=decision_question,
        coverage={
            "has_source_cards": bool(cards),
            "has_anchored_cards": bool(anchored_cards),
            "has_direct_answer_evidence": bool(direct_cards),
            "has_support": role_counts.get("supports", 0) > 0,
            "has_counterweight": role_counts.get("challenges", 0) > 0,
            "has_scope_boundary": role_counts.get("scopes", 0) > 0,
            "has_quantitative_anchor": bool(quantity_cards),
        },
        missing_source_categories=missing,
        bounded_answer_required=status != "sufficient_for_decision_ready_answer",
        notes=_source_sufficiency_notes(status, missing),
    )
    return report.model_dump()


def build_evidence_quality_report(source_evidence_cards: dict[str, Any]) -> dict[str, Any]:
    cards = [card for card in source_evidence_cards.get("cards", []) if isinstance(card, dict)]
    components: dict[str, dict[str, Any]] = {}
    weak_or_indirect = 0
    unknown_quality = 0
    for card in cards:
        card_id = str(card.get("source_card_id", "")).strip()
        component = _quality_component(card)
        components[card_id] = component
        if component["overall"] in {"weak", "indirect"}:
            weak_or_indirect += 1
        if component["overall"] == "unknown":
            unknown_quality += 1
    report = EvidenceQualityReport(
        card_count=len(cards),
        weak_or_indirect_count=weak_or_indirect,
        unknown_quality_count=unknown_quality,
        quality_components=components,
        issues=[] if cards else ["no_source_cards_available_for_quality_weighting"],
    )
    return report.model_dump()


def build_section_context_acceptance_report(section_packets: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[SectionContextAcceptanceRow] = []
    for packet in section_packets:
        if not isinstance(packet, dict):
            continue
        row = _section_context_row(packet)
        rows.append(row)
    if any(row.status == "not_synthesis_ready" for row in rows):
        status = "not_synthesis_ready"
    elif any(row.status == "warning" for row in rows):
        status = "warning"
    else:
        status = "ready"
    report = SectionContextAcceptanceReport(
        status=status,
        sections=rows,
        issues=[issue for row in rows for issue in row.issues],
    )
    return report.model_dump()


def _quality_component(card: dict[str, Any]) -> dict[str, Any]:
    relevance = _int_value(card.get("decision_relevance_score"))
    anchor = str(card.get("anchor_confidence") or "missing")
    evidence_type = str(card.get("evidence_type") or "unspecified").lower()
    limitations = _string_list(card.get("limitations"))
    directness = "direct" if relevance >= 7 else "partial" if relevance >= 4 else "indirect"
    provenance = "unspecified"
    if any(term in evidence_type for term in ("review", "meta", "guideline", "trial", "cohort", "study")):
        provenance = evidence_type
    uncertainty = "limited" if limitations or anchor == "missing" else "not_flagged"
    if anchor == "missing" or directness == "indirect":
        overall = "indirect"
    elif provenance == "unspecified":
        overall = "unknown"
    elif limitations:
        overall = "weak"
    else:
        overall = "usable"
    return {
        "source_card_id": card.get("source_card_id"),
        "source_id": card.get("source_id"),
        "directness": directness,
        "provenance": provenance,
        "anchor_strength": anchor,
        "uncertainty": uncertainty,
        "limitations": limitations,
        "overall": overall,
    }


def _section_context_row(packet: dict[str, Any]) -> SectionContextAcceptanceRow:
    title = str(packet.get("title", "")).strip() or "Untitled Section"
    model_packet = packet.get("model_packet", {}) if isinstance(packet.get("model_packet"), dict) else {}
    raw_packet = packet.get("packet", {}) if isinstance(packet.get("packet"), dict) else {}
    owned = [row for row in model_packet.get("owned_evidence", []) if isinstance(row, dict)]
    obligations = [
        row for row in raw_packet.get("required_main_memo_obligations", []) if isinstance(row, dict)
    ]
    cruxes = [row for row in model_packet.get("canonical_cruxes", []) if isinstance(row, dict)]
    quantities = [row for row in model_packet.get("must_include_quantities", []) if isinstance(row, dict)]
    substantive = _is_substantive_section(title)
    issues: list[str] = []
    if substantive and not str(model_packet.get("section_thesis", "")).strip() and not str(packet.get("section_job", "")).strip():
        issues.append(f"{title}: missing section decision move")
    if substantive and not (owned or cruxes or quantities or obligations):
        issues.append(f"{title}: no owned source-backed context or explicit substitute")
    missing_roles = [
        str(row.get("claim", ""))[:80]
        for row in owned
        if not str(row.get("intended_role", "")).strip()
    ]
    if missing_roles:
        issues.append(f"{title}: owned cards missing intended_role")
    missing_reasons = [
        str(row.get("claim", ""))[:80]
        for row in owned
        if not str(row.get("reason_for_inclusion", "")).strip()
    ]
    if missing_reasons:
        issues.append(f"{title}: owned cards missing reason_for_inclusion")
    count = len(owned)
    if not substantive or count == 0 and (cruxes or quantities or obligations):
        budget_status = "justified_exception"
    elif count < 3:
        budget_status = "under_budget"
        if substantive:
            issues.append(f"{title}: owned card count below default budget")
    elif count > 7:
        budget_status = "over_budget"
        issues.append(f"{title}: owned card count above default budget")
    else:
        budget_status = "within_budget"
    context_risk = "high" if any("no owned" in issue or "missing section" in issue for issue in issues) else "medium" if issues else "low"
    status = "not_synthesis_ready" if context_risk == "high" else "warning" if issues else "ready"
    can_answer = _section_can_answer(title, model_packet, owned, cruxes, quantities, obligations)
    missing_context = [
        issue.split(": ", 1)[1]
        for issue in issues
        if ": " in issue
    ]
    return SectionContextAcceptanceRow(
        section=title,
        status=status,
        owned_card_count=count,
        card_budget_status=budget_status,
        this_section_can_answer=can_answer,
        because=_because_for_section(owned, cruxes, quantities, obligations),
        missing_context=missing_context,
        context_risk_level=context_risk,
        issues=issues,
    )


def _is_substantive_section(title: str) -> bool:
    lowered = title.strip().lower()
    return lowered not in {"sources", "evidence trail"} and "appendix" not in lowered


def _section_can_answer(
    title: str,
    model_packet: dict[str, Any],
    owned: list[dict[str, Any]],
    cruxes: list[dict[str, Any]],
    quantities: list[dict[str, Any]],
    obligations: list[dict[str, Any]],
) -> str:
    thesis = str(model_packet.get("section_thesis", "")).strip()
    if thesis:
        return thesis
    if owned:
        return f"{title} can explain its owned evidence."
    if cruxes:
        return f"{title} can summarize decision-changing cruxes."
    if quantities:
        return f"{title} can carry assigned quantitative anchors."
    if obligations:
        return f"{title} can satisfy assigned memo obligations."
    return ""


def _because_for_section(
    owned: list[dict[str, Any]],
    cruxes: list[dict[str, Any]],
    quantities: list[dict[str, Any]],
    obligations: list[dict[str, Any]],
) -> str:
    parts: list[str] = []
    if owned:
        parts.append(f"{len(owned)} owned evidence card(s)")
    if cruxes:
        parts.append(f"{len(cruxes)} crux item(s)")
    if quantities:
        parts.append(f"{len(quantities)} quantitative anchor(s)")
    if obligations:
        parts.append(f"{len(obligations)} memo obligation(s)")
    return ", ".join(parts)


def _generic_missing_categories(
    *,
    cards: list[dict[str, Any]],
    direct_cards: list[dict[str, Any]],
    anchored_cards: list[dict[str, Any]],
    role_counts: Counter[str],
    quantity_cards: list[dict[str, Any]],
    existing_sufficiency: dict[str, Any],
) -> list[str]:
    missing: list[str] = []
    if not cards:
        missing.append("source_cards")
    if not anchored_cards:
        missing.append("source_anchors")
    if not direct_cards:
        missing.append("direct_answer_evidence")
    if role_counts.get("supports", 0) == 0:
        missing.append("supporting_evidence")
    if role_counts.get("challenges", 0) == 0:
        missing.append("counterweight_evidence")
    if role_counts.get("scopes", 0) == 0:
        missing.append("scope_boundary_evidence")
    if not quantity_cards:
        missing.append("quantitative_anchor")
    for slot in _string_list(existing_sufficiency.get("missing_expected_decision_slots")):
        missing.append(f"decision_slot:{slot}")
    for family in _string_list(existing_sufficiency.get("missing_expected_evidence_families")):
        missing.append(f"evidence_family:{family}")
    return _dedupe(missing)


def _source_sufficiency_notes(status: str, missing: list[str]) -> list[str]:
    if status == "sufficient_for_decision_ready_answer":
        return ["Provided documents expose source-backed support, counterweight, and scope context."]
    return [
        "The final memo should be framed as bounded to the provided documents.",
        "Missing source categories: " + ", ".join(missing[:8]) + ".",
    ]


def _claims(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    claims = candidate_map.get("claims", [])
    return [claim for claim in claims if isinstance(claim, dict)] if isinstance(claims, list) else []


def _claim_text(claim: dict[str, Any]) -> str:
    return str(claim.get("claim") or claim.get("text") or claim.get("proposition") or "").strip()


def _excerpt_for_claim(claim: dict[str, Any], fallback: str) -> str:
    for key in ("source_quote_or_excerpt", "source_excerpt", "excerpt", "source_span_text"):
        value = str(claim.get(key, "")).strip()
        if value:
            return _shorten(value, 600)
    return _shorten(fallback, 600)


def _source_span(claim: dict[str, Any]) -> str:
    explicit = str(claim.get("source_span", "")).strip()
    if explicit:
        return explicit
    start, end = claim.get("source_start"), claim.get("source_end")
    if start is not None and end is not None:
        return f"{start}:{end}"
    return ""


def _anchor_confidence(claim: dict[str, Any], excerpt: str) -> str:
    if claim.get("source_text_hash") or claim.get("excerpt_hash") or claim.get("source_span"):
        return "exact"
    if claim.get("source_start") is not None and claim.get("source_end") is not None:
        return "exact"
    return "recovered" if excerpt else "missing"


def _role_for_claim(claim: dict[str, Any]) -> str:
    values = " ".join(
        str(claim.get(key, ""))
        for key in ("evidence_role", "section", "relation_type", "claim_type", "tags")
    ).lower()
    if any(term in values for term in ("challenge", "counter", "conflict", "tension", "risk")):
        return "challenges"
    if any(term in values for term in ("scope", "limit", "boundary", "exception")):
        return "scopes"
    if any(term in values for term in ("support", "main", "conclusion")):
        return "supports"
    return "uncategorized"


def _limitations_for_claim(claim: dict[str, Any]) -> list[str]:
    values = _string_list(claim.get("limitations"))
    values.extend(_string_list(claim.get("noise")))
    if claim.get("appendix_only"):
        values.append("appendix_only")
    return _dedupe(values)


def _has_noise(claim: dict[str, Any], marker: str) -> bool:
    text = " ".join(_string_list(claim.get("noise")) + _string_list(claim.get("noise_flags"))).lower()
    return marker in text


def _directness_score(question_terms: set[str], text: str) -> int:
    if not question_terms:
        return 0
    terms = _content_terms(text)
    return len(question_terms & terms)


def _content_terms(text: str) -> set[str]:
    stop = {
        "about",
        "after",
        "against",
        "between",
        "could",
        "does",
        "from",
        "have",
        "into",
        "should",
        "than",
        "that",
        "their",
        "there",
        "this",
        "what",
        "when",
        "where",
        "whether",
        "which",
        "with",
        "would",
    }
    return {
        token
        for token in re.findall(r"[a-z0-9]{4,}", text.lower())
        if token not in stop
    }


def _stable_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16] if text else ""


def _int_value(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, tuple):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _shorten(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"
