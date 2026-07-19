from __future__ import annotations

import json
import re
from typing import Any

from epistemic_case_mapper.model_backends import run_model_backend


def arbitrate_canonical_decision_spine(
    spine: dict[str, Any],
    *,
    backend: str,
    backend_timeout: int | None,
    backend_retries: int,
) -> dict[str, Any]:
    prompt = build_spine_arbitration_prompt(spine)
    if backend.strip() == "prompt":
        return {
            "spine": spine,
            "report": _report("skipped_prompt_backend", "Prompt backend does not run model arbitration."),
            "prompt": prompt,
            "raw": "",
        }
    result = run_model_backend(prompt, backend, timeout_seconds=backend_timeout, max_retries=backend_retries)
    payload = _parse_json(result.text)
    if not isinstance(payload, dict):
        return {
            "spine": spine,
            "report": _report("invalid_model_output", "Model arbitration did not return a JSON object."),
            "prompt": prompt,
            "raw": result.text,
        }
    application = _apply_model_arbitration(spine, payload)
    return {
        "spine": application["spine"],
        "report": application["report"],
        "prompt": prompt,
        "raw": result.text,
    }


def build_spine_arbitration_prompt(spine: dict[str, Any]) -> str:
    packet = {
        "decision_question": spine.get("decision_question"),
        "current_status": spine.get("status"),
        "fields": _model_visible_fields(spine),
    }
    return (
        "You are reviewing a canonical decision-support spine.\n"
        "Choose salience only among the provided pre-validated fields. Use only supplied sources and IDs.\n"
        "Also write a concise default_answer_claim that directly answers the decision question using only the listed fields.\n"
        "The answer must name the subject of the question and use the question's natural answer vocabulary when it supplies options.\n"
        "Lead with the decision read, then include the most important caveat after it.\n"
        "If any counterevidence fields are listed, select at least one counterevidence_field_id and explain why it does or does not change the answer.\n"
        "The answer should be decision-ready prose, not a label, instruction, or study-by-study summary.\n"
        "Return only JSON with this schema:\n"
        "{\n"
        '  "default_answer_field_id": "field id from fields",\n'
        '  "default_answer_claim": "one grounded sentence or short paragraph",\n'
        '  "support_field_ids": ["field id"],\n'
        '  "counterevidence_field_ids": ["field id"],\n'
        '  "boundary_field_ids": ["field id"],\n'
        '  "rationale": "short reason grounded in the listed fields"\n'
        "}\n\n"
        "Allowed spine packet:\n"
        f"{json.dumps(packet, indent=2, ensure_ascii=False)}"
    )


def _apply_model_arbitration(spine: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    allowed = {field["field_id"]: field for field in _all_fields(spine) if field.get("field_id")}
    issues = _payload_issues(payload, allowed)
    if issues:
        return {"spine": spine, "report": _report("rejected_invalid_ids", "; ".join(issues))}
    updated = dict(spine)
    updated["model_arbitration"] = {
        "schema_id": "canonical_decision_spine_model_arbitration_v1",
        "status": "accepted",
        "default_answer_field_id": payload.get("default_answer_field_id"),
        "support_field_ids": _allowed_ids(payload.get("support_field_ids"), allowed),
        "counterevidence_field_ids": _allowed_ids(payload.get("counterevidence_field_ids"), allowed),
        "boundary_field_ids": _allowed_ids(payload.get("boundary_field_ids"), allowed),
        "rationale": _short_text(str(payload.get("rationale", "")), 360),
    }
    default_update = _model_default_answer_update(updated, payload, allowed)
    if default_update["accepted"]:
        updated["default_answer"] = default_update["default_answer"]
        updated["model_arbitration"]["accepted_default_answer_claim"] = default_update["default_answer"]["claim"]
    elif default_update["reason"]:
        updated["model_arbitration"]["default_answer_claim_rejection_reason"] = default_update["reason"]
    updated["strongest_support"] = _reordered_fields(updated.get("strongest_support", []), updated["model_arbitration"]["support_field_ids"])
    updated["strongest_counterevidence"] = _reordered_fields(updated.get("strongest_counterevidence", []), updated["model_arbitration"]["counterevidence_field_ids"])
    updated["population_boundaries"] = _reordered_fields(updated.get("population_boundaries", []), updated["model_arbitration"]["boundary_field_ids"])
    updated["dose_or_intensity_boundaries"] = _reordered_fields(updated.get("dose_or_intensity_boundaries", []), updated["model_arbitration"]["boundary_field_ids"])
    return {"spine": updated, "report": _report("accepted", "Model salience ordering accepted with existing provenance only.")}


def _payload_issues(payload: dict[str, Any], allowed: dict[str, dict[str, Any]]) -> list[str]:
    issues = []
    default_id = str(payload.get("default_answer_field_id", "")).strip()
    if default_id and default_id not in allowed:
        issues.append(f"default_answer_field_id not allowed: {default_id}")
    for key in ("support_field_ids", "counterevidence_field_ids", "boundary_field_ids"):
        for field_id in _string_list(payload.get(key)):
            if field_id not in allowed:
                issues.append(f"{key} contains unallowed field id: {field_id}")
    return issues


def _model_visible_fields(spine: dict[str, Any]) -> list[dict[str, Any]]:
    fields = []
    for field in _all_fields(spine):
        fields.append(
            {
                "field_id": field.get("field_id"),
                "role": field.get("role"),
                "claim": field.get("claim"),
                "source_ids": field.get("source_ids", [])[:4] if isinstance(field.get("source_ids"), list) else [],
                "candidate_card_ids": field.get("candidate_card_ids", [])[:4] if isinstance(field.get("candidate_card_ids"), list) else [],
                "confidence": field.get("confidence"),
            }
        )
    return fields


def _all_fields(spine: dict[str, Any]) -> list[dict[str, Any]]:
    fields = []
    default = spine.get("default_answer")
    if isinstance(default, dict):
        fields.append(default)
    for key in (
        "exception_answers",
        "dose_or_intensity_boundaries",
        "population_boundaries",
        "strongest_support",
        "strongest_counterevidence",
        "mechanism_or_proxy_evidence",
        "comparator_or_substitution",
        "evidence_quality_limits",
    ):
        fields.extend(row for row in spine.get(key, []) if isinstance(row, dict))
    return fields


def _reordered_fields(fields: Any, preferred_ids: list[str]) -> list[dict[str, Any]]:
    rows = [row for row in fields if isinstance(row, dict)]
    order = {field_id: index for index, field_id in enumerate(preferred_ids)}
    return sorted(rows, key=lambda row: (order.get(str(row.get("field_id")), len(order)), str(row.get("field_id", ""))))


def _allowed_ids(value: Any, allowed: dict[str, dict[str, Any]]) -> list[str]:
    return [field_id for field_id in _string_list(value) if field_id in allowed]


def _model_default_answer_update(
    spine: dict[str, Any],
    payload: dict[str, Any],
    allowed: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    default_id = str(payload.get("default_answer_field_id", "")).strip() or "default_answer"
    selected_default = allowed.get(default_id) or _dict(spine.get("default_answer"))
    current_default = _dict(spine.get("default_answer"))
    selected_fields = _selected_fields_for_grounding(payload, allowed, selected_default)
    claim = _short_text(str(payload.get("default_answer_claim", "")), 520)
    if not claim:
        if default_id and default_id != "default_answer" and selected_default:
            return {
                "accepted": True,
                "reason": "",
                "default_answer": _default_answer_from_selected_field(selected_default, current_default, selected_default.get("claim")),
            }
        return {"accepted": False, "reason": "", "default_answer": current_default}
    rejection = _default_answer_claim_rejection_reason(claim, selected_fields, question=str(spine.get("decision_question", "")))
    if not rejection and _has_counterevidence_available(spine) and not _allowed_ids(payload.get("counterevidence_field_ids"), allowed):
        rejection = "default_answer_claim_omits_available_counterevidence"
    if rejection:
        return {"accepted": False, "reason": rejection, "default_answer": current_default}
    return {
        "accepted": True,
        "reason": "",
        "default_answer": _default_answer_from_selected_field(selected_default, current_default, claim),
    }


def _default_answer_from_selected_field(
    selected: dict[str, Any],
    current: dict[str, Any],
    claim: Any,
) -> dict[str, Any]:
    updated = dict(current)
    for key in ("source_ids", "candidate_card_ids", "claim_ids", "quantity_ids", "confidence", "limits"):
        if selected.get(key):
            updated[key] = selected.get(key)
    updated["field_id"] = "default_answer"
    updated["role"] = "default_answer"
    updated["claim"] = _short_text(str(claim or current.get("claim") or selected.get("claim") or ""), 520)
    return updated


def _selected_fields_for_grounding(
    payload: dict[str, Any],
    allowed: dict[str, dict[str, Any]],
    selected_default: dict[str, Any],
) -> list[dict[str, Any]]:
    field_ids = [
        str(payload.get("default_answer_field_id", "")).strip(),
        *_allowed_ids(payload.get("support_field_ids"), allowed),
        *_allowed_ids(payload.get("counterevidence_field_ids"), allowed),
        *_allowed_ids(payload.get("boundary_field_ids"), allowed),
    ]
    fields = []
    if selected_default:
        fields.append(selected_default)
    for field_id in field_ids:
        field = allowed.get(field_id)
        if field and field not in fields:
            fields.append(field)
    return fields


def _has_counterevidence_available(spine: dict[str, Any]) -> bool:
    return any(isinstance(field, dict) and field.get("field_id") for field in spine.get("strongest_counterevidence", []))


def _default_answer_claim_rejection_reason(claim: str, selected_fields: list[dict[str, Any]], *, question: str) -> str:
    if _looks_like_answer_instruction(claim):
        return "default_answer_claim_looks_like_instruction"
    terms = _content_terms(claim)
    if len(terms) < 6:
        return "default_answer_claim_too_short"
    if len(terms) > 90:
        return "default_answer_claim_too_long"
    if "http://" in claim or "https://" in claim or "](" in claim:
        return "default_answer_claim_contains_citation_markup"
    evidence_terms = set(_content_terms(" ".join(str(field.get("claim", "")) for field in selected_fields)))
    overlap = set(terms) & evidence_terms
    if len(overlap) < 3:
        return "default_answer_claim_not_grounded_in_selected_fields"
    question_terms = set(_content_terms(question))
    question_overlap = set(terms) & question_terms
    if question_terms and len(question_overlap) < min(2, len(question_terms)):
        return "default_answer_claim_does_not_answer_question"
    return ""


def _looks_like_answer_instruction(text: str) -> bool:
    return str(text).strip().lower().startswith(
        (
            "state ",
            "write ",
            "say ",
            "explain ",
            "summarize ",
            "use ",
            "do not ",
            "avoid ",
        )
    )


def _content_terms(text: str) -> list[str]:
    stopwords = {
        "about",
        "after",
        "also",
        "among",
        "answer",
        "because",
        "being",
        "brief",
        "could",
        "current",
        "decision",
        "does",
        "evidence",
        "from",
        "have",
        "into",
        "only",
        "question",
        "should",
        "source",
        "that",
        "their",
        "there",
        "these",
        "this",
        "under",
        "using",
        "when",
        "where",
        "which",
        "while",
        "with",
        "without",
        "would",
    }
    terms = []
    for term in re.findall(r"[a-z0-9][a-z0-9'-]{2,}", str(text).lower()):
        if term not in stopwords and term not in terms:
            terms.append(term)
    return terms


def _parse_json(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            return None


def _report(status: str, message: str) -> dict[str, Any]:
    return {
        "schema_id": "canonical_decision_spine_model_arbitration_report_v1",
        "status": status,
        "message": message,
    }


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _short_text(text: str, limit: int) -> str:
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "..."


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
