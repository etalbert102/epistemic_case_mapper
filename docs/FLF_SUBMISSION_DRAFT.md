# FLF Submission Draft

Status: `human-review-needed`

## Problem Framing

Modern AI systems can produce fluent syntheses, but fluent synthesis often erodes decision space. Important caveats, disagreements, dependencies, and source boundaries disappear into a plausible paragraph before a reviewer can inspect them.

This prototype offers a lightweight workflow and artifact format for AI-assisted epistemic case mapping. The goal is not to maximize summary polish. The goal is to preserve source-grounded structure so another investigator can inspect, challenge, extend, and reuse the work.

This maps directly to the FLF contest brief. FLF asks for AI-assisted workflows that produce reusable, refinable knowledge artifacts rather than single-user summaries. Decision-space erosion names the failure mode; epistemic case maps provide the preservation artifact; erosion audits provide the measurement layer.

## Workflow Summary

The workflow has six steps:

1. Scope a narrow worked region.
2. Fix a local source subset.
3. Extract source-grounded claims with span markers and entailment checks.
4. Add support, challenge, dependency, tension, crux, refinement, and similarity relations.
5. Write a normal flat synthesis from the same source subset.
6. Audit where the flat synthesis loses decision-relevant structure that the map preserves.

The prototype includes deterministic scaffold generation plus curated judge-facing worked regions. Generated artifacts live under `artifacts/`; curated snapshots and worked examples live under `examples/`.

## Artifact Format

The core schema in `src/epistemic_case_mapper/schema.py` represents sources, claims, relations, open questions, audit notes, and metadata. The curated Markdown worked regions mirror the same structure in a judge-readable form:

- source IDs from `case.yaml`,
- claim IDs and source-local spans,
- short excerpts and `entailed_by_excerpt` checks,
- relation IDs, relation types, and rationales,
- crux candidates,
- similar-but-not-identical groupings,
- FLF judge-question scores,
- flat-synthesis erosion audits.

## LHC Worked-Region Summary

Region: `lhc_cosmic_ray_argument`

Question: does the cosmic-ray safety argument, including compact-star variants and critiques, rule out decision-relevant LHC microscopic-black-hole risk?

Key files:

- `docs/worked_regions/lhc_cosmic_ray_argument.md`
- `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`
- `examples/lhc_black_holes/flat_synthesis_baseline.md`
- `examples/lhc_black_holes/decision_space_erosion_audit.md`
- `examples/lhc_black_holes/BEST_REGIONS.md`

The map preserves the natural exposure argument, the low-velocity trapping caveat, Hawking-radiation and independent-decay assumptions, white-dwarf versus neutron-star scope, Plaga's metastable critique, and GM's response. The flat baseline remains broadly correct but loses several dependencies, especially the relation between velocity, trapping, and why compact-star analysis matters.

## Eggs Worked-Region Summary

Region: `eggs_observational_vs_rct`

Question: how should a synthesis preserve the relationship between observational CVD outcome evidence, randomized lipid-marker evidence, guideline framing, and population/context caveats for egg consumption?

Key files:

- `docs/worked_regions/eggs_observational_vs_rct.md`
- `examples/eggs/worked_region_observational_vs_rct_map.md`
- `examples/eggs/flat_synthesis_baseline.md`
- `examples/eggs/decision_space_erosion_audit.md`
- `examples/eggs/BEST_REGIONS.md`

The map keeps observational CVD outcomes, randomized lipid markers, dietary-pattern guidance, replacement-food modeling, baseline intake, high-LDL guidance, diabetes and regional caveats, and NNR evidence-grade limits separate. The flat baseline gives a reasonable answer but weakens the endpoint boundary and the BMJ/JAMA tension.

## Evidence That Flat Synthesis Loses Decision-Relevant Structure

The LHC erosion audit counts six surviving losses. The strongest is `lhc_loss_001`: the flat baseline mentions the velocity caveat but loses the dependency between low LHC product velocities, Earth trapping, and why Earth cosmic-ray survival alone is not the whole argument.

The eggs erosion audit counts seven surviving losses. The strongest is `eggs_loss_001`: the flat baseline mentions biomarkers but does not preserve that randomized egg trials measure LDL-c and LDL-c/HDL-c rather than direct CVD outcomes.

The repository also includes a reproducible local-model blinded-baseline procedure in `scripts/run_blinded_baselines.py`. It generates flat syntheses from raw source text line spans without loading the curated maps, erosion audits, judge walkthrough, or `BEST_REGIONS.md` files. Checked-in outputs include Gemma4, Qwen3, Phi4, and Granite baselines for both worked regions.

An agent-authored audit of the original Gemma4 blinded baselines is recorded in `docs/review/BLINDED_BASELINE_AUDIT.md`. A broader multi-model audit is recorded in `docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md`.

Against the blinded comparators, the stronger claim is not that every flat synthesis misses every major distinction. The stronger claim is that flat synthesis preservation is brittle and model-dependent, while the map/audit workflow creates an explicit surface for checking which distinctions survived, flattened, disappeared, or distorted.

These are not claims that the flat syntheses are bad. They are claims that a normal paragraph is a lossy container for reviewable epistemic structure.

## Limitations

- Current worked regions are source-grounded but not human-reviewed.
- Original baseline comparisons are illustrative; the added blinded local-model baselines improve isolation from the map, but they are span-limited and still need human fairness audit before being treated as decisive evidence.
- The curated maps cover strong slices, not full exhaustive case maps.
- Relation labels and crux choices need domain-review pressure.
- The current prototype is file-based and command-line oriented.
- More source-span automation would improve scale and reduce manual curation burden.

## Install And Run

```bash
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
PYTHONPATH=src python3 scripts/run_flf_demo.py
PYTHONPATH=src python3 scripts/build_case_map.py --case data/cases/lhc_black_holes/case.yaml
PYTHONPATH=src python3 scripts/build_case_map.py --case data/cases/eggs/case.yaml
PYTHONPATH=src python3 scripts/validate_case_artifact.py --case data/cases/lhc_black_holes/case.yaml --examples examples/lhc_black_holes
PYTHONPATH=src python3 scripts/validate_case_artifact.py --case data/cases/eggs/case.yaml --examples examples/eggs
PYTHONPATH=src python3 scripts/validate_worked_regions.py
PYTHONPATH=src python3 scripts/validate_blinded_baselines.py
PYTHONPATH=src python3 scripts/reproducibility_gate.py --include-worked-regions --include-blinded-baselines
```

## Remaining Human-Review Needs

Use `docs/HUMAN_REVIEW_CHECKLIST.md` to review:

- whether each source excerpt entails its claim,
- whether relation types are justified,
- whether the cruxes are real decision points,
- whether flat-synthesis losses are fair,
- whether review status and certainty are not overstated.

Case-specific handoff packets are available at:

- `docs/review/LHC_HUMAN_AUDIT_PACKET.md`
- `docs/review/EGGS_HUMAN_AUDIT_PACKET.md`

Until that pass occurs, the artifact should remain `human-review-needed`.
