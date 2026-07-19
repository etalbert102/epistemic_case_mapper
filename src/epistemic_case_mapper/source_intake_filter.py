"""Compatibility facade for the documents-stage source intake filter."""

from epistemic_case_mapper.pipeline.documents.source_intake_filter import (
    ARXIV_RE,
    AUTHOR_YEAR_RE,
    BRACKET_CITATION_RE,
    DATE_RE,
    DOI_RE,
    PMID_RE,
    REFERENCE_HEADING_RE,
    SOURCE_INTAKE_FILTER_SCHEMA,
    URL_RE,
    ModelSourceJudgment,
    ModelSourceJudgmentOutput,
    SourceIntakeFilterResult,
    render_source_intake_filter_markdown,
    run_source_intake_filter,
)

__all__ = [
    "ARXIV_RE",
    "AUTHOR_YEAR_RE",
    "BRACKET_CITATION_RE",
    "DATE_RE",
    "DOI_RE",
    "PMID_RE",
    "REFERENCE_HEADING_RE",
    "SOURCE_INTAKE_FILTER_SCHEMA",
    "URL_RE",
    "ModelSourceJudgment",
    "ModelSourceJudgmentOutput",
    "SourceIntakeFilterResult",
    "render_source_intake_filter_markdown",
    "run_source_intake_filter",
]
