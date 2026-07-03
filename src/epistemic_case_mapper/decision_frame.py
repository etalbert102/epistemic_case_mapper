from __future__ import annotations

import re
from typing import Any


GENERIC_TERMS = (
    "intervention",
    "option",
    "setting, scale, population, and intensity",
    "all versions of the intervention",
    "adoption",
)


def build_decision_frame(
    candidate_map: dict[str, Any],
    evidence_ledger: dict[str, Any],
    quality_report: dict[str, Any],
    *,
    question: str,
) -> dict[str, Any]:
    text = _case_text(candidate_map, evidence_ledger, question)
    frame_type = _frame_type(text, question)
    source_role = _source_role(text)
    direct_answer = _direct_answer(frame_type, source_role)
    return {
        "schema_id": "decision_frame_v1",
        "method": "deterministic_question_and_evidence_role_inference",
        "frame_type": frame_type,
        "source_role": source_role,
        "decision_object": _decision_object(frame_type),
        "allowed_use": _allowed_use(frame_type, source_role),
        "not_deciding": _not_deciding(frame_type),
        "direct_answer": direct_answer,
        "opening_template": direct_answer,
        "section_jobs": _section_jobs(frame_type),
        "practical_actions": _practical_actions(frame_type),
        "preferred_terms": _preferred_terms(frame_type),
        "generic_terms_to_avoid": list(GENERIC_TERMS),
        "confidence_cap": _confidence_cap(quality_report),
    }


def refine_crux_contract(crux_contract: dict[str, Any], candidate_map: dict[str, Any]) -> dict[str, Any]:
    claim_lookup = {str(claim.get("claim_id", "")): claim for claim in _claims(candidate_map)}
    refined: list[dict[str, Any]] = []
    for row in crux_contract.get("cruxes", []) if isinstance(crux_contract.get("cruxes"), list) else []:
        if not isinstance(row, dict):
            continue
        source = claim_lookup.get(str(row.get("source_claim", "")), {})
        target = claim_lookup.get(str(row.get("target_claim", "")), {})
        if not _claim_text(source) and not _claim_text(target):
            continue
        refined.append(_refine_crux_row(row, source, target))
    return {
        "schema_id": "refined_crux_contract_v1",
        "method": "relation_claim_text_grounding_and_generic_placeholder_repair",
        "cruxes": _dedupe_cruxes(refined)[:5],
        "rejected_count": max(0, int(crux_contract.get("crux_count", len(refined))) - len(refined)),
    }


def memo_quality_report(markdown: str, scaffold: dict[str, Any]) -> dict[str, Any]:
    frame = _frame(scaffold)
    issues: list[dict[str, str]] = []
    generic_hits = _generic_term_hits(markdown, frame)
    for term in generic_hits:
        issues.append({"severity": "warning", "issue_type": "generic_template_language", "message": f"Generic term remains visible: {term}"})
    if _has_generic_crux_language(markdown):
        issues.append({"severity": "risk", "issue_type": "generic_crux_language", "message": "Crux table contains placeholder current-read or reversal language."})
    if _first_paragraph_is_procedural(markdown):
        issues.append({"severity": "risk", "issue_type": "procedural_opening", "message": "Opening tells the writer what to say instead of answering the reader."})
    if _inventory_heavy(markdown):
        issues.append({"severity": "warning", "issue_type": "inventory_heavy_prose", "message": "Main memo still reads like evidence inventory rather than synthesized decision support."})
    score = max(0, 100 - sum(20 if issue["severity"] == "risk" else 8 for issue in issues))
    return {
        "schema_id": "memo_quality_report_v1",
        "method": "frame_aware_template_leakage_and_crux_lints",
        "status": "polished" if score >= 90 else "usable_with_review" if score >= 70 else "needs_revision",
        "score": score,
        "frame_type": frame.get("frame_type", "unknown"),
        "generic_term_hits": generic_hits,
        "issues": issues,
    }


def _refine_crux_row(row: dict[str, Any], source: dict[str, Any], target: dict[str, Any]) -> dict[str, Any]:
    source_text = _claim_text(source)
    target_text = _claim_text(target)
    relation_type = str(row.get("relation_type", "")).replace("_", " ").strip()
    crux = str(row.get("crux", "")).strip()
    if _generic_crux_label(crux) and source_text and target_text:
        crux = _semantic_crux_label(source_text)
    current = str(row.get("current_read", "")).strip()
    if _generic_crux_cell(current) and source_text:
        current = _snippet(source_text, 180)
    would_change = str(row.get("would_change_if", "")).strip()
    if _generic_crux_cell(would_change) and source_text:
        would_change = "New evidence showed that this concern is false or immaterial to the interpretation."
    why = str(row.get("why_it_matters", "")).strip()
    if (_generic_crux_cell(why) or re.search(r"\bclaim\s+[ab]\b", why, flags=re.IGNORECASE)) and relation_type:
        why = f"This {relation_type} relation marks a condition that can change the interpretation of the evidence."
    return {
        **row,
        "crux": crux,
        "current_read": current,
        "would_change_if": would_change,
        "why_it_matters": why,
        "refined": True,
    }


def _frame_type(text: str, question: str) -> str:
    lowered = f" {text.lower()} {question.lower()} "
    if any(marker in lowered for marker in (" debate", " debater", " judge", "postmortem", "process critique", "methodology", "bayesian", "argument")):
        return "process_or_method_evaluation"
    if any(marker in lowered for marker in (" adjudicat", " origins", " cause ", "causal", "which explanation")):
        return "evidence_adjudication"
    if any(marker in lowered for marker in (" should ", "adopt", "implement", "policy", "recommend", "pilot")):
        return "action_or_policy_decision"
    if any(marker in lowered for marker in (" versus ", " vs ", " compared", " rather than ", " over ")):
        return "comparative_option_decision"
    return "general_evidence_use"


def _source_role(text: str) -> str:
    lowered = text.lower()
    if any(marker in lowered for marker in ("scope-setting", "case study", "postmortem", "process critique")):
        return "scope-setting evidence packet"
    if any(marker in lowered for marker in ("review", "commentary", "blog", "debate")):
        return "interpretive source packet"
    return "source packet"


def _direct_answer(frame_type: str, source_role: str) -> str:
    if frame_type == "process_or_method_evaluation":
        return f"Use this {source_role} to evaluate process and method failure modes, not as a neutral adjudication of the underlying dispute."
    if frame_type == "evidence_adjudication":
        return f"Use this {source_role} as a scoped contribution to the adjudication, not as a complete resolution of the case."
    if frame_type == "action_or_policy_decision":
        return "Treat the current answer as conditional on the named implementation constraints, risks, and missing evidence."
    if frame_type == "comparative_option_decision":
        return "Compare the named alternatives directly, and keep the conditions that would reverse the preference visible."
    return f"Use this {source_role} as structured decision support with named limits, not as a final literature review."


def _allowed_use(frame_type: str, source_role: str) -> str:
    if frame_type == "process_or_method_evaluation":
        return f"Diagnose process, method, and interpretation failure modes using the {source_role}."
    return f"Use the {source_role} to support a scoped, uncertainty-aware decision read."


def _not_deciding(frame_type: str) -> str:
    if frame_type == "process_or_method_evaluation":
        return "The memo is not deciding the underlying scientific or factual dispute on its own."
    return "The memo is not claiming the current source packet exhausts the evidence base."


def _decision_object(frame_type: str) -> str:
    return {
        "process_or_method_evaluation": "process and method read",
        "evidence_adjudication": "evidence adjudication read",
        "action_or_policy_decision": "action read",
        "comparative_option_decision": "comparative read",
    }.get(frame_type, "decision-support read")


def _section_jobs(frame_type: str) -> dict[str, str]:
    if frame_type == "process_or_method_evaluation":
        return {
            "Decision Brief": "State what the packet is useful for and what it should not be used to adjudicate.",
            "Practical Read": "Name concrete uses for future investigations, debate design, or postmortem review.",
            "Why This Read": "Explain the process or method failure modes, not just the evidence inventory.",
            "Decision Cruxes": "Name conditions that would change the process/method lesson.",
            "Limits of the Current Map": "Separate source-scope limits from unresolved factual disputes.",
        }
    return {
        "Decision Brief": "Answer the decision question directly with calibrated uncertainty.",
        "Practical Read": "Name concrete actions or checks implied by the evidence.",
        "Why This Read": "Explain why the support, tensions, and scope limits produce this read.",
        "Decision Cruxes": "Name conditions that would change the answer.",
        "Limits of the Current Map": "State missing evidence and scope limits without filling them by inference.",
    }


def _practical_actions(frame_type: str) -> list[str]:
    if frame_type == "process_or_method_evaluation":
        return [
            "Use the packet for postmortem and process critique.",
            "Do not treat public-debate nonresponse as evidence by itself.",
            "Keep method-feedback failures separate from the underlying factual dispute.",
            "Compare adjudication methods before treating a debate result as decisive.",
        ]
    return []


def _preferred_terms(frame_type: str) -> list[str]:
    if frame_type == "process_or_method_evaluation":
        return ["source packet", "process critique", "method", "debate", "adjudication", "evidence"]
    return ["source packet", "evidence", "decision read", "scope", "uncertainty"]


def _case_text(candidate_map: dict[str, Any], evidence_ledger: dict[str, Any], question: str) -> str:
    claims = " ".join(_claim_text(claim) for claim in _claims(candidate_map))
    rows = " ".join(str(row.get("claim", "")) for row in evidence_ledger.get("all_evidence", []) if isinstance(row, dict))
    title = str(candidate_map.get("title", ""))
    return " ".join([question, title, claims, rows])


def _claims(candidate_map: dict[str, Any]) -> list[dict[str, Any]]:
    return [claim for claim in candidate_map.get("claims", []) if isinstance(claim, dict)]


def _claim_text(claim: dict[str, Any]) -> str:
    return str(claim.get("claim") or claim.get("text") or "").strip()


def _snippet(text: str, max_chars: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip().rstrip(".")
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[:max_chars].rsplit(" ", 1)[0].rstrip(" ,;:")


def _semantic_crux_label(source_text: str) -> str:
    lowered = source_text.lower()
    if any(marker in lowered for marker in ("feedback", "probabilistic", "probability", "judge")):
        return "Whether judge feedback and probability calibration change the interpretation"
    if any(marker in lowered for marker in ("public debate", "challenge", "rhetoric")):
        return "Whether public-debate rhetoric should count as evidence"
    return "Whether the stated concern changes the interpretation"


def _generic_crux_label(value: str) -> bool:
    lowered = value.lower()
    return lowered in {"decision-changing condition", "tradeoff between competing evidence", "implementation dependency"} or lowered.startswith("another line of evidence")


def _generic_crux_cell(value: str) -> bool:
    lowered = value.lower()
    return not value.strip() or any(
        marker in lowered
        for marker in (
            "current packet treats this condition",
            "new evidence showed the condition did not materially affect",
            "changing this condition would materially alter",
            "not specified",
        )
    )


def _dedupe_cruxes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for row in rows:
        key = " ".join(re.findall(r"[a-z0-9]{4,}", str(row.get("crux", "")).lower())[:10])
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _frame(scaffold: dict[str, Any]) -> dict[str, Any]:
    value = scaffold.get("decision_frame", {})
    return value if isinstance(value, dict) else {}


def _generic_term_hits(markdown: str, frame: dict[str, Any]) -> list[str]:
    if frame.get("frame_type") not in {"process_or_method_evaluation", "evidence_adjudication"}:
        return []
    lowered = markdown.lower()
    return [term for term in GENERIC_TERMS if term in lowered]


def _has_generic_crux_language(markdown: str) -> bool:
    lowered = markdown.lower()
    return any(marker in lowered for marker in ("current packet treats this condition", "new evidence showed the condition did not materially affect"))


def _first_paragraph_is_procedural(markdown: str) -> bool:
    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", markdown) if part.strip() and not part.strip().startswith("##")]
    if not paragraphs:
        return False
    lowered = paragraphs[0].lower()
    return lowered.startswith("state ") or "do not frame" in lowered


def _inventory_heavy(markdown: str) -> bool:
    main = markdown.split("## Evidence Trail", 1)[0]
    inventory_markers = len(re.findall(r"\b(?:main support|scope and boundary|evidence type|implementation constraints):", main, flags=re.IGNORECASE))
    return inventory_markers >= 5


def _confidence_cap(quality_report: dict[str, Any]) -> str:
    status = str(quality_report.get("status", "")).lower()
    if "fail" in status or "insufficient" in status:
        return "low"
    if "review" in status or "warning" in status:
        return "medium"
    return "high"
