# Current State

Purpose: keep a brutally honest ledger of what the prototype does today, what is partial, and what remains planned.

Last updated: 2026-06-27.

## Implemented

- Source-grounded manifests exist for `lhc_black_holes`, `eggs`, and `covid_origins_slice`.
- Local source text and inventories exist for the two main cases, with local source notes for the COVID slice.
- The deterministic starter mapper emits `case_map.json`, `report.md`, and `audit.md`.
- Claims include source IDs, normalized source spans, source-text hashes, excerpt hashes, extraction method, provenance tag, review state, and entailment flag.
- Generated case maps include preservation metadata from case-specific metadata files.
- Generated case maps include workflow telemetry for extraction, relation mapping, and open-question mapping.
- `scripts/validate_case_artifact.py` checks schema, source metadata, claim traceability, preservation metadata, workflow telemetry, determinism, and example snapshot parity.
- `scripts/validate_worked_regions.py` validates the filled LHC, eggs, and COVID worked-region definitions, maps, flat baselines, erosion audits, best-region pointers, and judge-facing docs.
- `scripts/validate_worked_regions.py --region ...` supports validating one worked region at a time for phased goal runs.
- Consolidated human-review guidance exists in `docs/HUMAN_AUDIT_GUIDE.md`.
- Internal goal prompts and planning notes are archived under `docs/archive/internal/`.
- Source excerpt packets exist in `docs/worked_regions/lhc_source_excerpt_packet.md` and `docs/worked_regions/eggs_source_excerpt_packet.md`.
- A mini filled format example exists in `docs/worked_regions/mini_filled_example.md`.
- Validator repair guidance exists in `docs/VALIDATOR_FAILURE_GUIDE.md`.
- Filled curated LHC, eggs, and narrow COVID worked-region maps exist under `examples/`.
- Filled controlled flat-synthesis baselines exist for the canonical worked regions.
- Reproducible blinded local-model baseline generation exists in `scripts/run_blinded_baselines.py`.
- Checked-in blinded Gemma4 flat-synthesis baselines can be validated with `scripts/validate_blinded_baselines.py`.
- Agent-authored blinded-baseline survival audit exists in `docs/review/BLINDED_BASELINE_AUDIT.md`.
- Checked-in Qwen3, Phi4, and Granite blinded baselines exist for the LHC and eggs worked regions.
- A multi-model blinded-baseline audit exists in `docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md`.
- A one-command judge demo exists in `scripts/run_flf_demo.py`.
- A compact before/after comparison exists in `docs/FLF_BEFORE_AFTER_COMPARISON.md`.
- Case-specific human audit packets exist for LHC, eggs, and the COVID slice.
- A reviewer-first handoff page and self-contained Tier 1 checklist exist:
  - `docs/review/REVIEWER_START_HERE.md`
  - `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv`
- A polished judge-first start page exists at `docs/START_HERE.md`, with the fuller submission packet at `docs/SUBMISSION_PACKET.md`.
- The full seven-dimension FLF judging rubric is recorded as background reference at `docs/reference/flf_judging_rubric.md`; first-read docs use evidence-first framing rather than a direct criteria map.
- A reference-lineage note maps contest-provided examples of epistemic scrutiny to the prototype's design choices at `docs/REFERENCE_LINEAGE.md`.
- A generalizability red-team note names transfer limits, failure boundaries, fresh-case test criteria, and a second-operator validation path at `docs/GENERALIZABILITY_RED_TEAM.md`.
- An unseen-case quality test plan and `ecm quality init/check/gate` workflow exist at `docs/UNSEEN_CASE_QUALITY_TEST_PLAN.md`.
- Source provenance metadata, relation ontology validation, generated quality warnings, and generated risk tasks are tracked in `docs/QUALITY_RISK_GATE_IMPROVEMENT_PLAN.md`.
- A code generalizability implementation plan is saved at `docs/CODE_GENERALIZABILITY_PLAN.md`.
- A reusable-engine plan is recorded at `docs/REUSABLE_ENGINE_PLAN.md`.
- Reusable-engine architecture and manifest docs are recorded at `docs/ENGINE_ARCHITECTURE.md` and `docs/PACKAGE_MANIFEST_SPEC.md`.
- `submission_manifest.yaml` is the source of truth for worked regions, full-case scaffolds, UI inclusion, review priorities, validation thresholds, and blinded baseline spans.
- `scripts/validate_submission_manifest.py` checks manifest wiring, paths, source membership, review target IDs, and blinded-baseline span bounds.
- `tests/test_submission_manifest_generalization.py` builds a temporary synthetic case with a custom ID prefix and runs the manifest, worked-region, and reference validators against it.
- A contributor guide for adding cases exists at `docs/ADDING_A_CASE.md`.
- A compact architecture diagram exists in `docs/ARCHITECTURE.md`.
- A combined evidence ledger, failure-mode analysis, and risk register exists in `docs/EVIDENCE_AND_LIMITATIONS.md`.
- Broad full-case knowledge scaffolds exist for LHC and eggs:
  - `examples/lhc_black_holes/full_case_index.md`
  - `examples/lhc_black_holes/full_case_map.md`
  - `examples/eggs/full_case_index.md`
  - `examples/eggs/full_case_map.md`
- `scripts/validate_full_case_knowledge.py` requires every manifest source to appear in the full-case index and map.
- Operational realism guidance exists:
  - `docs/OPERATIONAL_WORKFLOW_AND_REALISM.md`
  - `examples/lhc_black_holes/investigator_task_queue.md`
  - `examples/eggs/investigator_task_queue.md`
- `scripts/validate_realism_artifacts.py` checks playbook, realism audit, and task queue structure.
- A static inspection UI exists under `ui/`, generated from checked-in artifacts.
- `scripts/build_ui_data.py` generates `ui/data.json`.
- `scripts/validate_ui.py` checks UI files and artifact references.
- Structured worked-region JSON exports exist for the curated maps.
- `scripts/validate_submission_references.py` checks judge-facing file, claim, relation, and loss references.
- `scripts/validate_update_demo.py` checks the new-source update demo's source IDs, spans, target claims, and relation labels.
- `scripts/judge_smoke_test.py` validates and prints the ten-minute judge path.
- `scripts/summarize_submission_artifacts.py` generates `docs/SUBMISSION_ARTIFACT_SUMMARY.md`.
- Filled decision-space erosion audits compare each baseline to its frozen map.
- Judge walkthrough and submission draft point to completed worked-region artifacts.
- Full-case flat synthesis baselines exist for LHC and eggs as illustrative, non-blinded whole-case comparison surfaces.
- Evidence, failure modes, and limitations are consolidated in `docs/EVIDENCE_AND_LIMITATIONS.md`.
- A new-to-map source update demonstration exists in `docs/NEW_SOURCE_UPDATE_DEMO.md`.
- The compact worked judge example and fuller auditor walkthrough are consolidated in `docs/HUMAN_AUDIT_GUIDE.md`.
- A draft public-risk/governance worked region exists at `examples/lhc_black_holes/worked_region_public_risk_framing_map.md`.

## Partially Implemented

- The starter mapper produces heuristic candidate claims, not a final curated case map.
- Relations are deterministic shared-tag seed links, not audited source-grounded argument relations.
- Starter open questions can be supplied through case manifest templates; the fallback questions remain heuristic.
- Reports are navigable but still too large because they include many heuristic claims.
- Preservation metadata is incorporated, but not yet used to guide relation extraction automatically.
- Human-review workflow is specified, but no human-reviewed decisions have been recorded.
- Worked-region maps are source-grounded and validated, but they remain `human-review-needed`.
- The public-risk/governance worked region is useful as a draft extension, but it is not yet promoted into the canonical validated worked-region set.
- Full-case flat baselines are illustrative and were not generated in a clean blinded context.

## Not Yet Implemented

- Full regulatory case study.
- Interactive reviewer/editor UI with persisted decisions.
- Human-reviewed status for any artifact.

## Current Evidence Boundary

The prototype currently demonstrates artifact shape, source grounding, provenance discipline, auditability scaffolding, and worked-region comparisons where curated maps preserve structure that flat synthesis weakens. The original baselines are illustrative because they were produced in the same Codex run as the maps. The repository now also includes reproducible local blinded-baseline paths that prompt only from selected source spans and do not expose the curated maps or erosion audits. Multi-model baselines show that flat synthesis preservation is model-dependent: some models preserve more detail, but none make the decision-relevant structure as reviewable as the maps. Broad full-case scaffolds now cover every acquired LHC and eggs source, with the curated worked regions retained as deeper anchors. The COVID artifact is a narrow adversarial stress test for Bayesian disagreement and scope preservation, not a full COVID origins map or adjudication.

## Validation Commands

```bash
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 scripts/run_flf_demo.py
PYTHONPATH=src python3 scripts/run_flf_demo.py --skip-build
PYTHONPATH=src python3 scripts/judge_smoke_test.py
PYTHONPATH=src python3 scripts/validate_submission_manifest.py
PYTHONPATH=src python3 scripts/validate_submission_references.py
PYTHONPATH=src python3 scripts/validate_full_case_knowledge.py
PYTHONPATH=src python3 scripts/validate_realism_artifacts.py
PYTHONPATH=src python3 scripts/build_ui_data.py --check
PYTHONPATH=src python3 scripts/validate_ui.py
PYTHONPATH=src python3 scripts/export_worked_region_json.py --check
PYTHONPATH=src python3 scripts/summarize_submission_artifacts.py --check
PYTHONPATH=src python3 scripts/build_tier1_review_checklist.py --check
PYTHONPATH=src python3 scripts/validate_update_demo.py
PYTHONPATH=src python3 scripts/build_case_map.py --case data/cases/lhc_black_holes/case.yaml
PYTHONPATH=src python3 scripts/build_case_map.py --case data/cases/eggs/case.yaml
PYTHONPATH=src python3 scripts/validate_case_artifact.py --case data/cases/lhc_black_holes/case.yaml --examples examples/lhc_black_holes
PYTHONPATH=src python3 scripts/validate_case_artifact.py --case data/cases/eggs/case.yaml --examples examples/eggs
PYTHONPATH=src python3 scripts/validate_worked_regions.py
PYTHONPATH=src python3 scripts/validate_worked_regions.py --region lhc_cosmic_ray_argument
PYTHONPATH=src python3 scripts/validate_worked_regions.py --region eggs_observational_vs_rct
PYTHONPATH=src python3 scripts/validate_worked_regions.py --region covid_bayesian_disagreement
PYTHONPATH=src python3 scripts/run_blinded_baselines.py --model gemma4:e4b --case all
PYTHONPATH=src python3 scripts/validate_blinded_baselines.py
PYTHONPATH=src python3 scripts/reproducibility_gate.py --include-worked-regions
PYTHONPATH=src python3 scripts/reproducibility_gate.py --include-worked-regions --include-blinded-baselines
```
