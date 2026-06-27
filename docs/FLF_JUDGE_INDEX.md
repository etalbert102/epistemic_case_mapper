# FLF Judge Index

Purpose: tell a contest judge where to look first once the worked-region plan is executed.

Current status: source-grounded scaffold, curated worked regions, illustrative flat baselines, multi-model blinded local baselines, erosion audits, human audit packets, and judge walkthroughs exist for LHC and eggs. All remain `human-review-needed`.

## One-Command Demo

```bash
PYTHONPATH=src python3 scripts/run_flf_demo.py
```

For a faster validation-only pass over checked-in artifacts:

```bash
PYTHONPATH=src python3 scripts/run_flf_demo.py --skip-build
```

## Fast Inspection Path

1. Start with `docs/SUBMISSION_PACKET.md`.
2. Read `docs/FLF_JUDGE_WALKTHROUGH.md`.
3. Read the before/after comparison:
   - `docs/FLF_BEFORE_AFTER_COMPARISON.md`
4. Inspect the worked-region maps:
   - `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`
   - `examples/eggs/worked_region_observational_vs_rct_map.md`
5. Compare the flat baselines:
   - `examples/lhc_black_holes/flat_synthesis_baseline.md`
   - `examples/eggs/flat_synthesis_baseline.md`
6. Compare the more isolated blinded local-model baselines:
   - `examples/lhc_black_holes/blinded_flat_synthesis_baseline_*.md`
   - `examples/eggs/blinded_flat_synthesis_baseline_*.md`
7. Inspect erosion audits:
   - `examples/lhc_black_holes/decision_space_erosion_audit.md`
   - `examples/eggs/decision_space_erosion_audit.md`
8. Inspect the blinded-comparator survival audits:
   - `docs/review/BLINDED_BASELINE_AUDIT.md`
   - `docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md`
9. Inspect best-region pointers:
   - `examples/lhc_black_holes/BEST_REGIONS.md`
   - `examples/eggs/BEST_REGIONS.md`
10. Use the human audit packets before trusting the examples as reviewed:
   - `docs/review/LHC_HUMAN_AUDIT_PACKET.md`
   - `docs/review/EGGS_HUMAN_AUDIT_PACKET.md`

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
- `docs/review/LHC_HUMAN_AUDIT_PACKET.md`
- `docs/review/EGGS_HUMAN_AUDIT_PACKET.md`
- `docs/review/LHC_HUMAN_AUDIT_CHECKLIST.csv`
- `docs/review/EGGS_HUMAN_AUDIT_CHECKLIST.csv`
