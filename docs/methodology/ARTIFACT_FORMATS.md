# Artifact Formats

Status: `implemented`

The current engine supports markdown key-value artifacts and JSON case-map artifacts.

Worked maps use blocks beginning with:

- `claim_id:`
- `relation_id:`

Erosion audits use blocks beginning with:

- `loss_id:`

The parser preserves free-form values, so package-specific ID grammars such as `claim:demo:001` are supported.

JSON worked maps use the same normalized keys:

- `title`
- `status`
- `sources`
- `claims`
- `relations`
- `crux_candidates`
- `similar_but_not_identical`
- `evidence_check`

JSON audits use:

- `title`
- `status`
- `losses`
- `borderline_or_rejected`

Set `map_format: json_case_map_v1` and `audit_format: json_case_map_v1` on a worked region to use the JSON adapter.
