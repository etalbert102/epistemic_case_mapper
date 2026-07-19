"""Compatibility facade for the documents-stage case initializer."""

from epistemic_case_mapper.pipeline.documents.case_initializer import (
    STARTER_PROMPT_PROCEDURE,
    InitializedCase,
    init_case_package,
)

__all__ = ["STARTER_PROMPT_PROCEDURE", "InitializedCase", "init_case_package"]
