# FLF Judge Walkthrough

Status: `human-review-needed`

Purpose: give a fast path through the prototype without requiring a judge to inspect raw JSON first.

## One-Command Check

Run:

```bash
PYTHONPATH=src python3 scripts/run_flf_demo.py
```

This regenerates deterministic starter artifacts, validates the checked-in worked regions, validates all blinded local-model baselines, and prints the entry-point files. Use `--skip-build` for a faster validation-only pass over checked-in artifacts.

## Ten-Minute Path

1. Read `docs/FLF_BEFORE_AFTER_COMPARISON.md` to see the central before/after claim.
2. Open the dashboard at `ui/index.html` or `http://localhost:8787/ui/` if serving locally.
3. Read `docs/FLF_CONTEST_CRITERIA_SELF_ASSESSMENT.md` to see how the prototype maps to FLF's criteria.
4. Inspect `docs/FAILURE_MODES_AND_COUNTEREXAMPLES.md` to see where the method can fail.
5. Read `docs/FLF_WORKED_JUDGE_EXAMPLE.md` for a compact task/output/auditor-decision example.
6. Read `docs/FLF_AUDITOR_WALKTHROUGH_EXAMPLE.md` to see the audit sequence before trusting a worked region.
7. Inspect `docs/NEW_SOURCE_UPDATE_DEMO.md` to see the compounding/update workflow.
8. Skim the two full-case flat baselines:
   - `examples/lhc_black_holes/full_case_flat_synthesis_baseline.md`
   - `examples/eggs/full_case_flat_synthesis_baseline.md`
9. Use the two-minute LHC and eggs paths below to verify the worked-region evidence.

## Two-Minute Path: LHC

1. Open `examples/lhc_black_holes/BEST_REGIONS.md`.
2. Inspect the strongest claim cluster in `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`: `lhc_c001` through `lhc_c004`.
3. Follow relations `lhc_r003`, `lhc_r004`, and `lhc_r016` to see how the velocity/trapping caveat modifies the natural cosmic-ray analogy.
4. Compare `examples/lhc_black_holes/flat_synthesis_baseline.md` with `examples/lhc_black_holes/decision_space_erosion_audit.md`, especially `lhc_loss_001`.
5. Optionally compare the more isolated local-model baselines at `examples/lhc_black_holes/blinded_flat_synthesis_baseline_*.md`.
6. For an extension beyond the technical safety core, inspect the draft public-risk map at `examples/lhc_black_holes/worked_region_public_risk_framing_map.md`.

What to notice: the flat baseline is broadly correct, but the map preserves why "cosmic rays already do this" is not a standalone argument. The map keeps Earth/Sun/stars exposure, low-velocity trapping, compact-star bounds, Plaga's critique, and GM's response as separate reviewable nodes.

## Two-Minute Path: Eggs

1. Open `examples/eggs/BEST_REGIONS.md`.
2. Inspect `examples/eggs/worked_region_observational_vs_rct_map.md` claims `eggs_c004`, `eggs_c008`, `eggs_c012`, `eggs_c015`, `eggs_c016`, and `eggs_c018`.
3. Follow relations `eggs_r003`, `eggs_r005`, `eggs_r006`, `eggs_r007`, and `eggs_r015`.
4. Compare `examples/eggs/flat_synthesis_baseline.md` with `examples/eggs/decision_space_erosion_audit.md`, especially `eggs_loss_001` and `eggs_loss_002`.
5. Optionally compare the more isolated local-model baselines at `examples/eggs/blinded_flat_synthesis_baseline_*.md`.

What to notice: "eggs are fine in moderation" is too compressed, while "eggs raise CVD risk" is also too compressed. The map preserves study design, endpoint, population, dietary-pattern, replacement-food, and guideline-process distinctions.

## Why The Workflow Helps Reasoning

The workflow makes claims, sources, relations, cruxes, caveats, and losses inspectable. It does not ask a final synthesis paragraph to carry all decision-relevant structure implicitly. The worked regions demonstrate the same pattern in two different domains: a closed technical-risk argument and a messy everyday nutrition question.

The before/after comparison is intentionally conservative. Each counted erosion loss must be supported by the same source subset, decision-relevant, preserved by the map, omitted or flattened by the baseline, and pass an adversarial fairness check.

For the compact before/after version, read `docs/FLF_BEFORE_AFTER_COMPARISON.md`.

## How Artifacts Can Be Extended

The extension path is local and incremental:

- Add a source to `data/cases/<case_id>/case.yaml`.
- Regenerate starter artifacts with `scripts/build_case_map.py`.
- Add or revise curated worked-region claims with stable claim IDs.
- Add relation rationales, cruxes, and similar-but-not-identical groupings.
- Re-run `scripts/validate_worked_regions.py` and `scripts/reproducibility_gate.py --include-worked-regions`.

Future investigators can dispute one relation, add one caveat, or replace one source span without rewriting the whole case.

## Where Human Judgment Remains Required

Human review is still required for:

- source-excerpt fidelity,
- whether relation types are technically fair,
- whether cruxes would really change the assessment,
- whether flat-synthesis losses are fair,
- whether the artifact is useful to reason with,
- whether the final submission overclaims certainty or review status.

Use `docs/HUMAN_REVIEW_CHECKLIST.md` for that pass. Current review status remains `human-review-needed`.

## Limits And Residual Risks

- The worked-region maps are curated by Codex from local excerpt packets and source text, not human-reviewed.
- The flat baselines are illustrative because this same run had access to the curated-map task and source-packet orientation.
- The blinded local-model baselines improve isolation from the curated maps, but they are span-limited and still need human fairness review.
- The full-case flat baselines are stronger realism checks than the worked-region baselines, but they have not yet been human-scored.
- The public-risk framing map is an extension draft and has not been promoted to the canonical validated worked-region set.
- The examples cover strong regions, not exhaustive case maps.
- Relation typing is useful but still requires expert review.
- The prototype is a file-based workflow, not yet an interactive tool.
