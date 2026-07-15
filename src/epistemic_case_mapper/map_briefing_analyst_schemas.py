from __future__ import annotations

from copy import deepcopy
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


MemoUse = Literal[
    "load_bearing_primary_support",
    "load_bearing_counterweight",
    "quantitative_anchor",
    "scope_or_applicability",
    "decision_crux",
    "mechanism_or_context",
    "background_only",
    "covered_by_group",
    "not_decision_relevant",
    "needs_human_or_model_review",
]

AnswerRelation = Literal[
    "supports_answer",
    "challenges_answer",
    "bounds_scope",
    "identifies_crux",
    "contextualizes_answer",
    "not_decision_relevant",
    "uncertain_relation",
]


class EvidenceAdjudicationRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_item_id: str
    memo_use: MemoUse
    importance_rank: int = Field(ge=1, le=100)
    rationale: str = Field(min_length=1)
    answer_relation: AnswerRelation = "uncertain_relation"
    covered_by: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    quantity_values: list[str] = Field(default_factory=list)
    target_answer_option: str = ""
    effect_on_final_answer: str = ""
    tension_type: str = ""
    downgrade_reason: str = ""

    @field_validator("covered_by", "source_ids", "quantity_values", mode="before")
    @classmethod
    def _list_field(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []

    @field_validator("evidence_item_id", "rationale", mode="before")
    @classmethod
    def _strip_required_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("downgrade_reason", "target_answer_option", "effect_on_final_answer", "tension_type", mode="before")
    @classmethod
    def _strip_optional_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("memo_use", mode="before")
    @classmethod
    def _normalize_memo_use(cls, value: Any) -> str:
        return _memo_use_alias(str(value or ""))

    @field_validator("answer_relation", mode="before")
    @classmethod
    def _normalize_answer_relation(cls, value: Any) -> str:
        return _answer_relation_alias(str(value or ""))

    @model_validator(mode="after")
    def _validate_covered_by(self) -> "EvidenceAdjudicationRow":
        if self.memo_use == "covered_by_group" and not self.covered_by:
            raise ValueError("covered_by_group rows must name covered_by target IDs")
        if self.evidence_item_id in set(self.covered_by):
            raise ValueError("covered_by cannot point to the same evidence_item_id")
        return self


class AnalystAdjudication(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["analyst_adjudication_v1"] = "analyst_adjudication_v1"
    decision_question: str
    rows: list[EvidenceAdjudicationRow]
    overall_rationale: str = ""

    @model_validator(mode="after")
    def _unique_rows(self) -> "AnalystAdjudication":
        ids = [row.evidence_item_id for row in self.rows]
        if len(ids) != len(set(ids)):
            raise ValueError("rows must have unique evidence_item_id values")
        return self


class AnalystAnswerFrame(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["analyst_answer_frame_v1"] = "analyst_answer_frame_v1"
    decision_question: str
    direct_answer: str = Field(min_length=1)
    confidence: Literal["low", "medium", "high", "not_specified"] = "not_specified"
    why_this_read: str = Field(min_length=1)
    strongest_counterargument: str = ""
    why_counterargument_does_or_does_not_change_answer: str = ""
    scope: str = ""
    what_would_change_the_answer: str = ""
    must_not_overstate: list[str] = Field(default_factory=list)
    supporting_evidence_item_ids: list[str] = Field(default_factory=list)
    counterweight_evidence_item_ids: list[str] = Field(default_factory=list)
    scope_evidence_item_ids: list[str] = Field(default_factory=list)


class AnalystEvidenceGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str
    proposition: str = Field(min_length=1)
    memo_role: MemoUse
    source_memo_role: str = ""
    importance_rank: int = Field(default=100, ge=1, le=100)
    covered_evidence_item_ids: list[str] = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    source_labels: list[str] = Field(default_factory=list)
    quantity_values: list[str] = Field(default_factory=list)
    applicability_limits: list[str] = Field(default_factory=list)
    answer_relation: AnswerRelation = "uncertain_relation"
    target_answer_option: str = ""
    effect_on_final_answer: str = ""
    tension_type: str = ""
    rationale: str = Field(min_length=1)
    conflict_note: str = ""
    evidence_strength: str = ""
    answer_impact: str = ""
    uncertainty_type: str = ""
    source_appraisal: dict[str, Any] = Field(default_factory=dict)
    source_use_warnings: list[str] = Field(default_factory=list)
    allowed_wording: dict[str, Any] = Field(default_factory=dict)

    @field_validator("answer_relation", mode="before")
    @classmethod
    def _normalize_answer_relation(cls, value: Any) -> str:
        return _answer_relation_alias(str(value or ""))

    @field_validator("source_memo_role", "target_answer_option", "effect_on_final_answer", "tension_type", mode="before")
    @classmethod
    def _strip_optional_text(cls, value: Any) -> str:
        return str(value or "").strip()


class AnalystSynthesisPacket(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["analyst_synthesis_packet_v1"] = "analyst_synthesis_packet_v1"
    decision_question: str
    bottom_line: str = Field(min_length=1)
    primary_reasoning_chain: list[AnalystEvidenceGroup] = Field(default_factory=list)
    main_counterweights: list[AnalystEvidenceGroup] = Field(default_factory=list)
    decision_cruxes: list[AnalystEvidenceGroup] = Field(default_factory=list)
    scope_and_applicability: list[AnalystEvidenceGroup] = Field(default_factory=list)
    quantitative_anchors: list[AnalystEvidenceGroup] = Field(default_factory=list)
    background_context: list[AnalystEvidenceGroup] = Field(default_factory=list)
    must_not_overstate: list[str] = Field(default_factory=list)
    warnings_to_address: list[str] = Field(default_factory=list)
    warning_obligations: list[dict[str, Any]] = Field(default_factory=list)
    argument_plan: list[dict[str, Any]] = Field(default_factory=list)
    decision_logic: dict[str, Any] = Field(default_factory=dict)
    writer_guidance_packet: dict[str, Any] = Field(default_factory=dict)
    source_notes: list[dict[str, Any]] = Field(default_factory=list)
    evidence_accounting_summary: dict[str, Any] = Field(default_factory=dict)


class AnalystDecisionEvidenceGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    group_id: str
    proposition: str = Field(min_length=1)
    memo_role: MemoUse
    source_memo_role: str = ""
    importance_rank: int = Field(default=100, ge=1, le=100)
    covered_evidence_item_ids: list[str] = Field(min_length=1)
    answer_relation: AnswerRelation = "uncertain_relation"
    target_answer_option: str = ""
    effect_on_final_answer: str = ""
    tension_type: str = ""
    rationale: str = Field(min_length=1)
    evidence_strength: str = ""
    answer_impact: str = ""
    uncertainty_type: str = ""
    applicability_limits: list[str] = Field(default_factory=list)
    conflict_note: str = ""

    @field_validator("covered_evidence_item_ids", "applicability_limits", mode="before")
    @classmethod
    def _list_field(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []

    @field_validator("memo_role", mode="before")
    @classmethod
    def _normalize_memo_role(cls, value: Any) -> str:
        return _memo_use_alias(str(value or ""))

    @field_validator("answer_relation", mode="before")
    @classmethod
    def _normalize_answer_relation(cls, value: Any) -> str:
        return _answer_relation_alias(str(value or ""))

    @field_validator("source_memo_role", "target_answer_option", "effect_on_final_answer", "tension_type", mode="before")
    @classmethod
    def _strip_optional_text(cls, value: Any) -> str:
        return str(value or "").strip()


class AnalystEvidenceDisposition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_item_id: str
    disposition: Literal["foreground", "background", "not_decision_relevant", "covered_by_group", "needs_review"]
    group_id: str = ""
    rationale: str = ""

    @field_validator("evidence_item_id", "group_id", "rationale", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> str:
        text = str(value or "").strip()
        if text.lower().replace("_", " ") in {"none", "no group", "n/a", "na", "null"}:
            return ""
        return text

    @field_validator("disposition", mode="before")
    @classmethod
    def _normalize_disposition(cls, value: Any) -> str:
        text = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
        return {
            "background_only": "background",
            "covered": "covered_by_group",
            "review": "needs_review",
            "needs_human_or_model_review": "needs_review",
        }.get(text, text)


MemoInclusion = Literal["memo_spine", "supporting_context", "trace_only", "exclude"]
QuantityInclusion = Literal["must_use", "supporting_context", "trace_only", "exclude"]


class AnalystMemoRelevanceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_item_id: str
    memo_inclusion: MemoInclusion
    rationale: str = Field(min_length=1)
    group_id: str = ""
    source_ids: list[str] = Field(default_factory=list)

    @field_validator("evidence_item_id", "memo_inclusion", "rationale", "group_id", mode="before")
    @classmethod
    def _strip_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("source_ids", mode="before")
    @classmethod
    def _list_field(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []

    @field_validator("memo_inclusion", mode="before")
    @classmethod
    def _normalize_memo_inclusion(cls, value: Any) -> str:
        return _memo_inclusion_alias(str(value or ""))


class AnalystQuantityRelevanceDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_item_id: str
    quantity_value: str
    memo_inclusion: QuantityInclusion
    quantity_role: Literal["decision_anchor", "supporting_detail", "study_descriptor", "statistical_detail", "audit_only"] = "audit_only"
    retention_phrase: str = ""
    rationale: str = Field(min_length=1)

    @field_validator(
        "evidence_item_id",
        "quantity_value",
        "memo_inclusion",
        "quantity_role",
        "retention_phrase",
        "rationale",
        mode="before",
    )
    @classmethod
    def _strip_text(cls, value: Any) -> str:
        return str(value or "").strip()

    @field_validator("memo_inclusion", mode="before")
    @classmethod
    def _normalize_quantity_inclusion(cls, value: Any) -> str:
        return _quantity_inclusion_alias(str(value or ""))


class AnalystDecisionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["analyst_decision_model_v1"] = "analyst_decision_model_v1"
    decision_question: str
    direct_answer: str = Field(min_length=1)
    confidence: Literal["low", "medium", "high", "not_specified"] = "not_specified"
    overall_rationale: str = Field(min_length=1)
    evidence_groups: list[AnalystDecisionEvidenceGroup] = Field(default_factory=list)
    evidence_dispositions: list[AnalystEvidenceDisposition] = Field(default_factory=list)
    quantitative_anchors: list[str] = Field(default_factory=list)
    what_would_change_the_answer: list[str] = Field(default_factory=list)
    memo_relevance_decisions: list[AnalystMemoRelevanceDecision] = Field(default_factory=list)
    quantity_relevance_decisions: list[AnalystQuantityRelevanceDecision] = Field(default_factory=list)
    argument_plan: list[dict[str, Any]] = Field(default_factory=list)
    decision_logic: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize_payload_aliases(cls, value: Any) -> Any:
        return _normalize_decision_model_payload(value)

    @field_validator("quantitative_anchors", "what_would_change_the_answer", mode="before")
    @classmethod
    def _list_field(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []

    @model_validator(mode="after")
    def _unique_group_and_disposition_ids(self) -> "AnalystDecisionModel":
        group_ids = [group.group_id for group in self.evidence_groups]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("evidence_groups must have unique group_id values")
        disposition_ids = [row.evidence_item_id for row in self.evidence_dispositions]
        if len(disposition_ids) != len(set(disposition_ids)):
            raise ValueError("evidence_dispositions must have unique evidence_item_id values")
        return self


WarningMemoAction = Literal[
    "incorporate_as_counterweight",
    "bound_scope_or_confidence",
    "background_context",
    "not_needed_for_memo",
]


class AnalystWarningObligation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    warning_id: str
    memo_action: WarningMemoAction
    obligation: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    source_labels: list[str] = Field(default_factory=list)
    key_terms: list[str] = Field(default_factory=list)

    @field_validator("source_ids", "source_labels", "key_terms", mode="before")
    @classmethod
    def _list_field(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []


class AnalystDecisionLogic(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bounded_bottom_line: str = ""
    support_summary: str = ""
    strongest_counterweight: str = ""
    counterweight_weighting: str = ""
    reconciled_cruxes: list[str] = Field(default_factory=list)
    scope_boundaries: list[str] = Field(default_factory=list)
    practical_implications: list[str] = Field(default_factory=list)
    do_not_overstate: list[str] = Field(default_factory=list)

    @field_validator("reconciled_cruxes", "scope_boundaries", "practical_implications", "do_not_overstate", mode="before")
    @classmethod
    def _list_field(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []


class AnalystPacketRefinement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_id: Literal["analyst_packet_refinement_v1"] = "analyst_packet_refinement_v1"
    decision_question: str
    direct_answer: str = Field(min_length=1)
    answer_rationale: str = Field(min_length=1)
    decision_logic: AnalystDecisionLogic = Field(default_factory=AnalystDecisionLogic)
    warning_obligations: list[AnalystWarningObligation] = Field(default_factory=list)
    argument_plan: list[dict[str, Any]] = Field(default_factory=list)


def build_analyst_adjudication_parse_report(
    payload: Any,
    ledger: dict[str, Any],
    *,
    expected_evidence_item_ids: list[str] | None = None,
    known_evidence_item_ids: list[str] | None = None,
) -> dict[str, Any]:
    expected_ids = expected_evidence_item_ids or _ledger_ids(ledger)
    known_ids = set(known_evidence_item_ids or _ledger_ids(ledger))
    payload = _normalize_adjudication_payload(payload)
    try:
        parsed = AnalystAdjudication.model_validate(payload)
    except ValidationError as exc:
        return {
            "schema_id": "analyst_adjudication_parse_report_v1",
            "status": "invalid_schema",
            "valid": False,
            "errors": _jsonable_errors(exc),
            "missing_evidence_item_ids": expected_ids,
            "unknown_evidence_item_ids": [],
            "invalid_covered_by": [],
        }
    row_ids = [row.evidence_item_id for row in parsed.rows]
    unknown = sorted({row_id for row_id in row_ids if row_id not in known_ids})
    missing = sorted(set(expected_ids) - set(row_ids))
    invalid_covered_by = sorted(
        {
            target
            for row in parsed.rows
            for target in row.covered_by
            if target not in known_ids and target not in row_ids
        }
    )
    issues = [
        *(["missing_ledger_rows"] if missing else []),
        *(["unknown_evidence_item_ids"] if unknown else []),
        *(["invalid_covered_by_targets"] if invalid_covered_by else []),
    ]
    return {
        "schema_id": "analyst_adjudication_parse_report_v1",
        "status": "ready" if not issues else "warning",
        "valid": not issues,
        "row_count": len(parsed.rows),
        "ledger_row_count": len(expected_ids),
        "missing_evidence_item_ids": missing,
        "unknown_evidence_item_ids": unknown,
        "invalid_covered_by": invalid_covered_by,
        "issues": issues,
    }


def analyst_decision_retention_obligations(ledger: dict[str, Any]) -> dict[str, list[str]]:
    rows = [row for row in ledger.get("rows", []) if isinstance(row, dict)]
    obligations = {
        "quantitative_anchor_ids": [],
        "counterweight_ids": [],
        "crux_ids": [],
        "scope_boundary_ids": [],
    }
    for row in rows:
        evidence_id = str(row.get("evidence_item_id") or "").strip()
        if not evidence_id:
            continue
        role_text = " ".join(
            str(value or "")
            for value in (
                row.get("current_role"),
                row.get("directionality"),
                row.get("relation_semantic_role"),
            )
        ).lower()
        relation_type = str(row.get("relation_semantic_role") or row.get("directionality") or "").lower()
        if _has_quantity(row):
            obligations["quantitative_anchor_ids"].append(evidence_id)
        if "counterweight" in role_text or "challenge" in role_text or relation_type in {"in_tension_with", "challenges"}:
            obligations["counterweight_ids"].append(evidence_id)
        if "crux" in role_text or relation_type == "crux_for":
            obligations["crux_ids"].append(evidence_id)
        if "scope" in role_text or "applicability" in role_text or relation_type in {"depends_on", "refines"}:
            obligations["scope_boundary_ids"].append(evidence_id)
    return {key: _dedupe_ids(values) for key, values in obligations.items()}


def build_analyst_decision_model_parse_report(
    payload: Any,
    ledger: dict[str, Any],
    *,
    retention_obligations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expected_ids = _ledger_ids(ledger)
    known_ids = set(expected_ids)
    obligations = _normalize_retention_obligations(retention_obligations) or analyst_decision_retention_obligations(ledger)
    payload = _normalize_decision_model_payload(payload)
    try:
        parsed = AnalystDecisionModel.model_validate(payload)
    except ValidationError as exc:
        return {
            "schema_id": "analyst_decision_model_parse_report_v1",
            "status": "invalid_schema",
            "valid": False,
            "errors": _jsonable_errors(exc),
            "ledger_row_count": len(expected_ids),
            "covered_evidence_item_count": 0,
            "unknown_evidence_item_ids": [],
            "missing_disposition_ids": expected_ids,
            "missing_accounting_ids": expected_ids,
            "unknown_disposition_ids": [],
            "invalid_disposition_group_ids": [],
            "obligation_omissions": {
                "ungrouped_quantitative_anchor_ids": obligations["quantitative_anchor_ids"],
                "ungrouped_counterweight_ids": obligations["counterweight_ids"],
                "ungrouped_crux_ids": obligations["crux_ids"],
                "ungrouped_scope_boundary_ids": obligations["scope_boundary_ids"],
            },
            "issues": ["invalid_schema"],
        }
    group_ids = {group.group_id for group in parsed.evidence_groups}
    covered_ids = {
        evidence_id
        for group in parsed.evidence_groups
        for evidence_id in group.covered_evidence_item_ids
    }
    disposition_ids = {row.evidence_item_id for row in parsed.evidence_dispositions}
    unknown_ids = sorted(covered_ids - known_ids)
    unknown_disposition_ids = sorted(disposition_ids - known_ids)
    accounted_ids = covered_ids | disposition_ids
    missing_disposition_ids = sorted(known_ids - disposition_ids)
    missing_accounting_ids = sorted(known_ids - accounted_ids)
    invalid_disposition_group_ids = sorted(
        {
            row.group_id
            for row in parsed.evidence_dispositions
            if row.group_id and row.group_id not in group_ids
        }
    )
    obligation_omissions = {
        "ungrouped_quantitative_anchor_ids": sorted(set(obligations["quantitative_anchor_ids"]) - covered_ids),
        "ungrouped_counterweight_ids": sorted(set(obligations["counterweight_ids"]) - covered_ids),
        "ungrouped_crux_ids": sorted(set(obligations["crux_ids"]) - covered_ids),
        "ungrouped_scope_boundary_ids": sorted(set(obligations["scope_boundary_ids"]) - covered_ids),
    }
    fatal_issues = [
        *(["unknown_evidence_item_ids"] if unknown_ids else []),
        *(["invalid_disposition_group_ids"] if invalid_disposition_group_ids else []),
    ]
    warning_issues = [
        *(["unknown_disposition_ids"] if unknown_disposition_ids else []),
        *(["missing_dispositions"] if missing_accounting_ids else []),
        *(["quantitative_anchor_not_grouped"] if obligation_omissions["ungrouped_quantitative_anchor_ids"] else []),
        *(["counterweight_not_grouped"] if obligation_omissions["ungrouped_counterweight_ids"] else []),
        *(["crux_not_grouped"] if obligation_omissions["ungrouped_crux_ids"] else []),
        *(["scope_boundary_not_grouped"] if obligation_omissions["ungrouped_scope_boundary_ids"] else []),
        *(["no_evidence_groups"] if not parsed.evidence_groups else []),
        *(["missing_bounded_bottom_line"] if not str(parsed.decision_logic.get("bounded_bottom_line") or "").strip() else []),
        *(["missing_practical_implications"] if not parsed.decision_logic.get("practical_implications") else []),
    ]
    issues = [*fatal_issues, *warning_issues]
    valid = not fatal_issues and bool(parsed.evidence_groups)
    return {
        "schema_id": "analyst_decision_model_parse_report_v1",
        "status": "ready" if not issues else "warning" if valid else "invalid",
        "valid": valid,
        "ledger_row_count": len(expected_ids),
        "group_count": len(parsed.evidence_groups),
        "covered_evidence_item_count": len(covered_ids & known_ids),
        "unknown_evidence_item_ids": unknown_ids,
        "missing_disposition_ids": missing_disposition_ids,
        "missing_accounting_ids": missing_accounting_ids,
        "unknown_disposition_ids": unknown_disposition_ids,
        "invalid_disposition_group_ids": invalid_disposition_group_ids,
        "retention_obligations": obligations,
        "obligation_omissions": obligation_omissions,
        "issues": issues,
    }


def _ledger_ids(ledger: dict[str, Any]) -> list[str]:
    return [
        str(row.get("evidence_item_id"))
        for row in ledger.get("rows", [])
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    ]


def _has_quantity(row: dict[str, Any]) -> bool:
    values = row.get("quantity_values")
    if isinstance(values, list):
        return any(_looks_quantitative(str(value)) for value in values)
    return _looks_quantitative(str(values or ""))


def _looks_quantitative(text: str) -> bool:
    normalized = text.strip().lower()
    if not normalized:
        return False
    if re.search(r"\d|%|<|>|=", normalized):
        return True
    return bool(
        re.search(
            r"\b(one|two|three|four|five|six|seven|eight|nine|ten|half|per|daily|weekly|monthly|annual|ratio|risk|hazard|confidence interval|ci|hr|rr|mg/dl)\b",
            normalized,
        )
    )


def _dedupe_ids(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    return out


def _normalize_retention_obligations(value: dict[str, Any] | None) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    aliases = {
        "quantitative_anchor_ids": ("quantitative_anchor_ids", "quantitative_anchors"),
        "counterweight_ids": ("counterweight_ids", "counterweights"),
        "crux_ids": ("crux_ids", "cruxes"),
        "scope_boundary_ids": ("scope_boundary_ids", "scope_boundaries"),
    }
    normalized: dict[str, list[str]] = {}
    for target, keys in aliases.items():
        values: list[str] = []
        for key in keys:
            raw = value.get(key)
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, dict):
                        values.append(str(item.get("evidence_item_id") or ""))
                    else:
                        values.append(str(item or ""))
        normalized[target] = _dedupe_ids(values)
    return normalized


def _normalize_adjudication_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    normalized = deepcopy(payload)
    rows = normalized.get("rows")
    if not isinstance(rows, list):
        return normalized
    for row in rows:
        if not isinstance(row, dict):
            continue
        for key in ("covered_by", "source_ids", "quantity_values"):
            value = row.get(key)
            if value is None:
                row[key] = []
        if isinstance(row.get("memo_use"), str):
            row["memo_use"] = _memo_use_alias(row["memo_use"])
        if isinstance(row.get("answer_relation"), str):
            row["answer_relation"] = _answer_relation_alias(row["answer_relation"])
        if row.get("downgrade_reason") is None:
            row["downgrade_reason"] = ""
    return normalized


def _normalize_decision_model_payload(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    normalized = deepcopy(payload)
    groups = normalized.get("evidence_groups")
    if isinstance(groups, list):
        for group in groups:
            if not isinstance(group, dict):
                continue
            _normalize_decision_group_aliases(group)
    group_ids = {
        str(group.get("group_id") or "").strip()
        for group in (groups if isinstance(groups, list) else [])
        if isinstance(group, dict)
    }
    dispositions = normalized.get("evidence_dispositions")
    if isinstance(dispositions, list):
        for row in dispositions:
            if not isinstance(row, dict):
                continue
            _normalize_decision_disposition_aliases(row, group_ids)
    relevance = normalized.get("memo_relevance_decisions")
    if isinstance(relevance, list):
        for row in relevance:
            if isinstance(row, dict) and isinstance(row.get("memo_inclusion"), str):
                row["memo_inclusion"] = _memo_inclusion_alias(row["memo_inclusion"])
    quantities = normalized.get("quantity_relevance_decisions")
    if isinstance(quantities, list):
        for row in quantities:
            if isinstance(row, dict) and isinstance(row.get("memo_inclusion"), str):
                row["memo_inclusion"] = _quantity_inclusion_alias(row["memo_inclusion"])
    return normalized


def _normalize_decision_group_aliases(group: dict[str, Any]) -> None:
    if not group.get("memo_role"):
        for alias in ("memo_relevance", "role", "evidence_role"):
            if group.get(alias):
                group["memo_role"] = group.get(alias)
                break
    for alias in ("memo_relevance", "role", "evidence_role"):
        if alias in group:
            group.pop(alias, None)


def _normalize_decision_disposition_aliases(row: dict[str, Any], group_ids: set[str]) -> None:
    group_id = str(row.get("group_id") or "").strip()
    if not group_id:
        return
    normalized = _memo_use_alias(group_id)
    if group_id not in group_ids and normalized in set(_allowed_decision_memo_uses()):
        row["group_id"] = ""


def _allowed_decision_memo_uses() -> tuple[str, ...]:
    return (
        "load_bearing_primary_support",
        "load_bearing_counterweight",
        "quantitative_anchor",
        "scope_or_applicability",
        "decision_crux",
        "mechanism_or_context",
        "background_only",
        "covered_by_group",
        "not_decision_relevant",
        "needs_human_or_model_review",
    )


def _memo_use_alias(value: str) -> str:
    normalized = value.strip().strip("'\"").lower().replace("-", "_").replace(" ", "_")
    return {
        "covered_by": "covered_by_group",
        "covered": "covered_by_group",
        "primary_support": "load_bearing_primary_support",
        "support": "load_bearing_primary_support",
        "memo_spine": "load_bearing_primary_support",
        "counterweight": "load_bearing_counterweight",
        "scope": "scope_or_applicability",
        "applicability": "scope_or_applicability",
        "crux": "decision_crux",
        "context": "mechanism_or_context",
        "supporting_context": "mechanism_or_context",
        "trace_only": "background_only",
        "background": "background_only",
        "exclude": "not_decision_relevant",
    }.get(normalized, normalized)


def _memo_inclusion_alias(value: str) -> str:
    normalized = value.strip().strip("'\"").lower().replace("-", "_").replace(" ", "_")
    return {
        "must_use": "memo_spine",
        "must_include": "memo_spine",
        "foreground": "memo_spine",
        "include": "memo_spine",
        "supporting": "supporting_context",
        "should_include": "supporting_context",
        "context": "supporting_context",
        "background": "trace_only",
        "appendix": "trace_only",
        "omit": "trace_only",
        "not_relevant": "exclude",
        "not_decision_relevant": "exclude",
        "irrelevant": "exclude",
    }.get(normalized, normalized)


def _quantity_inclusion_alias(value: str) -> str:
    normalized = value.strip().strip("'\"").lower().replace("-", "_").replace(" ", "_")
    return {
        "yes": "must_use",
        "must_include": "must_use",
        "memo_spine": "must_use",
        "include": "must_use",
        "should_include": "supporting_context",
        "context": "supporting_context",
        "context_only": "supporting_context",
        "background": "trace_only",
        "appendix": "trace_only",
        "omit": "trace_only",
        "no": "exclude",
        "not_relevant": "exclude",
        "not_decision_relevant": "exclude",
    }.get(normalized, normalized)


def _answer_relation_alias(value: str) -> str:
    normalized = value.strip().strip("'\"").lower().replace("-", "_").replace(" ", "_")
    return {
        "": "uncertain_relation",
        "support": "supports_answer",
        "supports": "supports_answer",
        "supports_default": "supports_answer",
        "supports_bottom_line": "supports_answer",
        "for_answer": "supports_answer",
        "counterweight": "challenges_answer",
        "counter_weight": "challenges_answer",
        "challenge": "challenges_answer",
        "challenges": "challenges_answer",
        "challenges_default": "challenges_answer",
        "against_answer": "challenges_answer",
        "opposes_answer": "challenges_answer",
        "limit": "bounds_scope",
        "limits": "bounds_scope",
        "limits_answer": "bounds_scope",
        "bounds_answer": "bounds_scope",
        "scope": "bounds_scope",
        "scope_boundary": "bounds_scope",
        "applicability": "bounds_scope",
        "crux": "identifies_crux",
        "decision_crux": "identifies_crux",
        "mechanism": "contextualizes_answer",
        "context": "contextualizes_answer",
        "background": "contextualizes_answer",
        "not_relevant": "not_decision_relevant",
        "irrelevant": "not_decision_relevant",
        "uncertain": "uncertain_relation",
    }.get(normalized, normalized)


def _jsonable_errors(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {
            "type": str(error.get("type") or ""),
            "loc": [str(part) for part in error.get("loc", [])],
            "msg": str(error.get("msg") or ""),
            "input": repr(error.get("input"))[:240],
        }
        for error in exc.errors()
    ]
