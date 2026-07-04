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
DecisionCruxType = Literal[
    "biomarker_vs_hard_outcome",
    "subgroup_exception",
    "dose_boundary",
    "comparator_dependency",
    "causal_attribution",
    "scope_boundary",
]


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


class ArgumentEvidenceItem(BaseModel):
    statement: str = Field(min_length=3)
    why_it_matters: str = ""
    evidence_type: str = "unspecified"
    endpoint_type: str = "unspecified"
    weight: Confidence = "medium"
    source_ids: list[str] = Field(default_factory=list, max_length=10)
    claim_ids: list[str] = Field(default_factory=list, max_length=10)
    relation_ids: list[str] = Field(default_factory=list, max_length=10)
    quantity_ids: list[str] = Field(default_factory=list, max_length=10)
    quantities: list[str] = Field(default_factory=list, max_length=10)
    limitations: list[str] = Field(default_factory=list, max_length=5)


class ArgumentModelOutput(BaseModel):
    schema_id: Literal["argument_model_v1"] = "argument_model_v1"
    decision_question: str = Field(min_length=8)
    proposed_answer: str = Field(min_length=8)
    confidence: Confidence = "medium"
    confidence_reasons: list[str] = Field(default_factory=list, max_length=5)
    strongest_support: list[ArgumentEvidenceItem] = Field(default_factory=list, max_length=5)
    strongest_counterarguments: list[ArgumentEvidenceItem] = Field(default_factory=list, max_length=5)
    evidence_weights: list[ArgumentEvidenceItem] = Field(default_factory=list, max_length=8)
    quantitative_anchors: list[ArgumentEvidenceItem] = Field(default_factory=list, max_length=8)
    scope_boundaries: list[ArgumentEvidenceItem] = Field(default_factory=list, max_length=8)
    cruxes: list[ArgumentEvidenceItem] = Field(default_factory=list, max_length=8)
    missing_evidence: list[ArgumentEvidenceItem] = Field(default_factory=list, max_length=6)
    known_failure_modes: list[ArgumentEvidenceItem] = Field(default_factory=list, max_length=6)
    audit: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_anchor_for_load_bearing_items(self) -> "ArgumentModelOutput":
        load_bearing = [
            *self.strongest_support,
            *self.strongest_counterarguments,
            *self.quantitative_anchors,
            *self.scope_boundaries,
            *self.cruxes,
        ]
        unanchored = [
            item.statement
            for item in load_bearing
            if not (item.source_ids or item.claim_ids or item.relation_ids or item.quantity_ids)
        ]
        if unanchored:
            raise ValueError("load-bearing argument items missing anchors: " + "; ".join(unanchored[:3]))
        return self


class DecisionCrux(BaseModel):
    crux: str = Field(min_length=12)
    uncertainty: str = Field(min_length=12)
    current_read: str = Field(min_length=12)
    decision_effect: str = Field(min_length=12)
    would_change_if: str = Field(min_length=12)
    supporting_claim_ids: list[str] = Field(default_factory=list, max_length=8)
    challenging_claim_ids: list[str] = Field(default_factory=list, max_length=8)
    relation_ids: list[str] = Field(default_factory=list, max_length=8)
    crux_type: DecisionCruxType

    @model_validator(mode="after")
    def require_decision_changing_and_disjoint_ids(self) -> "DecisionCrux":
        would = self.would_change_if.lower()
        if "would change if" not in would and "recommendation would change if" not in would:
            raise ValueError("crux missing explicit decision-changing condition")
        overlap = set(self.supporting_claim_ids) & set(self.challenging_claim_ids)
        if overlap:
            raise ValueError("supporting_claim_ids and challenging_claim_ids overlap")
        return self


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
