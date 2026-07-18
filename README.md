# Epistemic Case Mapper

Lightweight FLF competition prototype for producing reusable, navigable epistemic case maps with AI assistance.

For judges: start with `docs/START_HERE.md`, then inspect `docs/INVESTIGATOR_CHALLENGE.md` and `docs/RECOVER_REPAIR_UPDATE_DEMO.md`.

For running locally: use `PYTHONPATH=src python3 scripts/run_flf_demo.py --skip-build`.

For reuse on a new question: use the `ecm` CLI path below.

For implementation details: use `docs/SUBMISSION_PACKET.md` and `docs/PIPELINE_DEMONSTRATION_EXAMPLES.md`.

This repo is intentionally separate from `decision_space_harness`.

- `decision_space_harness`: research benchmark, metrics, paper-grade evaluation.
- `epistemic_case_mapper`: judge-facing prototype and workflow for real case studies.

## Goal

Help an investigator preserve operational judgment while AI systems transform evidence into claims, maps, and prose.

The project uses the decision-space writing framework as its organizing logic:

```text
retrieval gate -> claim normalization -> decision-space construction -> judgment anchors -> artifact fidelity -> auditable authority
```

In plain terms: the workflow records what evidence entered, how source material was normalized into claims, which options and dependencies remained visible, which checkpoints preserve human judgment, whether the artifact stayed reviewable, and where a reviewer can intervene.

The core artifacts preserve:

- source provenance
- claims and similar claims
- support/challenge relationships
- cruxes and open questions
- missing perspectives
- uncertainty and audit notes

The immediate failure mode is reasoning-structure loss during evidence transformation. That becomes **decision-space erosion** when a synthesis or workflow makes a decision-relevant option, interpretation, evidence path, caveat, or review boundary materially less visible or recoverable before accountable review.

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

## Use On A New Question

The canonical reusable path is:

```bash
ecm --repo-root /path/to/package case filter-sources \
  --question "What should a careful reader conclude?" \
  --docs doc_a.txt doc_b.md

ecm --repo-root /path/to/package --package package.yaml case init \
  --case-id my_case \
  --title "My Case" \
  --question "What should a careful reader conclude?" \
  --docs doc_a.txt doc_b.md

ecm --repo-root /path/to/package --package package.yaml semantic staged brief \
  --region my_case_initial_region \
  --backend prompt
```

Use `--backend prompt` first to inspect prompts and generated scaffolding without calling a model. Swap in `--backend command:<cmd>` or `--backend ollama:<model>` for a live run.

`case filter-sources` is an optional intake screen. It records deterministic source-readability signals and, with a live backend, model judgments about likely relevance or trust concerns before sources enter the package. It is report-only unless `case init --filter-sources --exclude-filtered-sources` is used.

The staged brief command writes a generated map, a decision briefing, a summary JSON, progress logs, and `FINAL_REVIEW_PACKET.md`. Start with the printed briefing path, then use the final review packet to inspect map quality, traceability, and warnings.

To inspect or resume a run from saved artifacts:

```bash
ecm --repo-root /path/to/package --package package.yaml semantic staged status \
  --region my_case_initial_region

ecm --repo-root /path/to/package --package package.yaml semantic staged resume \
  --region my_case_initial_region \
  --from-stage map \
  --backend ollama:gemma4:26b
```

The resumable handoffs are `documents`, `map`, and `briefing`. More detail: `docs/CASE_INIT_AND_MODEL_BACKENDS.md`.

## Judge Path

Start with `docs/START_HERE.md`. It now opens with the investigator challenge, a compact recover/repair/update packet, and a matched strong-model comparison before sending readers into the full LHC map.

For the shortest judge path, read:

- `docs/INVESTIGATOR_CHALLENGE.md`
- `docs/RECOVER_REPAIR_UPDATE_DEMO.md`
- `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`
- `docs/evaluations/MATCHED_STRONG_MODEL_LHC_COMPARISON.md`

For the full submission boundary, add:

- `docs/SUBMISSION_PACKET.md`
- `docs/DECISION_SPACE_FRAMEWORK_INTEGRATION.md`
- `docs/FLF_BEFORE_AFTER_COMPARISON.md`
- `docs/PIPELINE_DEMONSTRATION_EXAMPLES.md`
- `docs/EVIDENCE_AND_LIMITATIONS.md`
- `docs/GENERALIZABILITY_RED_TEAM.md`

For human audit rather than judge orientation, use:

- `docs/review/REVIEWER_START_HERE.md`
- `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv`

For implementation and reuse details, use:

- `docs/CASE_INIT_AND_MODEL_BACKENDS.md`
- `docs/PACKAGE_MANIFEST_SPEC.md`
- `docs/ADDING_A_CASE.md`
- `docs/ENGINE_ARCHITECTURE.md`

Background contest-reference notes and the recorded judging rubric live under `docs/reference/`.

Full-case scaffold entry points are `examples/lhc_black_holes/full_case_index.md` and `examples/eggs/full_case_index.md`. These are useful after the worked-region value is clear.

To open the UI locally:

```bash
python3 -m http.server 8787
```

Then visit `http://localhost:8787/ui/`.

Reusable structured exports are checked in at:

- `examples/lhc_black_holes/worked_region_cosmic_ray_map.json`
- `examples/eggs/worked_region_observational_vs_rct_map.json`
- `examples/covid_origins_slice/worked_region_bayesian_disagreement_map.json`

To use LLMs as automated red-teamers rather than final judges:

```bash
PYTHONPATH=src python3 scripts/ecm.py eval llm-stress \
  --region lhc_cosmic_ray_argument \
  --backend ollama:gemma4:26b
```

This writes `llm_stress_eval.json`, `LLM_STRESS_EVAL.md`, prompts, raw outputs, reference-check failures, and built-in metamorphic checks under `artifacts/llm_stress_eval/<region>/`.

To add another case or worked region, follow `docs/ADDING_A_CASE.md`; the submission manifest is the source of truth for discovery, validation, export, review-checklist generation, baseline configuration, and UI inclusion.

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
