# FLF Judge Index

Purpose: tell a contest judge where to look first once the worked-region plan is executed.

Current status: source-grounded scaffold exists for LHC and eggs; curated worked regions are planned but not yet complete.

## Fast Inspection Path

1. Start with `docs/FLF_JUDGE_WALKTHROUGH.md` once created.
2. Inspect the worked-region maps:
   - `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`
   - `examples/eggs/worked_region_observational_vs_rct_map.md`
3. Compare the flat baselines:
   - `examples/lhc_black_holes/flat_synthesis_baseline.md`
   - `examples/eggs/flat_synthesis_baseline.md`
4. Inspect erosion audits:
   - `examples/lhc_black_holes/decision_space_erosion_audit.md`
   - `examples/eggs/decision_space_erosion_audit.md`
5. Inspect best-region pointers:
   - `examples/lhc_black_holes/BEST_REGIONS.md`
   - `examples/eggs/BEST_REGIONS.md`

## What The Judge Should See

The prototype should make these features easy to verify:

- source provenance,
- source-local claim support,
- similar-but-not-identical claims,
- support/challenge/dependency/tension/crux relations,
- missing evidence,
- correlated evidence warnings,
- decision contexts,
- ways another investigator can extend the artifact.

## Current Metadata Supports

LHC:

- `data/cases/lhc_black_holes/metadata/source_method_metadata.md`
- `data/cases/lhc_black_holes/metadata/source_independence.md`
- `data/cases/lhc_black_holes/metadata/argument_evolution_timeline.md`
- `data/cases/lhc_black_holes/metadata/stakeholder_contexts.md`

Eggs:

- `data/cases/eggs/metadata/source_method_metadata.md`
- `data/cases/eggs/metadata/source_independence.md`
- `data/cases/eggs/metadata/guideline_evolution_timeline.md`
- `data/cases/eggs/metadata/stakeholder_contexts.md`

Human review:

- `docs/review/HUMAN_REVIEW_RUBRIC.md`
