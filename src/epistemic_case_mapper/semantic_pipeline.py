"""Compatibility facade for map-stage semantic prompt and validation APIs."""

from epistemic_case_mapper.pipeline.map.semantic_pipeline import (
    CRITIQUE_PROMPT_VERSION,
    MAP_PROMPT_VERSION,
    VALID_CRITIQUE_CATEGORY,
    VALID_CRITIQUE_SEVERITY,
    VALID_ENTAILMENT,
    build_critique_prompt,
    build_map_prompt,
    validate_critique_candidate,
    validate_map_candidate,
)

__all__ = [
    "CRITIQUE_PROMPT_VERSION",
    "MAP_PROMPT_VERSION",
    "VALID_CRITIQUE_CATEGORY",
    "VALID_CRITIQUE_SEVERITY",
    "VALID_ENTAILMENT",
    "build_critique_prompt",
    "build_map_prompt",
    "validate_critique_candidate",
    "validate_map_candidate",
]
