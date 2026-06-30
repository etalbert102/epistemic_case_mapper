# Validation Profiles

Status: `implemented-core`

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

This lets small transfer fixtures and larger curated regions use the same validator without Python edits.

The current validators still assume the markdown key-value artifact shape. Package-specific optional section requirements should be added as explicit profile fields before supporting substantially different audit formats.
