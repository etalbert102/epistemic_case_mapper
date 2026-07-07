from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class SpineField(BaseModel):
    model_config = ConfigDict(extra="allow")

    field_id: str
    claim: str
    role: str
    source_ids: list[str] = Field(default_factory=list)
    candidate_card_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    quantity_ids: list[str] = Field(default_factory=list)
    confidence: str = "medium"
    limits: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_traceability(self) -> "SpineField":
        method_backed = self.role in {"missing_slot", "evidence_quality_limit"} and self.limits
        if not method_backed and not (self.source_ids or self.candidate_card_ids or self.claim_ids):
            raise ValueError("evidence-backed spine field lacks traceability")
        return self


class CanonicalDecisionSpine(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_id: str = "canonical_decision_spine_v1"
    decision_question: str
    status: str = "warning"
    default_answer: SpineField
    exception_answers: list[SpineField] = Field(default_factory=list)
    dose_or_intensity_boundaries: list[SpineField] = Field(default_factory=list)
    population_boundaries: list[SpineField] = Field(default_factory=list)
    strongest_support: list[SpineField] = Field(default_factory=list)
    strongest_counterevidence: list[SpineField] = Field(default_factory=list)
    mechanism_or_proxy_evidence: list[SpineField] = Field(default_factory=list)
    comparator_or_substitution: list[SpineField] = Field(default_factory=list)
    evidence_quality_limits: list[SpineField] = Field(default_factory=list)
    missing_decision_slots: list[SpineField] = Field(default_factory=list)
    confidence: str = "medium"
    source_anchors: list[dict[str, Any]] = Field(default_factory=list)


def validate_canonical_decision_spine(spine: dict[str, Any]) -> dict[str, Any]:
    issues: list[str] = []
    try:
        parsed = CanonicalDecisionSpine.model_validate(spine)
    except ValidationError as exc:
        return {
            "schema_id": "canonical_decision_spine_validation_v1",
            "status": "invalid",
            "issue_count": len(exc.errors()),
            "issues": [str(error.get("msg", "")) for error in exc.errors()],
        }
    field_ids = _all_field_ids(parsed)
    if len(field_ids) != len(set(field_ids)):
        issues.append("duplicate_spine_field_ids")
    if not parsed.default_answer.claim.strip():
        issues.append("missing_default_answer_claim")
    if parsed.missing_decision_slots and parsed.status == "ready":
        issues.append("ready_spine_has_missing_decision_slots")
    orphan_fields = [
        field.field_id
        for field in _all_fields(parsed)
        if field.role not in {"missing_slot", "evidence_quality_limit"}
        and not (field.source_ids or field.candidate_card_ids or field.claim_ids)
    ]
    for field_id in orphan_fields:
        issues.append(f"{field_id}: evidence-backed field lacks anchors")
    return {
        "schema_id": "canonical_decision_spine_validation_v1",
        "status": "valid" if not issues else "warning",
        "issue_count": len(issues),
        "issues": issues,
        "field_count": len(field_ids),
        "source_anchor_count": len(parsed.source_anchors),
    }


def build_decision_spine_consistency_report(
    spine: dict[str, Any],
    slot_eligibility_audit: dict[str, Any],
) -> dict[str, Any]:
    issues = []
    missing_slot_ids = {
        str(field.get("slot_id") or field.get("field_id", "")).replace("missing_", "")
        for field in spine.get("missing_decision_slots", [])
        if isinstance(field, dict)
    }
    for slot in slot_eligibility_audit.get("slots", []) if isinstance(slot_eligibility_audit.get("slots"), list) else []:
        if not isinstance(slot, dict):
            continue
        slot_id = str(slot.get("slot_id", ""))
        if slot.get("status") == "filled" and slot_id in missing_slot_ids:
            issues.append(f"{slot_id}: filled in eligibility audit but missing in spine")
    default_sources = set(_string_list(_dict(spine.get("default_answer")).get("source_ids")))
    if not default_sources and _dict(spine.get("default_answer")).get("role") != "missing_slot":
        issues.append("default_answer_lacks_source_anchor")
    return {
        "schema_id": "decision_spine_consistency_report_v1",
        "status": "pass" if not issues else "warning",
        "issue_count": len(issues),
        "issues": issues,
    }


def _all_fields(parsed: CanonicalDecisionSpine) -> list[SpineField]:
    fields = [parsed.default_answer]
    for key in (
        "exception_answers",
        "dose_or_intensity_boundaries",
        "population_boundaries",
        "strongest_support",
        "strongest_counterevidence",
        "mechanism_or_proxy_evidence",
        "comparator_or_substitution",
        "evidence_quality_limits",
        "missing_decision_slots",
    ):
        fields.extend(getattr(parsed, key))
    return fields


def _all_field_ids(parsed: CanonicalDecisionSpine) -> list[str]:
    return [field.field_id for field in _all_fields(parsed)]


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
