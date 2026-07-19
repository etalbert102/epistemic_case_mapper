"""Compatibility facade for documents-stage evidence bundles."""

from epistemic_case_mapper.pipeline.documents.evidence_bundles import (
    ASSERTION_BUNDLE_SCHEMA_ID,
    assertion_bundle_from_quantity,
    bundle_quantities_for_prompt,
    bundle_reconciliation_report,
    collect_assertion_bundles,
    normalize_assertion_bundles,
    semantic_realization_report,
)

__all__ = [
    "ASSERTION_BUNDLE_SCHEMA_ID",
    "assertion_bundle_from_quantity",
    "bundle_quantities_for_prompt",
    "bundle_reconciliation_report",
    "collect_assertion_bundles",
    "normalize_assertion_bundles",
    "semantic_realization_report",
]
