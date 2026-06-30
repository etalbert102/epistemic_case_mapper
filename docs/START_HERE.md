# Start Here: FLF Submission

Status: `human-review-needed`

This prototype is easiest to judge through one concrete question:

> Can an AI-assisted workflow preserve the reasoning structure that a normal synthesis tends to flatten?

The answer demonstrated here is not a better paragraph. It is a reusable review surface: source-grounded claims, relation IDs, caveats, cruxes, erosion losses, and human-review handoff packets.

## Reference Lineage

The contest examples point to a family of epistemic work where progress comes from finding hidden mismatches: the measure is not the construct, the same label hides different interventions, the dataset is not what it appears to be, or a broadly true result is framed as more decisive than it is.

This prototype is built for that kind of scrutiny. It gives reviewers stable handles for source boundaries, measurement or endpoint fit, same-label differences, relation dependencies, caveats, cruxes, and update triggers.

For the fuller mapping from contest references to prototype design, see `docs/REFERENCE_LINEAGE.md`.

## One-Minute Demo

Flat synthesis can say:

> Cosmic-ray exposure shows LHC black-hole risk is ruled out.

That is broadly right, but it hides a dependency. Earth cosmic-ray survival is not the whole argument once LHC-produced objects may be slower and more trappable than cosmic-ray products.

The LHC map preserves that dependency as reviewable pieces:

- `lhc_c004`: the velocity caveat.
- `lhc_c012`: the trapping analysis.
- `lhc_r003` and `lhc_r004`: why compact-star arguments become relevant.

This is the submission's value proposition: the map keeps the part of the reasoning a later reviewer would need to accept, challenge, or revise.

## Fastest Judge Path

1. Read `docs/FLF_BEFORE_AFTER_COMPARISON.md`.
2. Open `examples/lhc_black_holes/worked_region_cosmic_ray_map.md` and read only `What To Notice` plus the first six claims.
3. Open `examples/lhc_black_holes/decision_space_erosion_audit.md` and inspect `lhc_loss_001`.

That path should be enough to decide whether the core mechanism is interesting. Then use eggs for generalization and COVID as a narrow adversarial disagreement stress test.

The full judging rubric is recorded in `docs/reference/flf_judging_rubric.md`. The self-assessment in `docs/FLF_SELF_ASSESSMENT_AND_LIMITATIONS.md` maps the submission to those seven dimensions.

## What The Prototype Shows

- LHC: dependency structure and critique/response structure survive as reviewable nodes.
- Eggs: outcome evidence, lipid-marker evidence, guideline framing, and population caveats stay separate.
- COVID slice: Bayesian disagreement and subargument boundaries stay visible without claiming to settle origins.

## What To Ignore At First

- Do not start with the full-case maps.
- Do not start with the generated scaffold artifacts under `artifacts/`.
- Do not treat the UI as the source of truth.
- Do not treat `human-review-needed` as a flaw in itself; it is the current review boundary.

## Run The Checks

```bash
PYTHONPATH=src python3 scripts/run_flf_demo.py --skip-build
PYTHONPATH=src python3 scripts/reproducibility_gate.py --include-worked-regions
```

Passing checks mean the package is reproducible and internally consistent. They do not mean the maps have been externally reviewed.

## Visual Mode

```bash
python3 -m http.server 8787
```

Then open `http://localhost:8787/ui/`.

Use the top Judge Mode section for orientation, then use the case tabs only after the basic value is clear.

## Current Boundary

The submission is a polished prototype workflow. It is not a finished product, not an exhaustive case adjudication, and not a human-validated knowledge base. The next credibility upgrade is one completed external review pass over a small set of claims, relations, and erosion losses.
