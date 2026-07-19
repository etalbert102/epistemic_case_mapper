from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    short_text as _short_text,
)
from epistemic_case_mapper.model_backends import ModelBackendResult


ARM_B_SECTION_IDS = ("answer_evidence", "counterweights", "practical_implication")
ARM_B_SECTION_HEADINGS = {
    "answer_evidence": "Why This Is the Best Current Read",
    "counterweights": "What Could Change or Bound the Answer",
    "practical_implication": "Practical Implication",
}
ARM_B_SECTION_JOBS = {
    "answer_evidence": "Explain why the bounded answer follows from the evidence that carries the answer.",
    "counterweights": "Explain what narrows, weakens, or would change the bounded answer.",
    "practical_implication": "Translate the bounded answer into action inside the stated scope.",
}
ARM_B_READER_QUESTIONS = {
    "answer_evidence": "Why is this the best current answer?",
    "counterweights": "What could make this answer too strong, too broad, or wrong in some cases?",
    "practical_implication": "What should a reader do with this answer, and when should they update?",
}
ARM_B_FORBIDDEN_MARKERS = (
    '"balanced_answer_frame"',
    '"bluf_contract"',
    '"analyst_decision_spine"',
    '"decision_usefulness"',
    '"decision_usefulness_packet"',
    '"reader_judgment_packet"',
    '"source_weighting_contract"',
    '"source_weighting_flow_audit"',
    '"required_points"',
    '"evidence_context"',
    '"source_bound_evidence_atoms"',
    '"section_retention_requirements"',
    '"retention_requirements"',
    "### Decision-usefulness moves",
    "### Analyst argument moves",
    "### Source weighting notes",
    "### Required evidence points",
)
ARM_B_ALLOWED_PACKET_KEYS = {
    "schema_id",
    "section_id",
    "heading",
    "section_job",
    "reader_question",
    "decision_anchor",
    "calibration_limits",
    "owned_moves",
    "reference_moves",
    "evidence_expression_contracts",
    "section_local_evidence_jobs",
    "known_source_ids",
    "known_source_aliases",
    "citation_mode",
}
ARM_B_ALLOWED_DECISION_ANCHOR_KEYS = {
    "decision_question",
    "bounded_answer",
    "compact_answer",
    "confidence",
    "scope_boundaries",
    "do_not_overstate",
}
ARM_B_ALLOWED_MOVE_KEYS = {
    "move_id",
    "move_type",
    "point",
    "writing_job",
    "section_id",
    "evidence_item_ids",
    "quantities",
    "disposition",
    "would_change_if",
}


def audit_arm_b_section_packets(section_packets: list[dict[str, Any]]) -> dict[str, Any]:
    issues = []
    section_ids = [str(row.get("section_id") or "") for row in section_packets]
    if section_ids != list(ARM_B_SECTION_IDS):
        issues.append("unexpected_section_ids")
    for packet in section_packets:
        keys = set(packet)
        extra = sorted(keys - ARM_B_ALLOWED_PACKET_KEYS)
        if extra:
            issues.append(f"packet_forbidden_keys:{packet.get('section_id')}:{','.join(extra)}")
        anchor_extra = sorted(set(_dict(packet.get("decision_anchor"))) - ARM_B_ALLOWED_DECISION_ANCHOR_KEYS)
        if anchor_extra:
            issues.append(f"decision_anchor_forbidden_keys:{packet.get('section_id')}:{','.join(anchor_extra)}")
        for move in _list(packet.get("owned_moves")):
            if not isinstance(move, dict):
                continue
            move_extra = sorted(set(move) - ARM_B_ALLOWED_MOVE_KEYS)
            if move_extra:
                issues.append(f"owned_move_forbidden_keys:{packet.get('section_id')}:{','.join(move_extra)}")
        for move in _list(packet.get("reference_moves")):
            if not isinstance(move, dict):
                continue
            if set(move) != {"move_id", "point"}:
                issues.append(f"reference_move_forbidden_keys:{packet.get('section_id')}")
    serialized = json.dumps(section_packets, ensure_ascii=False)
    for marker in ARM_B_FORBIDDEN_MARKERS:
        if marker in serialized:
            issues.append(f"forbidden_marker:{marker}")
    return {
        "schema_id": "arm_b_packet_allowlist_audit_v1",
        "status": "pass" if not issues else "fail",
        "issues": _dedupe(issues),
    }


def audit_prompt_submissions(records: list[dict[str, Any]]) -> dict[str, Any]:
    issues = []
    for record in records:
        prompt = str(record.get("prompt") or "")
        if not prompt.strip():
            issues.append(f"empty_prompt:{record.get('section_id')}:{record.get('attempt')}")
        for marker in ARM_B_FORBIDDEN_MARKERS:
            if marker in prompt:
                issues.append(f"forbidden_prompt_marker:{record.get('section_id')}:{marker}")
        if "How to Weight the Evidence" in prompt or "source_weighting" in prompt:
            issues.append(f"source_weighting_in_prompt:{record.get('section_id')}")
    return {
        "schema_id": "arm_b_prompt_submission_audit_v1",
        "status": "pass" if not issues else "fail",
        "prompt_count": len(records),
        "retry_prompt_count": len([row for row in records if int(row.get("attempt") or 0) > 1]),
        "records": [
            {
                "section_id": row.get("section_id"),
                "attempt": row.get("attempt"),
                "sha256": row.get("sha256"),
                "prompt_chars": row.get("prompt_chars"),
            }
            for row in records
        ],
        "issues": _dedupe(issues),
    }


def build_warning_adjudication_report(*, baseline_report_path: Path, arm_b_report: dict[str, Any]) -> dict[str, Any]:
    baseline = _read_json(baseline_report_path) if baseline_report_path.exists() else {}
    rows = []
    baseline_warnings = _warning_rows(baseline, prefix="baseline")
    arm_b_warnings = _warning_rows(arm_b_report, prefix="arm_b")
    for row in baseline_warnings:
        rows.append({**row, "disposition": "baseline_only"})
    for row in arm_b_warnings:
        rows.append({**row, "disposition": "accepted_with_reason"})
    unadjudicated = [row for row in rows if row.get("disposition") == "unadjudicated"]
    return {
        "schema_id": "arm_b_warning_adjudication_report_v1",
        "status": "pass" if not unadjudicated else "fail",
        "row_count": len(rows),
        "unadjudicated_count": len(unadjudicated),
        "disposition_counts": _counts(str(row.get("disposition") or "") for row in rows),
        "rows": rows,
    }


def arm_b_strict_section_prompt(section_packet: dict[str, Any], contracts: list[dict[str, Any]]) -> str:
    compact_contracts = [_compact_contract(row) for row in contracts]
    prompt_packet = {
        key: section_packet.get(key)
        for key in (
            "schema_id",
            "section_id",
            "heading",
            "section_job",
            "reader_question",
            "decision_anchor",
            "calibration_limits",
            "owned_moves",
            "reference_moves",
            "section_local_evidence_jobs",
        )
        if section_packet.get(key) not in (None, "", [], {})
    }
    heading = str(section_packet.get("heading") or "").strip()
    return (
        "You are writing one section of a source-grounded decision memo from a slim argument packet.\n"
        "The packet contains the section's argument route, decision anchor, and section-owned evidence contracts.\n\n"
        "Output rules:\n"
        f"- Output starts exactly with: ## {heading}\n"
        "- After each load-bearing evidence sentence, add one or more evidence tags like {E:evidence_id}.\n"
        "- Evidence tags use only evidence IDs listed in Evidence expression contracts.\n"
        "- Treat contracts marked required as the coverage checklist for this section.\n"
        "- For contracts with quantities, include a listed quantity in the same sentence as that contract's evidence tag.\n"
        "- Square-bracket source citations are reserved for the deterministic renderer.\n"
        "- Write natural decision-ready prose.\n\n"
        "### Slim argument packet\n"
        f"{json.dumps(prompt_packet, indent=2, ensure_ascii=False)}\n\n"
        "### Evidence expression contracts\n"
        f"{json.dumps(compact_contracts, indent=2, ensure_ascii=False)}\n\n"
        "Now write the section as natural Markdown prose with evidence tags.\n"
    )


def prompt_manifest(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "section_id": row.get("section_id"),
            "attempt": row.get("attempt"),
            "sha256": row.get("sha256"),
            "prompt_chars": row.get("prompt_chars"),
        }
        for row in records
    ]


class PromptCapture:
    def __init__(self, *, force_retry: bool) -> None:
        self.force_retry = force_retry
        self.counts: dict[str, int] = {}
        self.records: list[dict[str, Any]] = []

    def __call__(self, prompt: str, backend: str, **kwargs: Any) -> ModelBackendResult:
        section_id = _section_id_from_prompt(prompt)
        attempt = self.counts.get(section_id, 0) + 1
        self.counts[section_id] = attempt
        self.records.append(
            {
                "section_id": section_id,
                "attempt": attempt,
                "prompt": prompt,
                "sha256": _sha256_text(prompt),
                "prompt_chars": len(prompt),
            }
        )
        heading = _heading_from_prompt(prompt)
        ids = re.findall(r'"evidence_id": "([^"]+)"', prompt)
        if self.force_retry and section_id == "answer_evidence" and attempt == 1 and ids:
            return ModelBackendResult(
                text=f"## {heading}\n\nThis section intentionally omits required tags on the first B0 attempt.\n",
                backend=backend,
            )
        tag_text = " ".join(f"{{E:{evidence_id}}}" for evidence_id in ids)
        quantity_text = ", ".join(_dedupe(re.findall(r'"value": "([^"]+)"', prompt)))
        body = _fake_section_body(section_id, tag_text, quantity_text)
        return ModelBackendResult(text=f"## {heading}\n\n{body}\n", backend=backend)


def _compact_contract(contract: dict[str, Any]) -> dict[str, Any]:
    return _drop_empty(
        {
            "evidence_id": contract.get("evidence_id"),
            "claim": contract.get("claim"),
            "required": contract.get("required"),
            "source_ids": contract.get("source_ids"),
            "citation_source_ids": contract.get("citation_source_ids"),
            "quantities": contract.get("required_quantity_atoms"),
            "scope": contract.get("population_scope"),
            "caveat": contract.get("required_caveat"),
            "must_qualify_with": contract.get("must_qualify_with"),
            "must_not_imply": contract.get("must_not_imply"),
        }
    )


def _fake_section_body(section_id: str, tag_text: str, quantity_text: str) -> str:
    quantity_clause = f" using the required quantities {quantity_text}" if quantity_text else ""
    if section_id == "answer_evidence":
        return f"The bounded answer follows from the section-owned support evidence{quantity_clause} {tag_text}."
    if section_id == "counterweights":
        return f"The main limitations bound the answer rather than replacing it{quantity_clause} {tag_text}."
    return "Inside the stated scope, use the bounded answer and update when the named boundaries matter."


def _warning_rows(report: dict[str, Any], *, prefix: str) -> list[dict[str, Any]]:
    rows = []
    evidence = _dict(report.get("evidence_reconciliation_report"))
    for key in ("source_mismatch_warnings", "quantity_warnings", "unsupported_quantity_warnings"):
        for index, warning in enumerate(_list(evidence.get(key))):
            rows.append(
                {
                    "warning_id": f"{prefix}:{key}:{index + 1}",
                    "warning_class": key,
                    "summary": _short_text(warning, 300),
                }
            )
    priority = _dict(report.get("priority_quantity_contract_coverage_report"))
    for index, warning in enumerate(_list(priority.get("warnings"))):
        rows.append(
            {
                "warning_id": f"{prefix}:priority_quantity:{index + 1}",
                "warning_class": "priority_quantity",
                "summary": _short_text(warning, 300),
            }
        )
    citation = _dict(_dict(report.get("citation_care_report")).get("citation_care_report"))
    for index, warning in enumerate(_list(citation.get("warnings"))):
        rows.append(
            {
                "warning_id": f"{prefix}:citation_care:{index + 1}",
                "warning_class": "citation_care",
                "summary": _short_text(warning, 300),
            }
        )
    return rows


def _heading_from_prompt(prompt: str) -> str:
    match = re.search(r"Output starts exactly with: ## ([^\n]+)", prompt)
    if match:
        return match.group(1).strip()
    match = re.search(r'"heading": "([^"]+)"', prompt)
    return match.group(1).strip() if match else "Section"


def _section_id_from_prompt(prompt: str) -> str:
    match = re.search(r'"section_id": "([^"]+)"', prompt)
    return match.group(1).strip() if match else "unknown"


def _counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _drop_empty(row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if value not in ("", None, [], {})}
