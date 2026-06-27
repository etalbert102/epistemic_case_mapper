# AGENTS.md

Instructions for Codex and other coding agents working in this repo.

## Mission

This repo builds a lightweight FLF competition prototype for AI-assisted epistemic case mapping. The prototype should preserve decision-relevant structure: sources, claims, relations, cruxes, caveats, uncertainty, missing evidence, and audit status.

Do not optimize for fluent summaries at the expense of provenance or disagreement structure.

## Repo Layout

- `data/cases/*/case.yaml`: case manifests and seed/source material.
- `src/epistemic_case_mapper/`: package code and schema.
- `scripts/`: runnable CLI tools.
- `docs/`: workflow, criteria, plans, and protocols.
- `examples/`: checked-in judge-facing snapshots.
- `artifacts/`: generated local outputs; gitignored.
- `tests/`: pytest coverage.

## Required Reading Before Substantial Edits

Before a multi-file change or Codex `/goal` run, read:

- `README.md`
- `docs/WORKFLOW_SPEC.md`
- `docs/protocols/epistemic_case_map_v0.md`
- `docs/CODEX_GOAL_FLF_PROTOTYPE_CRITERIA.md`
- the relevant `docs/plans/*.md`
- the relevant `data/cases/*/case.yaml`

Record at least one concrete implication from each required input in the active plan before broad implementation edits.

## Evidence Rules

There are two evidence modes:

- `seed`: uses local seed notes; useful for workflow scaffolding only.
- `source_grounded`: uses recorded source material with URLs or local paths, retrieval dates for web sources, and source-local excerpts or span markers.

Never present seed-mode output as a final source-grounded FLF demo.

Do not invent source claims. If source evidence is missing, record a gap in the audit or open questions.

Use web search only when the active plan explicitly authorizes source acquisition. When web use is authorized, record URL, access date, source type, relevance, and enough local excerpt or notes for audit.

## Artifact Policy

Generated working artifacts go under `artifacts/` and are ignored by git.

Curated judge-facing snapshots go under `examples/<case_id>/` and must be checked in:

- `case_map.json`
- `report.md`
- `audit.md`
- `README.md`

Snapshots must be reproducible by documented commands and validated against regenerated artifacts.

## Agent Work Roles

Use explicit roles during substantial prototype work:

- `developer`: changes code, schemas, docs, or artifacts.
- `verifier`: runs tests, validators, reproducibility gates, and checks generated artifacts against source manifests.
- `reviewer`: inspects source fidelity, relation correctness, erosion findings, and human-review packet completeness.
- `process-cleanup`: updates plans, current-state notes, and backlog status after repeated failures or completed work.

One agent or session may perform multiple roles, but the final report must say which verification was actually performed. Do not let a developer pass substitute for human review.

## Commands

Set up:

```bash
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
```

Test:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
```

Build a case map:

```bash
PYTHONPATH=src ./.venv/bin/python scripts/build_case_map.py --case data/cases/lhc_black_holes/case.yaml
```

Validate a curated example after it exists:

```bash
PYTHONPATH=src ./.venv/bin/python scripts/validate_case_artifact.py --case data/cases/lhc_black_holes/case.yaml --examples examples/lhc_black_holes
```

Run the FLF reproducibility gate:

```bash
PYTHONPATH=src ./.venv/bin/python scripts/reproducibility_gate.py
```

## Done Standard

A change is not done until:

- relevant tests pass,
- generated artifacts are reproducible,
- validation passes when examples are touched,
- residual risks and deferred work are recorded in the relevant plan,
- review status does not overclaim human review.

## Stop Rules

Stop and report rather than continuing if:

- source evidence is insufficient and web use is not authorized,
- a source-grounded claim would require invention,
- validation cannot be made deterministic,
- a schema redesign is needed outside the active plan,
- tests fail and the failure is not local to the current slice,
- work would spill into another case before the current one satisfies its done checklist.
