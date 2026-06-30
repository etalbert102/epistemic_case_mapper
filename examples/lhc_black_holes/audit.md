# LHC Black Hole Risk Audit

Case ID: `lhc_black_holes`
Evidence mode: `source_grounded`
Review status: `draft`

## Status

This artifact is source-grounded according to the case manifest.

## Completeness Signals

- Sources: 10
- Claims: 632
- Relations: 25
- Relations with rationales: 25
- Open questions: 3
- Seed sources: 0
- Preservation metadata files: 4
- Key preservation requirements: 5
- Workflow telemetry stages: 3

## Artifact Evidence Check

| Area | Evidence | Boundary |
| --- | --- | --- |
| Ingestion | Claims preserve source IDs, normalized spans, text hashes, and source-grounded local paths/excerpts. | Completeness signals are not a substitute for source review. |
| Structure | Relations are candidate links and rationales are explicit. | Relation labels remain draft. |
| Assessment | Open questions surface cruxes and missing sources. | Crux usefulness needs human review. |
| Compounding | JSON schema, stable IDs, and Markdown outputs support reuse. | Multi-reviewer workflow is not exercised here. |
| Navigation | Report is navigable, but claims and relations remain draft until audited. | Large starter reports are less useful than curated worked regions. |
| Verification | Build command generated artifacts; full validator should be run separately. | Generated starter output is not final evidence. |
| Plan discipline | Internal goal-plan history is archived under docs/archive/internal/plans/. | Archives are implementation history, not first-read material. |

## Missing Evidence

- No seed-mode evidence gap was detected, but source coverage still needs human audit.

## Preservation Metadata

These files are incorporated into the generated case map as decision-context metadata:
- `data/cases/lhc_black_holes/metadata/source_method_metadata.md` (present): LHC Source Method Metadata
- `data/cases/lhc_black_holes/metadata/source_independence.md` (present): LHC Source Independence Notes
- `data/cases/lhc_black_holes/metadata/argument_evolution_timeline.md` (present): LHC Argument Evolution Timeline
- `data/cases/lhc_black_holes/metadata/stakeholder_contexts.md` (present): LHC Stakeholder Contexts

### Key Preservation Requirements

- Separate technical safety evidence from institutional endorsement.
- Separate public reassurance from technical argument.
- Preserve critique and response rather than treating "settled" as "never contested."
- Do not treat CMS non-observation as direct proof of no catastrophic risk; it is an empirical update in model space.
- Preserve the legal/public-risk question separately from the physics question.

## Workflow Telemetry

- Extraction candidate sentences: 13911
- Extraction claims created: 632
- Extraction skipped as too short: 9221
- Extraction skipped without claim marker: 4058
- Relation mapping stage: shared_tag_seed_relations
- Open question mapping stage: case_specific_seed_open_questions

## Open Questions

- `oq_0001` (crux; claim_0003, claim_0011, claim_0035, claim_0068, claim_0077): Which assumptions make the natural cosmic-ray analogue valid or invalid for LHC conditions?
- `oq_0002` (missing source needed; claim_0014, claim_0015, claim_0059, claim_0066, claim_0069): Which source-grounded evidence directly supports the claim that hypothetical microscopic black holes would evaporate quickly?
- `oq_0003` (missing source needed; claim_0009, claim_0053, claim_0054, claim_0064, claim_0165): Which independent reviews, critiques, or public-risk arguments should be added before treating this as source-grounded?
