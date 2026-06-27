# Epistemic Case Mapper

Lightweight FLF competition prototype for producing reusable, navigable epistemic case maps with AI assistance.

Start with the judge packet: `docs/SUBMISSION_PACKET.md`.

For a visual inspection surface, run the static UI at `ui/index.html`.

This repo is intentionally separate from `decision_space_harness`.

- `decision_space_harness`: research benchmark, metrics, paper-grade evaluation.
- `epistemic_case_mapper`: judge-facing prototype and workflow for real case studies.

## Goal

Help an investigator preserve the structure of a complex epistemic case while synthesizing it:

- source provenance
- claims and similar claims
- support/challenge relationships
- cruxes and open questions
- missing perspectives
- uncertainty and audit notes

The central failure mode is **decision-space erosion**: a synthesis can remain fluent and plausible while flattening the options, frames, caveats, cruxes, or disagreements that a serious investigator needs.

## Current Shape

The current implementation is a runnable contest prototype:

- source-grounded case manifests and local source text for LHC black holes, eggs, and a narrow COVID origins slice,
- deterministic starter map generation in `scripts/build_case_map.py`,
- curated worked-region maps with claim, relation, crux, and erosion-audit surfaces,
- full-case scaffolds and illustrative full-case flat baselines,
- multi-model local blinded baselines for the worked regions,
- human audit packets, review checklists, and judge-facing walkthroughs,
- a static inspection UI under `ui/`.

The deterministic builder is not the final AI workflow. It creates a repeatable artifact shape; the checked-in examples show how that shape is filled, audited, and handed to a reviewer.

## Quick Start

```bash
python -m venv .venv
./.venv/bin/pip install -e ".[dev]"
./.venv/bin/python scripts/run_flf_demo.py
```

The demo command regenerates the deterministic starter artifacts, validates the checked-in LHC, eggs, and COVID worked regions, validates the blinded baseline set, and prints the judge-facing entry points.

For a faster checked-in artifact audit without rebuilding generated starter outputs:

```bash
PYTHONPATH=src python3 scripts/run_flf_demo.py --skip-build
```

Generated starter output is written to `artifacts/<case_id>/`. Curated judge-facing snapshots live under `examples/`.

## Judge Path

Start with:

- `docs/SUBMISSION_PACKET.md`
- `ui/index.html`
- `docs/FLF_BEFORE_AFTER_COMPARISON.md`
- `docs/review/REVIEWER_START_HERE.md`
- `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv`
- `docs/HUMAN_AUDIT_GUIDE.md`
- `docs/FLF_SELF_ASSESSMENT_AND_LIMITATIONS.md`
- `docs/FLF_SUBMISSION_DRAFT.md`

The fastest evidence check is:

1. Start with the full-case index for a case.
2. Inspect the best-region pointer and worked-region anchor.
3. Compare the worked-region map to the flat synthesis baseline.
4. Read the erosion audit.
5. Check the blinded and multi-model baseline audits to see which losses survive stronger comparators.
6. Use the case-specific human audit packet before treating any artifact as reviewed.

Full-case scaffold entry points:

- `examples/lhc_black_holes/full_case_index.md`
- `examples/eggs/full_case_index.md`

Operational realism entry points:

- `docs/OPERATIONAL_WORKFLOW_AND_REALISM.md`
- `examples/lhc_black_holes/investigator_task_queue.md`
- `examples/eggs/investigator_task_queue.md`

To open the UI locally:

```bash
python3 -m http.server 8787
```

Then visit `http://localhost:8787/ui/`.

Reusable structured exports are checked in at:

- `examples/lhc_black_holes/worked_region_cosmic_ray_map.json`
- `examples/eggs/worked_region_observational_vs_rct_map.json`
- `examples/covid_origins_slice/worked_region_bayesian_disagreement_map.json`

## Target FLF Demonstrations

Initial demonstration cases:

1. `lhc_black_holes`: closed technical risk case; good for dependency and crux mapping.
2. `eggs`: messy everyday evidence case; good for heterogeneity, framing, and methods-of-knowing.
3. `covid_origins_slice`: narrow adversarial slice; good for Bayesian disagreement, update triggers, and subargument boundaries, but not a full COVID origins assessment.

## Intended Submission Package

- A short methodology/spec.
- A runnable prototype.
- At least two worked examples.
- Clear before/after examples showing where ordinary synthesis loses structure.
- A reusable artifact format that other investigators can extend.
