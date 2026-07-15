from __future__ import annotations

import json
import re
from typing import Any, Callable

from epistemic_case_mapper.map_briefing_memo_polish_diagnostics import prose_quality_diagnostics
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import list_value as _list
from epistemic_case_mapper.map_briefing_memo_ready_polish_guardrails import build_memo_ready_final_polish_guardrails
from epistemic_case_mapper.map_briefing_source_identity import (
    project_source_text_to_ids_for_model,
    project_sources_to_ids_for_model,
    replace_source_aliases_with_ids,
    source_id_alias_map,
    source_id_registry_for_model,
)
from epistemic_case_mapper.model_backends import ModelBackendResult, model_parallelism, run_model_backend, run_parallel


ModelRunner = Callable[..., ModelBackendResult]


def split_memo_into_polishable_paragraphs(memo: str) -> list[dict[str, Any]]:
    """Return paragraph rows that can be safely targeted by exact replacement."""
    body = _strip_sources_section(str(memo or ""))
    blocks = [block for block in re.split(r"\n\s*\n", body.strip()) if block.strip()]
    rows: list[dict[str, Any]] = []
    current_heading = "Opening"
    for index, block in enumerate(blocks, start=1):
        stripped = block.strip()
        heading_match = re.match(r"^(#{1,3})\s+(.+?)\s*$", stripped)
        if heading_match and "\n" not in stripped:
            if heading_match.group(1) != "#":
                current_heading = heading_match.group(2).strip()
            continue
        leading_heading = re.match(r"^(#{2,3})\s+(.+?)\s*\n", stripped)
        if leading_heading:
            current_heading = leading_heading.group(2).strip()
        if stripped.startswith("# "):
            current_heading = "Opening"
        rows.append(
            {
                "paragraph_id": f"p{index:03d}",
                "paragraph_index": index,
                "section_heading": current_heading,
                "markdown": stripped,
                "issues": _paragraph_polish_issues(stripped),
            }
        )
    return rows


def collect_parallel_paragraph_memo_polish_proposals(
    memo: str,
    packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    max_paragraphs: int = 5,
    run_model: ModelRunner = run_model_backend,
) -> dict[str, Any]:
    paragraphs = split_memo_into_polishable_paragraphs(memo)
    selected = _select_paragraphs_for_polish(paragraphs, max_paragraphs=max_paragraphs)
    source_trail = _list(packet.get("source_trail"))
    known_source_ids = _known_source_ids(packet)

    def run_paragraph(paragraph: dict[str, Any]) -> dict[str, Any]:
        prompt = build_paragraph_memo_polish_prompt(
            paragraph,
            paragraphs=paragraphs,
            packet=packet,
            source_trail=source_trail,
        )
        report = {
            "paragraph_id": paragraph.get("paragraph_id"),
            "paragraph_index": paragraph.get("paragraph_index"),
            "section_heading": paragraph.get("section_heading"),
            "prompt": prompt,
            "raw": "",
            "replacement_markdown": "",
            "reason": "",
            "parse_report": {},
            "accepted_candidate": False,
            "issues": [],
        }
        try:
            result = run_model(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
        except RuntimeError as exc:
            report["parse_report"] = {"status": "backend_error", "issues": [str(exc)]}
            report["issues"] = ["backend_error", str(exc)]
            return report
        raw = result.text
        parse = parse_paragraph_memo_polish_response(raw)
        replacement = str(parse.get("paragraph_markdown") or "").strip()
        issues = _paragraph_candidate_issues(paragraph, replacement, known_source_ids=known_source_ids)
        report.update(
            {
                "raw": raw,
                "replacement_markdown": replacement,
                "reason": parse.get("reason", ""),
                "parse_report": parse,
                "accepted_candidate": parse.get("status") == "parsed" and not issues,
                "issues": issues,
            }
        )
        return report

    paragraph_reports = run_parallel(selected, run_paragraph, max_workers=model_parallelism(backend))
    accepted_candidates = [row for row in paragraph_reports if row.get("accepted_candidate")]
    report = {
        "schema_id": "memo_ready_paragraph_polish_proposal_report_v1",
        "status": "parsed" if accepted_candidates else "no_accepted_paragraph_candidates",
        "method": "parallel_targeted_paragraph_polish",
        "parallelism": min(model_parallelism(backend), len(selected)) if selected else 0,
        "paragraph_count": len(paragraphs),
        "selected_paragraph_count": len(selected),
        "accepted_candidate_count": len(accepted_candidates),
        "selected_paragraphs": [_public_paragraph_row(row) for row in selected],
        "paragraph_reports": [_public_paragraph_report(row) for row in paragraph_reports],
        "issues": [] if accepted_candidates else ["no paragraph returned an applicable replacement"],
    }
    return {
        "prompt": _combined_prompts(paragraph_reports),
        "raw": _combined_raw(paragraph_reports),
        "paragraphs": paragraphs,
        "selected_paragraphs": selected,
        "paragraph_reports": paragraph_reports,
        "report": report,
    }


def build_paragraph_memo_polish_prompt(
    paragraph: dict[str, Any],
    *,
    paragraphs: list[dict[str, Any]],
    packet: dict[str, Any],
    source_trail: list[Any],
) -> str:
    index = int(paragraph.get("paragraph_index", 0) or 0)
    previous_text = _neighbor_text(paragraphs, index, -1)
    next_text = _neighbor_text(paragraphs, index, 1)
    paragraph_text = replace_source_aliases_with_ids(str(paragraph.get("markdown") or ""), source_trail)
    guardrails = project_source_text_to_ids_for_model(
        project_sources_to_ids_for_model(build_memo_ready_final_polish_guardrails(packet), source_trail),
        source_trail,
    )
    return (
        "You are polishing one paragraph of a source-grounded decision memo.\n"
        "Return JSON with one replacement for this paragraph only.\n\n"
        "Goal:\n"
        "- Improve this paragraph's readability, flow, and citation clarity without changing its meaning.\n"
        "- Preserve source IDs, quantities, uncertainty, and decision implications already present.\n"
        "- Keep neighboring paragraphs in mind only for transition fit while replacing only the target paragraph.\n\n"
        "Style target:\n"
        "- The paragraph should read like calm decision analysis, not assembled notes.\n"
        "- Prefer a direct topic sentence and concrete transitions.\n"
        "- Keep citations attached to supported claims, but make the prose readable before citation brackets appear.\n\n"
        "JSON schema:\n"
        "{\n"
        '  "paragraph_markdown": "replacement paragraph markdown only",\n'
        '  "reason": "why the replacement improves this paragraph"\n'
        "}\n\n"
        "Rules:\n"
        "- Return valid JSON only.\n"
        "- Include only the target paragraph and any section heading already present in it.\n"
        "- Use facts, numbers, source IDs, populations, recommendations, and comparisons already present in this paragraph or guardrails.\n"
        "- If a safe improvement is unavailable, return the paragraph unchanged.\n\n"
        f"Decision question: {packet.get('decision_question')}\n"
        f"Section heading: {paragraph.get('section_heading')}\n"
        f"Paragraph issues: {json.dumps(paragraph.get('issues') or [], ensure_ascii=False)}\n\n"
        f"Source registry:\n{json.dumps(source_id_registry_for_model(source_trail), indent=2, ensure_ascii=False)}\n\n"
        f"Validation guardrails:\n{json.dumps(guardrails, indent=2, ensure_ascii=False)}\n\n"
        f"Paragraph diagnostics:\n{json.dumps(prose_quality_diagnostics(paragraph_text), indent=2, ensure_ascii=False)}\n\n"
        f"Previous paragraph for transition context:\n{previous_text}\n\n"
        f"Target paragraph:\n{paragraph_text.strip()}\n\n"
        f"Next paragraph for transition context:\n{next_text}\n"
    )


def parse_paragraph_memo_polish_response(raw: str) -> dict[str, Any]:
    payload = _parse_json_payload(raw)
    if not isinstance(payload, dict):
        return {
            "schema_id": "memo_ready_paragraph_polish_parse_report_v1",
            "status": "unparseable",
            "paragraph_markdown": "",
            "reason": "",
            "issues": ["response was not valid JSON object"],
        }
    markdown = str(payload.get("paragraph_markdown") or payload.get("paragraph") or payload.get("markdown") or "").strip()
    if not markdown:
        return {
            "schema_id": "memo_ready_paragraph_polish_parse_report_v1",
            "status": "missing_paragraph_markdown",
            "paragraph_markdown": "",
            "reason": "",
            "issues": ["response did not include paragraph_markdown"],
        }
    return {
        "schema_id": "memo_ready_paragraph_polish_parse_report_v1",
        "status": "parsed",
        "paragraph_markdown": markdown,
        "reason": str(payload.get("reason") or "").strip(),
        "issues": [],
    }


def _select_paragraphs_for_polish(paragraphs: list[dict[str, Any]], *, max_paragraphs: int) -> list[dict[str, Any]]:
    scored = [
        (_paragraph_issue_priority(_list(row.get("issues"))), len(_list(row.get("issues"))), int(row.get("paragraph_index", 0) or 0), row)
        for row in paragraphs
        if _list(row.get("issues"))
    ]
    scored.sort(key=lambda row: (-row[0], -row[1], row[2]))
    return [row for _, _, _, row in scored[: max(0, max_paragraphs)]]


def _paragraph_polish_issues(markdown: str) -> list[str]:
    issues: list[str] = []
    text = str(markdown or "")
    lowered = text.lower()
    if "..." in text or "…" in text:
        issues.append("unfinished")
    if text.count("[") >= 5:
        issues.append("citation_dense")
    for phrase in ("supporting this is", "to ensure a complete picture", "these points bound", "primary evidence", "rooted in"):
        if phrase in lowered:
            issues.append("stock_phrase")
            break
    if len(re.findall(r"\b\w+\b", text)) > 150:
        issues.append("long_paragraph")
    return issues


def _paragraph_issue_priority(issues: list[str]) -> int:
    if "unfinished" in issues:
        return 100
    if "citation_dense" in issues:
        return 70
    if "long_paragraph" in issues:
        return 55
    if "stock_phrase" in issues:
        return 40
    return 10


def _paragraph_candidate_issues(paragraph: dict[str, Any], replacement: str, *, known_source_ids: set[str]) -> list[str]:
    original = str(paragraph.get("markdown") or "").strip()
    if not replacement.strip():
        return ["empty_paragraph_replacement"]
    if replacement.lstrip().startswith("#") and not original.lstrip().startswith("#"):
        return ["added_heading_to_paragraph"]
    unknown = sorted(ref for ref in _bracket_source_refs(replacement) if ref not in known_source_ids and ref not in _bracket_source_refs(original))
    if unknown:
        return [f"unknown_source_ids:{', '.join(unknown)}"]
    if _word_count(replacement) > max(_word_count(original) + 80, int(_word_count(original) * 1.8)):
        return ["paragraph_over_expanded"]
    return []


def _strip_sources_section(memo: str) -> str:
    return re.split(r"(?m)^##\s+Sources\s*$", str(memo or ""), maxsplit=1)[0].strip()


def _neighbor_text(paragraphs: list[dict[str, Any]], paragraph_index: int, offset: int) -> str:
    wanted = paragraph_index + offset
    for row in paragraphs:
        if int(row.get("paragraph_index", 0) or 0) == wanted:
            return str(row.get("markdown") or "").strip()
    return ""


def _known_source_ids(packet: dict[str, Any]) -> set[str]:
    aliases = source_id_alias_map(_list(packet.get("source_trail")))
    return {source_id for source_id in aliases.values() if source_id}


def _bracket_source_refs(text: str) -> set[str]:
    refs: set[str] = set()
    for match in re.finditer(r"\[([^\]\n]{1,160})\]", str(text or "")):
        content = match.group(1)
        if "](" in content:
            continue
        for part in re.split(r"[,;]", content):
            token = part.strip()
            if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", token):
                refs.add(token)
    return refs


def _parse_json_payload(raw: str) -> Any:
    cleaned = str(raw or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _public_paragraph_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "paragraph_id": row.get("paragraph_id"),
        "paragraph_index": row.get("paragraph_index"),
        "section_heading": row.get("section_heading"),
        "issues": _list(row.get("issues")),
        "preview": _preview(row.get("markdown")),
    }


def _public_paragraph_report(row: dict[str, Any]) -> dict[str, Any]:
    parse = row.get("parse_report") if isinstance(row.get("parse_report"), dict) else {}
    return {
        "paragraph_id": row.get("paragraph_id"),
        "paragraph_index": row.get("paragraph_index"),
        "section_heading": row.get("section_heading"),
        "status": parse.get("status", "not_run"),
        "accepted_candidate": bool(row.get("accepted_candidate")),
        "issues": _list(row.get("issues")) + _list(parse.get("issues")),
        "reason": row.get("reason", ""),
        "replacement_preview": _preview(row.get("replacement_markdown")),
    }


def _combined_prompts(paragraph_reports: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"<!-- paragraph polish: {row.get('paragraph_id')} -->\n{row.get('prompt', '')}"
        for row in paragraph_reports
    )


def _combined_raw(paragraph_reports: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"<!-- paragraph polish: {row.get('paragraph_id')} raw -->\n{row.get('raw', '')}"
        for row in paragraph_reports
    )


def _preview(value: Any, *, limit: int = 180) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "..."


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", str(text or "")))
