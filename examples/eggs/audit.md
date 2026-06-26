# Eggs and Health Audit

Case ID: `eggs`
Evidence mode: `source_grounded`
Review status: `draft`

## Status

This artifact is source-grounded according to the case manifest.

## Completeness Signals

- Sources: 11
- Claims: 872
- Relations: 25
- Relations with rationales: 25
- Open questions: 3
- Seed sources: 0

## FLF Criteria Score

| Area | Score | Evidence |
| --- | ---: | --- |
| Ingestion | 2 | Claims preserve source IDs and source-grounded sources include local paths/excerpts. |
| Structure | 2 | Relations are candidate links and rationales are explicit. |
| Assessment | 2 | Open questions surface cruxes and missing sources. |
| Compounding | 2 | JSON schema, stable IDs, and Markdown outputs support reuse. |
| Judge usability | 1 | Report is navigable, but claims and relations remain draft until audited. |
| Verification | 1 | Build command generated artifacts; full validator should be run separately. |
| Plan discipline | 1 | Goal-plan discipline is documented in docs/plans/lhc_demo_goal_plan.md. |

## Missing Evidence

- No seed-mode evidence gap was detected, but source coverage still needs human audit.

## Open Questions

- `oq_0001` (crux; claim_0001, claim_0002, claim_0005, claim_0006, claim_0007): Which findings depend on substitution context: what foods eggs replace or accompany?
- `oq_0002` (crux; claim_0001, claim_0002, claim_0003, claim_0004, claim_0005): How should observational cardiovascular findings be weighted against randomized lipid-marker findings?
- `oq_0003` (population heterogeneity; claim_0031, claim_0048, claim_0051, claim_0054, claim_0076): Which populations need separate guidance, especially people with diabetes, high LDL cholesterol, or different baseline dietary patterns?
