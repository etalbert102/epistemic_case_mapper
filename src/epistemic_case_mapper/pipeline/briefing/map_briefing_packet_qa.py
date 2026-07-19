from __future__ import annotations

from collections import Counter
from typing import Any

from epistemic_case_mapper.pipeline.briefing.map_briefing_answer_frame import is_weak_answer_frame


def build_packet_qa_report(
    decision_packet: dict[str, Any],
    *,
    memo_ready_packet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Report semantic packet-quality risks without blocking synthesis."""

    decision_packet = decision_packet if isinstance(decision_packet, dict) else {}
    memo_ready_packet = memo_ready_packet if isinstance(memo_ready_packet, dict) else {}
    checks: list[dict[str, Any]] = []
    checks.extend(_answer_frame_checks(decision_packet))
    checks.extend(_bundle_checks(decision_packet))
    checks.extend(_memo_ready_checks(memo_ready_packet))
    issue_count = sum(1 for check in checks if check["status"] != "pass")
    blocker_count = sum(1 for check in checks if check.get("severity") == "blocker" and check["status"] != "pass")
    return {
        "schema_id": "packet_qa_report_v1",
        "status": "fail" if blocker_count else "warning" if issue_count else "pass",
        "method": "semantic_packet_quality_report_only_checks",
        "check_count": len(checks),
        "issue_count": issue_count,
        "blocker_count": blocker_count,
        "checks": checks,
        "summary": {
            "answer_frame_clean": not any(_is_answer_frame_issue(check) for check in checks),
            "generic_answer_frame_warning_count": sum(1 for check in checks if check["check_id"] == "answer_frame_generic_or_artifact_language"),
            "missing_source_lineage_count": sum(1 for check in checks if check["check_id"] == "missing_source_lineage"),
            "truncated_claim_count": sum(1 for check in checks if check["check_id"] == "truncated_or_broken_claim"),
            "role_dominance_warning_count": sum(1 for check in checks if check["check_id"] == "unjustified_role_dominance"),
            "weak_crux_warning_count": sum(1 for check in checks if check["check_id"] == "weak_or_topical_crux"),
            "quantity_blob_warning_count": sum(1 for check in checks if check["check_id"] == "unstructured_quantity_blob"),
            "primary_low_question_fit_warning_count": sum(1 for check in checks if check["check_id"] == "primary_bundle_low_question_fit"),
        },
    }


def _is_answer_frame_issue(check: dict[str, Any]) -> bool:
    if check.get("status") == "pass":
        return False
    check_id = str(check.get("check_id") or "")
    target = str(check.get("target") or "")
    return check_id.startswith("answer_frame_") or target.startswith("answer_frame.")


def _answer_frame_checks(packet: dict[str, Any]) -> list[dict[str, Any]]:
    answer = packet.get("answer_frame") if isinstance(packet.get("answer_frame"), dict) else {}
    default = str(answer.get("default_answer") or "").strip() if isinstance(answer, dict) else ""
    if _looks_like_stringified_structure(default):
        return [
            _check(
                "answer_frame_not_plain_text",
                "warning",
                "answer_frame.default_answer appears to contain a stringified or malformed structure.",
                target="answer_frame.default_answer",
                excerpt=default[:220],
            )
        ]
    if _is_truncated_or_broken(default):
        return [
            _check(
                "truncated_or_broken_claim",
                "warning",
                "answer_frame.default_answer appears truncated or syntactically broken.",
                target="answer_frame.default_answer",
                excerpt=default[:220],
            )
        ]
    if _looks_like_generic_answer_frame(default, question=str(packet.get("decision_question") or "")):
        return [
            _check(
                "answer_frame_generic_or_artifact_language",
                "warning",
                "answer_frame.default_answer uses generic artifact language rather than answering the decision question.",
                target="answer_frame.default_answer",
                excerpt=default[:220],
            )
        ]
    return [_pass("answer_frame_plain_text", target="answer_frame.default_answer")]


def _bundle_checks(packet: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for bundle in _dicts(packet.get("evidence_bundles")):
        claim = str(bundle.get("claim") or "").strip()
        target = str(bundle.get("bundle_id") or bundle.get("claim_ids") or "evidence_bundle")
        if _is_truncated_or_broken(claim):
            checks.append(
                _check(
                    "truncated_or_broken_claim",
                    "warning",
                    "Evidence bundle claim appears truncated or syntactically broken.",
                    target=target,
                    excerpt=claim[:220],
                )
            )
        if not _strings(bundle.get("source_ids")) and not _strings(bundle.get("source_labels")):
            checks.append(
                _check(
                    "missing_source_lineage",
                    "warning",
                    "Evidence bundle lacks source IDs and source labels.",
                    target=target,
                    excerpt=claim[:220],
                )
            )
        if str(bundle.get("decision_role") or "") == "decision_crux" and _looks_like_topical_tension(claim):
            checks.append(
                _check(
                    "weak_or_topical_crux",
                    "warning",
                    "Decision crux looks like a topical tension rather than an answer-changing uncertainty.",
                    target=target,
                    excerpt=claim[:220],
                )
            )
        assessment = bundle.get("decision_relevance_assessment") if isinstance(bundle.get("decision_relevance_assessment"), dict) else {}
        if _primary_low_question_fit(bundle, assessment):
            checks.append(
                _check(
                    "primary_bundle_low_question_fit",
                    "warning",
                    "Primary evidence bundle has low lexical overlap with the decision question; review before treating it as answer-bearing.",
                    target=target,
                    excerpt=claim[:220],
                    details={
                        "decision_role": str(bundle.get("decision_role") or ""),
                        "question_relevance_status": assessment.get("question_relevance_status", ""),
                        "question_overlap_count": assessment.get("question_overlap_count", 0),
                    },
                )
            )
    if not checks:
        checks.append(_pass("evidence_bundles_basic_semantics", target="evidence_bundles"))
    return checks


def _primary_low_question_fit(bundle: dict[str, Any], assessment: dict[str, Any]) -> bool:
    if str(bundle.get("decision_role") or "") not in {"strongest_support", "counterweight", "quantitative_anchor", "decision_crux"}:
        return False
    return str(assessment.get("question_relevance_status") or "") == "low_question_overlap"


def _memo_ready_checks(packet: dict[str, Any]) -> list[dict[str, Any]]:
    if not packet:
        return []
    checks: list[dict[str, Any]] = []
    items = _dicts(packet.get("evidence_items"))
    role_counts = Counter(str(item.get("role") or "unknown") for item in items)
    dominant = role_counts.most_common(1)[0] if role_counts else ("", 0)
    if len(items) >= 8 and dominant[1] / max(len(items), 1) > 0.55:
        checks.append(
            _check(
                "unjustified_role_dominance",
                "warning",
                "Memo-ready packet is dominated by one role without an explicit dominance justification.",
                target="memo_ready_packet.evidence_items",
                details={"dominant_role": dominant[0], "dominant_count": dominant[1], "item_count": len(items)},
            )
        )
    for item in items:
        target = str(item.get("item_id") or "memo_ready_item")
        claim = str(item.get("reader_claim") or "").strip()
        if _is_truncated_or_broken(claim):
            checks.append(
                _check(
                    "truncated_or_broken_claim",
                    "warning",
                    "Memo-ready claim appears truncated or syntactically broken.",
                    target=target,
                    excerpt=claim[:220],
                )
            )
        if item.get("role") == "decision_crux" and _looks_like_topical_tension(claim):
            checks.append(
                _check(
                    "weak_or_topical_crux",
                    "warning",
                    "Memo-ready crux looks like a topical tension rather than an answer-changing uncertainty.",
                    target=target,
                    excerpt=claim[:220],
                )
            )
        if item.get("role") == "quantitative_anchor" and _quantity_blob_risk(item):
            checks.append(
                _check(
                    "unstructured_quantity_blob",
                    "warning",
                    "Quantitative anchor has mixed raw quantities without normalized quantity slots.",
                    target=target,
                    details={"quantity_count": len(_dicts(item.get("quantities"))), "has_quantity_slots": bool(item.get("quantity_slots"))},
                )
            )
    if not checks:
        checks.append(_pass("memo_ready_packet_basic_semantics", target="memo_ready_packet"))
    return checks


def _quantity_blob_risk(item: dict[str, Any]) -> bool:
    quantities = _dicts(item.get("quantities"))
    if len(quantities) < 4:
        return False
    types = {str(quantity.get("quantity_type") or "") for quantity in quantities}
    return len(types) >= 2 and not item.get("quantity_slots")


def _looks_like_stringified_structure(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return stripped.startswith("{") or any(token in stripped for token in ("'classification'", '"classification"', "'current_read'", '"current_read"'))


def _looks_like_generic_answer_frame(text: str, *, question: str = "") -> bool:
    lowered = " ".join(text.lower().split())
    if is_weak_answer_frame(text, question=question):
        return True
    artifact_terms = (
        "default answer",
        "current answer",
        "source packet",
        "evidence packet",
        "decision question",
        "stated conditions",
        "available evidence",
    )
    if "default answer" in lowered and any(term in lowered for term in ("supports", "under stated conditions", "available evidence")):
        return True
    artifact_count = sum(1 for term in artifact_terms if term in lowered)
    return artifact_count >= 2 and len(lowered.split()) <= 24


def _is_truncated_or_broken(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if stripped.endswith(("(", "[", "{", "approx.", "approx")):
        return True
    if stripped.endswith("..."):
        return True
    return stripped.count("(") > stripped.count(")") or stripped.count("[") > stripped.count("]")


def _looks_like_topical_tension(text: str) -> bool:
    lowered = text.lower()
    return " in tension with " in lowered or " vs. " in lowered or " versus " in lowered


def _check(
    check_id: str,
    severity: str,
    message: str,
    *,
    target: str,
    excerpt: str = "",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "check_id": check_id,
        "status": "warning" if severity != "blocker" else "fail",
        "severity": severity,
        "message": message,
        "target": target,
        **({"excerpt": excerpt} if excerpt else {}),
        **({"details": details} if details else {}),
    }


def _pass(check_id: str, *, target: str) -> dict[str, Any]:
    return {"check_id": check_id, "status": "pass", "severity": "info", "target": target}


def _dicts(value: Any) -> list[dict[str, Any]]:
    return [row for row in value if isinstance(row, dict)] if isinstance(value, list) else []


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    return [str(row).strip() for row in value if str(row).strip()] if isinstance(value, list) else []
