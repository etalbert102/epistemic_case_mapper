from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Source(BaseModel):
    source_id: str
    title: str
    url: str | None = None
    author: str | None = None
    publication_date: str | None = None
    retrieval_date: str | None = None
    source_type: str = "document"
    notes: str | None = None
    text: str | None = None
    path: str | None = None
    excerpt: str | None = None


class CaseManifest(BaseModel):
    case_id: str
    title: str
    question: str
    case_type: str
    evidence_mode: Literal["seed", "source_grounded"] = "seed"
    review_status: Literal["draft", "agent-reviewed", "human-review-needed", "human-reviewed"] = "draft"
    status: Literal["draft", "in_progress", "reviewed"] = "draft"
    sources: list[Source] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    metadata_files: list[str] = Field(default_factory=list)


class Claim(BaseModel):
    claim_id: str
    text: str
    source_id: str
    source_span: str | None = None
    source_start: int | None = None
    source_end: int | None = None
    source_text_hash: str | None = None
    excerpt_hash: str | None = None
    extraction_method: str = "unspecified"
    provenance_tag: str = "model_generated_proposal"
    review_state: Literal[
        "model_generated_proposal",
        "source_supported",
        "interpretation_candidate",
        "human_review_needed",
        "human_reviewed",
    ] = "model_generated_proposal"
    entailed_by_excerpt: Literal["yes", "no", "uncertain"] = "uncertain"
    claim_type: str = "unclassified"
    confidence: Literal["low", "medium", "high"] = "low"
    tags: list[str] = Field(default_factory=list)


class Relation(BaseModel):
    relation_id: str
    source_claim_id: str
    target_claim_id: str
    relation_type: Literal[
        "supports",
        "challenges",
        "refines",
        "similar_to",
        "depends_on",
        "crux_for",
        "in_tension_with",
    ]
    rationale: str | None = None


class OpenQuestion(BaseModel):
    question_id: str
    text: str
    why_it_matters: str
    linked_claim_ids: list[str] = Field(default_factory=list)
    linked_source_ids: list[str] = Field(default_factory=list)
    gap_type: str | None = None


class CaseMap(BaseModel):
    schema_id: str = "epistemic_case_map/v0"
    case_id: str
    title: str
    question: str
    evidence_mode: Literal["seed", "source_grounded"] = "seed"
    review_status: Literal["draft", "agent-reviewed", "human-review-needed", "human-reviewed"] = "draft"
    sources: list[Source]
    claims: list[Claim] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    audit_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
