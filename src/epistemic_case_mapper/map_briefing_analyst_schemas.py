from __future__ import annotations

from copy import deepcopy
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


class EvidenceAdjudicationRow(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_item_id: str
    memo_use: MemoUse
    importance_rank: int = Field(ge=1, le=100)
    rationale: str = Field(min_length=1)
    covered_by: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    quantity_values: list[str] = Field(default_factory=list)
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

    @field_validator("memo_use", mode="before")
    @classmethod
    def _normalize_memo_use(cls, value: Any) -> str:
        return _memo_use_alias(str(value or ""))

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
    importance_rank: int = Field(default=100, ge=1, le=100)
    covered_evidence_item_ids: list[str] = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    source_labels: list[str] = Field(default_factory=list)
    quantity_values: list[str] = Field(default_factory=list)
    applicability_limits: list[str] = Field(default_factory=list)
    rationale: str = Field(min_length=1)
    conflict_note: str = ""


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
    source_notes: list[dict[str, Any]] = Field(default_factory=list)
    evidence_accounting_summary: dict[str, Any] = Field(default_factory=dict)


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
    source_labels: list[str] = Field(default_factory=list)
    key_terms: list[str] = Field(default_factory=list)

    @field_validator("source_labels", "key_terms", mode="before")
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


def _ledger_ids(ledger: dict[str, Any]) -> list[str]:
    return [
        str(row.get("evidence_item_id"))
        for row in ledger.get("rows", [])
        if isinstance(row, dict) and str(row.get("evidence_item_id") or "").strip()
    ]


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
        if row.get("downgrade_reason") is None:
            row["downgrade_reason"] = ""
    return normalized


def _memo_use_alias(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    return {
        "covered_by": "covered_by_group",
        "covered": "covered_by_group",
        "primary_support": "load_bearing_primary_support",
        "support": "load_bearing_primary_support",
        "counterweight": "load_bearing_counterweight",
        "scope": "scope_or_applicability",
        "applicability": "scope_or_applicability",
        "crux": "decision_crux",
        "context": "mechanism_or_context",
        "background": "background_only",
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
