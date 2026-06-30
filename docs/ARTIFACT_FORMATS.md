# Artifact Formats

Status: `implemented-core`

The current engine supports markdown key-value artifacts.

Worked maps use blocks beginning with:

- `claim_id:`
- `relation_id:`

Erosion audits use blocks beginning with:

- `loss_id:`

The parser preserves free-form values, so package-specific ID grammars such as `claim:demo:001` are supported.

The next adapter target is JSON case-map input. That requires adding format fields to worked-region config and dispatching parser calls through an artifact adapter registry.
