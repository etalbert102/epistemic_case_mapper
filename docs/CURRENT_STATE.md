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
- Reproducible blinded local-model baseline generation exists in `scripts/run_blinded_baselines.py`.
- Checked-in blinded Gemma4 flat-synthesis baselines can be validated with `scripts/validate_blinded_baselines.py`.
- Agent-authored blinded-baseline survival audit exists in `docs/review/BLINDED_BASELINE_AUDIT.md`.
- Checked-in Qwen3, Phi4, and Granite blinded baselines exist for both worked regions.
- A multi-model blinded-baseline audit exists in `docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md`.
- A one-command judge demo exists in `scripts/run_flf_demo.py`.
- A compact before/after comparison exists in `docs/FLF_BEFORE_AFTER_COMPARISON.md`.
- Case-specific human audit packets exist for LHC and eggs.
- A single judge-facing submission packet exists in `docs/SUBMISSION_PACKET.md`.
- A compact architecture diagram exists in `docs/ARCHITECTURE.md`.
- A limitations and risk register exists in `docs/SUBMISSION_LIMITATIONS.md`.
- Broad full-case knowledge scaffolds exist for LHC and eggs:
  - `examples/lhc_black_holes/full_case_index.md`
  - `examples/lhc_black_holes/full_case_map.md`
  - `examples/eggs/full_case_index.md`
  - `examples/eggs/full_case_map.md`
- `scripts/validate_full_case_knowledge.py` requires every manifest source to appear in the full-case index and map.
- Operational realism artifacts exist:
  - `docs/INVESTIGATOR_WORKFLOW_PLAYBOOK.md`
  - `docs/OPERATIONAL_REALISM_AUDIT.md`
  - `examples/lhc_black_holes/investigator_task_queue.md`
  - `examples/eggs/investigator_task_queue.md`
- `scripts/validate_realism_artifacts.py` checks playbook, realism audit, and task queue structure.
- Structured worked-region JSON exports exist for both curated maps.
- `scripts/validate_submission_references.py` checks judge-facing file, claim, relation, and loss references.
- `scripts/judge_smoke_test.py` validates and prints the ten-minute judge path.
- `scripts/summarize_submission_artifacts.py` generates `docs/SUBMISSION_ARTIFACT_SUMMARY.md`.
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

The prototype currently demonstrates artifact shape, source grounding, provenance discipline, auditability scaffolding, and two worked-region comparisons where curated maps preserve structure that flat synthesis weakens. The original baselines are illustrative because they were produced in the same Codex run as the maps. The repository now also includes reproducible local blinded-baseline paths that prompt only from selected source spans and do not expose the curated maps or erosion audits. Multi-model baselines show that flat synthesis preservation is model-dependent: some models preserve more detail, but none make the decision-relevant structure as reviewable as the maps. Broad full-case scaffolds now cover every acquired LHC and eggs source, with the curated worked regions retained as deeper anchors.

## Validation Commands

```bash
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 scripts/run_flf_demo.py
PYTHONPATH=src python3 scripts/run_flf_demo.py --skip-build
PYTHONPATH=src python3 scripts/judge_smoke_test.py
PYTHONPATH=src python3 scripts/validate_submission_references.py
PYTHONPATH=src python3 scripts/validate_full_case_knowledge.py
PYTHONPATH=src python3 scripts/validate_realism_artifacts.py
PYTHONPATH=src python3 scripts/export_worked_region_json.py --check
PYTHONPATH=src python3 scripts/summarize_submission_artifacts.py --check
PYTHONPATH=src python3 scripts/build_case_map.py --case data/cases/lhc_black_holes/case.yaml
PYTHONPATH=src python3 scripts/build_case_map.py --case data/cases/eggs/case.yaml
PYTHONPATH=src python3 scripts/validate_case_artifact.py --case data/cases/lhc_black_holes/case.yaml --examples examples/lhc_black_holes
PYTHONPATH=src python3 scripts/validate_case_artifact.py --case data/cases/eggs/case.yaml --examples examples/eggs
PYTHONPATH=src python3 scripts/validate_worked_regions.py
PYTHONPATH=src python3 scripts/validate_worked_regions.py --region lhc_cosmic_ray_argument
PYTHONPATH=src python3 scripts/validate_worked_regions.py --region eggs_observational_vs_rct
PYTHONPATH=src python3 scripts/run_blinded_baselines.py --model gemma4:e4b --case all
PYTHONPATH=src python3 scripts/validate_blinded_baselines.py
PYTHONPATH=src python3 scripts/reproducibility_gate.py --include-worked-regions
PYTHONPATH=src python3 scripts/reproducibility_gate.py --include-worked-regions --include-blinded-baselines
```
