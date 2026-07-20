# Fifty-Source Eggs Stress Run

Status: `machine-generated-not-decision-ready`

This packet preserves a fresh production-pipeline run over 50 acquired PMC
full-text sources. It demonstrates corpus-scale intake, staged mapping,
adjudication, synthesis, and fail-closed publication. It is not the project's
best substantive map and is not presented as a valid nutrition memo.

For the clearest substantive eggs example, start with the curated
[seven-source worked map](../eggs/worked_region_observational_vs_rct_map.md).
That map contains 19 claims, 17 relations, and 3 cruxes focused on the boundary
between observational cardiovascular outcomes, randomized lipid markers,
guideline framing, and population caveats.

## What This Run Shows

- The source corpus contains 50 acquired PMC articles, retained in
  [`data/cases/eggs_large_source_stress/`](../../data/cases/eggs_large_source_stress/).
- Gemma MLX 12B generated a source-grounded map with 165 initial claims, 6
  relations, and 5 crux candidates.
- Canonicalization retained 164 claims; prioritization routed 90 claims and 3
  relations into briefing.
- Analyst adjudication processed 117 rows in 59 chunks at parallelism 8, with
  no failed chunks.
- The map was rated `usable_with_review`, but the briefing remained
  `not_decision_ready`.
- Publication was blocked because critical packet evidence was omitted, source
  binding checks failed, and the active 90-claim graph had only 3 relations.

These results expose both capability and limitation. The pipeline handled a
large real corpus and retained detailed diagnostics, but source volume did not
automatically produce a decision-ready argument graph or memo.

## Inspection Path

1. Inspect the exact machine-generated [map](generated_map.json).
2. Read the [non-official blocked memo](blocked_memo.md) for the reader-facing
   output that the pipeline refused to publish.
3. Inspect the [final readiness report](final_decision_readiness_report.json)
   for the publication blockers.
4. Inspect the
   [adjudication chunk report](analyst_adjudication_chunk_reports.json) for
   chunk completion and parallelism.
5. Compare the graph with the substantive
   [seven-source eggs map](../eggs/worked_region_observational_vs_rct_map.md).

## Evidence Boundary

The generated map and reports are copied from the frozen run directory without
semantic edits. The blocked memo is retained because it makes the publication
decision inspectable, not because its dietary conclusion is endorsed. The
source corpus is broad and deliberately noisy; no independent domain expert
approved its selection, map, or memo.
