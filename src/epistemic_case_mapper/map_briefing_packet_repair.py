from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.map_briefing_markdown_quality import markdown_structure_issues, repair_markdown_structure
from epistemic_case_mapper.map_briefing_packet_retention import build_memo_packet_retention_report
from epistemic_case_mapper.model_backends import run_model_backend


def run_packet_retention_repair(
    memo: str,
    packet: dict[str, Any] | None,
    retention_report: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    packet = packet if isinstance(packet, dict) else {}
    issues = [issue for issue in retention_report.get("issues", []) if isinstance(issue, dict)]
    prompt = build_packet_retention_repair_prompt(memo, packet, retention_report)
    report: dict[str, Any] = {
        "schema_id": "packet_retention_repair_report_v1",
        "status": "not_needed" if not issues else "not_run",
        "accepted": False,
        "initial_issue_count": len(issues),
        "initial_missing_critical_count": retention_report.get("missing_critical_count", 0),
        "issues": [],
    }
    if not packet or not issues:
        return {"memo": memo, "prompt": "", "raw": "", "report": report}
    if backend.strip() == "prompt":
        report.update({"status": "skipped_prompt_backend", "issues": ["packet retention repair backend returned prompt only"]})
        return {"memo": memo, "prompt": prompt, "raw": "", "report": report}
    try:
        result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    except RuntimeError as exc:
        report.update({"status": "backend_error_kept_original", "issues": [str(exc)]})
        return {"memo": memo, "prompt": prompt, "raw": "", "report": report}
    raw = result.text
    if result.prompt_only:
        report.update({"status": "prompt_backend_kept_original", "issues": ["packet retention repair backend returned prompt only"]})
        return {"memo": memo, "prompt": prompt, "raw": raw, "report": report}
    candidate = repair_markdown_structure(_extract_markdown(raw))
    if not candidate:
        report.update({"status": "empty_response_kept_original", "issues": ["packet repair returned empty markdown"]})
        return {"memo": memo, "prompt": prompt, "raw": raw, "report": report}
    after = build_memo_packet_retention_report(candidate, packet)
    structure_issues = markdown_structure_issues(candidate, original=memo)
    accepted = _retention_improved(retention_report, after) and not structure_issues
    report.update(
        {
            "status": "accepted" if accepted else "no_retention_improvement_kept_original",
            "accepted": accepted,
            "final_issue_count": len(after.get("issues", [])),
            "final_missing_critical_count": after.get("missing_critical_count", 0),
            "final_retained_must_retain_count": after.get("retained_must_retain_count", 0),
            "structure_issues": structure_issues,
            "issues": [] if accepted else ["packet repair did not improve deterministic retention audit without damaging Markdown structure"],
            "final_retention_report": after,
        }
    )
    return {"memo": candidate if accepted else memo, "prompt": prompt, "raw": raw, "report": report}


def build_packet_retention_repair_prompt(
    memo: str,
    packet: dict[str, Any],
    retention_report: dict[str, Any],
) -> str:
    repair_packet = _repair_packet(packet, retention_report)
    return (
        "You are repairing a decision briefing memo after a packet-retention audit found missing decision-critical content.\n"
        "Use only the current memo and the targeted repair packet below.\n\n"
        "Rules:\n"
        "- Return the full revised memo in Markdown, not JSON.\n"
        "- Do not add new sources, quantities, populations, causal claims, or recommendations beyond the repair packet.\n"
        "- Preserve the decision question, confidence line, and Sources section if present.\n"
        "- Add the smallest necessary sentence or clause in the most relevant existing section.\n"
        "- Preserve exact quantities and source labels from the repair packet.\n"
        "- If a listed issue cannot be fixed from the repair packet alone, leave that issue unresolved rather than guessing.\n\n"
        "Targeted repair packet:\n"
        f"{json.dumps(repair_packet, indent=2, ensure_ascii=False)}\n\n"
        "Current memo:\n"
        f"{memo.strip()}\n"
    )


def _repair_packet(packet: dict[str, Any], retention_report: dict[str, Any]) -> dict[str, Any]:
    retained_lookup = {
        str(row.get("item_id", "")).strip(): row
        for row in retention_report.get("retained_items", [])
        if isinstance(row, dict) and str(row.get("item_id", "")).strip()
    }
    retain_source = {
        str(row.get("item_id", "")).strip(): row
        for row in packet.get("must_retain_ledger", [])
        if isinstance(row, dict) and str(row.get("item_id", "")).strip()
    }
    bundles = {
        str(row.get("bundle_id", "")).strip(): row
        for row in packet.get("evidence_bundles", [])
        if isinstance(row, dict) and str(row.get("bundle_id", "")).strip()
    }
    missing_items = []
    for issue in retention_report.get("issues", []) if isinstance(retention_report.get("issues"), list) else []:
        if not isinstance(issue, dict) or issue.get("issue_type") != "missing_must_retain_item":
            continue
        item_id = str(issue.get("item_id") or "").strip()
        source = retain_source.get(item_id, {})
        retained = retained_lookup.get(item_id, {})
        bundle_rows = [_compact_bundle(bundles[bundle_id]) for bundle_id in retained.get("bundle_ids", []) if bundle_id in bundles]
        missing_items.append(
            {
                "item_id": item_id,
                "decision_role": source.get("decision_role") or issue.get("decision_role"),
                "importance": source.get("importance") or issue.get("severity"),
                "statement": source.get("statement"),
                "required_terms": source.get("required_terms", []),
                "missing_required_terms": issue.get("missing_required_terms", []),
                "missing_source_labels": issue.get("missing_source_labels", []),
                "why_it_matters": source.get("why_it_matters"),
                "section_targets": source.get("section_targets", []),
                "supporting_bundles": bundle_rows,
            }
        )
    return {
        "schema_id": "packet_retention_repair_packet_v1",
        "decision_question": packet.get("decision_question"),
        "answer_frame": packet.get("answer_frame", {}),
        "missing_items": missing_items[:12],
        "source_trail": packet.get("source_trail", []),
    }


def _compact_bundle(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "bundle_id": row.get("bundle_id"),
        "decision_role": row.get("decision_role"),
        "claim": row.get("claim"),
        "source_labels": row.get("source_labels", []),
        "quantity_values": row.get("quantity_values", []),
        "why_it_matters": row.get("why_it_matters"),
        "limits": row.get("limits", []),
    }


def _retention_improved(before: dict[str, Any], after: dict[str, Any]) -> bool:
    before_critical = int(before.get("missing_critical_count", 0) or 0)
    after_critical = int(after.get("missing_critical_count", 0) or 0)
    if after_critical < before_critical:
        return True
    before_issues = len(before.get("issues", []) if isinstance(before.get("issues"), list) else [])
    after_issues = len(after.get("issues", []) if isinstance(after.get("issues"), list) else [])
    before_retained = int(before.get("retained_must_retain_count", 0) or 0)
    after_retained = int(after.get("retained_must_retain_count", 0) or 0)
    return after_issues < before_issues and after_retained >= before_retained


def _extract_markdown(raw: str) -> str:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:markdown|md)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned).strip()
    if cleaned.startswith("{") or cleaned.startswith("["):
        return ""
    return _clean_markdown(cleaned)


def _clean_markdown(text: str) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    collapsed: list[str] = []
    blank = False
    for line in lines:
        is_blank = not line.strip()
        if is_blank and blank:
            continue
        collapsed.append(line)
        blank = is_blank
    return "\n".join(collapsed).strip() + "\n"
