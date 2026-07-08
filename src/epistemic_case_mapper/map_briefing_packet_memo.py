from __future__ import annotations

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
    return {
        "schema_id": "packet_memo_plan_v1",
        "decision_question": packet.get("decision_question"),
        "answer_frame": packet.get("answer_frame", {}),
        "section_views": section_views,
        "source_trail": packet.get("source_trail", []),
        "coverage_report": packet.get("coverage_report", {}),
    }


def render_packet_first_draft(memo_plan: dict[str, Any]) -> str:
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
) -> dict[str, Any]:
    memo_plan = build_packet_memo_plan(packet)
    draft = render_packet_first_draft(memo_plan)
    memo_plan_path = artifacts / "memo_plan.json"
    draft_path = artifacts / "packet_first_draft.md"
    acceptance_path = artifacts / "section_context_acceptance_report.json"
    write_json(memo_plan_path, memo_plan)
    write_markdown(draft_path, draft)
    write_json(acceptance_path, _packet_first_acceptance_report(memo_plan))
    return {
        "memo_plan": memo_plan,
        "draft": draft,
        "memo_plan_path": memo_plan_path,
        "packet_first_draft_path": draft_path,
        "section_context_acceptance_report_path": acceptance_path,
        "report": {
            "schema_id": "packet_first_memo_plan_report_v1",
            "status": "ready" if memo_plan.get("section_views") else "warning",
            "section_count": len(memo_plan.get("section_views", [])),
            "draft_word_count": len(draft.split()),
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


def _bundle_lookup(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("bundle_id")): row
        for row in packet.get("evidence_bundles", [])
        if isinstance(row, dict) and row.get("bundle_id")
    }


def _retain_lookup(packet: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(row.get("item_id")): row
        for row in packet.get("must_retain_ledger", [])
        if isinstance(row, dict) and row.get("item_id")
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
