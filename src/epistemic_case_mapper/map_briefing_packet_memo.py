from __future__ import annotations

import ast
import json
import re
from pathlib import Path
from typing import Any

from epistemic_case_mapper.io import write_json, write_markdown


def build_packet_memo_plan(packet: dict[str, Any]) -> dict[str, Any]:
    bundles = _bundle_lookup(packet)
    retain = _retain_lookup(packet)
    section_views = []
    for view in packet.get("section_views", []) if isinstance(packet.get("section_views"), list) else []:
        if not isinstance(view, dict):
            continue
        section_views.append(
            {
                "section": view.get("section"),
                "section_job": view.get("section_job"),
                "primary_bundles": _bundles_for_ids(bundles, view.get("primary_bundle_ids")),
                "contrast_bundles": _bundles_for_ids(bundles, view.get("contrast_bundle_ids")),
                "boundary_bundles": _bundles_for_ids(bundles, view.get("boundary_bundle_ids")),
                "context_bundles": _bundles_for_ids(bundles, view.get("context_bundle_ids")),
                "must_retain_items": _retain_for_ids(retain, view.get("must_retain_item_ids")),
            }
        )
    reader_packet = build_reader_facing_packet(packet)
    return {
        "schema_id": "packet_memo_plan_v1",
        "decision_question": packet.get("decision_question"),
        "answer_frame": packet.get("answer_frame", {}),
        "section_views": section_views,
        "source_trail": packet.get("source_trail", []),
        "coverage_report": packet.get("coverage_report", {}),
        "reader_facing_packet": reader_packet,
    }


def build_reader_facing_packet(packet: dict[str, Any]) -> dict[str, Any]:
    """Project the internal packet into prose-ready evidence context.

    The internal packet remains the source of truth for validation. This view is
    intentionally smaller and avoids bundle IDs, claim IDs, repair reports, and
    required-term ledgers so generation starts from analyst-readable material.
    """

    cards = [_reader_card(row) for row in _ranked_bundles(packet)]
    cards = [card for card in cards if card.get("statement")]
    support_roles = {"strongest_support", "quantitative_anchor", "mechanism"}
    limit_roles = {"counterweight", "scope_boundary"}
    return {
        "schema_id": "reader_facing_decision_packet_v1",
        "decision_question": str(packet.get("decision_question") or "").strip(),
        "answer": _clean_answer_frame(packet.get("answer_frame", {})),
        "evidence_cards": _with_card_ids("evidence", [card for card in cards if card.get("role") in support_roles][:10]),
        "counterweight_cards": _with_card_ids("counterweight", [card for card in cards if card.get("role") in limit_roles][:8]),
        "decision_cruxes": _with_card_ids("crux", _decision_crux_cards(cards, packet)[:6]),
        "quantitative_anchors": _with_card_ids("quantitative", [card for card in cards if card.get("quantities")][:8]),
        "source_trail": _reader_source_trail(packet),
        "reader_limits": _reader_limits(packet),
    }


def build_reader_facing_packet_synthesis_prompt(reader_packet: dict[str, Any]) -> str:
    return (
        "You are a senior decision analyst writing for a thoughtful human decision-maker.\n"
        "Write a polished, decision-ready briefing memo from the reader-facing evidence packet below.\n"
        "Use the packet as the evidence record, but synthesize across rows into natural prose.\n\n"
        "Rules:\n"
        "- Answer the decision question directly.\n"
        "- Preserve load-bearing numbers, uncertainty, exceptions, and source labels.\n"
        "- Every evidence paragraph or bullet must include bracketed source labels copied from the packet's `source` fields.\n"
        "- Include the exact decision question near the top of the memo.\n"
        "- Do not add parenthetical examples or named conditions unless the same example or condition appears in an evidence card.\n"
        "- Do not add facts, sources, populations, causal interpretations, or recommendations beyond the packet.\n"
        "- Do not mention packet schema, IDs, validation, repair reports, or internal pipeline status.\n"
        "- Write like an analyst, not like a checklist renderer.\n\n"
        "Use this memo shape unless the evidence clearly calls for a small adjustment:\n"
        "## Decision Brief\n"
        "## What the Evidence Supports\n"
        "## What Limits the Inference\n"
        "## Decision Cruxes\n"
        "## Sources\n\n"
        "Reader-facing evidence packet:\n"
        f"{json.dumps(reader_packet, indent=2, ensure_ascii=False)}\n"
    )


def render_packet_first_draft(memo_plan: dict[str, Any]) -> str:
    reader_packet = memo_plan.get("reader_facing_packet")
    if isinstance(reader_packet, dict):
        return render_reader_facing_packet_draft(reader_packet)
    return _render_legacy_packet_first_draft(memo_plan)


def render_reader_facing_packet_draft(reader_packet: dict[str, Any]) -> str:
    question = str(reader_packet.get("decision_question") or "").strip()
    answer = reader_packet.get("answer", {}) if isinstance(reader_packet.get("answer"), dict) else {}
    lines = [
        "# Decision Briefing Memo",
        "",
        f"**Decision question:** {question or 'not specified'}",
        "",
        "## Decision Brief",
        "",
        _reader_bottom_line(answer),
    ]
    confidence = str(answer.get("confidence") or "").strip()
    if confidence:
        lines.extend(["", f"**Confidence:** {confidence}"])
    support = _reader_card_section(
        reader_packet.get("evidence_cards"),
        empty="The packet does not identify a clear support case beyond the bottom-line answer.",
    )
    if support:
        lines.extend(["", "## What the Evidence Supports", "", support])
    limits = _reader_card_section(
        reader_packet.get("counterweight_cards"),
        empty="The packet does not identify major counterweights beyond the uncertainty already named.",
    )
    if limits:
        lines.extend(["", "## What Limits the Inference", "", limits])
    cruxes = _reader_card_section(reader_packet.get("decision_cruxes"), empty="")
    if cruxes:
        lines.extend(["", "## Decision Cruxes", "", cruxes])
    reader_limits = _string_list(reader_packet.get("reader_limits"))
    if reader_limits:
        lines.extend(["", "## Evidence Gaps and Scope Limits", "", "\n".join(f"- {item}" for item in reader_limits[:4])])
    sources = _reader_sources_section(reader_packet)
    if sources:
        lines.extend(["", "## Sources", "", sources])
    return _clean_markdown("\n".join(lines).rstrip() + "\n")


def _render_legacy_packet_first_draft(memo_plan: dict[str, Any]) -> str:
    question = str(memo_plan.get("decision_question") or "").strip()
    answer = memo_plan.get("answer_frame", {}) if isinstance(memo_plan.get("answer_frame"), dict) else {}
    lines = [
        "# Decision Briefing Memo",
        "",
        f"**Decision question:** {question or 'not specified'}",
        "",
        "## Decision Brief",
        "",
        _bottom_line(answer),
    ]
    confidence = str(answer.get("confidence") or "").strip()
    if confidence:
        lines.extend(["", f"**Confidence:** {confidence}"])
    for section in memo_plan.get("section_views", []) if isinstance(memo_plan.get("section_views"), list) else []:
        title = str(section.get("section") or "").strip()
        if not title or title == "Decision Brief":
            continue
        body = _section_body(section)
        if body:
            lines.extend(["", f"## {title}", "", body])
    sources = _sources_section(memo_plan)
    if sources:
        lines.extend(["", "## Sources", "", sources])
    return _clean_markdown("\n".join(lines).rstrip() + "\n")


def write_packet_first_artifacts(
    *,
    artifacts: Path,
    packet: dict[str, Any],
    backend: str = "prompt",
    backend_timeout: int | None = None,
    backend_retries: int = 0,
) -> dict[str, Any]:
    memo_plan = build_packet_memo_plan(packet)
    from epistemic_case_mapper.map_briefing_reader_packet_verbalization import run_reader_packet_verbalization

    verbalization_result = run_reader_packet_verbalization(
        memo_plan.get("reader_facing_packet", {}) if isinstance(memo_plan.get("reader_facing_packet"), dict) else {},
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
    )
    memo_plan["reader_facing_packet"] = verbalization_result["reader_packet"]
    draft = render_packet_first_draft(memo_plan)
    memo_plan_path = artifacts / "memo_plan.json"
    reader_packet_path = artifacts / "reader_facing_packet.json"
    synthesis_prompt_path = artifacts / "reader_facing_packet_synthesis_prompt.txt"
    verbalization_prompt_path = artifacts / "reader_packet_verbalization_prompt.txt"
    verbalization_raw_path = artifacts / "reader_packet_verbalization_raw.txt"
    verbalization_report_path = artifacts / "reader_packet_verbalization_report.json"
    draft_path = artifacts / "packet_first_draft.md"
    acceptance_path = artifacts / "section_context_acceptance_report.json"
    write_json(memo_plan_path, memo_plan)
    write_json(reader_packet_path, memo_plan.get("reader_facing_packet", {}))
    write_markdown(verbalization_prompt_path, str(verbalization_result.get("prompt") or ""))
    write_markdown(verbalization_raw_path, str(verbalization_result.get("raw") or ""))
    write_json(verbalization_report_path, verbalization_result.get("report", {}))
    write_markdown(
        synthesis_prompt_path,
        build_reader_facing_packet_synthesis_prompt(
            memo_plan.get("reader_facing_packet", {}) if isinstance(memo_plan.get("reader_facing_packet"), dict) else {}
        ),
    )
    write_markdown(draft_path, draft)
    write_json(acceptance_path, _packet_first_acceptance_report(memo_plan))
    return {
        "memo_plan": memo_plan,
        "draft": draft,
        "memo_plan_path": memo_plan_path,
        "reader_facing_packet_path": reader_packet_path,
        "reader_facing_packet_synthesis_prompt_path": synthesis_prompt_path,
        "reader_packet_verbalization_prompt_path": verbalization_prompt_path,
        "reader_packet_verbalization_raw_path": verbalization_raw_path,
        "reader_packet_verbalization_report_path": verbalization_report_path,
        "packet_first_draft_path": draft_path,
        "section_context_acceptance_report_path": acceptance_path,
        "report": {
            "schema_id": "packet_first_memo_plan_report_v1",
            "status": "ready" if memo_plan.get("section_views") else "warning",
            "section_count": len(memo_plan.get("section_views", [])),
            "draft_word_count": len(draft.split()),
            "reader_packet_verbalization_status": verbalization_result.get("report", {}).get("status"),
            "reader_packet_verbalization_accepted_count": verbalization_result.get("report", {}).get("accepted_count", 0),
            "reader_packet_card_count": len(
                (memo_plan.get("reader_facing_packet", {}) if isinstance(memo_plan.get("reader_facing_packet"), dict) else {}).get(
                    "evidence_cards", []
                )
            ),
        },
    }


def packet_first_section_rewrite_result(plan_result: dict[str, Any]) -> dict[str, Any]:
    """Return the compatibility shape expected by final-output diagnostics."""

    report = {
        "schema_id": "section_rewrite_report_v1",
        "status": "skipped_packet_first_default",
        "accepted_section_count": 0,
        "section_count": 0,
        "sections": [],
        "whole_validation_status": "not_run",
        "packet_first": True,
        "memo_plan_report": plan_result.get("report", {}),
        "section_context_acceptance_status": "ready",
    }
    return {
        "memo": plan_result["draft"],
        "report": report,
        "section_packets_path": None,
        "section_context_acceptance_report_path": plan_result.get("section_context_acceptance_report_path"),
    }


def _packet_first_acceptance_report(memo_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": "section_context_acceptance_report_v1",
        "status": "ready",
        "mode": "packet_first_memo_plan",
        "section_count": len(memo_plan.get("section_views", [])),
        "issues": [],
    }


def _bottom_line(answer: dict[str, Any]) -> str:
    default = str(answer.get("default_answer") or "").strip()
    scope = str(answer.get("scope") or "").strip()
    uncertainty = str(answer.get("main_uncertainty") or "").strip()
    parts = []
    if default:
        parts.append(default)
    if scope:
        parts.append(f"Scope: {scope}")
    if uncertainty:
        parts.append(f"Main uncertainty: {uncertainty}")
    return " ".join(parts) if parts else "The packet does not yet contain a settled answer frame."


def _reader_bottom_line(answer: dict[str, Any]) -> str:
    thesis = str(answer.get("thesis") or "").strip()
    scope = str(answer.get("scope") or "").strip()
    uncertainty = str(answer.get("main_uncertainty") or "").strip()
    parts = [thesis] if thesis else []
    if scope and scope.lower() not in (thesis.lower() if thesis else ""):
        parts.append(f"Scope: {scope}")
    if uncertainty:
        parts.append(f"Main uncertainty: {uncertainty}")
    return " ".join(parts) if parts else "The packet does not yet contain a settled answer frame."


def _section_body(section: dict[str, Any]) -> str:
    paragraphs = []
    job = str(section.get("section_job") or "").strip()
    if job:
        paragraphs.append(job)
    primary = _bundle_sentences(section.get("primary_bundles"), prefix="Load-bearing evidence")
    contrast = _bundle_sentences(section.get("contrast_bundles"), prefix="Counterweight")
    boundary = _bundle_sentences(section.get("boundary_bundles"), prefix="Boundary")
    context = _bundle_sentences(section.get("context_bundles"), prefix="Context")
    retain = _retain_sentences(section.get("must_retain_items"))
    for block in (primary, contrast, boundary, context, retain):
        if block:
            paragraphs.append(block)
    return "\n\n".join(paragraphs)


def _bundle_sentences(value: Any, *, prefix: str) -> str:
    rows = [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
    sentences = []
    for row in rows[:5]:
        claim = str(row.get("claim") or "").strip()
        if not claim:
            continue
        source = _source_label(row)
        quantities = ", ".join(_string_list(row.get("quantity_values"))[:3])
        why = str(row.get("why_it_matters") or "").strip()
        limit = "; ".join(_string_list(row.get("limits"))[:2])
        sentence = f"- **{prefix}:** {claim}"
        if quantities:
            sentence += f" Key quantity: {quantities}."
        if source:
            sentence += f" Source: {source}."
        if why:
            sentence += f" Why it matters: {why}"
        if limit:
            sentence += f" Limit: {limit}."
        sentences.append(sentence)
    return "\n".join(sentences)


def _retain_sentences(value: Any) -> str:
    rows = [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
    if not rows:
        return ""
    sentences = []
    for row in rows[:6]:
        statement = str(row.get("statement") or "").strip()
        terms = ", ".join(_string_list(row.get("required_terms"))[:4])
        if statement:
            text = f"- **Must retain:** {statement}"
            if terms:
                text += f" Required terms: {terms}."
            sentences.append(text)
    return "\n".join(sentences)


def _sources_section(memo_plan: dict[str, Any]) -> str:
    rows = [row for row in memo_plan.get("source_trail", []) if isinstance(row, dict)]
    lines = []
    for row in rows:
        if not row.get("appears_in_packet"):
            continue
        label = str(row.get("source_label") or row.get("source_id") or "").strip()
        used_for = ", ".join(_string_list(row.get("used_for")))
        if label:
            lines.append(f"- {label}" + (f" ({used_for})" if used_for else ""))
    return "\n".join(lines)


def _ranked_bundles(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [
        row
        for row in packet.get("evidence_bundles", [])
        if isinstance(row, dict) and not row.get("synthesis_suppressed") and str(row.get("claim") or "").strip()
    ]
    return sorted(rows, key=_bundle_rank)


def _bundle_rank(row: dict[str, Any]) -> tuple[int, int, str]:
    role_rank = {
        "quantitative_anchor": 0,
        "strongest_support": 1,
        "counterweight": 2,
        "scope_boundary": 3,
        "decision_crux": 4,
        "mechanism": 5,
        "context": 6,
    }.get(str(row.get("decision_role") or ""), 8)
    weight_rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(str(row.get("weight") or row.get("importance") or ""), 2)
    return (role_rank, weight_rank, str(row.get("claim") or ""))


def _reader_card(row: dict[str, Any]) -> dict[str, Any]:
    statement = _clean_reader_statement(str(row.get("claim") or "").strip())
    if not _statement_is_reader_usable(statement, row):
        return {}
    return _drop_empty(
        {
            "role": str(row.get("decision_role") or "context").strip(),
            "statement": statement,
            "source": _source_label(row),
            "quantities": _string_list(row.get("quantity_values"))[:4],
            "interpretation": _clean_interpretation(str(row.get("why_it_matters") or row.get("section_use") or "").strip()),
            "limits": [_clean_reader_statement(item) for item in _string_list(row.get("limits"))[:3]],
        }
    )


def _with_card_ids(prefix: str, cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for index, card in enumerate(cards, start=1):
        copied = dict(card)
        copied["card_id"] = f"{prefix}_{index:02d}"
        result.append(copied)
    return result


def _decision_crux_cards(cards: list[dict[str, Any]], packet: dict[str, Any]) -> list[dict[str, Any]]:
    cruxes = [card for card in cards if card.get("role") == "decision_crux" and _statement_is_reader_usable(str(card.get("statement", "")), {})]
    if cruxes:
        return cruxes
    selected: list[dict[str, Any]] = []
    for card in cards:
        text = " ".join([str(card.get("statement", "")), str(card.get("interpretation", ""))]).lower()
        if card.get("role") in {"counterweight", "scope_boundary", "quantitative_anchor"} and any(
            term in text
            for term in (
                "would change",
                "crux",
                "depends",
                "uncertain",
                "heterogeneity",
                "subgroup",
                "population",
                "confounding",
                "adjusted",
                "proxy",
                "surrogate",
                "mechanism",
                "marker",
            )
        ):
            selected.append(_crux_from_card(card))
    if selected:
        return selected[:4]
    answer = packet.get("answer_frame", {}) if isinstance(packet.get("answer_frame"), dict) else {}
    uncertainty = str(answer.get("main_uncertainty") or "").strip()
    if uncertainty:
        return [{"role": "decision_crux", "statement": _reader_facing_uncertainty(uncertainty)}]
    return []


def _crux_from_card(card: dict[str, Any]) -> dict[str, Any]:
    statement = str(card.get("statement") or "").strip()
    text = " ".join([statement, str(card.get("interpretation") or "")]).lower()
    if any(term in text for term in ("uncertain", "confidence interval", "includes the usual null", "includes the null")):
        crux = f"Whether the uncertainty around this estimate should lower confidence in the default answer: {statement}"
    elif any(term in text for term in ("biomarker", "surrogate", "mechanism", "proxy", "marker")):
        crux = f"How much weight to place on mechanism or proxy evidence relative to direct outcome evidence: {statement}"
    elif any(term in text for term in ("subgroup", "population", "people with", "patients with")):
        crux = f"Whether a subgroup or population boundary should change the general recommendation: {statement}"
    elif any(term in text for term in ("confounding", "adjusted", "non-significant", "correlat")):
        crux = f"Whether adjustment or confounding explains the apparent association: {statement}"
    else:
        crux = f"Whether this evidence should materially change the default answer: {statement}"
    return _drop_empty(
        {
            "role": "decision_crux",
            "statement": _clean_reader_statement(crux),
            "source": card.get("source"),
            "quantities": card.get("quantities"),
            "interpretation": card.get("interpretation"),
        }
    )


def _clean_answer_frame(value: Any) -> dict[str, str]:
    answer = value if isinstance(value, dict) else {}
    default = _decode_answer_value(answer.get("default_answer"))
    if isinstance(default, dict):
        thesis = str(default.get("current_read") or default.get("primary_answer") or default.get("default_read") or default.get("classification") or "").strip()
    else:
        thesis = _extract_current_read_from_stringified_answer(str(default or "").strip())
    return _drop_empty(
        {
            "thesis": _clean_thesis(_clean_reader_statement(thesis)),
            "confidence": str(answer.get("confidence") or "").strip(),
            "scope": _clean_reader_statement(str(answer.get("scope") or "").strip()),
            "main_uncertainty": _reader_facing_uncertainty(str(answer.get("main_uncertainty") or "").strip()),
        }
    )


def _decode_answer_value(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text.startswith("{"):
        return text
    try:
        parsed = ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return text
    return parsed if isinstance(parsed, dict) else text


def _extract_current_read_from_stringified_answer(text: str) -> str:
    if not text:
        return ""
    match = re.search(r"['\"]current_read['\"]\s*:\s*['\"](?P<value>.*?)(?<!\\)['\"]\s*,", text)
    if match:
        return match.group("value").strip()
    match = re.search(r"['\"]classification['\"]\s*:\s*['\"](?P<value>[^'\"]+)", text)
    if match:
        return match.group("value").replace("_", " ").strip()
    return text


def _clean_thesis(text: str) -> str:
    cleaned = text.strip()
    cleaned = re.sub(r"^state that\s+", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(r"^say that\s+", "", cleaned, flags=re.IGNORECASE).strip()
    cleaned = re.sub(
        r",?\s+and separate those conditions from the general case\.?$",
        "; those conditions should be separated from the general case.",
        cleaned,
        flags=re.IGNORECASE,
    )
    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]
    return cleaned


def _reader_source_trail(packet: dict[str, Any]) -> list[dict[str, Any]]:
    rows = [row for row in packet.get("source_trail", []) if isinstance(row, dict) and row.get("appears_in_packet")]
    result = []
    for row in rows:
        label = str(row.get("source_label") or row.get("source_id") or "").strip()
        if not label:
            continue
        result.append(_drop_empty({"source": label, "used_for": _string_list(row.get("used_for"))[:5]}))
    return result


def _reader_limits(packet: dict[str, Any]) -> list[str]:
    coverage = packet.get("coverage_report", {}) if isinstance(packet.get("coverage_report"), dict) else {}
    limits: list[str] = []
    if coverage.get("high_priority_omitted_count"):
        limits.append("Some high-priority evidence was not included in the compact packet; treat the memo as a prioritized synthesis rather than an exhaustive review.")
    if coverage.get("source_label_missing_count"):
        limits.append("Some evidence lacked clean source labels in the packet.")
    if coverage.get("packet_quality_repair_warning_count"):
        limits.append("Some extracted evidence was too malformed for synthesis and was left out of the reader-facing evidence packet.")
    return _dedupe(limits)


def _reader_card_section(value: Any, *, empty: str) -> str:
    rows = [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []
    if not rows:
        return empty
    return "\n".join(f"- {_reader_card_sentence(row)}" for row in rows[:8])


def _reader_card_sentence(row: dict[str, Any]) -> str:
    prose = str(row.get("prose") or "").strip()
    if prose:
        return _clean_reader_statement(prose)
    statement = str(row.get("statement") or "").strip()
    quantities = ", ".join(_string_list(row.get("quantities"))[:3])
    source = str(row.get("source") or "").strip()
    interpretation = str(row.get("interpretation") or "").strip()
    limits = "; ".join(_string_list(row.get("limits"))[:2])
    text = statement
    if quantities and quantities not in text:
        text += f" Key quantities: {quantities}."
    if interpretation and not _text_contains_substance(text, interpretation):
        text += f" {interpretation}"
    if limits:
        text += f" Limit: {limits}."
    if source:
        text += f" [{source}]"
    return _clean_reader_statement(text)


def _reader_sources_section(reader_packet: dict[str, Any]) -> str:
    rows = [row for row in reader_packet.get("source_trail", []) if isinstance(row, dict)]
    lines = []
    for row in rows:
        source = str(row.get("source") or "").strip()
        used_for = ", ".join(_string_list(row.get("used_for")))
        if source:
            lines.append(f"- {source}" + (f" ({used_for})" if used_for else ""))
    return "\n".join(lines)


def _clean_reader_statement(text: str) -> str:
    text = re.sub(r"\s+", " ", str(text)).strip()
    text = re.sub(r"^[•*\-]\s*", "", text)
    text = re.sub(r"\bAppendix-only extraction with low atomicity or low decision relevance; use only as source context\.?", "", text)
    text = re.sub(r"\bMap quality status:\s*[^.]+\.?", "", text)
    text = text.replace("..", ".").strip(" ;")
    return text


def _clean_interpretation(text: str) -> str:
    cleaned = _clean_reader_statement(text)
    low = cleaned.lower()
    if not cleaned:
        return ""
    if "provides scope evidence with relevance" in low or "provides context evidence with relevance" in low:
        return ""
    if cleaned in {
        "This is high-priority support for the current answer.",
        "This limits or challenges the current answer.",
    }:
        return ""
    if low.startswith("relation type:"):
        return ""
    return cleaned


def _statement_is_reader_usable(statement: str, row: dict[str, Any]) -> bool:
    text = statement.strip()
    low = text.lower()
    if len(text) < 24:
        return False
    if any(marker in low for marker in ("accessed january", "https://", "www.", "nutrient data laboratory", "release 28")):
        return False
    if any(marker in low for marker in ("challenges the assertion in", "relation type:", "provides scope evidence with relevance")):
        return False
    if any(marker in low for marker in ("appendix-only extraction", "low atomicity", "hhs vulnerability disclosure")):
        return False
    if text in {"0%", "None"}:
        return False
    limits = " ".join(_string_list(row.get("limits"))).lower()
    if "off_question_risk" in limits:
        return False
    relevance = str(row.get("decision_relevance_score") or row.get("relevance") or "").strip()
    if relevance in {"0", "0/10"}:
        return False
    return True


def _reader_facing_uncertainty(text: str) -> str:
    cleaned = _clean_reader_statement(text)
    if not cleaned:
        return ""
    if "Accepted " in cleaned and "claims" in cleaned:
        return "The packet is usable but should be read as a prioritized synthesis; missing evidence slots are treated as gaps, not as negative evidence."
    if len(cleaned) > 260:
        return cleaned[:257].rstrip() + "..."
    return cleaned


def _text_contains_substance(text: str, other: str) -> bool:
    terms = [term for term in re.findall(r"[A-Za-z0-9%]+", other.lower()) if len(term) > 3]
    if not terms:
        return False
    base = text.lower()
    return sum(1 for term in terms if term in base) >= min(3, len(terms))


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", [], {}, None)}


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for item in items:
        text = str(item).strip()
        key = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        if not text or key in seen:
            continue
        seen.add(key)
        result.append(text)
    return result


def _bundle_lookup(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("bundle_id")): row
        for row in packet.get("evidence_bundles", [])
        if isinstance(row, dict) and row.get("bundle_id") and not row.get("synthesis_suppressed")
    }


def _retain_lookup(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("item_id")): row
        for row in packet.get("must_retain_ledger", [])
        if isinstance(row, dict) and row.get("item_id") and not row.get("synthesis_suppressed")
    }


def _bundles_for_ids(lookup: dict[str, dict[str, Any]], ids: Any) -> list[dict[str, Any]]:
    return [lookup[item] for item in _string_list(ids) if item in lookup]


def _retain_for_ids(lookup: dict[str, dict[str, Any]], ids: Any) -> list[dict[str, Any]]:
    return [lookup[item] for item in _string_list(ids) if item in lookup]


def _source_label(row: dict[str, Any]) -> str:
    labels = _string_list(row.get("source_labels"))
    return ", ".join(labels[:2])


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    return [text] if text else []


def _clean_markdown(text: str) -> str:
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"
