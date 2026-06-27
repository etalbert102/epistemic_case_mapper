# Epistemic Case Mapper

Lightweight FLF competition prototype for producing reusable, navigable epistemic case maps with AI assistance.

Start with the judge packet: `docs/SUBMISSION_PACKET.md`.

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

The current implementation is a scaffold:

- case manifests in `data/cases/*/case.yaml`
- a deterministic starter map builder in `scripts/build_case_map.py`
- shared schema helpers in `src/epistemic_case_mapper/`
- FLF-facing protocol notes in `docs/`

The deterministic builder is not the final AI workflow. It creates an auditable artifact shape that the LLM-assisted workflow can fill.

## Quick Start

```bash
python -m venv .venv
./.venv/bin/pip install -e ".[dev]"
./.venv/bin/python scripts/run_flf_demo.py
```

The demo command regenerates the deterministic starter artifacts, validates the checked-in LHC and eggs worked regions, validates the blinded baseline set, and prints the judge-facing entry points.

For a faster checked-in artifact audit without rebuilding generated starter outputs:

```bash
PYTHONPATH=src python3 scripts/run_flf_demo.py --skip-build
```

Generated starter output is written to `artifacts/<case_id>/`. Curated judge-facing snapshots live under `examples/`.

## Judge Path

Start with:

- `docs/FLF_JUDGE_INDEX.md`
- `docs/SUBMISSION_PACKET.md`
- `docs/FLF_JUDGE_WALKTHROUGH.md`
- `docs/FLF_BEFORE_AFTER_COMPARISON.md`
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

Reusable structured exports are checked in at:

- `examples/lhc_black_holes/worked_region_cosmic_ray_map.json`
- `examples/eggs/worked_region_observational_vs_rct_map.json`

## Target FLF Demonstrations

Initial demonstration cases:

1. `lhc_black_holes`: closed technical risk case; good for dependency and crux mapping.
2. `eggs`: messy everyday evidence case; good for heterogeneity, framing, and methods-of-knowing.
3. `covid_origins_slice`: optional narrow slice; good stress test, but not the first full worked example.

## Intended Submission Package

- A short methodology/spec.
- A runnable prototype.
- At least two worked examples.
- Clear before/after examples showing where ordinary synthesis loses structure.
- A reusable artifact format that other investigators can extend.
