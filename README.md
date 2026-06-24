# Epistemic Case Mapper

Lightweight FLF competition prototype for producing reusable, navigable epistemic case maps with AI assistance.

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
./.venv/bin/python scripts/build_case_map.py --case data/cases/lhc_black_holes/case.yaml
```

Output is written to `artifacts/<case_id>/`.

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
