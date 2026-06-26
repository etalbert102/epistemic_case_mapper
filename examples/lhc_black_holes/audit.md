# LHC Black Hole Risk Audit

Case ID: `lhc_black_holes`
Evidence mode: `source_grounded`
Review status: `draft`

## Status

This artifact is source-grounded according to the case manifest.

## Completeness Signals

- Sources: 10
- Claims: 599
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

- `oq_0001` (crux; claim_0003, claim_0011, claim_0035, claim_0068, claim_0077): Which assumptions make the natural cosmic-ray analogue valid or invalid for LHC conditions?
- `oq_0002` (missing source needed; claim_0014, claim_0015, claim_0059, claim_0066, claim_0069): Which source-grounded evidence directly supports the claim that hypothetical microscopic black holes would evaporate quickly?
- `oq_0003` (missing source needed; claim_0009, claim_0053, claim_0054, claim_0064, claim_0167): Which independent reviews, critiques, or public-risk arguments should be added before treating this as source-grounded?
