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

`require_best_sections: false` lets non-FLF packages omit `BEST_REGIONS.md`.

Validators support both `markdown_kv_v1` and `json_case_map_v1` worked-region artifacts.
