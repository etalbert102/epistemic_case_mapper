# Reproduce And Exercise The Prototype

The deterministic contest gate, heuristic starter builder, and live-model
pipeline answer different questions. None establishes domain correctness.

## Install

From a fresh checkout with Python 3.11 or newer:

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
```

Activate the environment if desired, or replace `python` below with the
environment's Python executable.

## Fast Contest Review

```bash
python scripts/run_flf_demo.py --skip-build
```

This calls no model, validates the curated examples and reviewer paths, and
normally completes in seconds.

For the full deterministic package gate:

```bash
python scripts/reproducibility_gate.py --include-worked-regions --include-blinded-baselines
```

## Preconfigured LHC Starter Exercise

The following clone-and-run command was exercised on the checked-in LHC case:

```bash
python scripts/build_case_map.py \
  --repo-root . \
  --case data/cases/lhc_black_holes/case.yaml \
  --output-root artifacts

python scripts/validate_case_artifact.py \
  --repo-root . \
  --case data/cases/lhc_black_holes/case.yaml \
  --examples artifacts/lhc_black_holes
```

On the verification machine, generation took about 0.6 seconds. Beneath the
ignored `artifacts/` directory it creates an `lhc_black_holes` folder containing
`case_map.json`, `report.md`, and `audit.md`. This is a deterministic heuristic
starter map used to reproduce the artifact contract; it is not the curated
worked map or a decision memo.

## Backend-Dependent Live Briefing

With Ollama running and a sufficiently large-context model already installed:

```bash
ecm --repo-root . \
  --package submission_manifest.yaml \
  semantic staged brief \
  --region lhc_cosmic_ray_argument \
  --backend ollama:<installed-model> \
  --backend-timeout 120 \
  --backend-retries 1
```

By default, the run creates a `staged_brief` directory beneath the ignored
`artifacts/` tree at semantic/lhc_cosmic_ray_argument, including a generated
map, quality report, briefing directory, summary, and final review packet. The five
LHC source documents total roughly 424 KB and the current
extractor can send whole documents, so the model needs an adequate context
window. Runtime is hardware- and model-dependent and may be several to tens of
minutes.

This live command is syntactically validated but was not executed end to end in
the reorganization environment because Ollama was unavailable. The `prompt`
backend is useful for inspecting some individual prompts, but it does not
produce a usable staged LHC briefing and is not offered here as a substitute.

The official briefing publishes only when readiness, provenance, citation,
source-binding, and retention checks pass. Otherwise the run returns nonzero
and leaves an inspectable non-publication packet. Use
[`../review/REVIEWER_START_HERE.md`](../review/REVIEWER_START_HERE.md) for the
substantive human-review handoff.
