# Decision-Grade Memo Pipeline Recovery Completion Audit

## Scope

This audit records execution of `docs/plans/DECISION_GRADE_MEMO_PIPELINE_RECOVERY_PLAN.md`.

The implemented milestone is the report-only recovery path: source evidence units, non-destructive routing, side-by-side global decision ownership, a global-model writer packet, and semantic memo acceptance reporting.

## Commits

- `38f96c7 Add source evidence unit substrate`
- `e6dfc11 Add report-only evidence unit routing`
- `e882c08 Add side-by-side global decision model`
- `1355413 Add global decision writer packet`
- `c839738 Add memo semantic acceptance report`

Baseline plan commit:

- `7c34a81 Record decision memo recovery plan`

## Changed Files By Slice

### Slice 1: Evidence-Unit Substrate

- `src/epistemic_case_mapper/staged_semantic_evidence_units.py`
- `src/epistemic_case_mapper/staged_semantic_whole_doc.py`
- `src/epistemic_case_mapper/staged_semantic_whole_doc_pipeline.py`
- `tests/test_source_evidence_units.py`

### Slice 2: Relevance And Routing

- `src/epistemic_case_mapper/staged_semantic_evidence_routing.py`
- `src/epistemic_case_mapper/staged_semantic_whole_doc_pipeline.py`
- `tests/test_evidence_unit_routing.py`

### Slice 3: Global Decision Model Side-By-Side

- `src/epistemic_case_mapper/map_briefing_global_decision_model.py`
- `src/epistemic_case_mapper/map_briefing_decision_packet_stage.py`
- `src/epistemic_case_mapper/map_briefing_artifacts.py`
- `tests/test_global_decision_model.py`

### Slice 4: Writer Packet Projection

- `src/epistemic_case_mapper/map_briefing_decision_writer_packet.py`
- `src/epistemic_case_mapper/map_briefing_decision_packet_stage.py`
- `src/epistemic_case_mapper/map_briefing_artifacts.py`
- `tests/test_decision_writer_packet.py`

### Slice 5: Semantic Memo Acceptance

- `src/epistemic_case_mapper/map_briefing_readiness.py`
- `src/epistemic_case_mapper/map_briefing_final_outputs.py`
- `tests/test_map_briefing_readiness.py`

## Verification

Full-suite verification after each main code slice:

- Slice 1: `PYTHONPATH=src python3 -m pytest -q` -> `632 passed`
- Slice 2: `PYTHONPATH=src python3 -m pytest -q` -> `634 passed`
- Slice 3: `PYTHONPATH=src python3 -m pytest -q` -> `637 passed`
- Slice 4: `PYTHONPATH=src python3 -m pytest -q` -> `640 passed`
- Slice 5: `PYTHONPATH=src python3 -m pytest -q` -> `642 passed`

Prompt-backend end-to-end smoke runs:

- Eggs: `artifacts/test_runs/plan_recovery_eggs_prompt/`
- Non-eggs: `artifacts/test_runs/plan_recovery_covid_prompt/`

Both smoke runs emitted:

- `global_decision_model.json`
- `global_decision_model_report.json`
- `global_decision_model_reconciliation_report.json`
- `global_decision_model_failure_accounting.json`
- `decision_writer_packet.json`
- `decision_writer_packet_quality_report.json`
- `evidence_unit_traceability_matrix.json`
- `memo_semantic_acceptance_report.json`

## Latest Smoke-Run Quality Signals

### Eggs Prompt Smoke

- `global_decision_model_report.json`: `ready_with_warnings`
- `decision_writer_packet_quality_report.json`: `warning`
- `memo_quality_report.json`: `polished`
- `final_decision_readiness_report.json`: `not_decision_ready`
- `memo_semantic_acceptance_report.json`: `not_accepted`

The new acceptance report correctly surfaces the prior failure mode: polish can be high while decision readiness fails.

### COVID Prompt Smoke

- `global_decision_model_report.json`: `ready_with_warnings`
- `decision_writer_packet_quality_report.json`: `warning`
- `memo_quality_report.json`: `polished`
- `final_decision_readiness_report.json`: `not_decision_ready`
- `memo_semantic_acceptance_report.json`: `not_accepted`

This confirms the same report-only behavior on a non-eggs case.

## Live-Model Comparison Status

The code slices are implemented and verified. The plan's full quality-comparison criterion is not yet satisfied because no fresh live-model eggs and non-eggs memo comparison was run after these changes.

The prompt-backend smoke runs verify wiring and failure visibility, not memo quality. A true completion comparison still needs:

- one live eggs run against the current baseline,
- one live non-eggs run,
- manual memo-quality comparison for retention, quantitative discipline, confidence visibility, and readability.

## Semantic Validation Mode

Semantic memo acceptance is currently report-only.

It writes `memo_semantic_acceptance_report.json` and prevents silent disagreement between polish and decision readiness, but it does not yet block artifact generation.

## Deferred Legacy Paths And Deletion Candidates

Deferred until live comparison shows the new path improves output quality:

- legacy memo-ready packet as active synthesis owner,
- older decision-spine answer ownership paths,
- blocking validators calibrated only on prompt-backend smoke runs.

## Remaining Risks

- Prompt-backend smoke runs can produce zero-claim scaffolds, so they are not evidence of live synthesis quality.
- The global decision model is still a projection from the analyst decision model, not yet a mandatory global reconciliation model call.
- The decision writer packet exists side-by-side and is not yet the active synthesis interface.
- Live-model timeout/failure behavior needs rerun after the new failure-accounting artifacts.
