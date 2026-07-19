from __future__ import annotations

import json
import re
from typing import Any, Callable

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_polish_diagnostics import prose_quality_diagnostics
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import list_value as _list, norm as _norm
from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_polish_guardrails import build_memo_ready_final_polish_guardrails
from epistemic_case_mapper.pipeline.briefing.map_briefing_source_identity import (
    project_source_text_to_ids_for_model,
    project_sources_to_ids_for_model,
    replace_source_aliases_with_ids,
    source_id_alias_map,
)
from epistemic_case_mapper.model_backends import ModelBackendResult, model_parallelism, run_model_backend, run_parallel


ModelRunner = Callable[..., ModelBackendResult]


POLISH_LENSES: tuple[dict[str, str], ...] = (
    {
        "lens_id": "bluf_sharpness",
        "name": "BLUF sharpness",
        "focus": (
            "Make the opening answer crisp, decision-shaped, and calibrated. The first paragraph should answer the "
            "decision question directly, then name the main limit without sounding like a pasted summary."
        ),
    },
    {
        "lens_id": "evidence_weighting",
        "name": "Evidence weighting",
        "focus": (
            "Make the evidence hierarchy legible in prose. Clarify what carries the conclusion, what only bounds it, "
            "and why the uncertainty remains, without adding new source judgments."
        ),
    },
    {
        "lens_id": "narrative_logic",
        "name": "Narrative logic",
        "focus": (
            "Find places where the memo reads like assembled notes. Replace local paragraphs or adjacent paragraph "
            "blocks so the reasoning moves naturally from answer, to why, to limits."
        ),
    },
    {
        "lens_id": "practical_implication",
        "name": "Practical implication",
        "focus": (
            "Make the final practical section useful rather than repetitive. It should translate the evidence-weighted "
            "answer into what a reader should do with the conclusion, while preserving scope and citations."
        ),
    },
    {
        "lens_id": "completion_integrity",
        "name": "Completion and integrity",
        "focus": (
            "Find incomplete sentences, dangling clauses, broken transitions, malformed markdown, and obvious places "
            "where the memo looks unfinished. Prioritize repairs that make the memo complete without changing the analysis."
        ),
    },
    {
        "lens_id": "citation_clarity",
        "name": "Citation and trace clarity",
        "focus": (
            "Find citation clutter, source-ID-as-subject phrasing, and claims whose citation placement makes the sentence "
            "hard to read. Prioritize local citation placement and prose clarity while preserving source IDs."
        ),
    },
)


def memo_ready_json_polish_lenses() -> list[dict[str, str]]:
    return [dict(lens) for lens in POLISH_LENSES]


def collect_parallel_memo_ready_json_polish_proposals(
    memo: str,
    packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    run_model: ModelRunner = run_model_backend,
) -> dict[str, Any]:
    lenses = memo_ready_json_polish_lenses()

    def run_lens(lens: dict[str, str]) -> dict[str, Any]:
        prompt = build_memo_ready_json_edit_polish_prompt(memo, packet, lens=lens)
        lens_id = str(lens.get("lens_id") or "unknown")
        report = {
            "lens_id": lens_id,
            "name": lens.get("name"),
            "prompt": prompt,
            "raw": "",
            "parse_report": {},
            "edits": [],
            "issues": [],
        }
        try:
            result = run_model(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
        except RuntimeError as exc:
            report.update(
                {
                    "parse_report": {
                        "schema_id": "memo_ready_json_edit_polish_parse_report_v1",
                        "status": "backend_error",
                        "edits": [],
                        "issues": [str(exc)],
                    },
                    "issues": ["backend_error", str(exc)],
                }
            )
            return report
        raw = result.text
        parse_report = parse_memo_ready_json_polish_response(raw)
        edits = [
            _with_lens_metadata(edit, lens_id=lens_id, edit_index=index)
            for index, edit in enumerate(_list(parse_report.get("edits")), start=1)
            if isinstance(edit, dict)
        ]
        report.update({"raw": raw, "parse_report": parse_report, "edits": edits})
        return report

    lens_results = run_parallel(lenses, run_lens, max_workers=model_parallelism(backend))
    edits = _dedupe_parallel_edits(lens_results)
    parsed_count = sum(1 for row in lens_results if row.get("parse_report", {}).get("status") == "parsed")
    failed_count = len(lens_results) - parsed_count
    parse_report = {
        "schema_id": "memo_ready_parallel_json_edit_polish_report_v1",
        "status": "parsed" if parsed_count else "unparseable",
        "method": "parallel_lens_json_edit_polish",
        "parallelism": min(model_parallelism(backend), len(lenses)) if lenses else 0,
        "lens_count": len(lenses),
        "parsed_lens_count": parsed_count,
        "failed_lens_count": failed_count,
        "edit_count_before_dedupe": sum(len(_list(row.get("edits"))) for row in lens_results),
        "edit_count": len(edits),
        "edits": edits,
        "lens_reports": [_public_lens_report(row) for row in lens_results],
        "issues": [] if parsed_count else ["no polish lens returned parseable JSON edits"],
    }
    return {
        "prompt": _combined_lens_prompts(lens_results),
        "raw": _combined_lens_raw(lens_results),
        "parse_report": parse_report,
        "edits": edits,
        "lens_results": lens_results,
    }


def build_memo_ready_json_edit_polish_prompt(
    memo: str,
    packet: dict[str, Any],
    *,
    lens: dict[str, str] | None = None,
) -> str:
    source_trail = _list(packet.get("source_trail"))
    guardrails = build_memo_ready_final_polish_guardrails(packet)
    guardrails = project_source_text_to_ids_for_model(project_sources_to_ids_for_model(guardrails, source_trail), source_trail)
    prose_diagnostics = prose_quality_diagnostics(memo)
    memo_for_model = replace_source_aliases_with_ids(memo, source_trail)
    lens_block = _lens_block(lens)
    return (
        "You are editing a source-grounded decision memo as a decision analyst.\n"
        "Return JSON edits, not a rewritten memo. The caller will apply only safe exact replacements.\n\n"
        f"{lens_block}"
        "Goal:\n"
        "- Improve readability, transitions, sentence rhythm, citation clutter, and analyst flow.\n"
        "- Keep the same answer, evidence, uncertainty, quantities, source IDs, and decision implications.\n"
        "- Prefer one or two high-value paragraph-level edits over many small wording changes.\n\n"
        "Style target:\n"
        "- The memo should read like decision-ready analysis written for a thoughtful human judge.\n"
        "- A beautiful edit is specific, source-weighted, and calm: it answers the reader's next question without sounding formulaic.\n"
        "- Prefer concrete sentences over stock phrases such as 'supporting this is', 'to ensure a complete picture', 'these points bound', or 'the primary evidence is rooted in'.\n"
        "- Keep citations attached to the claims they support, but make the sentence readable before the citation appears.\n\n"
        "Priorities:\n"
        "- First fix any prose-diagnostic warning that makes the memo look incomplete, especially unfinished_sentence_markers.\n"
        "- Then improve the BLUF, evidence-weighted reasoning, practical implication, stiff transitions, repeated phrasing, and citation-dense paragraphs when a local edit can preserve meaning.\n"
        "- If the memo ends with a truncated sentence, complete it from existing memo or guardrail content, or remove it when the same point already appears nearby.\n\n"
        "JSON schema:\n"
        "{\n"
        '  "edits": [\n'
        "    {\n"
        '      "target_text": "exact existing sentence, paragraph, or adjacent paragraph block from the memo",\n'
        '      "replacement_text": "localized replacement markdown",\n'
        '      "reason": "why this improves the read",\n'
        '      "intended_improvement": "bluf|evidence_weighting|narrative_logic|practical_implication|flow|transition|deduplication|citation_clutter|clarity|unsupported_side_point",\n'
        '      "edit_scope": "sentence|paragraph|paragraph_block"\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        "Rules:\n"
        "- Return valid JSON only.\n"
        "- Each target_text must be copied exactly from the memo and should occur once.\n"
        "- Replacement text may rewrite a paragraph or adjacent paragraph block for flow using existing facts, numbers, sources, populations, recommendations, and comparisons.\n"
        "- Preserve all source IDs and quantities that support the edited claim unless the edit removes a redundant or unsupported side point.\n"
        "- If a sentence is not useful for answering the decision question, remove it only when the surrounding memo still preserves the evidence-bearing point.\n"
        "- Propose edits that materially improve the read.\n"
        "- Keep headings intact unless the current heading itself is awkward.\n"
        "- If no safe improvement is available, return {\"edits\": []}.\n\n"
        f"Validation guardrails:\n{json.dumps(guardrails, indent=2, ensure_ascii=False)}\n\n"
        f"Current prose diagnostics:\n{json.dumps(prose_diagnostics, indent=2, ensure_ascii=False)}\n\n"
        f"Memo:\n{memo_for_model.strip()}\n"
    )


def parse_memo_ready_json_polish_response(raw: str) -> dict[str, Any]:
    payload = _parse_json_payload(raw)
    if not isinstance(payload, dict):
        return {
            "schema_id": "memo_ready_json_edit_polish_parse_report_v1",
            "status": "unparseable",
            "edits": [],
            "issues": ["response was not valid JSON object"],
        }
    edits = payload.get("edits")
    if not isinstance(edits, list):
        return {
            "schema_id": "memo_ready_json_edit_polish_parse_report_v1",
            "status": "missing_edits",
            "edits": [],
            "issues": ["JSON response did not include an edits list"],
        }
    valid_edits = [edit for edit in edits if isinstance(edit, dict)]
    issues = [] if len(valid_edits) == len(edits) else ["ignored non-object edit rows"]
    return {
        "schema_id": "memo_ready_json_edit_polish_parse_report_v1",
        "status": "parsed",
        "edits": valid_edits,
        "issues": issues,
    }


def candidate_for_json_polish_edit(current_memo: str, edit: dict[str, Any], packet: dict[str, Any]) -> dict[str, Any]:
    target = str(edit.get("target_text") or "")
    replacement = str(edit.get("replacement_text") or "")
    if not target.strip():
        return _candidate_report(False, current_memo, "missing_target_text")
    if not replacement.strip() and len(target.strip()) < 30:
        return _candidate_report(False, current_memo, "empty_replacement_for_short_target")
    count = current_memo.count(target)
    if count != 1:
        return _candidate_report(False, current_memo, "target_not_unique" if count else "target_not_found")
    citation_issue = _source_reference_issue(original=current_memo, replacement=replacement, packet=packet)
    if citation_issue:
        return _candidate_report(False, current_memo, citation_issue)
    candidate = current_memo.replace(target, replacement, 1)
    return _candidate_report(True, candidate, "")


def _lens_block(lens: dict[str, str] | None) -> str:
    if not lens:
        return ""
    return (
        "Polish lens:\n"
        f"- lens_id: {lens.get('lens_id')}\n"
        f"- name: {lens.get('name')}\n"
        f"- focus: {lens.get('focus')}\n\n"
    )


def _with_lens_metadata(edit: dict[str, Any], *, lens_id: str, edit_index: int) -> dict[str, Any]:
    row = dict(edit)
    row["polish_lens_id"] = lens_id
    row["polish_edit_index"] = edit_index
    return row


def _dedupe_parallel_edits(lens_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    edits: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for result in lens_results:
        for edit in _list(result.get("edits")):
            if not isinstance(edit, dict):
                continue
            key = (_norm(str(edit.get("target_text") or "")), _norm(str(edit.get("replacement_text") or "")))
            if key in seen:
                continue
            seen.add(key)
            edits.append(edit)
    return edits


def _public_lens_report(row: dict[str, Any]) -> dict[str, Any]:
    parse = row.get("parse_report") if isinstance(row.get("parse_report"), dict) else {}
    return {
        "lens_id": row.get("lens_id"),
        "name": row.get("name"),
        "status": parse.get("status", "not_run"),
        "edit_count": len(_list(row.get("edits"))),
        "issues": _list(parse.get("issues")) + _list(row.get("issues")),
    }


def _combined_lens_prompts(lens_results: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"<!-- polish lens: {row.get('lens_id')} -->\n{row.get('prompt', '')}" for row in lens_results
    )


def _combined_lens_raw(lens_results: list[dict[str, Any]]) -> str:
    return "\n\n".join(
        f"<!-- polish lens: {row.get('lens_id')} raw -->\n{row.get('raw', '')}" for row in lens_results
    )


def _candidate_report(applied: bool, memo: str, issue: str) -> dict[str, Any]:
    return {
        "schema_id": "memo_ready_json_edit_candidate_report_v1",
        "mechanically_applicable": applied,
        "memo": memo,
        "issue": issue,
    }


def _source_reference_issue(*, original: str, replacement: str, packet: dict[str, Any]) -> str:
    known = _known_source_ids(packet)
    if not known:
        return ""
    original_refs = _bracket_source_refs(original)
    for ref in _bracket_source_refs(replacement):
        if ref in known or ref in original_refs:
            continue
        return f"unknown_source_id:{ref}"
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
