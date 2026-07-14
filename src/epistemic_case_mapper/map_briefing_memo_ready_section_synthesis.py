from __future__ import annotations

import json
import re
from typing import Any, Callable

from epistemic_case_mapper.map_briefing_markdown_quality import markdown_structure_issues, repair_markdown_structure
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    list_value as _list,
    string_list as _string_list,
)
from epistemic_case_mapper.model_backends import ModelBackendResult, model_parallelism, run_model_backend, run_parallel


ModelRunner = Callable[..., ModelBackendResult]


def run_parallel_memo_ready_section_generation(
    section_plan: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    whole_prompt: str,
    run_model: ModelRunner = run_model_backend,
) -> dict[str, Any]:
    sections = [section for section in _list(section_plan.get("sections")) if isinstance(section, dict)]
    known_source_ids = set(_string_list(section_plan.get("known_source_ids")))
    report = {
        "schema_id": "memo_ready_section_generation_report_v1",
        "status": "not_run",
        "accepted": False,
        "synthesis_mode": "parallel_section_synthesis",
        "parallelism": min(model_parallelism(backend), len(sections)) if sections else 0,
        "section_count": len(sections),
        "issues": [],
    }

    def run_section(section: dict[str, Any]) -> dict[str, Any]:
        return _run_section(
            section,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            known_source_ids=known_source_ids,
            run_model=run_model,
        )

    section_reports = run_parallel(sections, run_section, max_workers=model_parallelism(backend))
    failed = [row for row in section_reports if not row.get("accepted")]
    combined_prompt = _combined_section_prompts(section_plan, whole_prompt=whole_prompt)
    combined_raw = "\n\n".join(
        f"<!-- {row.get('heading')} raw -->\n{row.get('raw', '')}" for row in section_reports
    )
    if failed:
        report.update(
            {
                "status": "section_synthesis_failed",
                "accepted": False,
                "section_reports": [_public_section_report(row) for row in section_reports],
                "issues": ["one_or_more_sections_failed_validation"],
            }
        )
        return {"memo": "", "prompt": combined_prompt, "raw": combined_raw, "report": report}
    report.update(
        {
            "status": "accepted",
            "accepted": True,
            "section_reports": [_public_section_report(row) for row in section_reports],
        }
    )
    return {
        "memo": _assemble_section_synthesis_memo(section_plan, section_reports),
        "prompt": combined_prompt,
        "raw": combined_raw,
        "report": report,
    }


def _run_section(
    section: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    known_source_ids: set[str],
    run_model: ModelRunner,
) -> dict[str, Any]:
    heading = str(section.get("heading") or "").strip()
    prompt = str(section.get("prompt") or "")
    section_report = {
        "section_id": section.get("section_id"),
        "heading": heading,
        "accepted": False,
        "issues": [],
        "unknown_source_ids": [],
        "raw": "",
        "prompt": prompt,
        "markdown": "",
    }
    try:
        result = run_model(
            prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
            json_mode=False,
        )
    except RuntimeError as exc:
        section_report["issues"] = ["backend_error", str(exc)]
        return section_report
    raw = result.text
    markdown = _extract_section_markdown(raw, heading)
    unknown = _unknown_section_source_ids(markdown, known_source_ids)
    structure_issues = markdown_structure_issues(markdown)
    heading_ok = markdown.lstrip().startswith(f"## {heading}\n") or markdown.strip() == f"## {heading}"
    issues = [
        *(["missing_exact_heading"] if not heading_ok else []),
        *([f"unknown_source_ids:{', '.join(unknown)}"] if unknown else []),
        *structure_issues,
    ]
    section_report.update(
        {
            "accepted": not issues,
            "issues": issues,
            "unknown_source_ids": unknown,
            "raw": raw,
            "markdown": markdown,
            "char_count": len(markdown),
            "attempts": result.attempts,
        }
    )
    return section_report


def _extract_section_markdown(raw: str, heading: str) -> str:
    candidate = repair_markdown_structure(_extract_markdown(raw))
    heading = str(heading or "").strip()
    if not candidate or not heading:
        return candidate
    candidate = re.sub(rf"(?m)^#+\s+{re.escape(heading)}\s*$", f"## {heading}", candidate, count=1)
    match = re.search(rf"(?ms)^##\s+{re.escape(heading)}\s*\n.*?(?=^##\s+\S|\Z)", candidate)
    if match:
        return repair_markdown_structure(match.group(0))
    return candidate


def _extract_markdown(raw: str) -> str:
    cleaned = str(raw).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:markdown|md|json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    payload = _parse_json(cleaned)
    if isinstance(payload, dict):
        for key in ("memo_markdown", "markdown", "memo", "text", "content"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        args = payload.get("args")
        if isinstance(args, dict):
            for key in ("memo_markdown", "markdown", "memo", "text", "content"):
                value = args.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return ""
    if isinstance(payload, list):
        return ""
    return cleaned


def _parse_json(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _unknown_section_source_ids(markdown: str, known_source_ids: set[str]) -> list[str]:
    unknown = []
    for citation in re.findall(r"\[([^\]]+)\]", str(markdown or "")):
        for token in re.split(r"[,;]", citation):
            source_id = token.strip()
            if source_id and source_id not in known_source_ids:
                unknown.append(source_id)
    return _dedupe(unknown)


def _combined_section_prompts(section_plan: dict[str, Any], *, whole_prompt: str) -> str:
    lines = [
        "Parallel section synthesis prompts.",
        "",
        "Whole-memo fallback prompt retained for artifact comparison:",
        whole_prompt.strip(),
    ]
    for section in _list(section_plan.get("sections")):
        if not isinstance(section, dict):
            continue
        lines.extend(
            [
                "",
                f"--- SECTION PROMPT: {section.get('heading')} ---",
                str(section.get("prompt") or "").strip(),
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _assemble_section_synthesis_memo(section_plan: dict[str, Any], section_reports: list[dict[str, Any]]) -> str:
    title = str(section_plan.get("title") or "Decision Memo").strip()
    question = str(section_plan.get("decision_question") or "").strip()
    bottom_line = str(section_plan.get("bottom_line") or "").strip()
    lines = [f"# Decision Memo: {title}" if title and title != "Decision Memo" else "# Decision Memo", ""]
    if question:
        lines.extend([f"**Decision Question:** {question}", ""])
    if bottom_line:
        lines.extend([f"**Bottom Line:** {bottom_line}", ""])
    for row in section_reports:
        section = str(row.get("markdown") or "").strip()
        if section:
            lines.extend([section, ""])
    return repair_markdown_structure("\n".join(lines).strip() + "\n")


def _public_section_report(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "section_id": row.get("section_id"),
        "heading": row.get("heading"),
        "accepted": bool(row.get("accepted")),
        "issues": _list(row.get("issues")),
        "unknown_source_ids": _list(row.get("unknown_source_ids")),
        "char_count": row.get("char_count", 0),
        "attempts": row.get("attempts", 0),
    }
