from __future__ import annotations

import json
from typing import Any, Literal, TypeVar

from pydantic import BaseModel, Field, ValidationError, model_validator

from epistemic_case_mapper.model_outputs import canonical_json_output

T = TypeVar("T", bound=BaseModel)

RelationType = Literal[
    "supports",
    "challenges",
    "refines",
    "similar_to",
    "depends_on",
    "crux_for",
    "in_tension_with",
    "none",
]
Confidence = Literal["low", "medium", "high"]


class RelationContractOutput(BaseModel):
    relation_type: RelationType
    source_claim: str | None = None
    target_claim: str | None = None
    rationale: str | None = None
    source_claim_support_excerpt: str | None = None
    target_claim_support_excerpt: str | None = None
    confidence: Confidence = "medium"

    @model_validator(mode="after")
    def require_contract_for_positive_relation(self) -> "RelationContractOutput":
        if self.relation_type == "none":
            return self
        missing = [
            field
            for field in (
                "source_claim",
                "target_claim",
                "rationale",
                "source_claim_support_excerpt",
                "target_claim_support_excerpt",
            )
            if not str(getattr(self, field) or "").strip()
        ]
        if missing:
            raise ValueError("positive relation missing contract fields: " + ", ".join(missing))
        return self


class RelationClassificationOutput(RelationContractOutput):
    pair_id: str | None = None


class RelationCriticOutput(BaseModel):
    accepted: bool
    confidence: Confidence = "medium"
    issues: list[str] = Field(default_factory=list, max_length=8)
    repair_instructions: list[str] = Field(default_factory=list, max_length=8)


class DecisionModelItem(BaseModel):
    statement: str
    why_it_matters: str = ""
    source_ids: list[str] = Field(default_factory=list, max_length=8)
    claim_ids: list[str] = Field(default_factory=list, max_length=8)
    relation_ids: list[str] = Field(default_factory=list, max_length=8)
    confidence: Confidence = "medium"


class DecisionAnswerFrame(BaseModel):
    question: str
    current_read: str
    confidence: Confidence
    why_this_frame: str = ""


class CompactDecisionModelOutput(BaseModel):
    schema_id: Literal["compact_decision_model_v1"] = "compact_decision_model_v1"
    answer_frame: DecisionAnswerFrame
    top_support: list[DecisionModelItem] = Field(default_factory=list, max_length=3)
    top_counterevidence_or_tensions: list[DecisionModelItem] = Field(default_factory=list, max_length=3)
    top_scope_boundaries: list[DecisionModelItem] = Field(default_factory=list, max_length=3)
    top_cruxes: list[DecisionModelItem] = Field(default_factory=list, max_length=3)
    confidence_drivers: list[DecisionModelItem] = Field(default_factory=list, max_length=3)
    missing_evidence: list[DecisionModelItem] = Field(default_factory=list, max_length=3)
    decision_implications: list[DecisionModelItem] = Field(default_factory=list, max_length=3)
    audit: dict[str, Any] = Field(default_factory=dict)


def parse_model_output(raw: str, schema: type[T]) -> T:
    canonical = canonical_json_output(raw)
    return schema.model_validate_json(canonical)


def validation_error_summary(error: ValidationError) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in error.errors():
        rows.append(
            {
                "path": ".".join(str(part) for part in item.get("loc", ())),
                "message": str(item.get("msg", "")),
                "type": str(item.get("type", "")),
            }
        )
    return rows


def parse_model_output_report(raw: str, schema: type[T]) -> dict[str, Any]:
    try:
        parsed = parse_model_output(raw, schema)
    except (json.JSONDecodeError, ValidationError) as error:
        if isinstance(error, ValidationError):
            errors = validation_error_summary(error)
        else:
            errors = [{"path": "", "message": str(error), "type": "json_decode"}]
        return {"ok": False, "errors": errors, "data": None}
    return {"ok": True, "errors": [], "data": parsed.model_dump()}
