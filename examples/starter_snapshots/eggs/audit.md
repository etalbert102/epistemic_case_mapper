# Eggs and Health Audit

Case ID: `eggs`
Evidence mode: `source_grounded`
Review status: `draft`

## Status

This artifact is source-grounded according to the case manifest.

## Completeness Signals

- Sources: 12
- Claims: 1022
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

## Missing Evidence

- No seed-mode evidence gap was detected, but source coverage still needs human audit.

## Preservation Metadata

These files are incorporated into the generated case map as decision-context metadata:
- `data/cases/eggs/metadata/source_method_metadata.md` (present): Eggs Source Method Metadata
- `data/cases/eggs/metadata/source_independence.md` (present): Eggs Source Independence Notes
- `data/cases/eggs/metadata/guideline_evolution_timeline.md` (present): Eggs Guideline And Evidence Evolution Timeline
- `data/cases/eggs/metadata/stakeholder_contexts.md` (present): Eggs Stakeholder Contexts

### Key Preservation Requirements

- Do not merge clinical-outcome evidence with lipid-biomarker evidence without labeling the evidential step.
- Do not treat meta-analyses as independent if they reuse overlapping cohort studies.
- Preserve population heterogeneity: diabetes, high LDL-C, baseline cardiovascular risk, and dietary pattern.
- Preserve substitution context: eggs replacing processed meat differs from eggs replacing legumes, fish, or whole-food plant proteins.
- Preserve guideline level vs evidence level: guideline communication is not the same as causal evidence.

## Workflow Telemetry

- Extraction candidate sentences: 11614
- Extraction claims created: 1022
- Extraction skipped as too short: 7982
- Extraction skipped without claim marker: 2610
- Relation mapping stage: shared_tag_seed_relations
- Open question mapping stage: case_specific_seed_open_questions

## Open Questions

- `oq_0001` (crux; claim_0001, claim_0002, claim_0005, claim_0006, claim_0007): Which findings depend on substitution context: what foods eggs replace or accompany?
- `oq_0002` (crux; claim_0001, claim_0002, claim_0003, claim_0004, claim_0005): How should observational cardiovascular findings be weighted against randomized lipid-marker findings?
- `oq_0003` (population heterogeneity; claim_0041, claim_0047, claim_0048, claim_0060, claim_0086): Which populations need separate guidance, especially people with diabetes, high LDL cholesterol, or different baseline dietary patterns?
