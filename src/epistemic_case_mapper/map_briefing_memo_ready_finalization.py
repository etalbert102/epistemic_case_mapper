from __future__ import annotations

import ast
import json
import re
from typing import Any

from epistemic_case_mapper.map_briefing_markdown_quality import markdown_structure_issues, repair_markdown_structure
from epistemic_case_mapper.map_briefing_memo_ready_packet import build_memo_ready_packet_synthesis_prompt
from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    norm as _norm,
    string_list as _string_list,
)
from epistemic_case_mapper.map_briefing_memo_warning_packet import (
    build_warning_resolution_report,
    unresolved_warning_repair_items,
)
from epistemic_case_mapper.model_backends import run_model_backend


def run_memo_ready_packet_synthesis(
    memo_ready_packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    prompt = build_memo_ready_packet_synthesis_prompt(memo_ready_packet)
    draft = render_memo_ready_packet_draft(memo_ready_packet)
    report = {
        "schema_id": "memo_ready_packet_synthesis_report_v1",
        "status": "deterministic_fallback" if backend.strip() == "prompt" else "not_run",
        "accepted": backend.strip() == "prompt",
        "used_default_path": True,
        "issues": [],
    }
    if backend.strip() == "prompt":
        return {"memo": draft, "prompt": prompt, "raw": "", "report": report}
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        report.update({"status": "backend_error_deterministic_fallback", "issues": [str(exc)]})
        return {"memo": draft, "prompt": prompt, "raw": "", "report": report}
    raw = result.text
    candidate = repair_markdown_structure(_extract_markdown(raw))
    if not candidate:
        report.update({"status": "empty_or_unparseable_deterministic_fallback", "issues": ["synthesis returned no markdown"]})
        return {"memo": draft, "prompt": prompt, "raw": raw, "report": report}
    retention = build_memo_ready_packet_retention_report(candidate, memo_ready_packet)
    accepted = _acceptable_synthesis(candidate, retention)
    report.update(
        {
            "status": "accepted" if accepted else "accepted_with_retention_warnings",
            "accepted": True,
            "retention_status": retention.get("status"),
            "missing_mandatory_count": retention.get("missing_mandatory_count", 0),
            "unresolved_warning_count": retention.get("unresolved_warning_count", 0),
            "warning_resolution_report": retention.get("warning_resolution_report", {}),
            "issues": [] if accepted else ["synthesis has packet-retention warnings"],
        }
    )
    return {"memo": candidate, "prompt": prompt, "raw": raw, "report": report}


def render_memo_ready_packet_draft(packet: dict[str, Any]) -> str:
    spine = _dict(packet.get("answer_spine"))
    items = _list(packet.get("evidence_items"))
    question = str(packet.get("decision_question") or "").strip()
    lines = [
        "## Decision Brief",
        "",
        f"**Decision question:** {question or 'not specified'}",
        "",
        _spine_text(spine.get("default_read")) or "The packet does not establish a clear default read.",
    ]
    confidence = str(spine.get("confidence") or "").strip()
    if confidence:
        lines.extend(["", f"**Confidence:** {confidence}"])
    support = _item_lines(items, {"strongest_support", "quantitative_anchor"})
    if support:
        lines.extend(["", "## What the Evidence Supports", "", *support])
    limits = _item_lines(items, {"strongest_counterweight", "scope_boundary"})
    if limits:
        lines.extend(["", "## What Limits the Inference", "", *limits])
    cruxes = _item_lines(items, {"decision_crux"})
    if cruxes:
        lines.extend(["", "## Decision Cruxes", "", *cruxes])
    sources = _source_lines(packet)
    if sources:
        lines.extend(["", "## Sources", "", *sources])
    return "\n".join(lines).rstrip() + "\n"


def build_memo_ready_packet_retention_report(memo: str, packet: dict[str, Any]) -> dict[str, Any]:
    source_aliases = _source_alias_lookup(packet)
    statuses = [_item_retention_status(memo, item, source_aliases) for item in _mandatory_items(packet)]
    item_issues = [row for row in statuses if not row["retained"]]
    warning_resolution = build_warning_resolution_report(
        memo,
        _dict(packet.get("memo_warning_packet")),
        source_aliases=source_aliases,
    )
    warning_issues = [
        {
            "issue_type": "unresolved_memo_warning",
            "warning_status": row.get("status"),
            "severity": row.get("severity"),
            "warning_id": row.get("warning_id"),
            "warning_type": row.get("warning_type"),
            "claim": row.get("claim"),
            "source_labels": row.get("source_labels", []),
            "missing_anchor_terms": row.get("missing_anchor_terms", []),
        }
        for row in _list(warning_resolution.get("warnings_needing_repair"))
        if isinstance(row, dict)
    ]
    issues = [*item_issues, *warning_issues]
    return {
        "schema_id": "memo_ready_packet_retention_report_v1",
        "status": "ready" if not issues else "warning",
        "must_retain_count": len(statuses),
        "retained_must_retain_count": sum(1 for row in statuses if row["retained"]),
        "missing_critical_count": len(item_issues),
        "missing_high_count": 0,
        "mandatory_item_count": len(statuses),
        "retained_mandatory_count": sum(1 for row in statuses if row["retained"]),
        "missing_mandatory_count": len(item_issues),
        "missing_quantity_count": sum(len(row.get("missing_quantities", [])) for row in item_issues),
        "unresolved_warning_count": len(warning_issues),
        "warning_resolution_report": warning_resolution,
        "item_statuses": statuses,
        "warning_issues": warning_issues,
        "issues": issues,
    }


def run_memo_ready_packet_repair(
    memo: str,
    packet: dict[str, Any],
    retention_report: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    prompt = build_memo_ready_packet_repair_prompt(memo, packet, retention_report)
    report = {
        "schema_id": "memo_ready_packet_repair_report_v1",
        "status": "not_needed" if not retention_report.get("issues") else "not_run",
        "accepted": False,
        "initial_missing_mandatory_count": retention_report.get("missing_mandatory_count", 0),
        "initial_unresolved_warning_count": retention_report.get("unresolved_warning_count", 0),
        "issues": [],
    }
    if not retention_report.get("issues"):
        return {"memo": memo, "prompt": "", "raw": "", "report": report}
    if backend.strip() == "prompt":
        report.update({"status": "skipped_prompt_backend", "issues": ["memo-ready repair backend returned prompt only"]})
        return {"memo": memo, "prompt": prompt, "raw": "", "report": report}
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        report.update({"status": "backend_error_kept_original", "issues": [str(exc)]})
        return {"memo": memo, "prompt": prompt, "raw": "", "report": report}
    raw = result.text
    candidate = repair_markdown_structure(_extract_markdown(raw))
    if not candidate:
        report.update({"status": "empty_response_kept_original", "issues": ["repair returned no markdown"]})
        return {"memo": memo, "prompt": prompt, "raw": raw, "report": report}
    after = build_memo_ready_packet_retention_report(candidate, packet)
    structure_issues = markdown_structure_issues(candidate, original=memo)
    accepted = _retention_improved(retention_report, after) and not structure_issues
    report.update(
        {
            "status": "accepted" if accepted else "no_retention_improvement_kept_original",
            "accepted": accepted,
            "final_missing_mandatory_count": after.get("missing_mandatory_count", 0),
            "final_retained_mandatory_count": after.get("retained_mandatory_count", 0),
            "final_unresolved_warning_count": after.get("unresolved_warning_count", 0),
            "final_retention_report": after,
            "structure_issues": structure_issues,
            "issues": [] if accepted else ["repair did not improve packet retention without markdown damage"],
        }
    )
    return {"memo": candidate if accepted else memo, "prompt": prompt, "raw": raw, "report": report}


def build_memo_ready_packet_repair_prompt(memo: str, packet: dict[str, Any], retention_report: dict[str, Any]) -> str:
    warning_packet = _dict(packet.get("memo_warning_packet"))
    warning_resolution = _dict(retention_report.get("warning_resolution_report"))
    repair_packet = {
        "decision_question": packet.get("decision_question"),
        "missing_items": [
            _repair_item(packet, issue)
            for issue in _list(retention_report.get("issues"))[:8]
            if isinstance(issue, dict) and issue.get("issue_type") == "missing_memo_ready_item"
        ],
        "unresolved_warnings": unresolved_warning_repair_items(warning_resolution, warning_packet, limit=8),
    }
    return (
        "You are repairing a decision memo using only a memo-ready evidence repair packet.\n"
        "Rewrite the affected paragraph or section naturally; do not append orphan facts.\n\n"
        "Rules:\n"
        "- Return the full revised memo in Markdown, not JSON.\n"
        "- Preserve the decision question, source labels, quantities, and answer stance already present.\n"
        "- Use only the missing items in the repair packet; do not introduce new evidence.\n"
        "- For unresolved warnings, incorporate the source-backed claim if it changes the read; otherwise use it to bound scope, confidence, or remaining uncertainty.\n"
        "- For each quantity you add, explain what it means for the decision.\n"
        "- Do not mention packet IDs, validation, telemetry, or internal pipeline machinery.\n\n"
        f"Repair packet:\n{json.dumps(repair_packet, indent=2, ensure_ascii=False)}\n\n"
        f"Current memo:\n{memo.strip()}\n"
    )


def run_memo_ready_final_polish(
    memo: str,
    packet: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    before = build_memo_ready_packet_retention_report(memo, packet)
    prompt = build_memo_ready_final_polish_prompt(memo, packet)
    report = {
        "schema_id": "memo_ready_final_polish_report_v1",
        "status": "skipped_prompt_backend" if backend.strip() == "prompt" else "not_run",
        "accepted": False,
        "issues": [],
    }
    if backend.strip() == "prompt":
        return {"memo": memo, "prompt": prompt, "raw": "", "report": report}
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        report.update({"status": "backend_error_kept_original", "issues": [str(exc)]})
        return {"memo": memo, "prompt": prompt, "raw": "", "report": report}
    raw = result.text
    candidate = repair_markdown_structure(_extract_markdown(raw))
    if not candidate:
        report.update({"status": "empty_response_kept_original", "issues": ["final polish returned no markdown"]})
        return {"memo": memo, "prompt": prompt, "raw": raw, "report": report}
    after = build_memo_ready_packet_retention_report(candidate, packet)
    structure_issues = markdown_structure_issues(candidate, original=memo)
    accepted = _retention_not_worse(before, after) and not structure_issues
    report.update(
        {
            "status": "accepted" if accepted else "rejected_kept_original",
            "accepted": accepted,
            "before_missing_mandatory_count": before.get("missing_mandatory_count", 0),
            "after_missing_mandatory_count": after.get("missing_mandatory_count", 0),
            "structure_issues": structure_issues,
            "issues": [] if accepted else ["final polish regressed retention or damaged markdown"],
        }
    )
    return {"memo": candidate if accepted else memo, "prompt": prompt, "raw": raw, "report": report}


def run_memo_ready_presentation_normalization(memo: str, packet: dict[str, Any]) -> dict[str, Any]:
    """Apply deterministic presentation-only fixes without changing analysis."""
    question = str(packet.get("decision_question") or "").strip()
    source_aliases = _source_alias_replacements(packet)
    normalized = str(memo or "").strip()
    changes: list[str] = []
    if question:
        next_memo = _ensure_decision_question(normalized, question)
        if next_memo != normalized:
            changes.append("inserted_decision_question")
            normalized = next_memo
    next_memo = _replace_source_aliases(normalized, source_aliases)
    if next_memo != normalized:
        changes.append("normalized_source_labels")
        normalized = next_memo
    normalized = normalized.rstrip() + "\n"
    return {
        "memo": normalized,
        "prompt": "",
        "raw": "",
        "report": {
            "schema_id": "memo_ready_presentation_normalization_report_v1",
            "status": "changed" if changes else "no_changes",
            "accepted": True,
            "changes": changes,
            "source_alias_count": len(source_aliases),
            "issues": [],
        },
    }


def build_memo_ready_final_polish_prompt(memo: str, packet: dict[str, Any]) -> str:
    protected = {
        "decision_question": packet.get("decision_question"),
        "mandatory_items": [
            {
                "source_label": item.get("source_label"),
                "reader_claim": item.get("reader_claim"),
                "quantities": item.get("quantities", []),
            }
            for item in _mandatory_items(packet)[:18]
        ],
        "memo_warnings": _list(_dict(packet.get("memo_warning_packet")).get("warnings"))[:8],
    }
    return (
        "You are doing a final prose polish on a source-grounded decision memo.\n"
        "Improve flow and remove awkward wording while preserving every protected source-backed item.\n\n"
        "Rules:\n"
        "- Return the full revised memo in Markdown, not JSON.\n"
        "- Do not drop protected quantities, source labels, caveats, counterweights, or scope boundaries.\n"
        "- Preserve or naturally integrate protected warning evidence; if it is only a limitation, keep it as a limitation.\n"
        "- Do not add facts or sources beyond the memo and protected item list.\n"
        "- Make the memo read like decision-ready analysis, not a checklist.\n\n"
        f"Protected item list:\n{json.dumps(protected, indent=2, ensure_ascii=False)}\n\n"
        f"Memo:\n{memo.strip()}\n"
    )


def _item_lines(items: list[Any], roles: set[str]) -> list[str]:
    lines = []
    for item in items:
        if not isinstance(item, dict) or item.get("role") not in roles:
            continue
        source = str(item.get("source_label") or "").strip()
        suffix = f" [{source}]" if source else ""
        quantities = _quantity_clause(item)
        lines.append(f"- {item.get('reader_claim')}{quantities}{suffix}")
    return lines


def _source_lines(packet: dict[str, Any]) -> list[str]:
    rows = []
    for source in _list(packet.get("source_trail")):
        if not isinstance(source, dict):
            continue
        label = str(source.get("source_label") or "").strip()
        url = str(source.get("source_url") or "").strip()
        if label and url:
            rows.append(f"- [{label}]({url})")
        elif label:
            rows.append(f"- {label}")
    return _dedupe(rows)


def _ensure_decision_question(memo: str, question: str) -> str:
    if _contains_text(memo, question):
        return memo
    line = f"**Decision question:** {question}"
    lines = memo.splitlines()
    if not lines:
        return f"## Decision Brief\n\n{line}\n"
    for index, existing in enumerate(lines):
        if existing.strip().lower() == "## decision brief":
            insert_at = index + 1
            while insert_at < len(lines) and not lines[insert_at].strip():
                insert_at += 1
            return "\n".join([*lines[: index + 1], "", line, "", *lines[insert_at:]])
    return f"## Decision Brief\n\n{line}\n\n{memo.strip()}"


def _replace_source_aliases(memo: str, replacements: dict[str, str]) -> str:
    normalized = memo
    for source_label, display in sorted(replacements.items(), key=lambda item: len(item[0]), reverse=True):
        if source_label and display and source_label != display:
            normalized = normalized.replace(source_label, display)
    return normalized


def _source_alias_replacements(packet: dict[str, Any]) -> dict[str, str]:
    labels = [
        str(source.get("source_label") or "").strip()
        for source in _list(packet.get("source_trail"))
        if isinstance(source, dict) and str(source.get("source_label") or "").strip()
    ]
    common_prefix = _common_token_prefix(labels)
    replacements: dict[str, str] = {}
    for source in _list(packet.get("source_trail")):
        if not isinstance(source, dict):
            continue
        source_label = str(source.get("source_label") or "").strip()
        if not source_label:
            continue
        display = _preferred_source_display(source, common_prefix=common_prefix)
        if display and display != source_label:
            replacements[source_label] = display
    return replacements


def _source_alias_lookup(packet: dict[str, Any]) -> dict[str, list[str]]:
    replacements = _source_alias_replacements(packet)
    aliases: dict[str, list[str]] = {}
    for source in _list(packet.get("source_trail")):
        if not isinstance(source, dict):
            continue
        source_label = str(source.get("source_label") or "").strip()
        if not source_label:
            continue
        values = [
            source_label,
            replacements.get(source_label, ""),
            str(source.get("display_label") or "").strip(),
            str(source.get("citation_label") or "").strip(),
        ]
        aliases[source_label] = _dedupe(value for value in values if value)
    return aliases


def _source_aliases_for_label(source_label: str, source_aliases: dict[str, list[str]]) -> list[str]:
    if source_label in source_aliases:
        return source_aliases[source_label]
    normalized = _norm(source_label)
    for label, aliases in source_aliases.items():
        if _norm(label) == normalized:
            return aliases
    return []


def _preferred_source_display(source: dict[str, Any], *, common_prefix: list[str]) -> str:
    label = str(source.get("source_label") or "").strip()
    for key in ("citation_label", "display_label"):
        value = str(source.get(key) or "").strip()
        if value and value != label:
            return value
    if common_prefix:
        tokens = label.split()
        if [token.lower() for token in tokens[: len(common_prefix)]] == [token.lower() for token in common_prefix]:
            stripped = " ".join(tokens[len(common_prefix) :]).strip()
            if stripped:
                return stripped
    return label


def _common_token_prefix(labels: list[str]) -> list[str]:
    tokenized = [label.split() for label in labels if label.strip()]
    if len(tokenized) < 2:
        return []
    prefix: list[str] = []
    for tokens in zip(*tokenized):
        lowered = {token.lower() for token in tokens}
        if len(lowered) != 1:
            break
        prefix.append(tokens[0])
    if len(prefix) < 2:
        return []
    shortest_remainder = min((len(tokens) - len(prefix) for tokens in tokenized), default=0)
    return prefix if shortest_remainder >= 2 else []


def _quantity_clause(item: dict[str, Any]) -> str:
    quantities = []
    for quantity in _list(item.get("quantities")):
        if not isinstance(quantity, dict):
            continue
        value = str(quantity.get("value") or "").strip()
        interpretation = str(quantity.get("interpretation") or "").strip()
        if value and interpretation:
            quantities.append(f"{value}: {interpretation}")
        elif value:
            quantities.append(value)
    return f" ({'; '.join(quantities)})" if quantities else ""


def _spine_text(value: Any) -> str:
    if isinstance(value, dict):
        return _best_spine_field(value)
    text = str(value or "").strip()
    parsed = _parse_python_literal(text)
    if isinstance(parsed, dict):
        return _best_spine_field(parsed)
    return text


def _best_spine_field(value: dict[str, Any]) -> str:
    for key in ("current_read", "default_read", "primary_answer", "answer_stance", "classification"):
        text = str(value.get(key) or "").strip()
        if text:
            return text
    return ""


def _parse_python_literal(text: str) -> Any:
    if not text.startswith("{"):
        return None
    try:
        return ast.literal_eval(text)
    except (SyntaxError, ValueError):
        return None


def _mandatory_items(packet: dict[str, Any]) -> list[dict[str, Any]]:
    return [item for item in _list(packet.get("evidence_items")) if isinstance(item, dict) and item.get("must_use")]


def _item_retention_status(memo: str, item: dict[str, Any], source_aliases: dict[str, list[str]] | None = None) -> dict[str, Any]:
    claim = str(item.get("reader_claim") or "").strip()
    source = str(item.get("source_label") or "").strip()
    quantities = [
        str(quantity.get("value") or "").strip()
        for quantity in _list(item.get("quantities"))
        if isinstance(quantity, dict) and str(quantity.get("value") or "").strip()
    ]
    missing_quantities = [quantity for quantity in quantities if not _contains_quantity(memo, quantity)]
    aliases = _dedupe([source, *(_source_aliases_for_label(source, source_aliases or {}) if source else [])])
    source_retained = not source or any(_contains_text(memo, alias) for alias in aliases)
    claim_retained = _mentions_enough_content_terms(memo, claim, minimum=4)
    retained = source_retained and claim_retained and not missing_quantities
    return {
        "item_id": item.get("item_id"),
        "severity": "critical",
        "issue_type": "missing_memo_ready_item",
        "role": item.get("role"),
        "retained": retained,
        "source_retained": source_retained,
        "claim_retained": claim_retained,
        "missing_quantities": missing_quantities,
        "reader_claim": claim,
        "source_label": source,
    }


def _repair_item(packet: dict[str, Any], issue: dict[str, Any]) -> dict[str, Any]:
    item_id = str(issue.get("item_id") or "")
    item = next((row for row in _mandatory_items(packet) if str(row.get("item_id") or "") == item_id), {})
    return {
        "item_id": item_id,
        "preferred_role": item.get("role"),
        "reader_claim": item.get("reader_claim"),
        "source_label": item.get("source_label"),
        "quantities": item.get("quantities", []),
        "decision_relevance": item.get("decision_relevance"),
        "caveat": item.get("caveat"),
        "missing_quantities": issue.get("missing_quantities", []),
    }


def _acceptable_synthesis(memo: str, retention: dict[str, Any]) -> bool:
    return bool(memo.strip()) and int(retention.get("missing_mandatory_count", 0) or 0) <= 2


def _retention_improved(before: dict[str, Any], after: dict[str, Any]) -> bool:
    before_missing = int(before.get("missing_mandatory_count", 0) or 0)
    after_missing = int(after.get("missing_mandatory_count", 0) or 0)
    if after_missing < before_missing:
        return True
    before_warnings = int(before.get("unresolved_warning_count", 0) or 0)
    after_warnings = int(after.get("unresolved_warning_count", 0) or 0)
    if after_warnings < before_warnings:
        return True
    return int(after.get("missing_quantity_count", 0) or 0) < int(before.get("missing_quantity_count", 0) or 0)


def _retention_not_worse(before: dict[str, Any], after: dict[str, Any]) -> bool:
    return (
        int(after.get("missing_mandatory_count", 0) or 0) <= int(before.get("missing_mandatory_count", 0) or 0)
        and int(after.get("unresolved_warning_count", 0) or 0) <= int(before.get("unresolved_warning_count", 0) or 0)
    )


def _extract_markdown(raw: str) -> str:
    cleaned = str(raw).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:markdown|md|json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    payload = _parse_json(cleaned)
    if isinstance(payload, dict):
        for key in ("memo_markdown", "markdown", "memo", "text"):
            value = payload.get(key)
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


def _contains_text(text: str, needle: str) -> bool:
    needle = str(needle).strip()
    return not needle or needle.lower() in text.lower()


def _contains_quantity(text: str, quantity: str) -> bool:
    if _contains_text(text, quantity):
        return True
    normalized_text = _norm(text)
    numbers = re.findall(r"\d+(?:\.\d+)?", quantity)
    return bool(numbers) and all(number in normalized_text for number in numbers)


def _mentions_enough_content_terms(text: str, statement: str, *, minimum: int) -> bool:
    terms = _content_terms(statement)
    if not terms:
        return True
    required = min(minimum, len(terms))
    lowered = text.lower()
    return sum(1 for term in terms if term in lowered) >= required


def _content_terms(text: str) -> list[str]:
    stop = {"about", "after", "also", "because", "before", "between", "could", "from", "have", "into", "only", "should", "that", "their", "there", "this", "when", "where", "with", "would"}
    return _dedupe([term.lower() for term in re.findall(r"[A-Za-z][A-Za-z-]{2,}", text) if term.lower() not in stop])
