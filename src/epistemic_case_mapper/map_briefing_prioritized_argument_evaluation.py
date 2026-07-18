from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from epistemic_case_mapper.map_briefing_memo_ready_packet_helpers import (
    dedupe as _dedupe,
    dict_value as _dict,
    list_value as _list,
    string_list as _string_list,
)
from epistemic_case_mapper.model_backends import ModelBackendResult, run_model_backend


def build_arm_comparison_to_current(
    *,
    baseline_memo_path: Path,
    baseline_report_path: Path,
    candidate_memo: str,
    candidate_report: dict[str, Any],
    prompt_audit: dict[str, Any],
    elapsed_seconds: float,
    baseline_resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    resolved_baseline = baseline_resolution or _baseline_resolution_from_paths(
        baseline_memo_path, baseline_report_path
    )
    baseline_available = resolved_baseline.get("status") == "available"
    baseline_memo = baseline_memo_path.read_text(encoding="utf-8") if baseline_memo_path.is_file() else ""
    baseline_report = _read_json(baseline_report_path) if baseline_report_path.is_file() else {}
    baseline_metrics = _memo_comparison_metrics(baseline_memo, baseline_report)
    candidate_metrics = _memo_comparison_metrics(candidate_memo, candidate_report)
    traceability = _traceability_delta(baseline_metrics, candidate_metrics) if baseline_available else {}
    repetition = _repetition_delta(baseline_metrics, candidate_metrics) if baseline_available else {}
    vetoes = _comparison_vetoes(candidate_report, traceability)
    return {
        "schema_id": "prioritized_argument_comparison_to_current_v1",
        "status": "pass" if not vetoes and baseline_available else "not_applicable" if not vetoes else "fail",
        "baseline_resolution": resolved_baseline,
        "baseline": baseline_metrics,
        "candidate": {
            **candidate_metrics,
            "elapsed_seconds": elapsed_seconds,
            "prompt_audit_status": prompt_audit.get("status"),
            "prompt_count": prompt_audit.get("prompt_count"),
            "retry_prompt_count": prompt_audit.get("retry_prompt_count"),
        },
        "traceability_delta": traceability,
        "repetition_delta": repetition,
        "quality_assessment": _quality_assessment(
            traceability, repetition, candidate_report, prompt_audit, baseline_available=baseline_available
        ),
        "issues": vetoes,
    }


def build_live_evaluation_aggregate_report(
    *,
    schema_id: str,
    projection: dict[str, Any],
    sample_runs: list[dict[str, Any]],
    elapsed_seconds: float,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    issues = []
    if projection.get("status") != "pass":
        issues.append("projection_failed")
    if any(row.get("prompt_audit_status") != "pass" for row in sample_runs):
        issues.append("prompt_audit_failed")
    if any(row.get("warning_adjudication_status") != "pass" for row in sample_runs):
        issues.append("warning_adjudication_failed")
    if any(row.get("comparison_status") not in {"pass", "not_applicable"} for row in sample_runs):
        issues.append("comparison_failed")
    same_gap = repeated_semantic_gap(sample_runs)
    return {
        "schema_id": schema_id,
        "status": "pass" if not issues else "fail",
        "projection_status": projection.get("status"),
        "sample_count": len(sample_runs),
        "accepted_sample_count": len([row for row in sample_runs if row.get("accepted")]),
        "elapsed_seconds": elapsed_seconds,
        "arm_c_authorized": bool(not issues and same_gap),
        "repeated_semantic_gap": same_gap,
        "samples": sample_runs,
        "issues": _dedupe(issues),
        "warnings": _dedupe(
            [
                "comparison_baseline_unavailable"
                for row in sample_runs
                if row.get("comparison_status") == "not_applicable"
            ]
        ),
        **(extra or {}),
    }


def resolve_current_baseline(briefing_dir: Path) -> dict[str, Any]:
    candidates = [
        (
            briefing_dir.parent / "replay_after_section_contract_fix_v3" / "memo.md",
            briefing_dir.parent / "replay_after_section_contract_fix_v3" / "report.json",
            "replay_after_section_contract_fix_v3",
        ),
        (
            briefing_dir.parent / "replay_after_section_contract_fix_v2" / "memo.md",
            briefing_dir.parent / "replay_after_section_contract_fix_v2" / "report.json",
            "replay_after_section_contract_fix_v2",
        ),
        (
            briefing_dir.parent / "replay_after_section_contract_fix" / "memo.md",
            briefing_dir.parent / "replay_after_section_contract_fix" / "report.json",
            "replay_after_section_contract_fix",
        ),
        (briefing_dir / "memo.md", briefing_dir / "report.json", "briefing_memo"),
        (
            briefing_dir / "memo_ready_synthesis_raw.md",
            briefing_dir / "memo_ready_final_polish_report.json",
            "memo_ready_synthesis_raw",
        ),
        (briefing_dir / "BRIEFING.md", briefing_dir / "final_decision_readiness_report.json", "briefing_markdown"),
    ]
    for memo_path, report_path, label in candidates:
        if memo_path.is_file():
            return {
                "status": "available",
                "label": label,
                "memo_path": str(memo_path),
                "report_path": str(report_path) if report_path.is_file() else "",
            }
    return {"status": "missing", "label": "", "memo_path": "", "report_path": ""}


def repeated_semantic_gap(sample_runs: list[dict[str, Any]]) -> str:
    gaps = [
        str(_dict(row.get("quality_assessment")).get("named_semantic_gap") or "").strip()
        for row in sample_runs
    ]
    counts: dict[str, int] = {}
    for gap in gaps:
        if not gap:
            continue
        counts[gap] = counts.get(gap, 0) + 1
    for gap, count in counts.items():
        if count >= 2:
            return gap
    return ""


class LivePromptRecorder:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.counts: dict[str, int] = {}

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
        return run_model_backend(prompt, backend, **kwargs)


def _memo_comparison_metrics(memo: str, report: dict[str, Any]) -> dict[str, Any]:
    sections = _memo_sections(memo)
    warning_counts = _warning_counts_from_report(report)
    return {
        "char_count": len(memo),
        "word_count": len(re.findall(r"\b\w+\b", memo)),
        "section_count": len(sections),
        "sentence_count": len(_sentences(memo)),
        "repeated_sentence_count": _repeated_sentence_count(memo),
        "section_token_overlap": _section_token_overlap(sections),
        "status": report.get("status"),
        "accepted": bool(report.get("accepted")),
        "evidence_trace_count": report.get("evidence_trace_count", 0),
        "missing_required_evidence_count": warning_counts["missing_required_evidence"],
        "source_mismatch_count": warning_counts["source_mismatch"],
        "quantity_warning_count": warning_counts["quantity"],
        "unsupported_quantity_count": warning_counts["unsupported_quantity"],
        "priority_quantity_warning_count": warning_counts["priority_quantity"],
    }


def _warning_counts_from_report(report: dict[str, Any]) -> dict[str, int]:
    evidence = _dict(report.get("evidence_reconciliation_report"))
    priority = _dict(report.get("priority_quantity_contract_coverage_report"))
    missing_required = len(_string_list(evidence.get("missing_required_evidence_ids")))
    section_reports = _list(report.get("section_reports"))
    if section_reports:
        missing_required += sum(
            1
            for section in section_reports
            for issue in _string_list(_dict(section).get("issues"))
            if issue.startswith("missing_required_evidence:")
        )
    return {
        "missing_required_evidence": missing_required,
        "source_mismatch": len(_list(evidence.get("source_mismatch_warnings"))),
        "quantity": len(_list(evidence.get("quantity_warnings"))),
        "unsupported_quantity": len(_list(evidence.get("unsupported_quantity_warnings")))
        + len(_list(evidence.get("untagged_unsupported_quantity_warnings"))),
        "priority_quantity": len(_list(priority.get("warnings"))),
    }


def _traceability_delta(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    fields = (
        "missing_required_evidence_count",
        "source_mismatch_count",
        "quantity_warning_count",
        "unsupported_quantity_count",
        "priority_quantity_warning_count",
    )
    return {field: int(candidate.get(field) or 0) - int(baseline.get(field) or 0) for field in fields}


def _repetition_delta(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "repeated_sentence_count": int(candidate.get("repeated_sentence_count") or 0)
        - int(baseline.get("repeated_sentence_count") or 0),
        "section_token_overlap": round(
            float(candidate.get("section_token_overlap") or 0.0)
            - float(baseline.get("section_token_overlap") or 0.0),
            4,
        ),
    }


def _comparison_vetoes(candidate_report: dict[str, Any], traceability: dict[str, Any]) -> list[str]:
    issues = []
    status = str(candidate_report.get("status") or "")
    if status not in {"accepted", "accepted_with_evidence_tag_warnings"}:
        issues.append(f"candidate_generation_not_accepted:{status or 'unknown'}")
    for field, delta in traceability.items():
        if int(delta or 0) > 0:
            issues.append(f"traceability_regression:{field}:{delta}")
    return issues


def _quality_assessment(
    traceability: dict[str, Any],
    repetition: dict[str, Any],
    candidate_report: dict[str, Any],
    prompt_audit: dict[str, Any],
    *,
    baseline_available: bool = True,
) -> dict[str, Any]:
    if not baseline_available:
        structural_flags = []
        if prompt_audit.get("status") == "pass":
            structural_flags.append("submitted_prompts_pass_allowlist")
        if candidate_report.get("accepted"):
            structural_flags.append("section_synthesis_accepted")
        return {
            "structural_flags": structural_flags,
            "semantic_flags": ["baseline_unavailable"],
            "named_semantic_gap": "",
            "requires_paired_review": True,
        }
    semantic_flags = []
    if int(repetition.get("repeated_sentence_count") or 0) < 0:
        semantic_flags.append("less_repeated_sentence_text")
    if float(repetition.get("section_token_overlap") or 0.0) < -0.03:
        semantic_flags.append("lower_cross_section_token_overlap")
    if not semantic_flags:
        semantic_flags.append("no_clear_repetition_improvement")
    structural_flags = []
    if prompt_audit.get("status") == "pass":
        structural_flags.append("submitted_prompts_pass_allowlist")
    if all(int(value or 0) <= 0 for value in traceability.values()):
        structural_flags.append("no_traceability_regression")
    if candidate_report.get("accepted"):
        structural_flags.append("section_synthesis_accepted")
    return {
        "structural_flags": structural_flags,
        "semantic_flags": semantic_flags,
        "named_semantic_gap": "shallow_or_repetitive_argument" if "no_clear_repetition_improvement" in semantic_flags else "",
        "requires_paired_review": True,
    }


def _baseline_resolution_from_paths(baseline_memo_path: Path, baseline_report_path: Path) -> dict[str, Any]:
    if baseline_memo_path.is_file():
        return {
            "status": "available",
            "label": "explicit",
            "memo_path": str(baseline_memo_path),
            "report_path": str(baseline_report_path) if baseline_report_path.is_file() else "",
        }
    return {"status": "missing", "label": "explicit", "memo_path": "", "report_path": ""}


def _memo_sections(memo: str) -> list[str]:
    sections = []
    current: list[str] = []
    for line in memo.splitlines():
        if line.startswith("## ") and current:
            sections.append("\n".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        text = "\n".join(current).strip()
        if text:
            sections.append(text)
    return sections


def _sentences(text: str) -> list[str]:
    return [
        re.sub(r"\s+", " ", row).strip()
        for row in re.split(r"(?<=[.!?])\s+", text)
        if len(re.sub(r"\s+", " ", row).strip()) > 40
    ]


def _repeated_sentence_count(text: str) -> int:
    normalized = [_normalize_sentence(row) for row in _sentences(text)]
    counts: dict[str, int] = {}
    for row in normalized:
        if not row:
            continue
        counts[row] = counts.get(row, 0) + 1
    return sum(count - 1 for count in counts.values() if count > 1)


def _section_token_overlap(sections: list[str]) -> float:
    token_sets = [_content_tokens(section) for section in sections if _content_tokens(section)]
    if len(token_sets) < 2:
        return 0.0
    scores = []
    for index, left in enumerate(token_sets):
        for right in token_sets[index + 1 :]:
            union = left | right
            if union:
                scores.append(len(left & right) / len(union))
    return round(sum(scores) / len(scores), 4) if scores else 0.0


def _content_tokens(text: str) -> set[str]:
    stop = {
        "about",
        "after",
        "again",
        "also",
        "because",
        "before",
        "between",
        "could",
        "does",
        "from",
        "have",
        "into",
        "more",
        "only",
        "over",
        "than",
        "that",
        "their",
        "there",
        "these",
        "this",
        "through",
        "with",
        "would",
    }
    return {token for token in re.findall(r"\b[a-z][a-z0-9_]{3,}\b", text.lower()) if token not in stop}


def _normalize_sentence(text: str) -> str:
    text = re.sub(r"\{E:[^}]+\}", "", text)
    text = re.sub(r"\[[^\]]+\]", "", text)
    text = re.sub(r"\s+", " ", text).strip().lower()
    return text


def _section_id_from_prompt(prompt: str) -> str:
    match = re.search(r'"section_id": "([^"]+)"', prompt)
    return match.group(1).strip() if match else "unknown"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
