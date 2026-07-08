from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.map_briefing_final_memo_diagnosis import (
    build_memo_final_diagnosis,
    build_memo_protected_spans,
)
from epistemic_case_mapper.map_briefing_packet_retention import build_memo_packet_retention_report
from epistemic_case_mapper.map_briefing_rewrite_edits import (
    NUMBER_RE,
    ReaderMemoEditSuggestion,
)
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.synthesis_uplift_packet import _parse_json

EDITORIAL_EDIT_TYPES = {
    "tighten_bluf",
    "add_payoff",
    "split_inventory",
    "smooth_transition",
    "shorten_sentence",
    "clarify_local_sentence",
    "remove_source_boilerplate",
    "remove_pipeline_leakage",
}
REMOVAL_EDIT_TYPES = {"remove_source_boilerplate", "remove_pipeline_leakage"}


def build_decision_memo_editorial_brief(memo: str, scaffold: dict[str, Any]) -> dict[str, Any]:
    """Build a bounded final-edit brief inspired by editorial-fit local packets."""

    sections = _sections(memo)
    diagnosis = build_memo_final_diagnosis(memo, {"question": str(scaffold.get("question", ""))})
    packets: list[dict[str, Any]] = []
    decision = sections.get("Decision Brief", "")
    if decision:
        packets.extend(_decision_brief_packets(decision))
    support = sections.get("What the Evidence Supports", "")
    if support:
        packets.extend(_evidence_payoff_packets(support, "What the Evidence Supports"))
    limits = sections.get("What Limits the Inference", "")
    if limits:
        packets.extend(_inventory_packets(limits, "What Limits the Inference"))
    packets.extend(_decision_memo_debris_packets(sections))
    packets.extend(_diagnosis_packets(diagnosis, memo))
    packets = _dedupe_packets(packets)
    packets.sort(key=lambda row: (-float(row.get("priority_score", 0) or 0), str(row.get("section", ""))))
    return {
        "schema_id": "decision_memo_editorial_brief_v1",
        "method": "local_decision_memo_edit_packets_with_patch_budget",
        "question": str(scaffold.get("question", "")).strip(),
        "patch_budget": {
            "max_edits": 4,
            "max_word_growth_percent": 3,
            "default_operation": "local_exact_replacement",
        },
        "findings": packets[:6],
        "preserve": [
            "decision question",
            "confidence line",
            "final source list",
            "bottom-line stance",
            "load-bearing numbers and confidence intervals unless the retention gate permits omission",
        ],
        "forbid": [
            "Do not add new facts, numbers, sources, populations, or recommendations.",
            "Do not rewrite unrelated sections.",
            "Do not remove uncertainty or caveats.",
            "Do not edit headings, the decision question, confidence line, or final Sources section.",
        ],
        "diagnosis": diagnosis,
    }


def run_decision_memo_editorial_pass(
    memo: str,
    scaffold: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    brief = build_decision_memo_editorial_brief(memo, scaffold)
    report: dict[str, Any] = {
        "schema_id": "decision_memo_editorial_pass_report_v1",
        "status": "not_run",
        "accepted": False,
        "brief": brief,
        "issues": [],
    }
    if backend.strip() == "prompt" or not brief["findings"]:
        report["status"] = "skipped_no_backend_or_findings"
        return {"memo": memo, "brief": brief, "prompt": "", "raw": "", "report": report}
    prompt = build_decision_memo_editorial_prompt(memo, brief)
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        report.update({"status": "backend_error_kept_original", "issues": [str(exc)]})
        return {"memo": memo, "brief": brief, "prompt": prompt, "raw": "", "report": report}
    raw = result.text
    if result.prompt_only:
        report.update({"status": "prompt_backend_kept_original", "issues": ["editorial backend returned prompt only"]})
        return {"memo": memo, "brief": brief, "prompt": prompt, "raw": raw, "report": report}
    payload = _parse_json(raw)
    if not isinstance(payload, dict) or not isinstance(payload.get("edits"), list):
        report.update({"status": "parse_failed_kept_original", "issues": ["editorial response was not JSON edits"]})
        return {"memo": memo, "brief": brief, "prompt": prompt, "raw": raw, "report": report}
    edit_result = _apply_editorial_edits(memo, payload, brief=brief)
    candidate = str(edit_result["memo"])
    gate_issues = _editorial_gate_issues(memo, candidate, scaffold, brief)
    accepted = bool(edit_result["applied_edits"]) and not gate_issues
    report.update(
        {
            "status": "accepted" if accepted else "rejected_kept_original",
            "accepted": accepted,
            "issues": gate_issues + edit_result["issues"],
            "raw_edit_count": edit_result["raw_edit_count"],
            "applied_edit_count": len(edit_result["applied_edits"]),
            "applied_edits": edit_result["applied_edits"],
            "skipped_edits": edit_result["skipped_edits"],
            "diagnosis_before": build_memo_final_diagnosis(memo, {"question": str(scaffold.get("question", ""))}),
            "diagnosis_after": build_memo_final_diagnosis(candidate, {"question": str(scaffold.get("question", ""))}),
        }
    )
    return {"memo": candidate if accepted else memo, "brief": brief, "prompt": prompt, "raw": raw, "report": report}


def build_decision_memo_editorial_prompt(memo: str, brief: dict[str, Any]) -> str:
    return (
        "You are a final decision-memo editor. Use the editorial brief to make only local edits that improve flow.\n"
        "Return JSON edits, not a rewritten memo.\n\n"
        "Rules:\n"
        "- Each edit must use exact target text from the memo and replace it once.\n"
        "- Make the smallest natural edit that resolves the finding.\n"
        "- Prefer rewriting the surrounding sentence or paragraph so restored evidence flows naturally.\n"
        "- Do not add new facts, numbers, sources, populations, or recommendations.\n"
        "- Do not edit headings, the decision question, confidence line, or final Sources section.\n"
        "- It is okay to compress or drop incidental numbers only when the core claim and caveat remain intact.\n"
        "- Use edit_type from allowed_edit_types.\n\n"
        "Return only valid JSON:\n"
        '{"edits":[{"target":"exact text","replacement":"replacement text","target_section":"section","edit_type":"tighten_bluf","reason":"brief reason"}]}\n\n'
        "Editorial brief:\n"
        f"{json.dumps(_model_facing_brief(brief), indent=2, ensure_ascii=False)}\n\n"
        "Memo:\n"
        f"{memo.strip()}\n"
    )


def _decision_brief_packets(markdown: str) -> list[dict[str, Any]]:
    paragraphs = _body_paragraphs(markdown)
    packets = []
    for paragraph in paragraphs[:2]:
        words = len(paragraph.split())
        if words > 85:
            packets.append(
                _packet(
                    "opening_answer_too_dense",
                    "Decision Brief",
                    paragraph,
                    "Compress the opening into a direct answer, the main evidence tension, and the practical boundary.",
                    "tighten_bluf",
                    priority=1.0,
                )
            )
    return packets


def _evidence_payoff_packets(markdown: str, section: str) -> list[dict[str, Any]]:
    packets = []
    for paragraph in _body_paragraphs(markdown):
        if len(paragraph.split()) < 45:
            continue
        if _number_count(paragraph) >= 2 and not _has_payoff_cue(paragraph):
            packets.append(
                _packet(
                    "evidence_without_payoff",
                    section,
                    paragraph,
                    "State what this evidence changes about the decision before moving on.",
                    "add_payoff",
                    priority=0.75,
                )
            )
    return packets


def _inventory_packets(markdown: str, section: str) -> list[dict[str, Any]]:
    packets = []
    for paragraph in _body_paragraphs(markdown):
        if paragraph.count(";") >= 1 or len(re.findall(r",|\band\b|\bor\b", paragraph)) >= 5:
            packets.append(
                _packet(
                    "inventory_shaped_prose",
                    section,
                    paragraph,
                    "Replace list-shaped prose with hierarchy: dominant caveat first, supporting details second.",
                    "split_inventory",
                    priority=0.65,
                )
            )
    return packets[:3]


def _decision_memo_debris_packets(sections: dict[str, str]) -> list[dict[str, Any]]:
    packets = []
    for section, markdown in sections.items():
        if section == "Sources":
            continue
        for paragraph in _body_paragraphs(markdown):
            if _has_source_boilerplate(paragraph):
                packets.append(
                    _packet(
                        "source_boilerplate_leakage",
                        section,
                        paragraph,
                        "Remove source-page boilerplate or quoted commentary that does not answer the decision question.",
                        "remove_source_boilerplate",
                        priority=0.9,
                    )
                )
            if _has_pipeline_leakage(paragraph):
                packets.append(
                    _packet(
                        "pipeline_leakage",
                        section,
                        paragraph,
                        "Remove internal process language and keep only the substantive uncertainty it implies, if any.",
                        "remove_pipeline_leakage",
                        priority=0.85,
                    )
                )
    return packets


def _diagnosis_packets(diagnosis: dict[str, Any], memo: str) -> list[dict[str, Any]]:
    packets = []
    prose = diagnosis.get("prose", {}) if isinstance(diagnosis.get("prose"), dict) else {}
    for issue in prose.get("issues", []) if isinstance(prose.get("issues"), list) else []:
        if not isinstance(issue, dict) or issue.get("kind") not in {"long_sentences", "dense_paragraphs"}:
            continue
        for item in issue.get("items", [])[:2] if isinstance(issue.get("items"), list) else []:
            text = str(item.get("text", "") if isinstance(item, dict) else "").strip()
            if text and text in memo:
                packets.append(
                    _packet(
                        str(issue.get("kind")),
                        str(item.get("section", "")) if isinstance(item, dict) else "",
                        text,
                        str(issue.get("message", "Improve local readability.")),
                        "shorten_sentence" if issue.get("kind") == "long_sentences" else "clarify_local_sentence",
                        priority=0.6,
                    )
                )
    return packets


def _apply_editorial_edits(memo: str, payload: dict[str, Any], *, brief: dict[str, Any]) -> dict[str, Any]:
    protected = build_memo_protected_spans(memo, {"question": str(brief.get("question", ""))})
    protected_texts = _hard_protected_texts(protected)
    candidate = memo
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    max_edits = int(brief.get("patch_budget", {}).get("max_edits", 4) or 4)
    for index, raw in enumerate(payload.get("edits", [])[:max_edits]):
        try:
            edit = ReaderMemoEditSuggestion.model_validate(raw)
        except Exception:
            skipped.append({"index": str(index), "reason": "edit was not a valid object"})
            continue
        issue = _editorial_edit_issue(candidate, edit, protected_texts)
        if issue:
            skipped.append({"index": str(index), "reason": issue, "target": edit.target[:120]})
            continue
        candidate = candidate.replace(edit.target.strip(), edit.replacement.strip(), 1)
        applied.append(
            {
                "index": str(index),
                "target": edit.target.strip(),
                "replacement": edit.replacement.strip(),
                "target_section": edit.target_section.strip(),
                "edit_type": edit.edit_type.strip(),
                "reason": edit.reason.strip(),
            }
        )
    return {
        "memo": _clean_memo_text(candidate),
        "raw_edit_count": len(payload.get("edits", [])),
        "applied_edits": applied,
        "skipped_edits": skipped,
        "issues": [row["reason"] for row in skipped],
    }


def _editorial_edit_issue(memo: str, edit: ReaderMemoEditSuggestion, protected_texts: set[str]) -> str:
    target = edit.target.strip()
    replacement = edit.replacement.strip()
    if edit.edit_type.strip() not in EDITORIAL_EDIT_TYPES:
        return "edit_type is not allowed for editorial pass"
    if not target:
        return "target is required"
    if not replacement and edit.edit_type.strip() not in REMOVAL_EDIT_TYPES:
        return "replacement is required for non-removal edits"
    if target == replacement:
        return "replacement is identical to target"
    if memo.count(target) != 1:
        return "target text was not found exactly once"
    if len(target) > 1400 or len(replacement) > 1400:
        return "edit exceeds local patch budget"
    if any(text and text in target for text in protected_texts):
        return "edit touches protected memo content"
    if "\n## " in target or "\n## " in replacement or target.startswith("##") or replacement.startswith("##"):
        return "top-level headings cannot be edited"
    before_numbers = set(NUMBER_RE.findall(target))
    after_numbers = set(NUMBER_RE.findall(replacement))
    if not after_numbers <= before_numbers:
        return "edit introduces unsupported numbers"
    return ""


def _editorial_gate_issues(before: str, after: str, scaffold: dict[str, Any], brief: dict[str, Any]) -> list[str]:
    issues = []
    before_diag = build_memo_final_diagnosis(before, {"question": str(scaffold.get("question", ""))})
    after_diag = build_memo_final_diagnosis(after, {"question": str(scaffold.get("question", ""))})
    packet = scaffold.get("decision_briefing_packet")
    before_retention = build_memo_packet_retention_report(before, packet if isinstance(packet, dict) else None)
    after_retention = build_memo_packet_retention_report(after, packet if isinstance(packet, dict) else None)
    if _int(after_retention.get("missing_critical_count")) > _int(before_retention.get("missing_critical_count")):
        issues.append("editorial edit increased critical packet-retention misses")
    if _int(after_retention.get("missing_high_count")) > _int(before_retention.get("missing_high_count")):
        issues.append("editorial edit increased high-priority packet-retention misses")
    if _new_numbers(before, after):
        issues.append("editorial edit introduced unsupported numbers")
    if _word_growth_exceeded(before, after, brief):
        issues.append("editorial edit exceeded word-growth patch budget")
    if not _editorial_diagnosis_improved_or_preserved(before_diag, after_diag):
        issues.append("editorial edit did not improve or preserve final-memo readability diagnostics")
    return issues


def _editorial_diagnosis_improved_or_preserved(before: dict[str, Any], after: dict[str, Any]) -> bool:
    before_metrics = before.get("metrics", {}) if isinstance(before.get("metrics"), dict) else {}
    after_metrics = after.get("metrics", {}) if isinstance(after.get("metrics"), dict) else {}
    keys = ("long_sentence_count", "dense_paragraph_count", "awkward_phrase_count", "diagnostic_leakage_count")
    improved = any(_int(after_metrics.get(key)) < _int(before_metrics.get(key)) for key in keys)
    worsened = any(_int(after_metrics.get(key)) > _int(before_metrics.get(key)) for key in keys)
    return improved or not worsened


def _sections(markdown: str) -> dict[str, str]:
    matches = list(re.finditer(r"^##\s+(.+?)\s*$", markdown, flags=re.MULTILINE))
    sections: dict[str, str] = {}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        sections[match.group(1).strip()] = markdown[match.end():end].strip()
    return sections


def _body_paragraphs(markdown: str) -> list[str]:
    paragraphs = []
    for paragraph in re.split(r"\n\s*\n", markdown):
        text = re.sub(r"\s+", " ", paragraph).strip()
        if text and not text.startswith("#") and not text.startswith("**Decision question:**") and not text.startswith("**Confidence:**"):
            paragraphs.append(text)
    return paragraphs


def _packet(code: str, section: str, text: str, action: str, edit_type: str, *, priority: float) -> dict[str, Any]:
    return {
        "code": code,
        "section": section or "unknown",
        "evidence_text": _short(text, 900),
        "recommended_move": action,
        "allowed_edit_types": [edit_type],
        "priority_score": priority,
        "forbidden_edits": [
            "Do not add unsupported evidence.",
            "Do not change the bottom-line stance.",
            "Do not edit protected metadata or sources.",
        ],
    }


def _model_facing_brief(brief: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_id": brief.get("schema_id"),
        "question": brief.get("question"),
        "patch_budget": brief.get("patch_budget"),
        "allowed_edit_types": sorted(EDITORIAL_EDIT_TYPES),
        "findings": brief.get("findings", [])[:6],
        "preserve": brief.get("preserve", []),
        "forbid": brief.get("forbid", []),
    }


def _has_payoff_cue(text: str) -> bool:
    return bool(re.search(r"\b(?:therefore|so|means|matters|suggests|supports|changes|decision|recommendation|practically)\b", text, flags=re.IGNORECASE))


def _has_source_boilerplate(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:all health/medical information|content editorial process|she said|he said|this website|reviewed and approved)\b",
            text,
            flags=re.IGNORECASE,
        )
    )


def _has_pipeline_leakage(text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:malformed for review|excluded from this synthesis|high-priority evidence was excluded|packet|artifact|validator|pipeline)\b",
            text,
            flags=re.IGNORECASE,
        )
    )


def _number_count(text: str) -> int:
    return len(NUMBER_RE.findall(text))


def _hard_protected_texts(protected_spans: dict[str, Any]) -> set[str]:
    hard = {"decision_question", "section_heading", "confidence_line", "sources_section"}
    return {
        str(span.get("text", "")).strip()
        for span in protected_spans.get("spans", []) if isinstance(span, dict) and str(span.get("kind", "")) in hard and str(span.get("text", "")).strip()
    }


def _new_numbers(before: str, after: str) -> set[str]:
    return set(NUMBER_RE.findall(after)) - set(NUMBER_RE.findall(before))


def _word_growth_exceeded(before: str, after: str, brief: dict[str, Any]) -> bool:
    before_count = len(before.split())
    if before_count <= 0:
        return False
    growth = len(after.split()) - before_count
    allowed = int(brief.get("patch_budget", {}).get("max_word_growth_percent", 3) or 3)
    return growth > max(10, round(before_count * allowed / 100))


def _dedupe_packets(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen = set()
    deduped = []
    for packet in packets:
        key = (packet.get("code"), packet.get("section"), packet.get("evidence_text"))
        if key not in seen:
            seen.add(key)
            deduped.append(packet)
    return deduped


def _clean_memo_text(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", "\n".join(line.rstrip() for line in text.strip().splitlines())).strip() + "\n"


def _short(text: str, max_chars: int) -> str:
    compact = re.sub(r"\s+", " ", text).strip()
    return compact if len(compact) <= max_chars else compact[: max_chars - 3].rstrip() + "..."


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
