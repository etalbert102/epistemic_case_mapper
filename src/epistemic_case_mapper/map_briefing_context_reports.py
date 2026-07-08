from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any

from epistemic_case_mapper.map_briefing_context_schemas import (
    EvidenceQualityReport,
    FinalBriefEvaluation,
    MemoCoherenceReport,
    PipelineMigrationLedger,
    RuntimeBudgetReport,
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
            "decision_relevance_score": _claim_relevance_score(claim),
            "endpoint_match": str(claim.get("endpoint_fit") or claim.get("endpoint_match") or "unknown"),
            "population_match": str(claim.get("population_fit") or claim.get("population_match") or "unknown"),
            "exposure_or_intervention": "",
            "comparator": "",
            "outcome_or_endpoint": str(claim.get("endpoint_type") or ""),
            "evidence_type": str(claim.get("evidence_family") or claim.get("claim_type") or _joined_evidence_slots(claim) or "unspecified"),
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
    candidate_map: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cards = [card for card in source_evidence_cards.get("cards", []) if isinstance(card, dict)]
    question_terms = _content_terms(decision_question)
    semantic_signals = _semantic_sufficiency_signals(
        cards=cards,
        candidate_map=candidate_map or {},
        scaffold=scaffold,
    )
    direct_cards = [
        card
        for card in cards
        if _directness_score(question_terms, str(card.get("source_quote_or_excerpt", ""))) >= 2
        or _int_value(card.get("decision_relevance_score")) >= 6
    ]
    anchored_cards = [card for card in cards if card.get("anchor_confidence") != "missing"]
    sufficiency = scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}
    missing = _generic_missing_categories(
        cards=cards,
        direct_cards=direct_cards,
        anchored_cards=anchored_cards,
        existing_sufficiency=sufficiency,
        semantic_signals=semantic_signals,
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
            "has_support": semantic_signals["has_support"],
            "has_counterweight": semantic_signals["has_counterweight"],
            "has_scope_boundary": semantic_signals["has_scope_boundary"],
            "has_quantitative_anchor": semantic_signals["has_quantitative_anchor"],
        },
        missing_source_categories=missing,
        bounded_answer_required=status != "sufficient_for_decision_ready_answer",
        notes=_source_sufficiency_notes(status, missing),
        semantic_signal_report=semantic_signals["report"],
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


def build_memo_coherence_report(
    *,
    memo_markdown: str,
    decision_question: str,
    scaffold: dict[str, Any],
) -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    if decision_question and _normalize(decision_question) not in _normalize(memo_markdown):
        issues.append({"kind": "decision_question_missing", "message": "Decision question is not visible in the memo."})
    first_answer = _first_body_paragraph(memo_markdown)
    if not first_answer:
        issues.append({"kind": "missing_opening_answer", "message": "Memo lacks a clear opening answer paragraph."})
    if _repetition_count(memo_markdown) > 2:
        issues.append({"kind": "repetition", "message": "Memo repeats exact or near-exact sentences across sections."})
    source_lookup = scaffold.get("source_display_names", {}) if isinstance(scaffold.get("source_display_names"), dict) else {}
    if source_lookup and "## Sources" not in memo_markdown:
        issues.append({"kind": "missing_sources_section", "message": "Memo has sources in scaffold but no final Sources section."})
    sufficiency = scaffold.get("source_sufficiency_report", {}) if isinstance(scaffold.get("source_sufficiency_report"), dict) else {}
    if sufficiency.get("bounded_answer_required") and "provided document" not in memo_markdown.lower() and "current map" not in memo_markdown.lower():
        issues.append({"kind": "bounded_answer_not_visible", "message": "Source sufficiency requires a bounded answer, but the memo does not visibly bound the claim."})
    status = "fail" if any(issue["kind"] in {"decision_question_missing", "missing_opening_answer"} for issue in issues) else "warning" if issues else "pass"
    return MemoCoherenceReport(status=status, issue_count=len(issues), issues=issues).model_dump()


def build_pipeline_migration_ledger(
    *,
    section_context_acceptance_path: str | None,
    scaffold: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scaffold = scaffold or {}
    projection = scaffold.get("section_projection_readiness_report", {}) if isinstance(scaffold.get("section_projection_readiness_report"), dict) else {}
    projection_ready = projection.get("status") in {"ready", "warning"}
    old_visible = [] if projection_ready else ["validation_obligations.required_main_memo_obligations"]
    new_visible = [
        "model_section_packet",
        "canonical_decision_spine" if scaffold.get("canonical_decision_spine") else "",
        "slot_reconciliation_report" if scaffold.get("slot_reconciliation_report") else "",
        "section_context_decision_packets" if scaffold.get("section_context_decision_packets") else "",
        "section_context_quality_report" if scaffold.get("section_context_quality_report") else "",
        "section_projection_packets" if scaffold.get("section_projection_packets") else "",
        "section_context_acceptance_report" if section_context_acceptance_path else "",
    ]
    new_visible = [item for item in new_visible if item]
    status = "warning" if old_visible else "clean"
    return PipelineMigrationLedger(
        old_context_fields_still_model_visible=old_visible,
        new_context_fields_model_visible=new_visible,
        debug_only_artifacts=["main_memo_obligation_ledger", "unified_requirement_ledger"],
        compatibility_shims=[] if projection_ready else ["main memo obligations remain as validation obligations until fully replaced"],
        status=status,
    ).model_dump()


def build_runtime_budget_report(
    *,
    section_rewrite_report: dict[str, Any],
    reader_rewrite_report: dict[str, Any],
) -> dict[str, Any]:
    section_attempts = 0
    for section in section_rewrite_report.get("sections", []) if isinstance(section_rewrite_report.get("sections"), list) else []:
        if isinstance(section, dict):
            section_attempts += _int_value(section.get("attempt_count"))
    if reader_rewrite_report.get("status") in {"skipped_after_section_rewrite", "not_run", "skipped_prompt_backend"}:
        reader_model_calls = 0
    else:
        reader_model_calls = max(1, _int_value(reader_rewrite_report.get("pass_count")))
    stages = [
        {"stage": "section_rewrite", "model_call_count": section_attempts},
        {"stage": "reader_memo_rewrite", "model_call_count": reader_model_calls},
    ]
    most_expensive = max(stages, key=lambda row: int(row.get("model_call_count", 0)))["stage"] if stages else ""
    return RuntimeBudgetReport(
        stages=stages,
        model_call_count=section_attempts + reader_model_calls,
        degraded_mode_triggers=_runtime_degraded_triggers(section_rewrite_report, reader_rewrite_report),
        most_expensive_stage=most_expensive,
    ).model_dump()


def build_final_brief_evaluation(
    *,
    memo_markdown: str,
    memo_path: str,
    decision_question: str,
    coherence_report: dict[str, Any],
    scaffold: dict[str, Any],
) -> dict[str, Any]:
    sufficiency = scaffold.get("source_sufficiency_report", {}) if isinstance(scaffold.get("source_sufficiency_report"), dict) else {}
    evidence_quality = scaffold.get("evidence_quality_report", {}) if isinstance(scaffold.get("evidence_quality_report"), dict) else {}
    scores = {
        "answers_decision_question": 1 if decision_question and _normalize(decision_question) in _normalize(memo_markdown) else 0,
        "clear_uncertainty": 1 if "**Confidence:**" in memo_markdown or "confidence" in memo_markdown.lower() else 0,
        "source_grounded": 1 if "## Sources" in memo_markdown else 0,
        "coherent_memo": 1 if coherence_report.get("status") == "pass" else 0,
        "bounded_when_sources_insufficient": 1 if not sufficiency.get("bounded_answer_required") or ("provided document" in memo_markdown.lower() or "current map" in memo_markdown.lower()) else 0,
        "evidence_quality_visible": 1 if not evidence_quality.get("weak_or_indirect_count") or any(term in memo_markdown.lower() for term in ("limited", "indirect", "weak", "uncertain")) else 0,
    }
    issues = _final_eval_issues(scores, coherence_report)
    status = "fail" if scores["answers_decision_question"] == 0 else "warning" if issues else "pass"
    return FinalBriefEvaluation(
        status=status,
        decision_question=decision_question,
        rubric_scores=scores,
        issues=issues,
        memo_path=memo_path,
    ).model_dump()


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


def _runtime_degraded_triggers(section_rewrite_report: dict[str, Any], reader_rewrite_report: dict[str, Any]) -> list[str]:
    triggers: list[str] = []
    if section_rewrite_report.get("status") in {"global_validation_failed_fallback", "no_sections_accepted"}:
        triggers.append(str(section_rewrite_report.get("status")))
    for section in section_rewrite_report.get("sections", []) if isinstance(section_rewrite_report.get("sections"), list) else []:
        if isinstance(section, dict) and section.get("structured_fallback"):
            triggers.append(f"structured_fallback:{section.get('title', '')}")
    if reader_rewrite_report.get("status") == "skipped_after_section_rewrite":
        triggers.append("reader_memo_rewrite_skipped")
    if reader_rewrite_report.get("status") == "skipped_prompt_backend":
        triggers.append("reader_memo_rewrite_prompt_backend")
    return triggers


def _final_eval_issues(scores: dict[str, int], coherence_report: dict[str, Any]) -> list[str]:
    labels = {
        "answers_decision_question": "memo does not visibly answer the decision question",
        "clear_uncertainty": "memo does not make confidence or uncertainty visible",
        "source_grounded": "memo lacks a final sources section",
        "coherent_memo": "memo coherence report has warnings or failures",
        "bounded_when_sources_insufficient": "memo does not visibly bound an insufficient-source answer",
        "evidence_quality_visible": "memo does not surface weak or indirect evidence quality limits",
    }
    issues = [message for key, message in labels.items() if scores.get(key) == 0]
    for issue in coherence_report.get("issues", []) if isinstance(coherence_report.get("issues"), list) else []:
        if isinstance(issue, dict) and issue.get("message"):
            issues.append(str(issue["message"]))
    return _dedupe(issues)


def _first_body_paragraph(markdown: str) -> str:
    for paragraph in re.split(r"\n\s*\n", markdown):
        stripped = paragraph.strip()
        if not stripped or stripped.startswith("#") or stripped.startswith("**Decision question:**"):
            continue
        return stripped
    return ""


def _repetition_count(markdown: str) -> int:
    seen: set[str] = set()
    repeated = 0
    for sentence in re.findall(r"[^.!?]+[.!?]", re.sub(r"\s+", " ", markdown)):
        normalized = _normalize(sentence)
        if len(normalized) < 40:
            continue
        if normalized in seen:
            repeated += 1
        seen.add(normalized)
    return repeated


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def _section_context_row(packet: dict[str, Any]) -> SectionContextAcceptanceRow:
    title = str(packet.get("title", "")).strip() or "Untitled Section"
    model_packet = packet.get("model_packet", {}) if isinstance(packet.get("model_packet"), dict) else {}
    raw_packet = packet.get("packet", {}) if isinstance(packet.get("packet"), dict) else {}
    owned = [row for row in model_packet.get("owned_evidence", []) if isinstance(row, dict)]
    if title.strip().lower() == "decision brief" and not owned:
        return SectionContextAcceptanceRow(
            section=title,
            status="ready",
            owned_card_count=0,
            card_budget_status="justified_exception",
            this_section_can_answer="Decision Brief is generated from the accepted body sections.",
            because="opening answer is generated last rather than from section-owned cards",
            context_risk_level="low",
        )
    obligations = [
        row for row in raw_packet.get("required_main_memo_obligations", []) if isinstance(row, dict)
    ]
    cruxes = [row for row in model_packet.get("canonical_cruxes", []) if isinstance(row, dict)]
    quantities = [row for row in model_packet.get("must_include_quantities", []) if isinstance(row, dict)]
    telemetry = [row for row in model_packet.get("telemetry_context", []) if isinstance(row, dict)]
    substantive = _is_substantive_section(title)
    issues: list[str] = []
    if substantive and not str(model_packet.get("section_thesis", "")).strip() and not str(packet.get("section_job", "")).strip():
        issues.append(f"{title}: missing section decision move")
    if substantive and not (owned or cruxes or quantities or obligations or telemetry):
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
    if not substantive or count == 0 and (cruxes or quantities or obligations or telemetry):
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
    can_answer = _section_can_answer(title, model_packet, owned, cruxes, quantities, obligations, telemetry)
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
        because=_because_for_section(owned, cruxes, quantities, obligations, telemetry),
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
    telemetry: list[dict[str, Any]],
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
    if telemetry:
        return f"{title} can bound the memo using pipeline telemetry and coverage diagnostics."
    return ""


def _because_for_section(
    owned: list[dict[str, Any]],
    cruxes: list[dict[str, Any]],
    quantities: list[dict[str, Any]],
    obligations: list[dict[str, Any]],
    telemetry: list[dict[str, Any]],
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
    if telemetry:
        parts.append(f"{len(telemetry)} telemetry substitute(s)")
    return ", ".join(parts)


def _generic_missing_categories(
    *,
    cards: list[dict[str, Any]],
    direct_cards: list[dict[str, Any]],
    anchored_cards: list[dict[str, Any]],
    existing_sufficiency: dict[str, Any],
    semantic_signals: dict[str, Any] | None = None,
) -> list[str]:
    semantic_signals = semantic_signals or {}
    missing: list[str] = []
    if not cards:
        missing.append("source_cards")
    if not anchored_cards:
        missing.append("source_anchors")
    if not direct_cards:
        missing.append("direct_answer_evidence")
    if not bool(semantic_signals.get("has_support")):
        missing.append("supporting_evidence")
    if not bool(semantic_signals.get("has_counterweight")):
        missing.append("counterweight_evidence")
    if not bool(semantic_signals.get("has_scope_boundary")):
        missing.append("scope_boundary_evidence")
    if not bool(semantic_signals.get("has_quantitative_anchor")):
        missing.append("quantitative_anchor")
    for slot in _string_list(existing_sufficiency.get("missing_expected_decision_slots")):
        missing.append(f"decision_slot:{slot}")
    for family in _string_list(existing_sufficiency.get("missing_expected_evidence_families")):
        missing.append(f"evidence_family:{family}")
    return _dedupe(missing)


def _semantic_sufficiency_signals(
    *,
    cards: list[dict[str, Any]],
    candidate_map: dict[str, Any],
    scaffold: dict[str, Any],
) -> dict[str, Any]:
    """Reconcile brittle card labels with richer map and briefing artifacts.

    This is intentionally conservative: deterministic code can confirm that a
    semantic category is present when multiple structured signals point to it,
    but it should not declare a category absent merely because one coarse label
    is missing.
    """

    card_roles = Counter(str(card.get("supports_challenges_or_scopes") or "uncategorized") for card in cards)
    card_text = "\n".join(str(card.get("source_quote_or_excerpt") or "") for card in cards).lower()
    relation_types = Counter(_relation_types(candidate_map))
    map_sufficiency = scaffold.get("map_sufficiency_report", {}) if isinstance(scaffold.get("map_sufficiency_report"), dict) else {}
    decision_model = scaffold.get("decision_model", {}) if isinstance(scaffold.get("decision_model"), dict) else {}
    decision_synthesis = scaffold.get("decision_synthesis_model", {}) if isinstance(scaffold.get("decision_synthesis_model"), dict) else {}
    argument_model = scaffold.get("argument_model", {}) if isinstance(scaffold.get("argument_model"), dict) else {}
    quantity_ledger = scaffold.get("quantity_ledger", {}) if isinstance(scaffold.get("quantity_ledger"), dict) else {}
    quantitative_anchors = scaffold.get("quantitative_anchors", []) if isinstance(scaffold.get("quantitative_anchors"), list) else []

    support_sources = _dedupe(
        [
            *_signal_sources_from_count("source_card_role:supports", card_roles.get("supports", 0)),
            *_signal_sources_from_count("relation:supports", relation_types.get("supports", 0)),
            *_signal_sources_from_list("decision_model:main_reasons", _listish(decision_model.get("main_reasons"))),
            *_signal_sources_from_list("argument_model:strongest_support", _listish(argument_model.get("strongest_support"))),
        ]
    )
    counter_sources = _dedupe(
        [
            *_signal_sources_from_count("source_card_role:challenges", card_roles.get("challenges", 0)),
            *_signal_sources_from_count("relation:challenges", relation_types.get("challenges", 0)),
            *_signal_sources_from_count("relation:in_tension_with", relation_types.get("in_tension_with", 0)),
            *_signal_sources_from_list("decision_model:strongest_counterarguments", _listish(decision_model.get("strongest_counterarguments"))),
            *_signal_sources_from_list("decision_synthesis:tensions", _listish(decision_synthesis.get("tensions"))),
            *_signal_sources_from_list("argument_model:strongest_counterarguments", _listish(argument_model.get("strongest_counterarguments"))),
            *_signal_sources_from_text("source_text:counter_signal", card_text, _counter_signal_terms()),
        ]
    )
    scope_sources = _dedupe(
        [
            *_signal_sources_from_count("source_card_role:scopes", card_roles.get("scopes", 0)),
            *_signal_sources_from_count("relation:refines", relation_types.get("refines", 0)),
            *_signal_sources_from_count("relation:depends_on", relation_types.get("depends_on", 0)),
            *_signal_sources_from_list("decision_model:tension_resolutions", _listish(decision_model.get("tension_resolutions"))),
            *_signal_sources_from_list("argument_model:scope_boundaries", _listish(argument_model.get("scope_boundaries"))),
        ]
    )
    quantity_sources = _dedupe(
        [
            *_signal_sources_from_count("source_card:quantity_values", sum(1 for card in cards if card.get("quantity_values"))),
            *_signal_sources_from_count("quantity_ledger:quantity_count", _int_value(quantity_ledger.get("quantity_count"))),
            *_signal_sources_from_count("scaffold:quantitative_anchors", len(quantitative_anchors)),
            *_signal_sources_from_list("argument_model:quantitative_anchors", _listish(argument_model.get("quantitative_anchors"))),
        ]
    )

    # The older map-sufficiency report is still useful as a missing-slot signal,
    # but it should not override stronger positive evidence found above.
    missing = set(_string_list(map_sufficiency.get("missing_expected_evidence_families")))
    if "counterweight_evidence" in missing and counter_sources:
        missing.remove("counterweight_evidence")

    report = {
        "schema_id": "semantic_sufficiency_signal_report_v1",
        "method": "reconcile_source_card_labels_with_relations_decision_artifacts_and_quantities",
        "source_card_role_counts": dict(card_roles),
        "relation_type_counts": dict(relation_types),
        "support_signal_sources": support_sources,
        "counterweight_signal_sources": counter_sources,
        "crux_signal_sources": _signal_sources_from_count("relation:crux_for", relation_types.get("crux_for", 0)),
        "scope_signal_sources": scope_sources,
        "quantitative_signal_sources": quantity_sources,
        "overridden_missing_evidence_families": sorted(set(_string_list(map_sufficiency.get("missing_expected_evidence_families"))) - missing),
    }
    return {
        "has_support": bool(support_sources),
        "has_counterweight": bool(counter_sources),
        "has_scope_boundary": bool(scope_sources),
        "has_quantitative_anchor": bool(quantity_sources),
        "report": report,
    }


def _relation_types(candidate_map: dict[str, Any]) -> list[str]:
    relations = candidate_map.get("relations", [])
    if not isinstance(relations, list):
        return []
    return [str(relation.get("relation_type") or "").strip() for relation in relations if isinstance(relation, dict) and str(relation.get("relation_type") or "").strip()]


def _counter_signal_terms() -> tuple[str, ...]:
    return (
        "higher risk",
        "increased risk",
        "increase in risk",
        "positive association",
        "mortality",
        "adverse",
        "counterargument",
        "counterevidence",
        "in tension",
    )


def _signal_sources_from_count(label: str, count: int) -> list[str]:
    return [f"{label}:{count}"] if count > 0 else []


def _signal_sources_from_list(label: str, values: list[Any]) -> list[str]:
    return [f"{label}:{len(values)}"] if values else []


def _signal_sources_from_text(label: str, text: str, terms: tuple[str, ...]) -> list[str]:
    hits = [term for term in terms if term in text]
    return [f"{label}:{','.join(hits[:4])}"] if hits else []


def _listish(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


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
        for key in ("role", "evidence_role", "section", "relation_type", "claim_type", "tags", "evidence_slots")
    ).lower()
    text = _claim_text(claim).lower()
    if any(term in values for term in ("challenge", "counter", "conflict", "tension")):
        return "challenges"
    if any(term in text for term in ("higher risk", "increased risk", "increase in risk", "worse outcome", "harm", "adverse")):
        return "challenges"
    if any(term in values for term in ("scope", "limit", "boundary", "exception", "constraint", "crux")):
        return "scopes"
    if any(term in values for term in ("support", "main", "conclusion")):
        return "supports"
    return "uncategorized"


def _claim_relevance_score(claim: dict[str, Any]) -> int:
    explicit = _int_value(claim.get("decision_relevance_score") or claim.get("relevance_score") or claim.get("score"))
    if explicit:
        return explicit
    relevance = str(claim.get("question_relevance") or claim.get("relevance") or "").lower()
    if "direct" in relevance:
        return 8
    if any(term in relevance for term in ("partial", "related", "moderate")):
        return 5
    if any(term in relevance for term in ("indirect", "background", "low")):
        return 2
    if claim.get("relevance_rationale"):
        return 4
    return 0


def _joined_evidence_slots(claim: dict[str, Any]) -> str:
    return "_".join(_string_list(claim.get("evidence_slots")))


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
