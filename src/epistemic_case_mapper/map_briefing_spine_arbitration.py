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
        "Choose salience only among the provided pre-validated fields. Do not invent claims, sources, or IDs.\n"
        "Return only JSON with this schema:\n"
        "{\n"
        '  "default_answer_field_id": "field id from fields",\n'
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
