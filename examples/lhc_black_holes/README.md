# LHC Black Holes Example

This is the canonical worked example for dependency preservation. The source
packet is declared in [`data/cases/lhc_black_holes/case.yaml`](../../data/cases/lhc_black_holes/case.yaml).

## Reviewer Path

1. [Scripted blinded Qwen synthesis](blinded_flat_synthesis_baseline_qwen3_8b.md):
   a strong local-model before view.
2. [Worked map](worked_region_cosmic_ray_map.md): the curated structured view.
3. [Multi-model audit](../../docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md):
   distinctions preserved, flattened, or distorted across four models.
4. [Structured export](worked_region_cosmic_ray_map.json): the same worked map
   in reusable JSON.

The original [flat synthesis](flat_synthesis_baseline.md) and
[erosion audit](decision_space_erosion_audit.md) are retained only as
non-evaluative audit-format examples because their writer had curated task
context.

## Strongest Claim Cluster

Claims `lhc_c001` through `lhc_c004` preserve the natural-exposure argument and
its velocity caveat. This is the fastest place to see why a broadly correct
reassurance sentence is not the same as a reviewable inference.

## Strongest Relation Cluster

Relations `lhc_r003`, `lhc_r004`, and `lhc_r016` connect the high-level velocity
caveat to the technical trapping analysis. The caveat is linked to the
inference it modifies instead of being left as free-floating prose.

## Strongest Crux

Does Plaga's metastable, Eddington-limited scenario create a real gap in the
compact-star bounds? Inspect `lhc_c013` through `lhc_c016` and `lhc_r010`
through `lhc_r015`.

## Strongest Preserved Caveat Or Disagreement

The map separates Plaga's white-dwarf stopping objection from the response:
scenario assumptions, semiclassical stopping, a 23-order power-calculation
dispute, and Eddington-limited accretion remain distinct review targets.

## Strongest Flat-Synthesis Loss

Start with `lhc_loss_001` in the multi-model audit. The low-velocity trapping
dependency survives as a loss across the blinded local-model comparisons even
when broader caveats are preserved.

## Starter Snapshot

The reproducibility-only heuristic snapshot is separated from the curated map
under [`../starter_snapshots/lhc_black_holes/`](../starter_snapshots/lhc_black_holes/).
Regenerate it with:

```bash
python scripts/build_case_map.py --case data/cases/lhc_black_holes/case.yaml --output-root examples/starter_snapshots
```

The curated map is source-grounded, agent-curated, and mechanically validated;
it has not received independent domain-expert review. Relation labels, crux
selection, and erosion findings therefore remain reviewable judgments rather
than settled facts.
