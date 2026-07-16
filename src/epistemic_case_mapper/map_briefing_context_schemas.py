from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

FieldOwnership = Literal["deterministic_only", "model_suggested", "hybrid", "model_prose_only"]
ValidationStatus = Literal["valid", "invalid"]


class SourceEvidenceCard(BaseModel):
    model_config = ConfigDict(extra="allow")

    source_card_id: str
    source_id: str
    source_title: str = ""
    source_url: str = ""
    source_span: str = ""
    source_quote_or_excerpt: str = ""
    span_hash: str = ""
    anchor_confidence: Literal["exact", "recovered", "missing"] = "missing"
    decision_relevance_score: int = 0
    endpoint_match: str = "unknown"
    population_match: str = "unknown"
    exposure_or_intervention: str = ""
    comparator: str = ""
    outcome_or_endpoint: str = ""
    evidence_type: str = "unspecified"
    quantity_values: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    supports_challenges_or_scopes: str = "uncategorized"
    fragment_risk: bool = False
    boilerplate_risk: bool = False

    @model_validator(mode="after")
    def require_anchor_or_missing_label(self) -> "SourceEvidenceCard":
        if self.anchor_confidence != "missing" and not (self.source_span or self.source_quote_or_excerpt or self.span_hash):
            raise ValueError("anchored source evidence card lacks span, excerpt, or hash")
        return self


class SourceEvidenceCardReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_id: Literal["source_evidence_cards_v1"] = "source_evidence_cards_v1"
    source_card_count: int = 0
    anchored_card_count: int = 0
    missing_anchor_count: int = 0
    cards: list[SourceEvidenceCard] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class SourceSufficiencyReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_id: Literal["source_sufficiency_report_v1"] = "source_sufficiency_report_v1"
    status: Literal["sufficient_for_decision_ready_answer", "sufficient_for_bounded_answer", "insufficient_source_set"]
    decision_question: str
    coverage: dict[str, bool] = Field(default_factory=dict)
    missing_source_categories: list[str] = Field(default_factory=list)
    bounded_answer_required: bool = False
    notes: list[str] = Field(default_factory=list)


class EvidenceQualityReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_id: Literal["evidence_quality_report_v1"] = "evidence_quality_report_v1"
    card_count: int = 0
    weak_or_indirect_count: int = 0
    unknown_quality_count: int = 0
    quality_components: dict[str, dict[str, Any]] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)


class SourceMapReconciliationRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    claim_id: str = ""
    claim_text: str = ""
    source_card_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    status: Literal["source_backed", "weakly_backed", "unbacked"]
    match_type: Literal["claim_id", "source_overlap", "none"] = "none"
    issues: list[str] = Field(default_factory=list)


class SourceMapReconciliationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_id: Literal["source_map_reconciliation_v1"] = "source_map_reconciliation_v1"
    claim_count: int = 0
    source_backed_count: int = 0
    weakly_backed_count: int = 0
    unbacked_count: int = 0
    rows: list[SourceMapReconciliationRow] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class CandidateEvidenceCard(BaseModel):
    model_config = ConfigDict(extra="allow")

    candidate_card_id: str
    source_card_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    source_ids: list[str] = Field(default_factory=list)
    source_titles: list[str] = Field(default_factory=list)
    claim: str
    source_excerpt: str = ""
    role: Literal["support", "counterweight", "scope", "quantity", "limitation", "context"]
    decision_relevance_score: int = 0
    quality: str = "unknown"
    inclusion_recommendation: Literal["main_text", "supporting_context", "appendix_only"] = "supporting_context"
    inclusion_reason: str = ""
    section_candidates: list[str] = Field(default_factory=list)
    quantity_values: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    anchor_confidence: Literal["exact", "recovered", "missing"] = "missing"
    off_question_risk: bool = False
    fragment_risk: bool = False


class CandidateEvidenceCardsReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_id: Literal["candidate_evidence_cards_v1"] = "candidate_evidence_cards_v1"
    card_count: int = 0
    main_text_count: int = 0
    appendix_only_count: int = 0
    cards: list[CandidateEvidenceCard] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class SourceCoverageReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_id: Literal["source_coverage_report_v1"] = "source_coverage_report_v1"
    total_source_card_count: int = 0
    candidate_card_count: int = 0
    assigned_main_card_count: int = 0
    omitted_high_relevance_card_ids: list[str] = Field(default_factory=list)
    unbacked_claim_ids: list[str] = Field(default_factory=list)
    appendix_only_card_ids: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class SectionContextAcceptanceRow(BaseModel):
    model_config = ConfigDict(extra="allow")

    section: str
    status: Literal["ready", "warning", "not_synthesis_ready"]
    owned_card_count: int = 0
    card_budget_status: Literal["within_budget", "under_budget", "over_budget", "justified_exception"] = "within_budget"
    this_section_can_answer: str = ""
    because: str = ""
    missing_context: list[str] = Field(default_factory=list)
    context_risk_level: Literal["low", "medium", "high"] = "low"
    issues: list[str] = Field(default_factory=list)


class SectionContextAcceptanceReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_id: Literal["section_context_acceptance_report_v1"] = "section_context_acceptance_report_v1"
    status: Literal["ready", "warning", "not_synthesis_ready"]
    sections: list[SectionContextAcceptanceRow] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)


class MemoCoherenceReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_id: Literal["memo_coherence_report_v1"] = "memo_coherence_report_v1"
    status: Literal["pass", "warning", "fail"]
    issue_count: int = 0
    issues: list[dict[str, Any]] = Field(default_factory=list)


class PipelineMigrationLedger(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_id: Literal["pipeline_migration_ledger_v1"] = "pipeline_migration_ledger_v1"
    old_context_fields_still_model_visible: list[str] = Field(default_factory=list)
    new_context_fields_model_visible: list[str] = Field(default_factory=list)
    debug_only_artifacts: list[str] = Field(default_factory=list)
    transition_notes: list[str] = Field(default_factory=list)
    status: Literal["clean", "warning"] = "clean"


class RuntimeBudgetReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_id: Literal["runtime_budget_report_v1"] = "runtime_budget_report_v1"
    stages: list[dict[str, Any]] = Field(default_factory=list)
    model_call_count: int = 0
    degraded_mode_triggers: list[str] = Field(default_factory=list)
    most_expensive_stage: str = ""


class FinalBriefEvaluation(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_id: Literal["final_brief_evaluation_v1"] = "final_brief_evaluation_v1"
    status: Literal["pass", "warning", "fail"]
    decision_question: str
    rubric_scores: dict[str, int] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    memo_path: str = ""


class ArtifactValidationReport(BaseModel):
    model_config = ConfigDict(extra="allow")

    schema_id: Literal["artifact_ownership_validation_v1"] = "artifact_ownership_validation_v1"
    artifact_name: str
    schema_name: str
    status: ValidationStatus
    schema_parse_ok: bool
    deterministic_only_violations: list[dict[str, str]] = Field(default_factory=list)
    validation_errors: list[dict[str, str]] = Field(default_factory=list)
    fallback_behavior: str = ""


def validate_artifact_ownership(
    artifact_name: str,
    artifact: dict[str, Any],
    *,
    schema: type[BaseModel],
    field_ownership: dict[str, FieldOwnership],
    model_generated_fields: list[str] | None = None,
    fallback_behavior: str = "quarantine_invalid_artifact",
) -> dict[str, Any]:
    """Validate artifact shape and deterministic/model field ownership.

    `model_generated_fields` is a list of dotted field paths known to have come
    from model output. If any path is marked deterministic-only, the report is
    invalid even when the JSON shape is otherwise valid.
    """
    validation_errors: list[dict[str, str]] = []
    try:
        schema.model_validate(artifact)
        schema_parse_ok = True
    except ValidationError as error:
        schema_parse_ok = False
        validation_errors = [
            {
                "path": ".".join(str(part) for part in item.get("loc", ())),
                "message": str(item.get("msg", "")),
                "type": str(item.get("type", "")),
            }
            for item in error.errors()
        ]
    model_paths = model_generated_fields or []
    violations = [
        {"path": path, "ownership": "deterministic_only"}
        for path in model_paths
        if field_ownership.get(path) == "deterministic_only"
    ]
    status: ValidationStatus = "valid" if schema_parse_ok and not violations else "invalid"
    return ArtifactValidationReport(
        artifact_name=artifact_name,
        schema_name=schema.__name__,
        status=status,
        schema_parse_ok=schema_parse_ok,
        deterministic_only_violations=violations,
        validation_errors=validation_errors,
        fallback_behavior=fallback_behavior if status == "invalid" else "",
    ).model_dump()


SOURCE_EVIDENCE_CARD_OWNERSHIP: dict[str, FieldOwnership] = {
    "source_card_id": "deterministic_only",
    "source_id": "deterministic_only",
    "source_title": "deterministic_only",
    "source_url": "deterministic_only",
    "source_span": "deterministic_only",
    "source_quote_or_excerpt": "deterministic_only",
    "span_hash": "deterministic_only",
    "anchor_confidence": "deterministic_only",
    "decision_relevance_score": "hybrid",
    "endpoint_match": "hybrid",
    "population_match": "hybrid",
    "evidence_type": "hybrid",
    "limitations": "hybrid",
    "supports_challenges_or_scopes": "hybrid",
}
