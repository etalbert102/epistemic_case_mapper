from __future__ import annotations

import re
from typing import Any

from epistemic_case_mapper.evidence_drift_validation import evidence_drift_issues
from epistemic_case_mapper.io import write_json, write_markdown
from epistemic_case_mapper.map_briefing_context_reports import build_section_context_acceptance_report
from epistemic_case_mapper.main_memo_obligations import build_main_memo_obligation_plan, obligation_issues_for_text, section_obligations_for_title
from epistemic_case_mapper.map_briefing_decision_brief_last import (
    decision_brief_last_issues,
    decision_brief_last_packet,
    deterministic_final_decision_brief,
    _sentence,
)
from epistemic_case_mapper.map_briefing_decision_brief_prompt import (
    _decision_brief_bluf_prompt,
    decision_brief_repair_prompt,
)
from epistemic_case_mapper.map_briefing_section_fallbacks import structured_section_fallback
from epistemic_case_mapper.map_briefing_memo_slots import (
    _replace_internal_reader_phrases,
    _repair_overclaim_strength_language,
    _repair_unbalanced_markdown_strong,
    _rewrite_has_raw_identifiers,
    _rewrite_mentions_anchor_row,
    _rewrite_mentions_gap,
)
from epistemic_case_mapper.map_briefing_reader_contracts import build_reader_memo_rewrite_contract
from epistemic_case_mapper.map_briefing_reader_polish import clean_reader_memo_text
from epistemic_case_mapper.map_briefing_section_attempts import run_section_model_attempts
from epistemic_case_mapper.map_briefing_section_adjudication import adjudicate_decision_brief_issues, adjudicate_section_issues
from epistemic_case_mapper.map_briefing_section_ownership import (
    build_section_evidence_ownership,
    compact_evidence_reference,
    evidence_reference_policy,
    repeated_owned_evidence_issues,
    section_owns_evidence,
)
from epistemic_case_mapper.map_briefing_section_input_compiler import compile_model_section_packet, select_section_cruxes
from epistemic_case_mapper.map_briefing_section_packets import prune_section_packet_for_ownership, section_synthesis_packet, write_section_packets_artifact
from epistemic_case_mapper.map_briefing_section_obligations import section_main_memo_obligations
from epistemic_case_mapper.map_briefing_section_prompt_contract import _text_mentions_owned_elsewhere
from epistemic_case_mapper.map_briefing_section_repair_prompt import section_repair_prompt
from epistemic_case_mapper.map_briefing_section_rewrite_prompt import section_rewrite_prompt as _section_rewrite_prompt
from epistemic_case_mapper.map_briefing_section_structure import (
    repair_structured_section,
    section_structure_issues,
)
from epistemic_case_mapper.map_briefing_validation import validate_briefing_against_scaffold
from epistemic_case_mapper.model_backends import run_model_backend


SECTION_RE = re.compile(r"^##\s+(.+?)\s*$", flags=re.MULTILINE)

def rewrite_reader_memo_by_section(
    memo: str,
    evidence_appendix: str,
    scaffold: dict[str, Any],
    candidate_map: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    artifacts: Any | None = None,
) -> dict[str, Any]:
    """Rewrite memo sections independently, accepting only locally valid sections."""
    contract = build_reader_memo_rewrite_contract(memo, scaffold)
    contract["_section_synthesis_scaffold"] = scaffold
    contract["_main_memo_obligation_plan"] = build_main_memo_obligation_plan(scaffold=scaffold)
    report: dict[str, Any] = {
        "schema_id": "section_rewrite_report_v1",
        "status": "not_run",
        "accepted_section_count": 0,
        "section_count": 0,
        "sections": [],
        "whole_validation_status": "not_run",
    }
    leading, sections = _split_sections(memo)
    report["section_count"] = len(sections)
    if not sections:
        report["status"] = "no_sections"
        return {"memo": memo, "report": report}
    contract["_section_evidence_ownership"] = build_section_evidence_ownership(sections, contract)
    report["evidence_ownership"] = {
        "owned_row_count": len(contract["_section_evidence_ownership"].get("rows", {})),
        "owner_counts": contract["_section_evidence_ownership"].get("owner_counts", {}),
    }
    if _projection_readiness_blocks_synthesis(scaffold):
        return _blocked_by_projection_readiness_result(memo, sections, contract, report, artifacts)
    if backend.strip() == "prompt":
        section_packets = _report_only_section_packets(sections, contract)
        report["status"] = "skipped_prompt_backend"
        section_packet_path, section_context_acceptance_report_path = _finalize_section_packet_outputs(
            section_packets,
            report,
            artifacts,
        )
        return _section_rewrite_result(memo, report, section_packet_path, section_context_acceptance_report_path)
    section_packets: list[dict[str, Any]] = []
    rewritten_sections: list[str] = []
    deferred_decision_section: dict[str, str] | None = None
    for index, section in enumerate(sections):
        if section["title"] == "Decision Brief":
            deferred_decision_section = section
            continue
        section_contract = _section_contract(section, contract)
        section_packets.append(
            {
                "title": section["title"],
                "section_job": section_contract.get("section_job"),
                "packet": section_contract.get("section_synthesis_packet", {}),
                "model_packet": section_contract.get("model_section_packet", {}),
            }
        )
        result = _rewrite_one_section(
            section,
            section_contract,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            previous_title=sections[index - 1]["title"] if index else "",
            next_title=sections[index + 1]["title"] if index + 1 < len(sections) else "",
        )
        if artifacts is not None:
            _write_section_debug_artifacts(artifacts, index, section["title"], result)
        report["sections"].append(result["report"])
        rewritten_sections.append(str(result["section"]))
    body_candidate = clean_reader_memo_text("\n\n".join(part for part in rewritten_sections if part.strip()))
    if deferred_decision_section is not None:
        section_packets.insert(
            0,
            {
                    "title": "Decision Brief",
                    "section_job": "Write the opening answer after the body sections are accepted.",
                    "packet": decision_brief_last_packet(contract, body_candidate),
                    "model_packet": compile_model_section_packet("Decision Brief", contract),
            },
        )
        brief_result = _rewrite_decision_brief_last(
            deferred_decision_section,
            contract,
            body_candidate,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
        )
        if artifacts is not None:
            _write_section_debug_artifacts(artifacts, 0, "Decision Brief Final", brief_result)
        report["sections"].insert(0, brief_result["report"])
        candidate = clean_reader_memo_text(
            "\n\n".join(part for part in [leading.strip(), str(brief_result["section"]), body_candidate] if part.strip())
        )
    else:
        candidate = clean_reader_memo_text("\n\n".join(part for part in [leading.strip(), body_candidate] if part.strip()))
    validation = validate_briefing_against_scaffold(candidate.rstrip() + "\n\n" + evidence_appendix.rstrip() + "\n", scaffold, candidate_map)
    report["whole_validation_status"] = validation.get("status", "unknown")
    report["whole_validation_issues"] = validation.get("issues", [])
    report["main_memo_obligation_validation"] = _post_synthesis_obligation_validation(candidate, contract)
    report["accepted_section_count"] = sum(1 for item in report["sections"] if item.get("accepted"))
    section_packet_path, section_context_acceptance_report_path = _finalize_section_packet_outputs(
        section_packets,
        report,
        artifacts,
    )
    if validation.get("status") == "needs_review":
        report["status"] = "global_validation_failed_fallback"
        return _section_rewrite_result(memo, report, section_packet_path, section_context_acceptance_report_path)
    report["status"] = "accepted_partial" if report["accepted_section_count"] else "no_sections_accepted"
    return _section_rewrite_result(candidate, report, section_packet_path, section_context_acceptance_report_path)


def _write_section_context_acceptance_report(artifacts: Any, report: dict[str, Any]) -> Any:
    path = artifacts / "section_context_acceptance_report.json"
    write_json(path, report)
    return path


def _finalize_section_packet_outputs(
    section_packets: list[dict[str, Any]],
    report: dict[str, Any],
    artifacts: Any | None,
    *,
    context_status_override: str | None = None,
) -> tuple[Any | None, Any | None]:
    context_acceptance_report = build_section_context_acceptance_report(section_packets)
    report["section_packet_count"] = len(section_packets)
    report["section_context_acceptance_status"] = context_status_override or context_acceptance_report.get("status")
    section_packet_path = None
    section_context_acceptance_report_path = None
    if artifacts is not None:
        section_packet_path = write_section_packets_artifact(artifacts, section_packets)
        section_context_acceptance_report_path = _write_section_context_acceptance_report(artifacts, context_acceptance_report)
        report["section_packets_path"] = str(section_packet_path)
        report["section_context_acceptance_report_path"] = str(section_context_acceptance_report_path)
    return section_packet_path, section_context_acceptance_report_path


def _section_rewrite_result(
    memo: str,
    report: dict[str, Any],
    section_packet_path: Any | None,
    section_context_acceptance_report_path: Any | None,
) -> dict[str, Any]:
    return {
        "memo": memo,
        "report": report,
        "section_packets_path": section_packet_path,
        "section_context_acceptance_report_path": section_context_acceptance_report_path,
    }


def _blocked_by_projection_readiness_result(
    memo: str,
    sections: list[dict[str, str]],
    contract: dict[str, Any],
    report: dict[str, Any],
    artifacts: Any | None,
) -> dict[str, Any]:
    section_packets = _report_only_section_packets(sections, contract)
    report["status"] = "blocked_by_spine_projection_readiness"
    report["issues"] = ["canonical spine projections are not synthesis-ready"]
    section_packet_path, section_context_acceptance_report_path = _finalize_section_packet_outputs(
        section_packets,
        report,
        artifacts,
        context_status_override="not_synthesis_ready",
    )
    return _section_rewrite_result(memo, report, section_packet_path, section_context_acceptance_report_path)


def _projection_readiness_blocks_synthesis(scaffold: dict[str, Any]) -> bool:
    readiness = scaffold.get("section_projection_readiness_report", {})
    if not isinstance(readiness, dict):
        return False
    return readiness.get("status") == "not_synthesis_ready"


def _rewrite_one_section(
    section: dict[str, str],
    section_contract: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
    previous_title: str,
    next_title: str,
) -> dict[str, Any]:
    prompt = _section_rewrite_prompt(section, section_contract, previous_title=previous_title, next_title=next_title)
    section_report: dict[str, Any] = {
        "title": section["title"],
        "status": "not_run",
        "accepted": False,
        "issues": [],
        "required_evidence_count": len(section_contract["required_evidence"]),
        "evidence_reference_count": len(section_contract.get("evidence_references", [])),
        "required_gap_count": len(section_contract["required_gaps"]),
        "required_crux_count": len(section_contract["required_cruxes"]),
        "required_main_memo_obligation_count": len(section_contract.get("required_main_memo_obligations", [])),
    }
    if not _should_rewrite_section(section, section_contract):
        section_report["status"] = "skipped_low_value_section"
        return {"section": section["markdown"], "prompt": prompt, "raw": "", "report": section_report}
    if section["title"].strip().lower() == "decision cruxes":
        structured = _structured_decision_crux_section(section_contract)
        repaired, issues = _validate_rewritten_section(structured, section, section_contract)
        if not issues:
            section_report.update({"status": "accepted_structured_cruxes", "accepted": True, "issues": [], "structured_cruxes": True})
            return {"section": clean_reader_memo_text(repaired), "prompt": prompt, "raw": "", "report": section_report}
    attempt_result = run_section_model_attempts(
        prompt=prompt, expected_title=section["title"], backend=backend, backend_timeout=backend_timeout, backend_retries=backend_retries,
        validate=lambda rewritten: _validate_rewritten_section(rewritten, section, section_contract),
        adjudicate=lambda rewritten, issues: adjudicate_section_issues(
            section_title=section["title"],
            validation_context=_section_allowed_evidence_context(section, section_contract),
            rewritten=rewritten,
            issues=issues,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            run_backend=run_model_backend,
        ),
        run_backend=run_model_backend,
    )
    _apply_attempt_report(section_report, attempt_result, deterministic_text=section["markdown"])
    if attempt_result["accepted"]:
        return {"section": clean_reader_memo_text(str(attempt_result["section"])), "prompt": attempt_result["prompt"], "raw": attempt_result["raw"], "report": section_report}
    repair_result = _repair_rejected_section_with_model(
        section,
        section_contract,
        attempt_result,
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
    )
    if repair_result["accepted"]:
        section_report["model_repair"] = repair_result["attempts"]
        section_report.update({"status": "accepted_model_repair", "accepted": True, "issues": [], "repair_attempt_count": repair_result["attempt_count"]})
        return {"section": clean_reader_memo_text(str(repair_result["section"])), "prompt": repair_result["prompt"], "raw": repair_result["raw"], "report": section_report}
    if repair_result["attempts"]:
        section_report["model_repair"] = repair_result["attempts"]
        section_report["model_repair_issues"] = repair_result["issues"]
    structured = structured_section_fallback(section, section_contract)
    if structured != section["markdown"]:
        fallback_issues = _section_rewrite_issues(structured, section, section_contract)
        hard_issues = [issue for issue in fallback_issues if not _structured_fallback_warning(issue)]
        section_report["structured_fallback_issues"] = fallback_issues
        if not hard_issues:
            status = "accepted_structured_fallback" if not fallback_issues else "accepted_structured_fallback_with_warnings"
            section_report.update({"status": status, "accepted": True, "issues": fallback_issues, "structured_fallback": True})
            return {"section": clean_reader_memo_text(structured), "prompt": attempt_result["prompt"], "raw": attempt_result["raw"], "report": section_report}
        section_report["structured_fallback_hard_issues"] = hard_issues
    section_report["status"] = "rejected_fallback"
    return {"section": section["markdown"], "prompt": attempt_result["prompt"], "raw": attempt_result["raw"], "report": section_report}


def _repair_rejected_section_with_model(
    section: dict[str, str],
    section_contract: dict[str, Any],
    attempt_result: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    rejected = str(attempt_result.get("rewritten") or "").strip()
    if not rejected:
        return {"accepted": False, "attempts": [], "issues": ["no rejected section available for repair"], "attempt_count": 0}
    prompt = section_repair_prompt(section, section_contract, rejected, attempt_result.get("issues", []))
    return run_section_model_attempts(
        prompt=prompt,
        expected_title=section["title"],
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        validate=lambda rewritten: _validate_rewritten_section(rewritten, section, section_contract),
        adjudicate=lambda rewritten, issues: adjudicate_section_issues(
            section_title=section["title"],
            validation_context=_section_allowed_evidence_context(section, section_contract),
            rewritten=rewritten,
            issues=issues,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            run_backend=run_model_backend,
        ),
        run_backend=run_model_backend,
    )


def _report_only_section_packets(sections: list[dict[str, str]], contract: dict[str, Any]) -> list[dict[str, Any]]:
    body_memo = clean_reader_memo_text(
        "\n\n".join(section["markdown"] for section in sections if section["title"] != "Decision Brief")
    )
    packets: list[dict[str, Any]] = []
    for section in sections:
        if section["title"] == "Decision Brief":
            packets.append(
                {
                    "title": "Decision Brief",
                    "section_job": "Write the opening answer after the body sections are accepted.",
                    "packet": decision_brief_last_packet(contract, body_memo),
                    "model_packet": compile_model_section_packet("Decision Brief", contract),
                }
            )
            continue
        section_contract = _section_contract(section, contract)
        packets.append(
            {
                "title": section["title"],
                "section_job": section_contract.get("section_job"),
                "packet": section_contract.get("section_synthesis_packet", {}),
                "model_packet": section_contract.get("model_section_packet", {}),
            }
        )
    return packets


def _rewrite_decision_brief_last(
    original: dict[str, str],
    contract: dict[str, Any],
    body_memo: str,
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    fallback = deterministic_final_decision_brief(contract, body_memo)
    prompt = _decision_brief_bluf_prompt(contract, body_memo, fallback)
    result = run_section_model_attempts(
        prompt=prompt,
        expected_title="Decision Brief",
        backend=backend,
        backend_timeout=backend_timeout,
        backend_retries=backend_retries,
        validate=lambda rewritten: _validate_final_decision_brief(rewritten, contract, body_memo),
        adjudicate=lambda rewritten, issues: adjudicate_decision_brief_issues(
            contract=contract,
            body_memo=body_memo,
            rewritten=rewritten,
            issues=issues,
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            run_backend=run_model_backend,
        ),
        run_backend=run_model_backend,
    )
    if result["accepted"]:
        section_report: dict[str, Any] = {
            "title": "Decision Brief",
            "status": "accepted_model_bluf",
            "accepted": True,
            "issues": [],
            "attempts": result["attempts"],
            "attempt_count": result["attempt_count"],
            "required_evidence_count": 0,
            "required_gap_count": 0,
            "required_crux_count": 0,
            "required_main_memo_obligation_count": len(
                section_obligations_for_title("Decision Brief", contract.get("_main_memo_obligation_plan", []))
            ),
            "generated_last": True,
            "deterministic_slots": False,
            "fallback_used": False,
        }
        return {"section": result["section"], "prompt": result["prompt"], "raw": result["raw"], "report": section_report}
    rejected = str(result.get("rewritten") or "").strip()
    if rejected:
        repair = run_section_model_attempts(
            prompt=decision_brief_repair_prompt(contract, body_memo, rejected, result["issues"]),
            expected_title="Decision Brief",
            backend=backend,
            backend_timeout=backend_timeout,
            backend_retries=backend_retries,
            validate=lambda rewritten: _validate_final_decision_brief(rewritten, contract, body_memo),
            adjudicate=lambda rewritten, issues: adjudicate_decision_brief_issues(
                contract=contract,
                body_memo=body_memo,
                rewritten=rewritten,
                issues=issues,
                backend=backend,
                backend_timeout=backend_timeout,
                backend_retries=backend_retries,
                run_backend=run_model_backend,
            ),
            run_backend=run_model_backend,
        )
        if repair["accepted"]:
            section_report = {"title": "Decision Brief", "status": "accepted_model_bluf_repair", "accepted": True, "issues": [], "attempts": result["attempts"], "attempt_count": result["attempt_count"], "model_repair": repair["attempts"], "repair_attempt_count": repair["attempt_count"], "required_evidence_count": 0, "required_gap_count": 0, "required_crux_count": 0, "required_main_memo_obligation_count": len(section_obligations_for_title("Decision Brief", contract.get("_main_memo_obligation_plan", []))), "generated_last": True, "deterministic_slots": False, "fallback_used": False}
            return {"section": repair["section"], "prompt": repair["prompt"], "raw": repair["raw"], "report": section_report}
    section_report: dict[str, Any] = {
        "title": "Decision Brief",
        "status": "accepted_deterministic_fallback_after_model",
        "accepted": True,
        "issues": result["issues"],
        "attempts": result["attempts"],
        "attempt_count": result["attempt_count"],
        "model_repair": repair["attempts"] if rejected else [],
        "model_repair_issues": repair["issues"] if rejected else [],
        "required_evidence_count": 0,
        "required_gap_count": 0,
        "required_crux_count": 0,
        "required_main_memo_obligation_count": len(
            section_obligations_for_title("Decision Brief", contract.get("_main_memo_obligation_plan", []))
        ),
        "generated_last": True,
        "deterministic_slots": False,
        "fallback_used": True,
    }
    return {"section": fallback, "prompt": result["prompt"], "raw": result["raw"], "report": section_report}


def _section_rewrite_issues(rewritten: str, original: dict[str, str], contract: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if not rewritten.strip():
        return ["missing section_markdown"]
    if not rewritten.lstrip().startswith(f"## {original['title']}"):
        issues.append("section heading changed or dropped")
    headings = SECTION_RE.findall(rewritten)
    if len(headings) != 1:
        issues.append("section rewrite included extra top-level sections")
    if contract["requires_confidence"] and "**Confidence:**" not in rewritten:
        issues.append("section dropped confidence line")
    if _rewrite_has_raw_identifiers(rewritten):
        issues.append("section contains raw map identifiers")
    if "crux" in original["title"].lower() and _has_generic_crux_language(rewritten):
        issues.append("section crux table contains generic placeholder language")
    if re.search(r"(?im)^\s*[-*]\s+\[[^\]]+\]\s+\([^)]+\)|named gaps and constraints", rewritten): issues.append("section surfaced internal evidence ownership metadata")
    min_decision_cruxes = int(contract.get("min_decision_changing_cruxes", 0) or 0)
    if min_decision_cruxes and _decision_changing_crux_count(rewritten) < min_decision_cruxes:
        issues.append("section does not preserve enough decision-changing crux conditions")
    for row in _validation_required_evidence(contract):
        if not _rewrite_mentions_anchor_row(rewritten, row):
            issues.append(f"section dropped required evidence: {str(row.get('claim', ''))[:90]}")
    if "crux" not in original["title"].lower():
        issues.extend(_blocking_repetition_issues(repeated_owned_evidence_issues(original["title"], rewritten, contract)))
    for gap in contract["required_gaps"]:
        if not _rewrite_mentions_gap(rewritten, gap):
            issues.append(f"section dropped required gap: {gap[:90]}")
    for crux in contract["required_cruxes"]:
        crux_text = str(crux.get("crux", "")).strip()
        if crux_text and _content_overlap(rewritten, crux_text) < 2:
            issues.append(f"section dropped required crux: {crux_text[:90]}")
    issues.extend(
        obligation_issues_for_text(
            contract.get("required_main_memo_obligations", []),
            rewritten,
            prefix="section dropped required main-memo obligation",
        )
    )
    for issue in evidence_drift_issues(
        rewritten,
        _section_allowed_evidence_context(original, contract),
        subject="section rewrite",
    ):
        issues.append(issue)
    original_words = max(1, len(original["markdown"].split()))
    if "crux" not in original["title"].lower() and contract["has_obligations"] and len(rewritten.split()) < max(35, int(original_words * 0.45)):
        issues.append("section rewrite is too short for its local contract")
    issues.extend(section_structure_issues(rewritten, contract))
    return issues


def _section_allowed_evidence_context(original: dict[str, str], contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "original_markdown": original.get("markdown", ""),
        "model_section_packet": contract.get("model_section_packet", {}),
        "validation_obligations": {
            "required_evidence": contract.get("required_evidence", []),
            "evidence_references": contract.get("evidence_references", []),
            "owned_elsewhere_evidence": contract.get("owned_elsewhere_evidence", []),
            "required_gaps": contract.get("required_gaps", []),
            "required_cruxes": contract.get("required_cruxes", []),
            "required_main_memo_obligations": contract.get("required_main_memo_obligations", []),
            "practical_actions": contract.get("practical_actions", []),
        },
        "section_synthesis_packet": contract.get("section_synthesis_packet", {}),
        "model_section_context": contract.get("model_section_context", {}),
    }


def _validation_required_evidence(contract: dict[str, Any]) -> list[dict[str, Any]]:
    model_packet = contract.get("model_section_packet", {}) if isinstance(contract.get("model_section_packet"), dict) else {}
    owned = model_packet.get("owned_evidence", []) if isinstance(model_packet.get("owned_evidence"), list) else []
    if any(isinstance(row, dict) for row in owned):
        return []
    return [
        row for row in contract.get("required_evidence", [])
        if isinstance(row, dict) and not _malformed_required_evidence(row)
    ]


def _validation_row_from_owned_card(row: dict[str, Any]) -> dict[str, Any]:
    claim = str(row.get("claim", "")).strip()
    if _malformed_claim_text(claim):
        return {}
    anchor_terms = _string_list(row.get("anchor_terms"))
    if not anchor_terms:
        anchor_terms = _validation_anchor_terms(row)
    return {
        "slot": row.get("intended_role") or row.get("slot"),
        "claim": claim,
        "source": row.get("source"),
        "anchor_terms": anchor_terms,
    }


def _validation_anchor_terms(row: dict[str, Any]) -> list[str]:
    text = " ".join(
        str(value)
        for value in [row.get("claim"), row.get("source"), " ".join(_string_list(row.get("quantity_values")))]
        if str(value).strip()
    )
    terms = [term for term in re.findall(r"[a-z0-9]{4,}", text.lower()) if term not in {"evidence", "section", "source", "claim"}]
    return list(dict.fromkeys(terms))[:8]


def _malformed_required_evidence(row: dict[str, Any]) -> bool:
    source = str(row.get("source", "")).lower()
    return "structured option comparison" in source or _malformed_claim_text(str(row.get("claim", "")))


def _malformed_claim_text(claim: str) -> bool:
    cleaned = re.sub(r"\s+", " ", claim).strip()
    if len(cleaned) < 12:
        return True
    return cleaned.endswith((" or.", " and.", " of.", " with."))


def _blocking_repetition_issues(issues: list[str]) -> list[str]:
    return issues if len(issues) > 1 else []


def _validate_rewritten_section(rewritten: str, section: dict[str, str], contract: dict[str, Any]) -> tuple[str, list[str]]:
    repaired = repair_structured_section(_repair_section(rewritten), contract)
    return repaired, _section_rewrite_issues(repaired, section, contract)


def _validate_final_decision_brief(rewritten: str, contract: dict[str, Any], body_memo: str) -> tuple[str, list[str]]:
    repaired = _repair_section(rewritten)
    return repaired, decision_brief_last_issues(repaired, contract, body_memo)


def _post_synthesis_obligation_validation(memo: str, contract: dict[str, Any]) -> dict[str, Any]:
    _, sections = _split_sections(memo)
    missing: list[dict[str, Any]] = []
    for section in sections:
        if section["title"].lower() in {"evidence trail", "sources"}:
            continue
        obligations = section_main_memo_obligations(section["title"], contract)
        if section["title"].strip().lower() == "decision cruxes":
            obligations = []
        issues = obligation_issues_for_text(obligations, section["markdown"], prefix="post-synthesis section missing obligation")
        for issue in issues:
            missing.append({"section": section["title"], "issue": issue})
    return {
        "schema_id": "section_obligation_validation_v1",
        "status": "passes" if not missing else "has_missing_obligations",
        "missing_count": len(missing),
        "missing": missing[:20],
    }


def _apply_attempt_report(report: dict[str, Any], result: dict[str, Any], *, deterministic_text: str) -> None:
    report.update({
        "status": result["status"],
        "accepted": bool(result["accepted"]),
        "issues": result["issues"],
        "attempts": result["attempts"],
        "attempt_count": result["attempt_count"],
    })
    if result.get("rewritten"):
        report["raw_word_count"] = len(str(result["rewritten"]).split())
        report["deterministic_word_count"] = len(deterministic_text.split())


def _structured_fallback_warning(issue: str) -> bool:
    return issue.startswith("section repeats evidence owned by ") or issue.startswith("section over-explains evidence owned by ")


def _section_contract(section: dict[str, str], full_contract: dict[str, Any]) -> dict[str, Any]:
    text = section["markdown"]
    title = section["title"]
    frame = full_contract.get("decision_frame", {}) if isinstance(full_contract.get("decision_frame"), dict) else {}
    section_jobs = frame.get("section_jobs", {}) if isinstance(frame.get("section_jobs"), dict) else {}
    required_evidence = [
        row for row in full_contract.get("required_evidence", [])
        if isinstance(row, dict)
        and _rewrite_mentions_anchor_row(text, row)
        and section_owns_evidence(title, row, full_contract)
    ]
    evidence_references = [
        compact_evidence_reference(title, row, full_contract)
        for row in full_contract.get("required_evidence", [])
        if isinstance(row, dict)
        and _rewrite_mentions_anchor_row(text, row)
        and not section_owns_evidence(title, row, full_contract)
    ]
    owned_elsewhere_evidence = [
        {**row, "reference_policy": evidence_reference_policy(title, row, full_contract)}
        for row in full_contract.get("required_evidence", [])
        if isinstance(row, dict)
        and not section_owns_evidence(title, row, full_contract)
    ]
    required_gaps = [
        gap for gap in _string_list(full_contract.get("required_gaps"))
        if "limit" in title.lower()
    ]
    required_cruxes = _section_required_cruxes(full_contract) if "crux" in title.lower() else []
    practical_actions = _section_practical_actions(title, full_contract, owned_elsewhere_evidence)
    main_memo_obligations = section_main_memo_obligations(title, full_contract)
    if title.strip().lower() == "decision cruxes":
        main_memo_obligations = []
    synthesis_packet = section_synthesis_packet(title, full_contract)
    synthesis_packet = prune_section_packet_for_ownership(title, synthesis_packet, owned_elsewhere_evidence)
    synthesis_packet["required_main_memo_obligations"] = main_memo_obligations
    section_contract = {
        "heading": title,
        "confidence": full_contract.get("confidence"),
        "requires_confidence": "**Confidence:**" in text,
        "required_evidence": required_evidence,
        "evidence_references": evidence_references,
        "owned_elsewhere_evidence": owned_elsewhere_evidence,
        "required_gaps": required_gaps,
        "required_cruxes": required_cruxes if isinstance(required_cruxes, list) else [],
        "required_main_memo_obligations": main_memo_obligations,
        "practical_actions": practical_actions if isinstance(practical_actions, list) else [],
        "min_decision_changing_cruxes": min(2, len(required_cruxes)) if "crux" in title.lower() else 0,
        "section_synthesis_packet": synthesis_packet,
        "_section_synthesis_scaffold": full_contract.get("_section_synthesis_scaffold", {}),
        "decision_frame": frame,
        "section_job": section_jobs.get(title, "Smooth this section while preserving its local evidence obligations."),
        "has_obligations": bool(required_evidence or required_gaps or required_cruxes or practical_actions or main_memo_obligations),
        "style": [
            "Keep the same heading.",
            "Use concrete prose; avoid internal phrases such as mapped support, map-backed read, and decision role.",
            "Prefer the decision-frame terms over generic intervention/option language when the frame provides them.",
            "For evidence_references, mention only the role-level implication when useful; do not restate full source details unless this section owns that evidence.",
            "Use short transition language only when it helps connect to adjacent sections.",
        ],
    }
    section_contract["model_section_packet"] = compile_model_section_packet(title, section_contract)
    return section_contract


def _section_practical_actions(
    title: str,
    full_contract: dict[str, Any],
    owned_elsewhere_evidence: list[dict[str, Any]],
) -> list[str]:
    if "practical" not in title.lower():
        return []
    rows = full_contract.get("practical_actions", [])
    if not isinstance(rows, list):
        return []
    actions: list[str] = []
    for action in rows:
        text = str(action).strip()
        if not text:
            continue
        if any(isinstance(row, dict) and _text_mentions_owned_elsewhere(text, row) for row in owned_elsewhere_evidence):
            continue
        actions.append(text)
    return actions


def _section_required_cruxes(full_contract: dict[str, Any]) -> list[dict[str, Any]]:
    selected = select_section_cruxes(full_contract, limit=3)
    if selected:
        return selected
    required = full_contract.get("required_cruxes", [])
    return [row for row in required if isinstance(row, dict)] if isinstance(required, list) else []


def _structured_decision_crux_section(contract: dict[str, Any]) -> str:
    cruxes = [row for row in contract.get("required_cruxes", []) if isinstance(row, dict)]
    if not cruxes:
        packet = contract.get("section_synthesis_packet", {}) if isinstance(contract.get("section_synthesis_packet"), dict) else {}
        artifacts = packet.get("decision_argument_artifacts", {}) if isinstance(packet.get("decision_argument_artifacts"), dict) else {}
        cruxes = [row for row in artifacts.get("structured_decision_cruxes", []) if isinstance(row, dict)]
    rows: list[list[str]] = []
    for row in cruxes[:3]:
        crux = _clean_crux_cell(str(row.get("crux", "")))
        why = _clean_crux_cell(str(row.get("why_it_matters", "")))
        current = _clean_crux_cell(_crux_current_read_cell(row, contract))
        change = _clean_crux_cell(str(row.get("would_change_if", "")))
        if crux and current and change:
            rows.append([crux, why or "This condition could change the recommendation.", current, change])
    if not rows:
        rows.append([
            "Whether the strongest counterevidence generalizes to the default case.",
            "This determines whether the answer should become narrower or more cautious.",
            "The current read treats the counterevidence as a boundary rather than the whole answer.",
            "The recommendation would change if stronger evidence showed the counterevidence applies broadly.",
        ])
    lines = [
        "## Decision Cruxes",
        "",
        "| Crux | Why it matters | Current read | Would change if |",
        "|---|---|---|---|",
    ]
    for row in rows:
        lines.append("| " + " | ".join(_markdown_cell(value) for value in row) + " |")
    return "\n".join(lines)

def _crux_current_read_cell(row: dict[str, Any], contract: dict[str, Any]) -> str:
    current = str(row.get("current_read", "")).strip()
    rows = contract.get("owned_elsewhere_evidence", [])
    for evidence in rows if current and isinstance(rows, list) else []:
        if isinstance(evidence, dict) and _rewrite_mentions_anchor_row(current, evidence):
            return "The current read treats this as a boundary or counterweight, not as decisive by itself."
    return current


def _clean_crux_cell(text: str) -> str:
    cleaned = re.sub(r"\bClaim\s+[A-Z]\b[:\s-]*", "", text, flags=re.I)
    cleaned = re.sub(r"\b(?:claim|relation|source)_?[a-z]*\d+\b", "", cleaned, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return _sentence(cleaned) if cleaned else ""


def _markdown_cell(text: str) -> str:
    return _short_text(re.sub(r"\|", "/", text).strip(), 220)


def _short_text(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned if len(cleaned) <= max_chars else cleaned[: max_chars - 3].rstrip(" ,.;") + "..."


def _decision_changing_crux_count(text: str) -> int:
    lowered = text.lower()
    explicit = len(re.findall(r"\b(?:would|could)\s+change\s+if\b|\brecommendation\s+would\s+change\b|\badvice\s+would\s+change\b", lowered))
    table_rows = 0
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        lowered = line.lower()
        if "crux" in lowered and "current" in lowered:
            continue
        if set(line.strip()) <= {"|", "-", ":", " "}:
            continue
        if "would change" in lowered and "if" in lowered:
            table_rows += 1
    return max(explicit, table_rows)


def _should_rewrite_section(section: dict[str, str], contract: dict[str, Any]) -> bool:
    words = len(section["markdown"].split())
    if words < 35 and not contract["has_obligations"]:
        return False
    if section["title"].lower() in {"evidence trail", "sources"}:
        return False
    return True


def _split_sections(markdown: str) -> tuple[str, list[dict[str, str]]]:
    matches = list(SECTION_RE.finditer(markdown))
    if not matches:
        return markdown, []
    leading = markdown[: matches[0].start()]
    sections: list[dict[str, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(markdown)
        title = match.group(1).strip()
        sections.append({"title": title, "markdown": markdown[start:end].strip()})
    return leading, sections


def _repair_section(text: str) -> str:
    repaired = clean_reader_memo_text(text)
    repaired = _replace_internal_reader_phrases(repaired)
    repaired = _repair_overclaim_strength_language(repaired)
    repaired = _repair_unbalanced_markdown_strong(repaired)
    return clean_reader_memo_text(repaired)


def _content_overlap(text: str, reference: str) -> int:
    text_terms = set(_content_terms(text))
    return sum(1 for term in _content_terms(reference) if term in text_terms)


def _has_generic_crux_language(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in (
            "current packet treats this condition",
            "new evidence showed the condition did not materially affect",
            "recommendation holds only where the actor can keep the intervention usable",
        )
    )


def _content_terms(text: str) -> list[str]:
    stop = {
        "the",
        "and",
        "that",
        "this",
        "with",
        "from",
        "into",
        "than",
        "when",
        "where",
        "which",
        "should",
        "whether",
        "recommendation",
        "change",
        "changes",
        "changed",
        "changing",
        "crux",
        "current",
        "would",
    }
    return [term for term in re.findall(r"[a-z0-9]{4,}", text.lower()) if term not in stop]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _write_section_debug_artifacts(artifacts: Any, index: int, title: str, result: dict[str, Any]) -> None:
    slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_") or f"section_{index + 1}"
    prefix = f"section_rewrite_{index + 1:02d}_{slug}"
    if result.get("prompt"):
        write_markdown(artifacts / f"{prefix}_prompt.txt", str(result.get("prompt", "")))
    if result.get("raw"):
        write_markdown(artifacts / f"{prefix}_raw.txt", str(result.get("raw", "")))
    write_json(artifacts / f"{prefix}_report.json", result.get("report", {}))
