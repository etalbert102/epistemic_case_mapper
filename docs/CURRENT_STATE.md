# Current State

Purpose: keep a brutally honest ledger of what the prototype does today, what is partial, and what remains planned.

Last updated: 2026-06-27.

## Implemented

- Source-grounded manifests exist for `lhc_black_holes` and `eggs`.
- Local source text and inventories exist for both main cases.
- The deterministic starter mapper emits `case_map.json`, `report.md`, and `audit.md`.
- Claims include source IDs, normalized source spans, source-text hashes, excerpt hashes, extraction method, provenance tag, review state, and entailment flag.
- Generated case maps include preservation metadata from case-specific metadata files.
- Generated case maps include workflow telemetry for extraction, relation mapping, and open-question mapping.
- `scripts/validate_case_artifact.py` checks schema, source metadata, claim traceability, preservation metadata, workflow telemetry, determinism, and example snapshot parity.
- `scripts/validate_worked_regions.py` validates the filled LHC and eggs worked-region definitions, maps, flat baselines, erosion audits, best-region pointers, and judge-facing docs.
- `scripts/validate_worked_regions.py --region ...` supports validating one worked region at a time for phased goal runs.
- Human-review rubric exists in `docs/review/HUMAN_REVIEW_RUBRIC.md`.
- Workspace enhancement backlog exists in `docs/plans/flf_workspace_enhancement_backlog.md`.
- A ready-to-use goal prompt exists in `docs/plans/GOAL_PROMPT.md`.
- Source excerpt packets exist in `docs/worked_regions/lhc_source_excerpt_packet.md` and `docs/worked_regions/eggs_source_excerpt_packet.md`.
- A mini filled format example exists in `docs/worked_regions/mini_filled_example.md`.
- Validator repair guidance exists in `docs/VALIDATOR_FAILURE_GUIDE.md`.
- Filled curated LHC and eggs worked-region maps exist under `examples/`.
- Filled controlled flat-synthesis baselines exist for both worked regions.
- Filled decision-space erosion audits compare each baseline to its frozen map.
- Judge walkthrough and submission draft point to completed worked-region artifacts.

## Partially Implemented

- The starter mapper produces heuristic candidate claims, not a final curated case map.
- Relations are deterministic shared-tag seed links, not audited source-grounded argument relations.
- Open questions are useful but hand-coded by case.
- Reports are navigable but still too large because they include many heuristic claims.
- Preservation metadata is incorporated, but not yet used to guide relation extraction automatically.
- Human-review workflow is specified, but no human-reviewed decisions have been recorded.
- Worked-region maps are source-grounded and validated, but they remain `human-review-needed`.

## Not Yet Implemented

- Full regulatory case study.
- UI or interactive navigator.
- Human-reviewed status for any artifact.

## Current Evidence Boundary

The prototype currently demonstrates artifact shape, source grounding, provenance discipline, auditability scaffolding, and two worked-region comparisons where curated maps preserve structure that flat synthesis weakens. These comparisons are illustrative because the baselines were not blinded from the same Codex run's context.

## Validation Commands

```bash
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 scripts/build_case_map.py --case data/cases/lhc_black_holes/case.yaml
PYTHONPATH=src python3 scripts/build_case_map.py --case data/cases/eggs/case.yaml
PYTHONPATH=src python3 scripts/validate_case_artifact.py --case data/cases/lhc_black_holes/case.yaml --examples examples/lhc_black_holes
PYTHONPATH=src python3 scripts/validate_case_artifact.py --case data/cases/eggs/case.yaml --examples examples/eggs
PYTHONPATH=src python3 scripts/validate_worked_regions.py
PYTHONPATH=src python3 scripts/validate_worked_regions.py --region lhc_cosmic_ray_argument
PYTHONPATH=src python3 scripts/validate_worked_regions.py --region eggs_observational_vs_rct
PYTHONPATH=src python3 scripts/reproducibility_gate.py --include-worked-regions
```
