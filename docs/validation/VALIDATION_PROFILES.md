# Validation Profiles

Status: `implemented`

Validation is package-configured through each worked region's `thresholds`.

Supported thresholds:

- `min_claims`
- `max_claims`
- `min_relation_types`
- `min_crux_mentions`
- `min_evidence_rows`
- `min_losses`
- `min_surviving_checks`
- `min_baseline_words`
- `require_best_sections`

This lets small transfer fixtures and larger curated regions use the same validator without Python edits.

`require_best_sections: false` lets non-FLF packages omit the configured
best-region sections (consolidated into each case README in this submission).

Validators support both `markdown_kv_v1` and `json_case_map_v1` worked-region artifacts.

Worked-region validation also checks relation labels against `relation_ontology`. Default labels are accepted automatically; custom labels must be defined in `relation_ontology.custom_definitions`.

Unseen-case quality validation is separate from package syntax validation. `ecm quality check --case <case_slug>` verifies that the quality-review packet exists, has no placeholder text, includes the required protocol and comparison sections, records 1-5 scores for the ten quality dimensions, and records acceptance statuses for the unseen-case criteria. `ecm quality gate --case <case_slug>` combines that review check with package preparation and package/export/UI/checklist validation.

When `ecm quality gate` succeeds, it also writes `docs/unseen_case_tests/<case_slug>/GENERATED_RISK_TASKS.md` from source provenance metadata and risk/fail quality rows.
