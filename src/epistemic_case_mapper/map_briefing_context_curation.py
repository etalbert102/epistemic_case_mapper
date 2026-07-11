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
    SourceCoverageReport,
    SourceMapReconciliationReport,
)
from epistemic_case_mapper.map_briefing_source_appraisal import (
    appraisal_for_sources,
    build_source_appraisal_report,
    run_source_caveat_appraisal,
)


def build_decision_ready_context_bundle(
    prioritized_map: dict[str, Any],
    *,
    scaffold: dict[str, Any],
    question: str,
    source_lookup: dict[str, str],
    backend: str = "prompt",
    backend_timeout: int | None = None,
    backend_retries: int = 0,
) -> dict[str, Any]:
    source_urls = scaffold.get("source_urls", {}) if isinstance(scaffold.get("source_urls"), dict) else {}
    source_cards = build_source_evidence_cards(prioritized_map, source_lookup=source_lookup, source_urls=source_urls)
    sufficiency = build_source_sufficiency_report(
        decision_question=question,
        source_evidence_cards=source_cards,
        scaffold=scaffold,
        candidate_map=prioritized_map,
    )
    quality = build_evidence_quality_report(source_cards)
    caveat_appraisal = run_source_caveat_appraisal(
        source_evidence_cards=source_cards,
        evidence_quality_report=quality,
        backend=backend,
        backend_timeout=_source_appraisal_timeout(backend, backend_timeout),
        backend_retries=backend_retries,
    )
    appraisal = build_source_appraisal_report(
        source_evidence_cards=source_cards,
        evidence_quality_report=quality,
        source_caveat_appraisal_report=caveat_appraisal.get("source_caveat_appraisal_report", {}),
    )
    reconciliation = build_source_map_reconciliation(prioritized_map, source_cards)
    candidates = build_candidate_evidence_cards(
        source_evidence_cards=source_cards,
        source_map_reconciliation=reconciliation,
        evidence_quality_report=quality,
        source_appraisal_report=appraisal,
        question=question,
    )
    candidates = apply_map_eligibility_to_candidate_cards(candidates, scaffold)
    coverage = build_source_coverage_report(
        source_evidence_cards=source_cards,
        candidate_evidence_cards=candidates,
        source_map_reconciliation=reconciliation,
    )
    return {
        "source_evidence_cards": source_cards,
        "source_sufficiency_report": sufficiency,
        "evidence_quality_report": quality,
        "source_appraisal_report": appraisal,
        **caveat_appraisal,
        "source_map_reconciliation": reconciliation,
        "candidate_evidence_cards": candidates,
        "source_coverage_report": coverage,
    }


def _source_appraisal_timeout(backend: str, backend_timeout: int | None) -> int | None:
    if backend.strip() == "prompt":
        return backend_timeout
    if backend_timeout is None:
        return 90
    return min(max(20, backend_timeout), 90)


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


def apply_map_eligibility_to_candidate_cards(
    candidate_evidence_cards: dict[str, Any],
    scaffold: dict[str, Any],
) -> dict[str, Any]:
    ledger = scaffold.get("evidence_weighting_ledger", {}) if isinstance(scaffold.get("evidence_weighting_ledger"), dict) else {}
    row_lookup = {
        str(row.get("claim_id", "")): row
        for row in ledger.get("all_evidence", [])
        if isinstance(row, dict) and str(row.get("claim_id", "")).strip()
    }
    cards: list[dict[str, Any]] = []
    for card in candidate_evidence_cards.get("cards", []) if isinstance(candidate_evidence_cards.get("cards"), list) else []:
        if not isinstance(card, dict):
            continue
        cards.append(_candidate_card_with_map_eligibility(card, row_lookup))
    updated = dict(candidate_evidence_cards)
    updated["cards"] = cards
    updated["main_text_count"] = sum(1 for card in cards if card.get("inclusion_recommendation") == "main_text")
    updated["appendix_only_count"] = sum(1 for card in cards if card.get("inclusion_recommendation") == "appendix_only")
    return updated


def _candidate_card_with_map_eligibility(card: dict[str, Any], row_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
    rows = [row_lookup[claim_id] for claim_id in _string_list(card.get("claim_ids")) if claim_id in row_lookup]
    if not rows:
        return card
    updated = dict(card)
    if any(row.get("appendix_only") for row in rows):
        updated["inclusion_recommendation"] = "appendix_only"
        updated["map_eligibility_reason"] = "underlying_map_claim_appendix_only"
        return updated
    statuses = {
        str(_dict(row.get("question_fit")).get("status", ""))
        for row in rows
        if isinstance(row.get("question_fit"), dict)
    }
    updated["map_question_fit_statuses"] = sorted(status for status in statuses if status)
    if "mismatch" in statuses:
        updated["inclusion_recommendation"] = "appendix_only"
        updated["map_eligibility_reason"] = "underlying_map_claim_question_mismatch"
        return updated
    if "narrower_than_question" in statuses and not any(bool(row.get("top_line_eligible")) for row in rows):
        roles = _dedupe([*_string_list(updated.get("evidence_roles")), "scope"])
        updated["evidence_roles"] = roles
        updated["scope_tags"] = _dedupe([*_string_list(updated.get("scope_tags")), "narrower_than_question"])
        if str(updated.get("role") or "") in ("support", "context"):
            updated["role"] = "scope"
        updated["section_candidates"] = _section_candidates_for_roles(roles, _string_list(updated.get("scope_tags")))
        if updated.get("inclusion_recommendation") == "main_text":
            updated["inclusion_recommendation"] = "supporting_context"
        updated["map_eligibility_reason"] = "narrower_scope_context_not_default_evidence"
    return updated


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_candidate_evidence_cards(
    *,
    source_evidence_cards: dict[str, Any],
    source_map_reconciliation: dict[str, Any],
    evidence_quality_report: dict[str, Any],
    source_appraisal_report: dict[str, Any] | None = None,
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
        profile = _candidate_profile(source_card)
        role = str(profile["primary_role"])
        claim_ids = _string_list(source_card.get("claim_ids"))
        source_ids = _string_list(source_card.get("source_id"))
        source_appraisal = appraisal_for_sources(source_appraisal_report or {}, source_ids)
        appendix_only = _appendix_only(source_card, score, quality_row, backed_claims, claim_ids)
        cards.append(
            {
                "candidate_card_id": f"ec{index:04d}",
                "source_card_ids": [source_card_id] if source_card_id else [],
                "claim_ids": claim_ids,
                "source_ids": source_ids,
                "source_titles": _string_list(source_card.get("source_title")),
                "claim": _shorten(str(source_card.get("source_quote_or_excerpt", "")), 300),
                "source_excerpt": _shorten(str(source_card.get("source_quote_or_excerpt", "")), 500),
                "role": role,
                "evidence_roles": profile["evidence_roles"],
                "scope_tags": profile["scope_tags"],
                "decision_relevance_score": score,
                "quality": str(quality_row.get("overall") or "unknown"),
                "inclusion_recommendation": "appendix_only" if appendix_only else "main_text" if score >= 7 else "supporting_context",
                "inclusion_reason": _inclusion_reason(source_card, role, score, quality_row),
                "section_candidates": profile["section_candidates"],
                "quantity_values": _string_list(source_card.get("quantity_values")),
                "limitations": _string_list(source_card.get("limitations")),
                "anchor_confidence": str(source_card.get("anchor_confidence") or "missing"),
                "source_appraisal": source_appraisal,
                "source_use_warnings": _string_list(source_appraisal.get("source_use_warnings")),
                "allowed_wording": source_appraisal.get("allowed_wording", {}),
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


def build_source_coverage_report(
    *,
    source_evidence_cards: dict[str, Any],
    candidate_evidence_cards: dict[str, Any],
    source_map_reconciliation: dict[str, Any],
    section_projection_packets: dict[str, Any] | None = None,
    section_context_decision_packets: dict[str, Any] | None = None,
) -> dict[str, Any]:
    final_assigned = _assigned_candidate_ids_from_final_packets(
        section_projection_packets=section_projection_packets,
        section_context_decision_packets=section_context_decision_packets,
    )
    assigned = final_assigned
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
        assignment_basis="final_projection_or_context_packets" if final_assigned else "pending_final_projection",
        final_assigned_main_card_count=len(final_assigned),
    ).model_dump()


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


def _candidate_profile(card: dict[str, Any]) -> dict[str, list[str] | str]:
    source_role = str(card.get("supports_challenges_or_scopes") or "").lower()
    decision_polarity = str(card.get("decision_polarity") or "").lower()
    explicit = " ".join(
        str(card.get(key) or "")
        for key in ("role", "evidence_role", "claim_type")
    ).lower()
    text = " ".join([source_role, decision_polarity, explicit]).lower()
    roles: list[str] = []
    if decision_polarity == "challenges_current_answer" or _explicit_counterweight_signal(source_role, text):
        roles.append("counterweight")
    if _string_list(card.get("quantity_values")) or _has_quantity_signal(text):
        roles.append("quantity")
    if _string_list(card.get("limitations")) or _explicit_limitation_signal(text):
        roles.append("limitation")
    if decision_polarity == "supports_current_answer" or _explicit_support_signal(source_role, text):
        roles.append("support")
    if decision_polarity == "scopes_current_answer" or "scope" in source_role or _explicit_scope_signal(text):
        roles.append("scope")
    roles = _dedupe(roles) or ["context"]
    primary = _primary_role(roles)
    scope_tags = _scope_tags(text, roles)
    return {
        "primary_role": primary,
        "evidence_roles": roles,
        "scope_tags": scope_tags,
        "section_candidates": _section_candidates_for_roles(roles, scope_tags),
    }


def _primary_role(roles: list[str]) -> str:
    for role in ("counterweight", "quantity", "limitation", "support", "scope", "context"):
        if role in roles:
            return role
    return "context"


def _explicit_counterweight_signal(source_role: str, text: str) -> bool:
    return any(marker in source_role for marker in ("challenge", "counter", "tension", "conflict")) or any(
        marker in text
        for marker in (
            "challenge",
            "counter",
            "counterweight",
            "conflict",
            "tension",
            "contrary",
            "conflicting_evidence",
        )
    )


def _explicit_support_signal(source_role: str, text: str) -> bool:
    return source_role in {"support", "supports", "strongest_support"} or bool(
        _explicit_label_set(text) & {"support", "supports", "strongest_support"}
    )


def _explicit_label_set(text: str) -> set[str]:
    return {token for token in re.split(r"[^a-zA-Z0-9_]+", text.lower()) if token}


def _has_quantity_signal(text: str) -> bool:
    return bool(re.search(r"\b\d+(?:\.\d+)?\s*(?:%|percent|fold|mg/dl|mmol/l|ci|rr|or|hr|i2|p\s*[<=>])\b", text))


def _explicit_limitation_signal(text: str) -> bool:
    return any(marker in text for marker in ("limit", "limitation", "uncertainty", "source_quality_caveat"))


def _explicit_scope_signal(text: str) -> bool:
    return any(
        marker in text
        for marker in (
            "subgroup",
            "population_or_subgroup",
            "scope",
            "scope_limit",
            "boundary",
            "exception",
        )
    )


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


def _section_candidates_for_roles(roles: list[str], scope_tags: list[str] | None = None) -> list[str]:
    sections: list[str] = []
    for role in roles:
        sections.extend(_section_candidates(role))
    if scope_tags:
        sections.extend(["Practical Scope and Exceptions", "Decision Cruxes"])
    return _dedupe(sections)


def _scope_tags(text: str, roles: list[str]) -> list[str]:
    tags: list[str] = []
    if any(marker in text for marker in ("subgroup", "population", "adult", "children", "older", "diabetes")):
        tags.append("population_boundary")
    if any(marker in text for marker in ("dose", "per week", "per day", "serving", "intake", "consumption")):
        tags.append("dose_or_intensity_boundary")
    if any(marker in text for marker in ("comparator", "substitution", "instead of", "replace")):
        tags.append("comparator_or_substitution")
    if "limitation" in roles:
        tags.append("evidence_quality_limit")
    if "scope" in roles and not tags:
        tags.append("scope_boundary")
    return _dedupe(tags)


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


def _assigned_candidate_ids_from_final_packets(
    *,
    section_projection_packets: dict[str, Any] | None,
    section_context_decision_packets: dict[str, Any] | None,
) -> set[str]:
    assigned: set[str] = set()
    for packet in (section_context_decision_packets, section_projection_packets):
        if not isinstance(packet, dict):
            continue
        for section in packet.get("sections", []) if isinstance(packet.get("sections"), list) else []:
            if not isinstance(section, dict):
                continue
            for card in section.get("owned_evidence", []) if isinstance(section.get("owned_evidence"), list) else []:
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
