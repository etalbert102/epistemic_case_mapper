# Goal Prompt For FLF Worked-Region Prototype

Use this prompt from the repository root when launching a long Codex goal run.

```text
/goal Execute docs/plans/flf_winning_submission_worked_regions_plan.md. Keep the plan updated as the living source of truth. Use docs/worked_regions/lhc_source_excerpt_packet.md and docs/worked_regions/eggs_source_excerpt_packet.md as the starting evidence packets. Use docs/worked_regions/mini_filled_example.md as a format example only. Stop only when the LHC and eggs worked regions each have source-grounded maps, before/after flat-synthesis comparisons, audit notes, curated judge pointers, validation passing, and explicit residual risks.
```

## Recommended Phases

Run the goal in phases if a single run starts to sprawl.

### Phase 1: LHC Only

```text
/goal Complete only the LHC worked region from docs/plans/flf_winning_submission_worked_regions_plan.md. Use docs/worked_regions/lhc_source_excerpt_packet.md. Do not touch the eggs worked region except to avoid breaking existing files. Finish when PYTHONPATH=src python3 scripts/validate_worked_regions.py --region lhc_cosmic_ray_argument passes or the blocker is recorded in the plan.
```

Validation:

```bash
PYTHONPATH=src python3 scripts/validate_worked_regions.py --region lhc_cosmic_ray_argument
PYTHONPATH=src python3 -m pytest -q
```

### Phase 2: Eggs Only

```text
/goal Complete only the eggs worked region from docs/plans/flf_winning_submission_worked_regions_plan.md. Use docs/worked_regions/eggs_source_excerpt_packet.md. Do not rewrite the LHC worked region unless validation exposes a concrete inconsistency. Finish when PYTHONPATH=src python3 scripts/validate_worked_regions.py --region eggs_observational_vs_rct passes or the blocker is recorded in the plan.
```

Validation:

```bash
PYTHONPATH=src python3 scripts/validate_worked_regions.py --region eggs_observational_vs_rct
PYTHONPATH=src python3 -m pytest -q
```

### Phase 3: Judge Packet

```text
/goal Complete the judge-facing packet for the FLF worked-region prototype. Do not add new sources or cases. Use the completed worked-region maps, baselines, audits, and BEST_REGIONS files to finalize docs/FLF_JUDGE_WALKTHROUGH.md and docs/FLF_SUBMISSION_DRAFT.md. Finish when PYTHONPATH=src python3 scripts/validate_worked_regions.py and PYTHONPATH=src python3 scripts/reproducibility_gate.py --include-worked-regions pass.
```

Validation:

```bash
PYTHONPATH=src python3 scripts/validate_worked_regions.py
PYTHONPATH=src python3 scripts/reproducibility_gate.py --include-worked-regions
```

## Stop Conditions

Stop and record a blocker in the plan if:

- A required claim cannot be tied to a local source excerpt.
- A flat-synthesis loss depends on a source outside the fixed subset.
- The baseline cannot be treated as isolated from the curated map.
- Validation can only be made to pass by weakening provenance or review-status claims.
- The output starts expanding into UI, COVID, regulatory tasks, or new source acquisition.
