# FLF Contest Criteria Self-Assessment

Status: `human-review-needed`

Purpose: map the current prototype directly to the FLF contest criteria so a judge can inspect the evidence quickly and see where the submission should not overclaim.

## Summary

This submission is strongest as a methodology plus reference prototype for preserving and auditing decision-relevant structure during AI-assisted investigation. It is not a finished epistemic stack. The core claim is that flat synthesis can be broadly useful while still eroding the decision space a later reviewer needs: source boundaries, caveats, dependencies, cruxes, similar-but-not-identical claims, and critique/response structure.

## Criteria Mapping

| FLF criterion | Current evidence | Self-score | Residual risk |
| --- | --- | ---: | --- |
| Helps someone reason better about a case | `docs/FLF_BEFORE_AFTER_COMPARISON.md`, worked maps, erosion audits, and review packets surface candidate distinctions a reviewer can inspect rather than trust implicitly. | 4 | Human reviewers still need to score relation correctness and claim fidelity. |
| Generalizes across cases | Demonstrated on LHC black-hole risk and eggs/health, which differ by domain, evidentiary closure, controversy profile, and decision context. | 3 | COVID-scale adversarial disputes are not yet implemented. |
| Scales with better AI or more compute | Stable schema, source IDs, claim IDs, relation IDs, Markdown/JSON exports, validators, and task queues make additional extraction/model passes composable. | 4 | Extraction and relation labeling are still curated rather than fully automated. |
| Compounds across people or teams | Review packets, CSV checklists, stable IDs, source inventories, and task queues let another investigator accept, reject, or extend local pieces. | 4 | Multi-reviewer merge and conflict-resolution workflow is only specified, not implemented. |
| Stands up to adversarial pressure | Erosion audits include adversarial checks, blinded local-model baselines, failure examples, and explicit limitations. | 3 | No completed external audit yet. |
| Produces reusable knowledge artifacts | Full-case scaffolds, worked-region maps, JSON exports, source metadata, and UI dashboard are all checked into the repo. | 4 | The static UI is inspection-only and cannot yet persist reviewer decisions. |

Scale: 1 means mostly absent, 3 means demonstrated but incomplete, 5 means strong contest-grade evidence.

## Best Evidence To Inspect

1. `docs/FLF_BEFORE_AFTER_COMPARISON.md`
2. `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`
3. `examples/eggs/worked_region_observational_vs_rct_map.md`
4. `docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md`
5. `docs/FAILURE_MODES_AND_COUNTEREXAMPLES.md`
6. `docs/FLF_WORKED_JUDGE_EXAMPLE.md`
7. `docs/FLF_AUDITOR_WALKTHROUGH_EXAMPLE.md`
8. `docs/NEW_SOURCE_UPDATE_DEMO.md`
9. `examples/lhc_black_holes/full_case_flat_synthesis_baseline.md`
10. `examples/eggs/full_case_flat_synthesis_baseline.md`
11. `docs/review/LHC_HUMAN_AUDIT_PACKET.md`
12. `docs/review/EGGS_HUMAN_AUDIT_PACKET.md`
13. `ui/index.html`

## What Would Upgrade The Scores

- Complete one human review pass over priority claims and relations in both worked regions.
- Promote the draft public-risk framing region into the validated worked-region set.
- Add a true external-source update after submission freeze, showing how a new source changes claims, relations, and reviewer tasks.
- Add a compact interactive graph or review UI only if reviewer-decision persistence can preserve provenance.
