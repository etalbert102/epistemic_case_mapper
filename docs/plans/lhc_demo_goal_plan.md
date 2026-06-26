# LHC Demo Goal Plan

This is the living plan for the first Codex `/goal` run. Keep it updated while work proceeds.

Use with:

```text
/goal Execute docs/plans/lhc_demo_goal_plan.md. Keep that plan updated as the living source of truth. Stop only when its done checklist and docs/CODEX_GOAL_FLF_PROTOTYPE_CRITERIA.md both pass, or when a stop rule requires reporting a blocker.
```

## Goal

Produce a judge-facing LHC black hole risk workflow scaffold that can be regenerated from the repo and inspected without relying on chat history.

This initial run is seed mode. It may demonstrate the workflow and artifact shape, but it must not be described as a final source-grounded FLF demo unless source acquisition is explicitly authorized and completed.

## Non-Goals

- Do not attempt the COVID origins case.
- Do not build a product UI.
- Do not claim source-grounded status while using only seed notes.
- Do not add unrelated refactors.
- Do not mark the output human-reviewed.

## Evidence Mode

Initial target: seed mode.

Upgrade target: source-grounded mode only after real LHC source material is added to `data/cases/lhc_black_holes/case.yaml` or local source files.

Web use: not allowed for this initial plan unless the user explicitly authorizes source acquisition.

## Required Reading

Record at least one implication from each input before editing implementation files.

- [ ] `README.md`
- [ ] `docs/WORKFLOW_SPEC.md`
- [ ] `docs/protocols/epistemic_case_map_v0.md`
- [ ] `docs/CODEX_GOAL_FLF_PROTOTYPE_CRITERIA.md`
- [ ] `docs/reference/flf_epistemic_case_study_competition_criteria.md`
- [ ] `docs/reference/codex_goal_ability_research.md`
- [ ] `data/cases/lhc_black_holes/case.yaml`
- [ ] `src/epistemic_case_mapper/schema.py`
- [ ] `src/epistemic_case_mapper/starter_mapper.py`
- [ ] `scripts/build_case_map.py`
- [ ] `tests/`

## Reading Notes

Fill in one concrete implication from each required input before editing implementation files.

- `README.md`:
- `docs/WORKFLOW_SPEC.md`:
- `docs/protocols/epistemic_case_map_v0.md`:
- `docs/CODEX_GOAL_FLF_PROTOTYPE_CRITERIA.md`:
- `docs/reference/flf_epistemic_case_study_competition_criteria.md`:
- `docs/reference/codex_goal_ability_research.md`:
- `data/cases/lhc_black_holes/case.yaml`:
- `src/epistemic_case_mapper/schema.py`:
- `src/epistemic_case_mapper/starter_mapper.py`:
- `scripts/build_case_map.py`:
- `tests/`:

## Current Inventory

Fill this in during the goal run.

- Current source manifest:
- Current mapper behavior:
- Current report behavior:
- Current tests:
- Current artifact policy:

## Bounded Slices

### Slice 1: Artifact Policy And Audit Output

Expected result:

- `scripts/build_case_map.py` produces `audit.md` in addition to JSON and report outputs.
- `examples/lhc_black_holes/` contains checked-in snapshots when the demo is ready.

Verification:

```bash
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python scripts/build_case_map.py --case data/cases/lhc_black_holes/case.yaml
```

### Slice 2: Seed-Mode Labeling

Expected result:

- Seed-derived claims are visibly low-confidence and audit-labeled.
- The report and audit do not present seed notes as final evidence.

Verification:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
```

### Slice 3: Case-Specific Assessment

Expected result:

- The LHC output has at least three case-specific open questions.
- Each open question links to claim/source IDs or an explicit missing-source gap.
- Crux/dependency candidates are tentative unless source-grounded.

Verification:

```bash
PYTHONPATH=src ./.venv/bin/python scripts/build_case_map.py --case data/cases/lhc_black_holes/case.yaml
```

### Slice 4: Example Snapshot

Expected result:

- `examples/lhc_black_holes/case_map.json`
- `examples/lhc_black_holes/report.md`
- `examples/lhc_black_holes/audit.md`
- `examples/lhc_black_holes/README.md`

Verification:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python scripts/build_case_map.py --case data/cases/lhc_black_holes/case.yaml
```

### Slice 5: Validation Command

Expected result:

- A validation command checks schema validity, required minimum counts, required fields, evidence mode, review status, deterministic ID stability across two builds, and parity between regenerated artifacts and `examples/lhc_black_holes/`.
- If parity differs by design, the validator reports exact expected differences and their reason.

Required command shape:

```bash
PYTHONPATH=src ./.venv/bin/python scripts/validate_case_artifact.py --case data/cases/lhc_black_holes/case.yaml --examples examples/lhc_black_holes
```

Verification:

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python scripts/build_case_map.py --case data/cases/lhc_black_holes/case.yaml
PYTHONPATH=src ./.venv/bin/python scripts/validate_case_artifact.py --case data/cases/lhc_black_holes/case.yaml --examples examples/lhc_black_holes
```

## Progress

- [ ] Plan created.

## Decisions

- Decision: Generated artifacts stay under ignored `artifacts/`; curated judge-facing snapshots are checked in under `examples/`.
  Rationale: This keeps routine local output out of git while giving reviewers stable artifacts.
  Date/Author: 2026-06-26 / Codex

## Surprises And Discoveries

Record unexpected implementation or evidence issues here.

## Verification Log

Record exact commands, timestamps, and outcomes here.

## Residual Risks

- Seed-mode output is useful as a workflow scaffold but not sufficient as final source-grounded FLF evidence.

## Deferred Work

Use this format:

- Owner:
  Reason:
  Risk:
  Next action:

## Done Checklist

- [ ] Required reading is complete and implications are recorded.
- [ ] `artifacts/lhc_black_holes/case_map.json` is generated.
- [ ] `artifacts/lhc_black_holes/report.md` is generated.
- [ ] `artifacts/lhc_black_holes/audit.md` is generated.
- [ ] Curated snapshots exist under `examples/lhc_black_holes/`.
- [ ] JSON validates against the Pydantic schema.
- [ ] Report is navigable without reading raw JSON first.
- [ ] Audit maps the output to FLF ingestion, structure, assessment, and compounding criteria.
- [ ] Seed-mode limitations are explicit.
- [ ] At least three case-specific open questions are present.
- [ ] Validation command checks completeness, stable IDs, and snapshot parity.
- [ ] Tests pass.
- [ ] Residual risks and deferred work are recorded.
- [ ] Review status is no stronger than `agent-reviewed` or `human-review-needed`.
