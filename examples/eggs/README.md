# Eggs And Health Example

This transfer example tests evidence-role, endpoint, and population boundaries.
The source packet is declared in
[`data/cases/eggs/case.yaml`](../../data/cases/eggs/case.yaml).

## Reviewer Path

1. [Scripted blinded Qwen synthesis](blinded_flat_synthesis_baseline_qwen3_8b.md):
   a strong local-model before view.
2. [Worked map](worked_region_observational_vs_rct_map.md): the curated
   structured view.
3. [Multi-model audit](../../docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md):
   distinctions preserved, flattened, or distorted across four models.
4. [Structured export](worked_region_observational_vs_rct_map.json): the same
   worked map in reusable JSON.

The original [flat synthesis](flat_synthesis_baseline.md) and
[erosion audit](decision_space_erosion_audit.md) are retained only as
non-evaluative audit-format examples because their writer had curated task
context.

## Strongest Claim Cluster

Claims `eggs_c004`, `eggs_c008`, `eggs_c012`, `eggs_c015`, `eggs_c016`, and
`eggs_c018` preserve the observational-outcome versus randomized-biomarker
structure that ordinary nutrition prose can blur.

## Strongest Relation Cluster

Relations `eggs_r003`, `eggs_r005`, `eggs_r006`, `eggs_r007`, and `eggs_r015`
show how apparently conflicting conclusions can all matter once endpoint and
method are explicit.

## Strongest Crux

Should direct cardiovascular-outcome evidence or lipid-marker RCT evidence
carry more weight in dietary advice? Inspect `eggs_c004`, `eggs_c008`,
`eggs_c015`, `eggs_c016`, `eggs_c018`, and `eggs_r015`.

## Strongest Preserved Caveat Or Disagreement

“Up to one egg per day” plays different roles in AHA public guidance, BMJ
observational evidence, and NNR scoping synthesis. The map keeps healthy-person
guidance, cohort baseline intake, and evidence-grade limits separate.

## Strongest Flat-Synthesis Loss

Start with `eggs_loss_005`, `eggs_loss_006`, and `eggs_loss_007` in the
multi-model audit. Stronger local models preserve the basic endpoint boundary,
while guideline-process provenance, review-method limits, and the different
meanings of “up to one egg/day” remain less stable.

## Starter Snapshot

The reproducibility-only heuristic snapshot is separated from the curated map
under [`../starter_snapshots/eggs/`](../starter_snapshots/eggs/). Regenerate it
with:

```bash
python scripts/build_case_map.py --case data/cases/eggs/case.yaml --output-root examples/starter_snapshots
```

The curated map is source-grounded, agent-curated, and mechanically validated;
it has not received independent domain-expert review. Relation labels, crux
selection, subgroup interpretation, and erosion findings remain reviewable
judgments. The current source packet uses AHA and Nordic Nutrition
Recommendations context because direct Dietary Guidelines PDF retrieval did
not complete during acquisition.
