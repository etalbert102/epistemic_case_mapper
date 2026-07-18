# Pipeline Demonstration Examples

Status: `human-review-needed`

Purpose: give reviewers concrete ways to exercise the pipeline against the FLF criteria without turning the front-door packet into a scoring rubric. The examples below are chosen from the recorded contest framing in `docs/reference/flf_epistemic_case_study_competition_criteria.md` and `docs/reference/flf_judging_rubric.md`: ingestion, structure, assessment, generalization across case shapes, compounding, and adversarial robustness.

Use these after reading `docs/START_HERE.md`. They are not separate claims that every case is solved; they are small demonstrations of the workflow mechanics.

## Example 1: Intake Filter Before The Pipeline

What it demonstrates: ingestion hygiene before source material can poison the full map.

Run:

```bash
PYTHONPATH=src python3 -m epistemic_case_mapper.cli case filter-sources \
  --question "Should a careful reviewer treat moderate egg consumption as generally acceptable for cardiovascular risk?" \
  --docs \
    data/cases/eggs/sources/text/bmj_2020_egg_consumption_cvd_pmc.txt \
    data/cases/eggs/sources/text/jama_2019_dietary_cholesterol_eggs_pmc.txt \
    data/cases/eggs/sources/text/aha_2023_dietary_cholesterol_news.txt \
  --output-dir artifacts/demo_examples/eggs_intake \
  --backend prompt
```

Inspect:

- `artifacts/demo_examples/eggs_intake/SOURCE_INTAKE_FILTER.md`
- `artifacts/demo_examples/eggs_intake/source_intake_filter.json`

What to look for:

- The filter records citation-density, reference-section, source-type, date, and traceability signals before model extraction.
- `prompt` mode writes the model prompt without calling a model, so the boundary between deterministic checks and model judgment is visible.
- The filter is report-only unless a user explicitly applies exclusions during `case init`.

Why it matters:

FLF's ingestion layer asks whether messy source material can become structured enough to reason over. This example shows the first guardrail: source inputs can be screened and documented before they enter claim extraction.

## Example 2: Closed Technical-Risk Dependency

What it demonstrates: structure preservation in a mostly settled technical case.

Inspect:

- `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`
- `examples/lhc_black_holes/decision_space_erosion_audit.md`
- `docs/FLF_BEFORE_AFTER_COMPARISON.md`

Fast path:

1. In the LHC map, read `What To Notice`.
2. Read claims `lhc_c001` through `lhc_c006`.
3. In the erosion audit, inspect `lhc_loss_001`.

What to look for:

- A flat synthesis can say that cosmic-ray exposure rules out LHC black-hole risk.
- The map keeps the dependency visible: Earth cosmic-ray survival is not by itself enough if LHC products are slower and more trappable.
- `lhc_c004`, `lhc_c012`, `lhc_r003`, and `lhc_r004` preserve why compact-star arguments become relevant.

Why it matters:

This is the cleanest example of decision-space erosion. The ordinary summary is broadly correct, but the map preserves the load-bearing caveat a later reviewer would need to inspect.

## Example 3: Messy Everyday Evidence With Method Boundaries

What it demonstrates: assessment support in a vague, contested, evidence-heavy question.

Inspect:

- `examples/eggs/worked_region_observational_vs_rct_map.md`
- `examples/eggs/decision_space_erosion_audit.md`
- `docs/baselines/deep_research/deep_research_eggs_Claude_Opus4.8.md`

What to look for:

- Observational cardiovascular outcomes are kept separate from randomized lipid-marker evidence.
- Guideline framing is not treated as direct causal evidence.
- Subgroup and substitution-context caveats remain visible rather than being blended into one answer.
- The Deep Research baseline is useful prose, but the map gives a more interrogable surface for checking which distinctions carried the conclusion.

Why it matters:

FLF's eggs case is deliberately mundane and under-specified. This example tests whether the workflow can preserve methods-of-knowing and population heterogeneity instead of returning a single plausible nutrition answer.

## Example 4: Narrow Adversarial Disagreement Slice

What it demonstrates: preserving disagreement structure without overclaiming settlement.

Inspect:

- `examples/covid_origins_slice/worked_region_bayesian_disagreement_map.md`
- `examples/covid_origins_slice/decision_space_erosion_audit.md`
- `examples/covid_origins_slice/flat_synthesis_baseline.md`

What to look for:

- Debate outcome, postmortem critique, superforecast aggregate, minority disagreement, and Bayesian decomposition assumptions are represented as different pieces.
- The artifact does not claim to settle COVID origins.
- The map makes visible where a reader would need to inspect assumptions rather than treating one debate result as a final answer.

Why it matters:

FLF explicitly names adversarial, high-stakes, information-scarce settings. This example shows a bounded version of that problem: not a full origins judgment, but a demonstration of preserving disagreement and update triggers.

## Example 5: Resume From Artifacts And Build A Reader Packet

What it demonstrates: compounding and shareability. A later investigator can pick up an intermediate artifact rather than rerunning the whole process.

Check stage status:

```bash
PYTHONPATH=src python3 -m epistemic_case_mapper.cli semantic staged status \
  --region eggs_observational_vs_rct
```

Resume from an existing map artifact when available:

```bash
PYTHONPATH=src python3 -m epistemic_case_mapper.cli semantic staged resume \
  --region eggs_observational_vs_rct \
  --from-stage map \
  --backend prompt
```

Inspect:

- The printed briefing path.
- The printed `FINAL_REVIEW_PACKET.md` path.
- `artifacts/semantic/<region>/staged_brief/briefing/briefing_summary.json` when generated.

What to look for:

- The pipeline has explicit handoff points: documents, map, briefing.
- Prompt-only mode allows inspection without model cost.
- The final packet surfaces warnings, source traceability, and remaining review work.

Why it matters:

FLF asks whether artifacts compound. Resume points, stable IDs, JSON/Markdown outputs, and review packets are the core answer: another investigator can inspect, revise, and extend a piece without rebuilding the whole case from scratch.

## Example 6: Local Reproducibility Gate

What it demonstrates: methodological transparency and package-level consistency.

Run:

```bash
PYTHONPATH=src python3 scripts/run_flf_demo.py --skip-build
PYTHONPATH=src python3 scripts/reproducibility_gate.py --include-worked-regions
```

What to look for:

- The commands validate checked-in examples, references, UI data, blinded baseline surfaces, and worked-region structure.
- Passing validation does not mean the maps are externally correct; it means the package is internally coherent and reproducible enough to inspect.

Why it matters:

This makes the prototype critiqueable. A judge can run the package, inspect artifact paths, and distinguish runnable workflow evidence from unresolved human-review risk.

## Choosing A Demo By Question

| Reviewer question | Fastest demonstration |
| --- | --- |
| Does the pipeline screen bad inputs before they contaminate the map? | Example 1 |
| Does it preserve a load-bearing dependency a summary hides? | Example 2 |
| Does it keep evidence types separate in a messy domain? | Example 3 |
| Does it handle adversarial disagreement without pretending to settle it? | Example 4 |
| Can another investigator pick up intermediate work? | Example 5 |
| Is the package reproducible enough to critique? | Example 6 |

## Boundary

These examples demonstrate the pipeline and artifact shape. They do not prove that every produced memo is expert-grade, that source collection is complete, or that the current maps have passed independent external review. The intended claim is narrower: the workflow keeps reasoning structure, source boundaries, and review obligations visible in ways that ordinary synthesis often does not.
