from __future__ import annotations

import json
import os
from typing import Any, Iterable

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
    string_list as _string_list,
)
from epistemic_case_mapper.model_backends import run_model_backend
from epistemic_case_mapper.model_outputs import canonical_json_output


def run_lightweight_writer_guidance(
    *,
    canonical_packet: dict[str, Any],
    scaffold: dict[str, Any],
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    """Create compact reader-facing guidance for final memo synthesis.

    This is intentionally narrower than packet critique: it does not repair
    packet semantics or adjudicate every bundle. It asks the model for writing
    guidance about source weighting, evidence-quality caveats, quantity wording,
    scope boundaries, and overstatement risks after the analyst/canonical packet
    exists.
    """

    prompt = build_lightweight_writer_guidance_prompt(canonical_packet=canonical_packet, scaffold=scaffold)
    mode = os.environ.get("ECM_LIGHTWEIGHT_GUIDANCE_MODE", "auto").strip().lower()
    if mode in {"off", "skip", "false", "0"}:
        guidance = _empty_guidance("disabled_by_ecm_lightweight_guidance_mode")
        return _bundle(guidance, prompt="", raw="", status="skipped", reason="disabled_by_ecm_lightweight_guidance_mode")
    if backend.strip() == "prompt":
        guidance = _empty_guidance("prompt_backend")
        return _bundle(guidance, prompt=prompt, raw="", status="skipped", reason="prompt_backend")
    try:
        raw = run_model_backend(
            prompt,
            backend,
            timeout_seconds=backend_timeout,
            max_retries=backend_retries,
            json_mode=True,
        ).text
    except RuntimeError as exc:
        guidance = _empty_guidance("backend_error")
        report = _report(guidance, status="backend_error", prompt=prompt, raw="", issues=[str(exc)])
        return _bundle(guidance, prompt=prompt, raw="", report=report)
    try:
        parsed = json.loads(canonical_json_output(raw))
        guidance = normalize_lightweight_writer_guidance(parsed)
        status = "parsed"
        issues: list[str] = []
    except Exception as exc:
        guidance = _empty_guidance("parse_error")
        status = "parse_error"
        issues = [str(exc)]
    return _bundle(guidance, prompt=prompt, raw=raw, report=_report(guidance, status=status, prompt=prompt, raw=raw, issues=issues))


def attach_lightweight_guidance_to_packet(memo_ready_packet: dict[str, Any], bundle: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(memo_ready_packet, dict):
        return memo_ready_packet
    guidance = _dict(bundle.get("lightweight_writer_guidance"))
    report = _dict(bundle.get("lightweight_writer_guidance_report"))
    memo_ready_packet["lightweight_writer_guidance"] = guidance
    memo_ready_packet["lightweight_writer_guidance_report"] = report
    canonical = _dict(memo_ready_packet.get("canonical_decision_writer_packet"))
    if canonical:
        canonical["lightweight_writer_guidance"] = guidance
        canonical["lightweight_writer_guidance_report"] = report
        memo_ready_packet["canonical_decision_writer_packet"] = canonical
    return memo_ready_packet


def build_lightweight_writer_guidance_prompt(*, canonical_packet: dict[str, Any], scaffold: dict[str, Any]) -> str:
    compact = build_lightweight_guidance_input(canonical_packet=canonical_packet, scaffold=scaffold)
    return (
        "You are creating lightweight reader-facing writing guidance for a source-grounded decision memo.\n"
        "Create guidance for the later memo writer by naming what must be made clear for a human decision-maker.\n"
        "Focus on source weighting, evidence-quality caveats, quantity wording, scope boundaries, and overstatement risks.\n"
        "Prefer specific caveats over generic phrases. If a quantity could be confused with another endpoint, give safe wording.\n"
        "Return concise JSON only. Keep reader-facing prose limited to source weighting, evidence caveats, quantity wording, scope, and overstatement risks.\n\n"
        "Required JSON shape:\n"
        f"{json.dumps(_guidance_schema(), indent=2, ensure_ascii=False)}\n\n"
        "Compact packet evidence:\n"
        f"{json.dumps(compact, indent=2, ensure_ascii=False)}\n"
    )


def build_lightweight_guidance_input(*, canonical_packet: dict[str, Any], scaffold: dict[str, Any]) -> dict[str, Any]:
    canonical = canonical_packet if isinstance(canonical_packet, dict) else {}
    evidence_quality = _dict(scaffold.get("evidence_quality_report"))
    quantity_binding = _dict(scaffold.get("analyst_quantity_binding_report"))
    return {
        "decision_question": canonical.get("decision_question"),
        "decision_brief_skeleton": _dict(canonical.get("decision_brief_skeleton")),
        "source_weight_judgments": _trim(_list(canonical.get("source_weight_judgments")), 8),
        "source_inventory": _compact_source_inventory(canonical),
        "priority_evidence": _trim(_list(canonical.get("priority_evidence")), 12),
        "counterweight_dispositions": _trim(_list(canonical.get("counterweight_dispositions")), 8),
        "scope_boundaries": _trim(_list(canonical.get("scope_boundaries")), 8),
        "decision_cruxes": _trim(_list(canonical.get("decision_cruxes")), 8),
        "mandatory_retention_checklist": _trim(_list(canonical.get("mandatory_retention_checklist")), 16),
        "packet_sufficiency": _status_and_issues(scaffold.get("packet_sufficiency_report")),
        "packet_quality_gate": _status_and_issues(scaffold.get("packet_quality_gate_report")),
        "evidence_quality_summary": {
            "issues": evidence_quality.get("issues", []),
            "weak_or_indirect_count": evidence_quality.get("weak_or_indirect_count", 0),
            "unknown_quality_count": evidence_quality.get("unknown_quality_count", 0),
            "quality_components": _trim(_list(evidence_quality.get("quality_components")), 16),
        },
        "source_weight_report": _dict(scaffold.get("source_weight_judgment_report")),
        "quantity_binding_summary": _compact_quantity_binding(quantity_binding),
        "known_final_memo_failure_modes_to_guard_against": [
            "internal claim IDs or memo obligation IDs leaking into prose",
            "generic evidence-quality language such as quality limit without explanation",
            "quantity wording that mixes distinct endpoints, such as ratio changes and concentration changes",
            "overstating subgroup or association claims when intervals cross the null",
        ],
    }


def normalize_lightweight_writer_guidance(
    payload: Any,
    *,
    allowed_source_ids: Iterable[str] | None = None,
) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    if isinstance(data.get("lightweight_writer_guidance"), dict):
        data = data["lightweight_writer_guidance"]
    guidance = {
        "schema_id": "lightweight_writer_guidance_v1",
        "overall_judgment": _short_text(data.get("overall_judgment"), 360),
        "reader_guidance": [_guidance_row(row) for row in _list(data.get("reader_guidance")) if isinstance(row, dict)],
        "evidence_quality_caveats": [_quality_caveat(row) for row in _list(data.get("evidence_quality_caveats")) if isinstance(row, dict)],
        "quantity_wording_risks": [_quantity_risk(row) for row in _list(data.get("quantity_wording_risks")) if isinstance(row, dict)],
        "do_not_overstate": [_short_text(row, 260) for row in _string_list(data.get("do_not_overstate"))],
        "suggested_reader_flow": [_short_text(row, 260) for row in _string_list(data.get("suggested_reader_flow"))],
    }
    return {**guidance, "summary": _guidance_summary(guidance)}


def compact_lightweight_guidance_for_prompt(guidance: dict[str, Any] | None) -> dict[str, Any]:
    row = guidance if isinstance(guidance, dict) else {}
    if row.get("schema_id") != "lightweight_writer_guidance_v1":
        return {}
    return {
        "schema_id": "lightweight_writer_guidance_v1",
        "overall_judgment": row.get("overall_judgment", ""),
        "reader_guidance": _trim(_list(row.get("reader_guidance")), 6),
        "evidence_quality_caveats": _trim(_list(row.get("evidence_quality_caveats")), 6),
        "quantity_wording_risks": _trim(_list(row.get("quantity_wording_risks")), 6),
        "do_not_overstate": _string_list(row.get("do_not_overstate"))[:6],
        "suggested_reader_flow": _string_list(row.get("suggested_reader_flow"))[:4],
    }


def evidence_quality_caveat_text(guidance: dict[str, Any] | None, source_ids: list[str]) -> list[str]:
    source_set = {source_id for source_id in source_ids if source_id}
    rows = []
    for row in _list(_dict(guidance).get("evidence_quality_caveats")):
        if not isinstance(row, dict):
            continue
        caveat_sources = set(_string_list(row.get("source_ids")))
        if source_set and caveat_sources and not source_set.intersection(caveat_sources):
            continue
        caveat = str(row.get("caveat") or "").strip()
        if caveat:
            rows.append(caveat)
    return _dedupe(rows)[:3]


def _bundle(
    guidance: dict[str, Any],
    *,
    prompt: str,
    raw: str,
    status: str | None = None,
    reason: str = "",
    report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    final_report = report or _report(guidance, status=status or "ready", prompt=prompt, raw=raw, issues=[])
    if reason:
        final_report["reason"] = reason
    return {
        "lightweight_writer_guidance": guidance,
        "lightweight_writer_guidance_prompt": prompt,
        "lightweight_writer_guidance_raw": raw,
        "lightweight_writer_guidance_report": final_report,
    }


def _report(guidance: dict[str, Any], *, status: str, prompt: str, raw: str, issues: list[str]) -> dict[str, Any]:
    summary = _dict(guidance.get("summary"))
    return {
        "schema_id": "lightweight_writer_guidance_report_v1",
        "status": status,
        "method": "compact_post_analyst_writer_guidance",
        "prompt_chars": len(prompt),
        "raw_chars": len(raw),
        "reader_guidance_count": summary.get("reader_guidance_count", 0),
        "evidence_quality_caveat_count": summary.get("evidence_quality_caveat_count", 0),
        "quantity_wording_risk_count": summary.get("quantity_wording_risk_count", 0),
        "do_not_overstate_count": summary.get("do_not_overstate_count", 0),
        "issues": issues,
    }


def _empty_guidance(reason: str) -> dict[str, Any]:
    return {
        "schema_id": "lightweight_writer_guidance_v1",
        "overall_judgment": "",
        "reader_guidance": [],
        "evidence_quality_caveats": [],
        "quantity_wording_risks": [],
        "do_not_overstate": [],
        "suggested_reader_flow": [],
        "summary": {"status": "empty", "reason": reason},
    }


def _guidance_schema() -> dict[str, Any]:
    return {
        "schema_id": "lightweight_writer_guidance_v1",
        "overall_judgment": "short string",
        "reader_guidance": [
            {
                "instruction": "reader-facing writing instruction",
                "why_it_matters": "why it affects the decision read",
                "source_ids": ["source_id"],
                "evidence_item_ids": ["item_id"],
                "validation_terms": ["term"],
            }
        ],
        "evidence_quality_caveats": [
            {
                "caveat": "specific caveat to surface in prose",
                "applies_to": "source or evidence family",
                "source_ids": ["source_id"],
                "severity": "low|medium|high",
            }
        ],
        "quantity_wording_risks": [
            {
                "risk": "specific wording risk",
                "safe_wording": "safe wording to use",
                "source_ids": ["source_id"],
                "quantities": ["quantity"],
            }
        ],
        "do_not_overstate": ["bounded warning"],
        "suggested_reader_flow": ["short prose flow instruction"],
    }


def _guidance_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "instruction": _short_text(row.get("instruction") or row.get("guidance") or row.get("recommended_action"), 360),
        "why_it_matters": _short_text(row.get("why_it_matters") or row.get("rationale") or row.get("reason"), 300),
        "source_ids": _string_list(row.get("source_ids"))[:6],
        "evidence_item_ids": _string_list(row.get("evidence_item_ids") or row.get("target_ids"))[:8],
        "validation_terms": _string_list(row.get("validation_terms"))[:10],
    }


def _quality_caveat(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "caveat": _short_text(row.get("caveat") or row.get("instruction") or row.get("description"), 360),
        "applies_to": _short_text(row.get("applies_to") or row.get("evidence_family"), 180),
        "source_ids": _string_list(row.get("source_ids"))[:6],
        "severity": str(row.get("severity") or "medium").strip() or "medium",
    }


def _quantity_risk(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "risk": _short_text(row.get("risk") or row.get("description"), 360),
        "safe_wording": _short_text(row.get("safe_wording") or row.get("recommended_wording"), 360),
        "source_ids": _string_list(row.get("source_ids"))[:6],
        "quantities": _string_list(row.get("quantities"))[:8],
    }


def _guidance_summary(guidance: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "ready",
        "reader_guidance_count": len(_list(guidance.get("reader_guidance"))),
        "evidence_quality_caveat_count": len(_list(guidance.get("evidence_quality_caveats"))),
        "quantity_wording_risk_count": len(_list(guidance.get("quantity_wording_risks"))),
        "do_not_overstate_count": len(_string_list(guidance.get("do_not_overstate"))),
    }


def _compact_source_inventory(canonical: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for row in _list(canonical.get("source_weight_judgments")):
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "source_ids": _string_list(row.get("source_ids")),
                "current_main_use": row.get("main_use"),
                "weight_summary": row.get("why_weight_this_way"),
                "reader_facing_limit": row.get("reader_facing_limit"),
                "what_not_to_use_it_for": row.get("what_not_to_use_it_for"),
                "evidence_item_ids": _string_list(row.get("evidence_item_ids")),
            }
        )
    return rows[:12]


def _compact_quantity_binding(report: dict[str, Any]) -> dict[str, Any]:
    rows = []
    for row in _list(report.get("approved_bindings"))[:12]:
        if not isinstance(row, dict):
            continue
        rows.append(
            {
                "value": row.get("value"),
                "interpretation": row.get("interpretation"),
                "quantity_role": row.get("quantity_role"),
                "memo_role": row.get("memo_role"),
                "source_ids": _string_list(row.get("source_ids")),
                "claim": row.get("group_proposition") or row.get("source_claim"),
                "warnings": _string_list(row.get("deterministic_warnings")),
            }
        )
    return {
        "status": report.get("status"),
        "issues": report.get("issues", []),
        "candidate_count": report.get("candidate_count", 0),
        "approved_count": report.get("approved_count", 0),
        "rejected_count": report.get("rejected_count", 0),
        "accepted_with_warning_count": report.get("accepted_with_warning_count", 0),
        "approved_bindings": rows,
    }


def _status_and_issues(value: Any) -> dict[str, Any]:
    row = _dict(value)
    return {"status": row.get("status", ""), "issues": row.get("issues", [])}


def _trim(rows: list[Any], limit: int) -> list[Any]:
    return rows[:limit] if isinstance(rows, list) else []


def _dedupe(rows: list[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for row in rows:
        key = row.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row.strip())
    return deduped
