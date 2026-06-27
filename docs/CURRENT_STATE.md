# Current State

Purpose: keep a brutally honest ledger of what the prototype does today, what is partial, and what remains planned.

Last updated: 2026-06-26.

## Implemented

- Source-grounded manifests exist for `lhc_black_holes` and `eggs`.
- Local source text and inventories exist for both main cases.
- The deterministic starter mapper emits `case_map.json`, `report.md`, and `audit.md`.
- Claims include source IDs, normalized source spans, source-text hashes, excerpt hashes, extraction method, provenance tag, review state, and entailment flag.
- Generated case maps include preservation metadata from case-specific metadata files.
- Generated case maps include workflow telemetry for extraction, relation mapping, and open-question mapping.
- `scripts/validate_case_artifact.py` checks schema, source metadata, claim traceability, preservation metadata, workflow telemetry, determinism, and example snapshot parity.
- `scripts/validate_worked_regions.py` exists and intentionally fails until worked-region templates are filled with final curated content.
- Human-review rubric exists in `docs/review/HUMAN_REVIEW_RUBRIC.md`.
- Workspace enhancement backlog exists in `docs/plans/flf_workspace_enhancement_backlog.md`.

## Partially Implemented

- The starter mapper produces heuristic candidate claims, not a final curated case map.
- Relations are deterministic shared-tag seed links, not audited source-grounded argument relations.
- Open questions are useful but hand-coded by case.
- Reports are navigable but still too large because they include many heuristic claims.
- Preservation metadata is incorporated, but not yet used to guide relation extraction automatically.
- Human-review workflow is specified, but no human-reviewed decisions have been recorded.
- Worked-region templates exist for LHC and eggs, but they are not yet filled.

## Not Yet Implemented

- Filled curated LHC and eggs worked-region maps.
- Filled controlled flat-synthesis baselines.
- Filled decision-space erosion audits comparing baselines to frozen maps.
- Final judge walkthrough over completed worked-region artifacts.
- Full regulatory case study.
- UI or interactive navigator.
- Human-reviewed status for any artifact.

## Current Evidence Boundary

The prototype currently demonstrates artifact shape, source grounding, provenance discipline, and auditability scaffolding. It does not yet demonstrate that the final workflow outperforms flat synthesis on the FLF cases. That requires the worked-region plan to be executed.

## Validation Commands

```bash
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 scripts/build_case_map.py --case data/cases/lhc_black_holes/case.yaml
PYTHONPATH=src python3 scripts/build_case_map.py --case data/cases/eggs/case.yaml
PYTHONPATH=src python3 scripts/validate_case_artifact.py --case data/cases/lhc_black_holes/case.yaml --examples examples/lhc_black_holes
PYTHONPATH=src python3 scripts/validate_case_artifact.py --case data/cases/eggs/case.yaml --examples examples/eggs
PYTHONPATH=src python3 scripts/reproducibility_gate.py
```

Final worked-region validation is expected to fail until templates are filled:

```bash
PYTHONPATH=src python3 scripts/validate_worked_regions.py
PYTHONPATH=src python3 scripts/reproducibility_gate.py --include-worked-regions
```
