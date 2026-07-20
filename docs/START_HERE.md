# Start Here: Epistemic Case Mapper

## Project In One Sentence

Epistemic Case Mapper turns a bounded investigation into stable, source-linked
reasoning objects so later investigators can inspect dependencies, preserve
disagreement, and update local parts without reconstructing the case from
prose.

## One-Minute Example

The broad LHC safety argument observes that natural cosmic-ray collisions have
occurred at or above LHC energies without destroying astronomical bodies. A
load-bearing caveat is that collider products may be slower and more trappable
than cosmic-ray products, so Earth survival is not sufficient by itself.

The map preserves the dependency as four addressable objects:

- `lhc_c004`: the low-velocity caveat;
- `lhc_c012`: the technical trapping analysis;
- `lhc_r003`: the caveat refines the broad cosmic-ray analogy;
- `lhc_r004`: the trapping analysis supports the caveat.

The scripted blinded Qwen synthesis reaches a broadly correct answer but does
not leave this chain as a durable review surface. Other local models preserve
different subsets of the case. The contribution is therefore inspectability
and persistence, not proof that models cannot recover the reasoning.

## Five-Minute Evidence Path

1. Read the blinded
   [Qwen LHC synthesis](../examples/lhc_black_holes/blinded_flat_synthesis_baseline_qwen3_8b.md).
2. Inspect `lhc_c004`, `lhc_c012`, `lhc_r003`, and `lhc_r004` in the
   [LHC map](../examples/lhc_black_holes/worked_region_cosmic_ray_map.md).
3. Inspect the substantive
   [seven-source eggs map](../examples/eggs/worked_region_observational_vs_rct_map.md),
   with 19 claims, 17 relations, and 3 cruxes spanning outcomes, biomarkers,
   guidelines, and subgroup caveats.
4. Open the
   [multi-model blinded audit](review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md),
   which records where Gemma, Qwen, Phi, and Granite preserved, flattened, or
   distorted distinctions in both LHC and eggs.
5. Inspect the [50-source eggs stress run](../examples/eggs_large_source_stress/README.md)
   to see corpus-scale processing and a defective memo blocked from publication.
6. Run `PYTHONPATH=src python3 scripts/run_flf_demo.py --skip-build`.

For the full project narrative, read the
[project writeup](submission/WRITEUP.md). For the compact evidence argument,
read [Proof By Example](submission/PROOF_BY_EXAMPLE.md). For limits, read
[Evidence And Limitations](submission/EVIDENCE_AND_LIMITATIONS.md).

## Evidence Hierarchy

### Primary Evidence

- Source-grounded LHC and eggs maps with structured JSON exports.
- Eight baselines produced by `scripts/run_blinded_baselines.py` from declared
  source spans without curated-map or erosion-audit context.
- The agent-authored multi-model audit, explicitly awaiting human review.
- Generic manifest, worked-region, source, export, UI, and reference validators.
- A [paired live Gemma MLX run](../examples/live_model_runs/README.md) preserves
  one valid-with-review eggs candidate and one rejected LHC candidate, including
  prompts, raw outputs, repair trails, and quality diagnostics.
- A [50-source eggs stress run](../examples/eggs_large_source_stress/README.md)
  preserves the exact generated map, adjudication report, blocked memo, and
  final readiness decision from the deeper production pipeline.
- The deterministic investigator challenge for object addressability,
  frozen-snapshot restoration, and prewritten update locality.

### Secondary Evidence

- The COVID origins slice tests disagreement representation across debate
  results, process critiques, forecasts, and Bayesian subarguments. It uses
  investigator notes and excerpts and is not source-grounded adjudication.

### Non-Evaluative And Appendix Material

- Original same-context flat syntheses and erosion audits illustrate the audit
  schema but cannot measure model performance because their writer had access
  to the curated task context.
- The matched top-model response is a reported claim-boundary illustration; its
  invocation transcript was not retained.
- The briefing pipeline shows implementation depth and fail-closed behavior,
  but generated memo quality is outside the central proof.

## Evidence By Evaluation Dimension

| Criterion | What is demonstrated | Main remaining gap |
| --- | --- | --- |
| Epistemic uplift | Load-bearing dependencies and evidence-role boundaries become directly inspectable. | No measured improvement over top-range deep research in reviewer accuracy or speed. |
| Generalizability | One schema operates across two grounded cases and one narrow disagreement stress test. | No unseen-case or independent second-operator result. |
| Compounding | Stable IDs, JSON, review packets, task queues, and update ledgers support local extension. | Multi-reviewer merge and conflict resolution are not implemented. |
| Scalability | Generic stages, model backends, and validators processed a 50-source eggs corpus; the retained trace shows completed adjudication and fail-closed memo publication. | The active relation graph remained sparse and hands-free decision-ready quality is not demonstrated. |
| Transparency | Prompts, manifests, source spans, validation rules, and limitations are retained. | Some historical model invocation records are incomplete. |
| Adversarial robustness | Multiple model families, explicit rejected findings, critique/response structure, and fail-closed gates expose failures. | No external motivated audit has challenged source selection or relation labels. |
| Insight | The package treats persistence and reviewability as separate from final prose quality. | The method may amount to argument mapping plus provenance unless the handoff mechanism proves useful. |

## Reproduce

The fast gate and full deterministic gate both call no model:

```bash
PYTHONPATH=src python3 scripts/run_flf_demo.py --skip-build
PYTHONPATH=src python3 scripts/reproducibility_gate.py \
  --include-worked-regions \
  --include-blinded-baselines
```

Passing establishes package integrity and selected local-edit behavior, not
scientific correctness. The install, starter-map exercise, and live backend
boundary are documented in [REPRODUCE.md](submission/REPRODUCE.md).
