from __future__ import annotations

from dataclasses import dataclass


CLAIM_EXTRACTION_METHOD = "whole_doc_source_card"
RELATION_PROMPT_VERSION = "staged_relation_prompt_v4_contextual_relation_json"
RELATION_BATCH_PROMPT_VERSION = "staged_relation_batch_prompt_v4_contextual_relation_json"
CONSOLIDATION_SIMILARITY_THRESHOLD = 0.72
CONSOLIDATION_OVERLAP_THRESHOLD = 0.82


@dataclass(frozen=True)
class SourceSpan:
    span_id: str
    source_id: str
    source_span: str
    text: str


@dataclass(frozen=True)
class SourceChunk:
    chunk_id: str
    source_id: str
    title: str
    start_line: int
    end_line: int
    ordinal: int
    numbered_text: str
    plain_text: str
    spans: tuple[SourceSpan, ...]
