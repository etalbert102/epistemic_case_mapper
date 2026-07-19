# Decision-Grade Memo Obligation Triage Completion Audit

## Scope

This audit records execution of `docs/plans/DECISION_GRADE_MEMO_OBLIGATION_TRIAGE_PLAN.md`.

The implemented architecture is reuse-first:

- Existing model judgments from `global_decision_model`, `analyst_adjudication`, `analyst_decision_model`, and `analyst_quantity_binding_report` are reused to build the memo contract.
- Deterministic code validates schemas, preserves lineage, applies writeability budgets, and reports fallback needs.
- No broad new semantic planner call was added.

## Commits

- `afae57f` - `Reuse model judgments for memo obligations`
- `5cdf749` - `Tighten memo obligation contract`
- `d8aae26` - `Batch analyst quantity binding`
- `ca1d939` - `Harden quantity binding and memo opening`

## Verification

Commands run:

```bash
PYTHONPATH=src python3 -m pytest -q
```

Latest result:

```text
652 passed in 17.76s
```

Focused suites run during implementation:

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_analyst_packet.py tests/test_decision_writer_packet.py tests/test_maintainability_gate.py -q
```

## Implemented Plan Items

### Reuse-First Obligation Plan

Implemented in:

- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_decision_writer_packet.py`
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_decision_writer_contract.py`

Artifacts now emitted:

- `decision_obligation_plan.json`
- `decision_obligation_plan_report.json`
- `decision_memo_contract.json`
- `decision_contract_source_judgment_lineage.json`

Result on saved eggs artifacts:

- Required obligations dropped from `19` to `11`.
- Obligation levels became `must_include=11`, `should_include=8`, `optional_context=13`.

### Quantity Binding Hardening

Implemented in:

- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_analyst_quantity_binding.py`

Changes:

- Quantity binding is batched at 8 candidates per call.
- Empty bindings are invalid when candidates were supplied.
- Missing model rows become `context_only` instead of deterministic `yes`.
- Model-selected mandatory quantities are capped by a writeability budget.

Live replay on eggs:

- `163` quantity candidates.
- Batched calls produced `32` model-approved quantities.
- Mandatory quantity budget reduced these to `12`.

### Writeability Telemetry

Implemented in:

- `writer_packet_writeability_report.json`
- `writer_packet_fallback_requests.json`

Telemetry reports:

- mandatory obligation count
- mandatory quantity count
- fallback recommendations
- reused judgment artifacts
- synthesis strategy recommendation

The current gate remains report-only, consistent with the plan.

### Clean Writing Interface

Implemented in:

- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_memo_ready_prompt.py`

The model now receives a clean source-bound writing interface for the active decision-writer path instead of raw packet internals. The prompt asks for:

- a direct bounded answer in the opening
- visible confidence and uncertainty when supplied
- source-bound evidence use
- quantities only from selected packet quantities or required obligations

### Final Synthesis And Repair

Existing strict synthesis and repair stages now operate against the reuse-first memo contract.

Live eggs run:

- Path: `artifacts/semantic/eggs_reuse_first_contract_e2e_20260711/`
- Active packet: `decision_writer_active`
- Memo-ready synthesis: `accepted`
- Missing mandatory obligations: `0`
- Memo-ready repair: `not_needed`
- Final polish: `accepted`
- Final readiness: `decision_ready_with_warnings`

Replay with budgeted quantity binding and updated opening prompt:

- Path: `artifacts/semantic/eggs_reuse_first_contract_e2e_20260711/briefing/memo_ready_synthesis_budgeted_replay/`
- Synthesis: `accepted`
- Missing mandatory obligations: `0`
- Required obligations: `11`
- Packet quantities available to the writer: `30`

## Before/After

Baseline saved eggs run:

- Path: `artifacts/semantic/eggs_real_contract_e2e_20260711/`
- Required obligations: `19`
- Item quantities: `183`
- Final missing mandatory obligations after repair: `7`
- Final readiness: `not_decision_ready`

Current reuse-first live/replay result:

- Required obligations: `11`
- Item quantities after budgeted replay: `30`
- Missing mandatory obligations: `0`
- Repair needed: no
- Final readiness: `decision_ready_with_warnings`

## Non-Egg Generalization Check

Saved COVID artifact check:

- Path: `artifacts/decision_model_live_quality/covid_recovery_actual_20260711/reuse_first_contract_eval.json`
- Decision question: `How should a narrow slice of COVID origins evidence be represented without flattening Bayesian disagreement?`
- Required obligations: `11`
- Obligation levels: `must_include=11`, `should_include=9`, `optional_context=8`
- Item quantities: `5`
- Quantity obligations: `3`
- Reused artifacts: `global_decision_model`, `analyst_adjudication`, `analyst_decision_model`, `analyst_quantity_binding_report`

This supports the generalization claim that the adapter uses artifact roles rather than egg-specific concepts.

## Remaining Warnings

The writeability report still emits `fallback_adjudication_recommended` on eggs and COVID.

Current interpretation:

- This is useful telemetry, not a blocking failure.
- The run can produce an accepted memo without executing a new fallback model call.
- The fallback call should remain report-only until calibrated across more runs.

Known residual quality issue:

- The memo can still choose a debatable answer frame if the global decision model selected a weak bounded answer.
- This is upstream of retention mechanics and should be addressed in global decision-model answer formation, not by deterministic memo repair.

## Completion Status

Implemented and verified:

- Reuse-first obligation planning.
- Tightened quantity binding.
- Writeability telemetry.
- Clean synthesis contract.
- Strict validation against selected obligations.
- Live eggs end-to-end verification.
- Non-eggs saved-artifact generalization check.
- Full test suite and maintainability gate.

Deferred by design:

- Executing fallback adjudication calls as blocking repairs. The current implementation emits fallback requests and keeps them report-only until their predictive value is calibrated.
