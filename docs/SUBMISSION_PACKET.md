# FLF Submission Packet

Status: `human-review-needed`

Purpose: provide a single judge-facing entry point for the FLF epistemic case study competition prototype.

## One-Sentence Claim

Fluent AI synthesis can preserve surface plausibility while eroding the decision space needed for accountable review; this prototype keeps claims, provenance, relations, cruxes, caveats, and losses as inspectable artifacts so another investigator can audit and extend the work.

## What To Run

```bash
PYTHONPATH=src python3 scripts/run_flf_demo.py
```

For a faster check over the checked-in artifacts:

```bash
PYTHONPATH=src python3 scripts/run_flf_demo.py --skip-build
```

The demo validates source-grounded artifacts, worked regions, blinded baselines, structured exports, internal references, and the judge path.

## What To Inspect First

1. `docs/FLF_BEFORE_AFTER_COMPARISON.md`
2. `examples/lhc_black_holes/full_case_index.md`
3. `examples/lhc_black_holes/full_case_map.md`
4. `examples/lhc_black_holes/BEST_REGIONS.md`
5. `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`
6. `examples/lhc_black_holes/decision_space_erosion_audit.md`
7. `examples/eggs/full_case_index.md`
8. `examples/eggs/full_case_map.md`
9. `examples/eggs/BEST_REGIONS.md`
10. `examples/eggs/worked_region_observational_vs_rct_map.md`
11. `examples/eggs/decision_space_erosion_audit.md`
12. `docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md`
13. `docs/review/LHC_HUMAN_AUDIT_PACKET.md`
14. `docs/review/EGGS_HUMAN_AUDIT_PACKET.md`
15. `docs/INVESTIGATOR_WORKFLOW_PLAYBOOK.md`
16. `docs/OPERATIONAL_REALISM_AUDIT.md`

## Submission Shape

This is a methodology plus runnable reference prototype. It is not a finished interactive product.

The package now has two evidence depths:

- full-case scaffolds that cover every currently acquired source for LHC and eggs,
- worked-region anchors that provide deeper claim-level and relation-level audit surfaces for the most important slices.

The contribution is the workflow:

1. Scope a worked region.
2. Fix a source subset.
3. Extract source-grounded claims with excerpts.
4. Preserve relations, caveats, cruxes, and similar-but-not-identical claims.
5. Generate normal flat syntheses from the same source subset.
6. Audit where flat synthesis preserved, flattened, omitted, or distorted decision-relevant distinctions.
7. Hand the result to a human reviewer through a structured packet.

## FLF Criteria Mapping

| FLF criterion | Prototype evidence | Main residual risk |
| --- | --- | --- |
| Helps someone reason better | Worked maps separate source claims, caveats, dependencies, critiques, and cruxes that flat synthesis tends to merge. | Human reviewers still need to confirm relation correctness. |
| Generalizes | Demonstrated on a closed technical-risk case and a messy nutrition evidence case. | COVID-scale investigations need more automation and review workflow maturity. |
| Scales with better AI or more compute | The schema and validators can accept more sources, claims, relations, and baselines. | Automated extraction can overproduce weak claims unless review pressure remains explicit. |
| Compounds across people or teams | Stable IDs, JSON exports, source spans, and review packets let another investigator revise local pieces. | Multi-reviewer merge workflow is not implemented yet. |

## Side-By-Side Evidence

### LHC Black Holes

| Decision-relevant distinction | Flat synthesis behavior | Map preservation | Blinded-baseline status |
| --- | --- | --- | --- |
| Low-velocity LHC products may be trappable even if cosmic-ray products are not. | Mentions velocity briefly without preserving the dependency on trapping and Earth cosmic-ray limits. | `lhc_c004`, `lhc_c012`, `lhc_r003`, `lhc_r004`, `lhc_r016`. | Recurs across models; Qwen is more detailed but still compresses the dependency. |
| White-dwarf and neutron-star arguments have different scope. | Lists compact stars together. | `lhc_c009`, `lhc_c011`, `lhc_r009`, `lhc_r014`. | Partly preserved by stronger baselines but still usually flattened. |
| Plaga critique and GM response are multi-threaded. | Treats critique/response as broad disagreement. | `lhc_c013`, `lhc_c014`, `lhc_c015`, `lhc_c016`, `lhc_r010` through `lhc_r013`. | Gemma preserves Plaga better; GM response threads still tend to erode. |
| Earth, Sun, stars, and universe-scale exposure are separate support roles. | Merges them into one natural-exposure reassurance. | `lhc_c001`, `lhc_c002`, `lhc_c003`, `lhc_c007`, `lhc_r001`, `lhc_r002`, `lhc_r005`. | Recurs across model families as a similar-claim merger. |

### Eggs And Health

| Decision-relevant distinction | Flat synthesis behavior | Map preservation | Blinded-baseline status |
| --- | --- | --- | --- |
| Observational CVD outcomes and randomized lipid markers answer different questions. | Original baseline weakens the endpoint boundary. | `eggs_c004`, `eggs_c015`, `eggs_c016`, `eggs_c017`, `eggs_r005`, `eggs_r006`. | Gemma and Qwen preserve this better, so the claim should be narrowed for blinded comparators. |
| BMJ and JAMA are in tension rather than merely sequential findings. | Reports both but does not make the tension a navigable relation. | `eggs_c008`, `eggs_c012`, `eggs_c013`, `eggs_r003`. | Stronger baselines preserve more of the tension; still useful as a review edge. |
| Guidelines are policy syntheses, not direct outcome studies. | Treats guidance as advice without preserving process provenance. | `eggs_c001`, `eggs_c002`, `eggs_c003`, `eggs_r013`. | Recurs across blinded baselines. |
| NNR is a scoping review with evidence-grade limits. | Uses NNR as total-picture synthesis without the review-method caveat. | `eggs_c018`, `eggs_c019`, `eggs_r014`. | Recurs across blinded baselines. |
| `up to one egg/day` has different meanings across sources. | Similar wording is merged across AHA, BMJ, and NNR. | `eggs_c007`, `eggs_c008`, `eggs_c018`, Similar But Not Identical section. | Recurs across blinded baselines as a scope-distinction loss. |

## Reusable Outputs

- Markdown worked maps for human review.
- JSON worked-region exports:
  - `examples/lhc_black_holes/worked_region_cosmic_ray_map.json`
  - `examples/eggs/worked_region_observational_vs_rct_map.json`
- Artifact count summary:
  - `docs/SUBMISSION_ARTIFACT_SUMMARY.md`
- Broad full-case scaffolds:
  - `examples/lhc_black_holes/full_case_index.md`
  - `examples/lhc_black_holes/full_case_map.md`
  - `examples/eggs/full_case_index.md`
  - `examples/eggs/full_case_map.md`
- Human review packets:
  - `docs/review/LHC_HUMAN_AUDIT_PACKET.md`
  - `docs/review/EGGS_HUMAN_AUDIT_PACKET.md`
  - `docs/review/LHC_HUMAN_AUDIT_CHECKLIST.csv`
  - `docs/review/EGGS_HUMAN_AUDIT_CHECKLIST.csv`
- Operational realism artifacts:
  - `docs/INVESTIGATOR_WORKFLOW_PLAYBOOK.md`
  - `docs/OPERATIONAL_REALISM_AUDIT.md`
  - `examples/lhc_black_holes/investigator_task_queue.md`
  - `examples/eggs/investigator_task_queue.md`

## What Is Not Claimed

- The maps are not human-reviewed yet.
- The worked regions are not exhaustive full-case maps.
- The baselines are span-limited, not full-corpus literature reviews.
- The prototype is file-based, not an interactive product.
- The claim is not that all summaries fail. The claim is that flat synthesis preservation is brittle and model-dependent unless reviewable structure is preserved explicitly.

See `docs/SUBMISSION_LIMITATIONS.md` for the full risk register.
