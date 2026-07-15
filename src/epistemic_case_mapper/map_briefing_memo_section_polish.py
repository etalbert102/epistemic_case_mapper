from __future__ import annotations

import json
import re
from typing import Any, Callable

from epistemic_case_mapper.map_briefing_memo_polish_diagnostics import prose_quality_diagnostics
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import dict_value as _dict
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


SECTION_POLISH_MODES: tuple[dict[str, str], ...] = (
    {
        "mode_id": "concise_safe",
        "name": "Concise safe polish",
        "focus": "Make the section cleaner and less formulaic with minimal expansion. Prefer preserving existing claims exactly.",
    },
    {
        "mode_id": "decision_grade",
        "name": "Decision-grade rewrite",
        "focus": "Make the section read like polished decision analysis while preserving the same evidence and scope.",
    },
    {
        "mode_id": "reader_usefulness",
        "name": "Reader usefulness",
        "focus": "Make the section more useful to a decision-maker, especially by clarifying implications already present in the section.",
    },
)

COMPLETION_ONLY_SECTION_POLISH_MODE: dict[str, str] = {
    "mode_id": "completion_only",
    "name": "Completion-only repair",
    "focus": "Only finish truncated or incomplete language. Leave complete sentences and the section structure unchanged.",
}


def split_memo_into_polish_sections(memo: str) -> list[dict[str, Any]]:
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", str(memo or ""), flags=re.MULTILINE))
    sections: list[dict[str, Any]] = []
    if not matches:
        text = str(memo or "").strip()
        return [_section_row("opening", "Opening", text, 0)] if text else []
    opening = str(memo or "")[: matches[0].start()].strip()
    if opening:
        sections.append(_section_row("opening", "Opening", opening, 0))
    for index, match in enumerate(matches, start=1):
        heading = match.group(1).strip()
        end = matches[index].start() if index < len(matches) else len(str(memo or ""))
        markdown = str(memo or "")[match.start() : end].strip()
        if heading.strip().lower() == "sources":
            continue
        sections.append(_section_row(_section_id(heading), heading, markdown, len(sections)))
    return sections


def collect_parallel_section_memo_polish_proposals(
    memo: str,
    packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    run_model: ModelRunner = run_model_backend,
) -> dict[str, Any]:
    sections = split_memo_into_polish_sections(memo)
    source_trail = _list(packet.get("source_trail"))
    known_source_ids = _known_source_ids(packet)
    guardrails = build_memo_ready_final_polish_guardrails(packet)
    prompts_by_id = {
        section["section_id"]: build_section_memo_polish_prompt(
            section,
            sections=sections,
            packet=packet,
            source_trail=source_trail,
        )
        for section in sections
    }

    def run_section(section: dict[str, Any]) -> dict[str, Any]:
        section_id = str(section.get("section_id") or "")
        prompt = prompts_by_id.get(section_id, "")
        report = {
            "section_id": section_id,
            "heading": section.get("heading"),
            "prompt": prompt,
            "raw": "",
            "reason": "",
            "replacement_markdown": "",
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
        parse = parse_section_memo_polish_response(raw)
        replacement = str(parse.get("section_markdown") or "").strip()
        issues = _section_candidate_issues(section, replacement, known_source_ids=known_source_ids, guardrails=guardrails)
        report.update(
            {
                "raw": raw,
                "reason": parse.get("reason", ""),
                "replacement_markdown": replacement,
                "parse_report": parse,
                "accepted_candidate": parse.get("status") == "parsed" and not issues,
                "issues": issues,
            }
        )
        return report

    section_reports = run_parallel(sections, run_section, max_workers=model_parallelism(backend))
    accepted_candidates = [row for row in section_reports if row.get("accepted_candidate")]
    report = {
        "schema_id": "memo_ready_section_polish_proposal_report_v1",
        "status": "parsed" if accepted_candidates else "no_accepted_section_candidates",
        "method": "parallel_section_memo_polish",
        "parallelism": min(model_parallelism(backend), len(sections)) if sections else 0,
        "section_count": len(sections),
        "accepted_candidate_count": len(accepted_candidates),
        "section_reports": [_public_section_report(row) for row in section_reports],
        "issues": [] if accepted_candidates else ["no section returned an applicable replacement"],
    }
    return {
        "prompt": _combined_section_prompts(section_reports),
        "raw": _combined_section_raw(section_reports),
        "sections": sections,
        "section_reports": section_reports,
        "report": report,
    }


def collect_parallel_hybrid_section_memo_polish_proposals(
    memo: str,
    packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    run_model: ModelRunner = run_model_backend,
) -> dict[str, Any]:
    sections = split_memo_into_polish_sections(memo)
    modes = [dict(mode) for mode in SECTION_POLISH_MODES]
    source_trail = _list(packet.get("source_trail"))
    known_source_ids = _known_source_ids(packet)
    guardrails = build_memo_ready_final_polish_guardrails(packet)
    tasks = [
        (section, mode)
        for section in sections
        for mode in _hybrid_modes_for_section(section, modes)
    ]

    def run_task(task: tuple[dict[str, Any], dict[str, str]]) -> dict[str, Any]:
        section, mode = task
        prompt = build_section_memo_polish_prompt(
            section,
            sections=sections,
            packet=packet,
            source_trail=source_trail,
            mode=mode,
        )
        report = {
            "section_id": section.get("section_id"),
            "heading": section.get("heading"),
            "mode_id": mode.get("mode_id"),
            "mode_name": mode.get("name"),
            "prompt": prompt,
            "raw": "",
            "reason": "",
            "replacement_markdown": "",
            "parse_report": {},
            "accepted_candidate": False,
            "score": -1000,
            "score_features": {},
            "issues": [],
        }
        try:
            result = run_model(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
        except RuntimeError as exc:
            report["parse_report"] = {"status": "backend_error", "issues": [str(exc)]}
            report["issues"] = ["backend_error", str(exc)]
            return report
        raw = result.text
        parse = parse_section_memo_polish_response(raw)
        replacement = str(parse.get("section_markdown") or "").strip()
        issues = _section_candidate_issues(section, replacement, known_source_ids=known_source_ids, guardrails=guardrails)
        mode_id = str(mode.get("mode_id") or "")
        score_report = score_section_polish_candidate(section, replacement, issues=issues, mode_id=mode_id)
        accepted_candidate = parse.get("status") == "parsed" and not issues and _score_is_selectable(score_report, mode_id=mode_id)
        report.update(
            {
                "raw": raw,
                "reason": parse.get("reason", ""),
                "replacement_markdown": replacement,
                "parse_report": parse,
                "accepted_candidate": accepted_candidate,
                "score": score_report["score"],
                "score_features": score_report["features"],
                "issues": issues if accepted_candidate else [*issues, *_score_rejection_issues(score_report, mode_id=mode_id)],
            }
        )
        return report

    candidate_reports = run_parallel(tasks, run_task, max_workers=model_parallelism(backend))
    by_section: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidate_reports:
        by_section.setdefault(str(candidate.get("section_id") or ""), []).append(candidate)
    section_reports = []
    for section in sections:
        candidates = sorted(
            by_section.get(str(section.get("section_id") or ""), []),
            key=lambda row: (bool(row.get("accepted_candidate")), int(row.get("score") or -1000)),
            reverse=True,
        )
        selected = candidates[0] if candidates else {}
        section_reports.append(
            {
                "section_id": section.get("section_id"),
                "heading": section.get("heading"),
                "candidate_reports": candidates,
                "accepted_candidate": bool(selected.get("accepted_candidate")),
                "replacement_markdown": selected.get("replacement_markdown", ""),
                "reason": selected.get("reason", ""),
                "selected_mode_id": selected.get("mode_id"),
                "selected_score": selected.get("score", -1000),
                "issues": [] if selected.get("accepted_candidate") else ["no_accepted_candidate"],
            }
        )
    accepted_sections = [row for row in section_reports if row.get("accepted_candidate")]
    report = {
        "schema_id": "memo_ready_hybrid_section_polish_proposal_report_v1",
        "status": "parsed" if accepted_sections else "no_accepted_section_candidates",
        "method": "parallel_hybrid_section_memo_polish",
        "parallelism": min(model_parallelism(backend), len(tasks)) if tasks else 0,
        "section_count": len(sections),
        "base_mode_count": len(modes),
        "mode_count": len({str(mode.get("mode_id") or "") for _, mode in tasks}),
        "completion_only_task_count": sum(1 for _, mode in tasks if mode.get("mode_id") == "completion_only"),
        "candidate_count": len(candidate_reports),
        "accepted_candidate_count": sum(1 for row in candidate_reports if row.get("accepted_candidate")),
        "selected_section_count": len(accepted_sections),
        "section_reports": [_public_hybrid_section_report(row) for row in section_reports],
        "issues": [] if accepted_sections else ["no section returned an applicable replacement"],
    }
    return {
        "prompt": _combined_section_prompts(candidate_reports),
        "raw": _combined_section_raw(candidate_reports),
        "sections": sections,
        "section_reports": section_reports,
        "report": report,
    }


def score_section_polish_candidate(
    section: dict[str, Any],
    replacement: str,
    *,
    issues: list[str],
    mode_id: str = "",
) -> dict[str, Any]:
    original = str(section.get("markdown") or "")
    if issues or not replacement.strip():
        return {"score": -1000, "features": {"invalid": True}}
    original_words = _word_count(original)
    replacement_words = _word_count(replacement)
    stock_delta = _stock_phrase_count(original) - _stock_phrase_count(replacement)
    unfinished_delta = _unfinished_count(original) - _unfinished_count(replacement)
    citation_delta = replacement.count("[") - original.count("[")
    expansion_ratio = (replacement_words / max(1, original_words)) if original_words else 1.0
    practical_gain = _practical_gain(section, original, replacement)
    score = 0
    score += stock_delta * 8
    score += unfinished_delta * 18
    score += practical_gain * 4
    if replacement.strip() != original.strip():
        score += 2
    if expansion_ratio > 1.18:
        score -= int((expansion_ratio - 1.18) * 40)
    if replacement_words > original_words + 80:
        score -= 12
    if citation_delta > 1:
        score -= citation_delta * 4
    if _contains_shaky_expansion_terms(replacement, original):
        score -= 10
    if mode_id == "completion_only":
        if unfinished_delta <= 0:
            score -= 40
        if stock_delta != 0:
            score -= 6
        if replacement_words > original_words + 55:
            score -= 24
        if citation_delta > 2:
            score -= citation_delta * 6
    shaky = _contains_shaky_expansion_terms(replacement, original)
    return {
        "score": score,
        "features": {
            "original_words": original_words,
            "replacement_words": replacement_words,
            "stock_phrase_delta": stock_delta,
            "unfinished_delta": unfinished_delta,
            "citation_delta": citation_delta,
            "expansion_ratio": round(expansion_ratio, 3),
            "practical_gain": practical_gain,
            "shaky_expansion": shaky,
        },
    }


def build_section_memo_polish_prompt(
    section: dict[str, Any],
    *,
    sections: list[dict[str, Any]],
    packet: dict[str, Any],
    source_trail: list[Any],
    mode: dict[str, str] | None = None,
) -> str:
    section_index = int(section.get("section_index", 0) or 0)
    previous_heading = str(sections[section_index - 1].get("heading") or "") if section_index > 0 else ""
    next_heading = str(sections[section_index + 1].get("heading") or "") if section_index + 1 < len(sections) else ""
    section_markdown = replace_source_aliases_with_ids(str(section.get("markdown") or ""), source_trail)
    guardrails = project_source_text_to_ids_for_model(
        project_sources_to_ids_for_model(build_memo_ready_final_polish_guardrails(packet), source_trail),
        source_trail,
    )
    section_type = "opening" if section.get("section_id") == "opening" else "body_section"
    mode_block = _mode_block(mode)
    if str((mode or {}).get("mode_id") or "") == "completion_only":
        return _build_completion_only_section_prompt(
            section,
            source_trail=source_trail,
            guardrails=guardrails,
            section_markdown=section_markdown,
            section_type=section_type,
            mode_block=mode_block,
            packet=packet,
        )
    return (
        "You are polishing one section of a source-grounded decision memo.\n"
        "Return a JSON object with one replacement for this section only.\n\n"
        f"{mode_block}"
        "Goal:\n"
        "- Make this section read like polished decision-ready analysis.\n"
        "- Preserve the section's answer, source IDs, quantities, uncertainty, and decision implications.\n"
        "- Improve paragraph flow inside this section; do not rewrite other sections.\n"
        "- Prefer a section-level rewrite when the current section sounds formulaic, repetitive, truncated, or assembled from notes.\n\n"
        "Style target:\n"
        "- The section should answer the reader's next question in plain analyst prose.\n"
        "- Prefer concrete sentences over stock phrases such as 'supporting this is', 'to ensure a complete picture', 'these points bound', or 'the primary evidence is rooted in'.\n"
        "- Keep citations attached to claims, but make the sentence readable before the citation appears.\n"
        "- Do not infer a new mechanism, trend, threshold, or recommendation beyond the section and guardrails.\n\n"
        "Section-specific guidance:\n"
        "- Opening: make the bottom line direct and calibrated; answer first, then give the main boundary.\n"
        "- Evidence sections: make the evidence hierarchy legible and explain why it carries or bounds the answer.\n"
        "- Practical sections: do not merely repeat the bottom line; translate the answer into the action-relevant implication using existing scope and caveats.\n\n"
        "JSON schema:\n"
        "{\n"
        '  "section_markdown": "replacement markdown for this section only",\n'
        '  "reason": "why this replacement improves the section"\n'
        "}\n\n"
        "Rules:\n"
        "- Return valid JSON only.\n"
        "- For body sections, section_markdown must start with exactly the same ## heading.\n"
        "- For the opening section, preserve the top title and decision question.\n"
        "- Do not add facts, numbers, sources, populations, recommendations, or comparisons not already in this section or guardrails.\n"
        "- Keep source IDs and quantities attached to the claims they support.\n"
        "- If no safe improvement is available, return it unchanged.\n\n"
        f"Section type: {section_type}\n"
        f"Section heading: {section.get('heading')}\n"
        f"Previous heading: {previous_heading}\n"
        f"Next heading: {next_heading}\n"
        f"Decision question: {packet.get('decision_question')}\n\n"
        f"Source registry:\n{json.dumps(source_id_registry_for_model(source_trail), indent=2, ensure_ascii=False)}\n\n"
        f"Validation guardrails:\n{json.dumps(guardrails, indent=2, ensure_ascii=False)}\n\n"
        f"Section prose diagnostics:\n{json.dumps(prose_quality_diagnostics(section_markdown), indent=2, ensure_ascii=False)}\n\n"
        f"Current section markdown:\n{section_markdown.strip()}\n"
    )


def _build_completion_only_section_prompt(
    section: dict[str, Any],
    *,
    source_trail: list[Any],
    guardrails: dict[str, Any],
    section_markdown: str,
    section_type: str,
    mode_block: str,
    packet: dict[str, Any],
) -> str:
    return (
        "You are repairing a truncated section of a source-grounded decision memo.\n"
        "Return a JSON object with one replacement for this section only.\n\n"
        f"{mode_block}"
        "Goal:\n"
        "- Finish only the visibly incomplete sentence or dangling phrase in this section.\n"
        "- Preserve complete sentences, section order, source IDs, quantities, and uncertainty.\n"
        "- Use only facts already present in this section or the validation guardrails.\n"
        "- If the section is not actually unfinished, return it unchanged.\n\n"
        "Style target:\n"
        "- The repaired sentence should read naturally and stop at the smallest sufficient completion.\n"
        "- Keep citations attached to claims when the completion uses cited evidence.\n"
        "- Do not turn this into a broader rewrite or add a new recommendation.\n\n"
        "JSON schema:\n"
        "{\n"
        '  "section_markdown": "replacement markdown for this section only",\n'
        '  "reason": "what unfinished text was repaired"\n'
        "}\n\n"
        "Rules:\n"
        "- Return valid JSON only.\n"
        "- For body sections, section_markdown must start with exactly the same ## heading.\n"
        "- For the opening section, preserve the top title and decision question.\n"
        "- The replacement should usually be close in length to the original section.\n"
        "- Do not add facts, numbers, populations, source IDs, or comparisons not already in this section or guardrails.\n\n"
        f"Section type: {section_type}\n"
        f"Section heading: {section.get('heading')}\n"
        f"Decision question: {packet.get('decision_question')}\n\n"
        f"Source registry:\n{json.dumps(source_id_registry_for_model(source_trail), indent=2, ensure_ascii=False)}\n\n"
        f"Validation guardrails:\n{json.dumps(guardrails, indent=2, ensure_ascii=False)}\n\n"
        f"Section prose diagnostics:\n{json.dumps(prose_quality_diagnostics(section_markdown), indent=2, ensure_ascii=False)}\n\n"
        f"Current section markdown:\n{section_markdown.strip()}\n"
    )


def parse_section_memo_polish_response(raw: str) -> dict[str, Any]:
    payload = _parse_json_payload(raw)
    if not isinstance(payload, dict):
        return {"schema_id": "memo_ready_section_polish_parse_report_v1", "status": "unparseable", "section_markdown": "", "reason": "", "issues": ["response was not valid JSON object"]}
    markdown = str(payload.get("section_markdown") or payload.get("markdown") or payload.get("section") or "").strip()
    if not markdown:
        return {"schema_id": "memo_ready_section_polish_parse_report_v1", "status": "missing_section_markdown", "section_markdown": "", "reason": "", "issues": ["response did not include section_markdown"]}
    return {
        "schema_id": "memo_ready_section_polish_parse_report_v1",
        "status": "parsed",
        "section_markdown": markdown,
        "reason": str(payload.get("reason") or "").strip(),
        "issues": [],
    }


def _section_candidate_issues(
    section: dict[str, Any],
    replacement: str,
    *,
    known_source_ids: set[str],
    guardrails: dict[str, Any] | None = None,
) -> list[str]:
    if not replacement.strip():
        return ["empty_section_replacement"]
    heading = str(section.get("heading") or "").strip()
    if section.get("section_id") == "opening":
        original_first = str(section.get("markdown") or "").strip().splitlines()[0].strip()
        replacement_first = replacement.strip().splitlines()[0].strip() if replacement.strip() else ""
        if original_first.startswith("#") and replacement_first != original_first:
            return ["opening_title_changed"]
    elif not replacement.lstrip().startswith(f"## {heading}"):
        return ["section_heading_changed"]
    unknown = sorted(ref for ref in _bracket_source_refs(replacement) if ref not in known_source_ids and ref not in _bracket_source_refs(str(section.get("markdown") or "")))
    if unknown:
        return [f"unknown_source_ids:{', '.join(unknown)}"]
    language_issues = _language_contract_issues(str(section.get("markdown") or ""), replacement, _dict(guardrails))
    return language_issues


def _language_contract_issues(original: str, replacement: str, guardrails: dict[str, Any]) -> list[str]:
    contracts = [row for row in _list(guardrails.get("evidence_language_contracts")) if isinstance(row, dict)]
    if not contracts:
        return []
    issues = []
    replacement_lower = str(replacement or "").lower()
    original_lower = str(original or "").lower()
    replacement_refs = _bracket_source_refs(replacement)
    for contract in contracts:
        source_ids = set(_list(contract.get("source_ids")))
        if source_ids and not source_ids.intersection(replacement_refs):
            continue
        for phrase in _list(contract.get("avoid_language")):
            phrase_text = str(phrase or "").strip().lower()
            if not phrase_text:
                continue
            if _contains_language_phrase(replacement_lower, phrase_text) and not _contains_language_phrase(original_lower, phrase_text):
                issues.append(f"unsupported_language_for_sources:{','.join(sorted(source_ids))}:{phrase_text}")
    return issues


def _contains_language_phrase(text: str, phrase: str) -> bool:
    if not phrase:
        return False
    pattern = r"\b" + r"\s+".join(re.escape(part) for part in phrase.split()) + r"\b"
    return bool(re.search(pattern, text, flags=re.IGNORECASE))


def _section_row(section_id: str, heading: str, markdown: str, section_index: int) -> dict[str, Any]:
    return {"section_id": section_id, "heading": heading, "markdown": markdown, "section_index": section_index}


def _section_id(heading: str) -> str:
    text = re.sub(r"[^a-z0-9]+", "_", str(heading or "").strip().lower()).strip("_")
    return text or "section"


def _known_source_ids(packet: dict[str, Any]) -> set[str]:
    aliases = source_id_alias_map(_list(packet.get("source_trail")))
    return {source_id for source_id in aliases.values() if source_id}


def _hybrid_modes_for_section(section: dict[str, Any], base_modes: list[dict[str, str]]) -> list[dict[str, str]]:
    modes = [dict(mode) for mode in base_modes]
    if _unfinished_count(str(section.get("markdown") or "")):
        modes.append(dict(COMPLETION_ONLY_SECTION_POLISH_MODE))
    return modes


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


def _public_section_report(row: dict[str, Any]) -> dict[str, Any]:
    parse = row.get("parse_report") if isinstance(row.get("parse_report"), dict) else {}
    return {
        "section_id": row.get("section_id"),
        "heading": row.get("heading"),
        "status": parse.get("status", "not_run"),
        "accepted_candidate": bool(row.get("accepted_candidate")),
        "issues": _list(row.get("issues")) + _list(parse.get("issues")),
    }


def _public_hybrid_section_report(row: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        {
            "mode_id": candidate.get("mode_id"),
            "accepted_candidate": bool(candidate.get("accepted_candidate")),
            "score": candidate.get("score"),
            "score_features": candidate.get("score_features", {}),
            "issues": _list(candidate.get("issues")),
        }
        for candidate in _list(row.get("candidate_reports"))
        if isinstance(candidate, dict)
    ]
    return {
        "section_id": row.get("section_id"),
        "heading": row.get("heading"),
        "accepted_candidate": bool(row.get("accepted_candidate")),
        "selected_mode_id": row.get("selected_mode_id"),
        "selected_score": row.get("selected_score"),
        "candidate_reports": candidates,
        "issues": _list(row.get("issues")),
    }


def _combined_section_prompts(section_reports: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"<!-- section polish: {row.get('section_id')} {row.get('mode_id', '')} -->\n{row.get('prompt', '')}"
        for row in section_reports
    )


def _combined_section_raw(section_reports: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"<!-- section polish: {row.get('section_id')} {row.get('mode_id', '')} raw -->\n{row.get('raw', '')}"
        for row in section_reports
    )


def _mode_block(mode: dict[str, str] | None) -> str:
    if not mode:
        return ""
    return (
        "Polish mode:\n"
        f"- mode_id: {mode.get('mode_id')}\n"
        f"- name: {mode.get('name')}\n"
        f"- focus: {mode.get('focus')}\n\n"
    )


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", str(text or "")))


def _stock_phrase_count(text: str) -> int:
    lowered = str(text or "").lower()
    phrases = ("supporting this is", "to ensure a complete picture", "these points bound", "primary evidence", "rooted in")
    return sum(lowered.count(phrase) for phrase in phrases)


def _unfinished_count(text: str) -> int:
    return int("..." in str(text or "") or "…" in str(text or ""))


def _practical_gain(section: dict[str, Any], original: str, replacement: str) -> int:
    if str(section.get("section_id") or "") != "practical_implication":
        return 0
    cues = ("advise", "guidance", "restrict", "monitor", "treat", "use", "limit", "distinguish", "applies")
    return max(0, _cue_count(replacement, cues) - _cue_count(original, cues))


def _cue_count(text: str, cues: tuple[str, ...]) -> int:
    lowered = str(text or "").lower()
    return sum(1 for cue in cues if cue in lowered)


def _contains_shaky_expansion_terms(replacement: str, original: str) -> bool:
    replacement_norm = str(replacement or "").lower()
    original_norm = str(original or "").lower()
    for term in ("mortality", "dose-response", "dose dependent", "mechanism", "causal"):
        if term in replacement_norm and term not in original_norm:
            return True
    return False


def _score_is_selectable(score_report: dict[str, Any], *, mode_id: str = "") -> bool:
    features = score_report.get("features") if isinstance(score_report.get("features"), dict) else {}
    score = int(score_report.get("score") or -1000)
    if features.get("shaky_expansion"):
        return False
    if mode_id == "completion_only":
        return (
            int(features.get("unfinished_delta") or 0) > 0
            and score >= -8
            and int(features.get("replacement_words") or 0) <= int(features.get("original_words") or 0) + 55
            and int(features.get("citation_delta") or 0) <= 2
        )
    if score >= 0:
        return True
    simple_completion = (
        int(features.get("unfinished_delta") or 0) > 0
        and int(features.get("replacement_words") or 0) <= int(features.get("original_words") or 0) + 45
        and int(features.get("citation_delta") or 0) <= 2
    )
    return simple_completion


def _score_rejection_issues(score_report: dict[str, Any], *, mode_id: str = "") -> list[str]:
    if _score_is_selectable(score_report, mode_id=mode_id):
        return []
    features = score_report.get("features") if isinstance(score_report.get("features"), dict) else {}
    issues = ["low_section_polish_score"]
    if features.get("shaky_expansion"):
        issues.append("shaky_expansion_terms")
    return issues
