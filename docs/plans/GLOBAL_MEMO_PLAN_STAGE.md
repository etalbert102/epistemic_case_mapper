# Plan: Global Memo Plan Stage

## Objective

Add a model-authored, deterministically validated global memo plan between map scaffolding and section writing. The plan should manage rhetorical context across the whole brief: one bottom-line narrative, one owner per evidence role, section budgets, cross-reference rules, and compression priorities.

## Current Gap

The pipeline preserves evidence well but does not manage the reader's mental model well. Section rewrites are local, so sections repeat facts, inherit awkward deterministic draft language, and fail to coordinate what each section should own. The most visible failure is that the final memo can be evidence-complete while still sounding mechanical.

## Non-Goals

- Do not add source retrieval.
- Do not hard-code domain-specific memo plans.
- Do not let the model decide factual admissibility.
- Do not remove deterministic validation or appendices.
- Do not make prose fluency override source grounding.

## Design Principles

- Deterministic code owns evidence identity, obligations, validation, artifact writing, and fallback behavior.
- The model owns narrative judgment: bottom-line story, section role, compression, transitions, and omission/cross-reference choices.
- The plan is an intermediate artifact, not hidden prompt text.
- Section packets should consume the approved plan, not reinvent memo architecture.
- Prompt-backend and model-failure paths must still produce a valid deterministic plan.

## Workstreams

1. Global Plan Builder
   - Purpose: generate a compact plan from scaffold artifacts.
   - Changes: add a module that builds a prompt, calls the configured backend, parses JSON, and falls back deterministically.
   - Artifacts: `global_memo_plan.json`, prompt, raw output, validation report.
   - Validation: required sections exist, obligations are assigned once, budgets are bounded, and plan status is visible.

2. Pipeline Integration
   - Purpose: make the plan available before section rewriting.
   - Changes: attach `global_memo_plan` to `scaffold` before scaffold artifacts and final reader outputs are built.
   - Artifacts: summary paths and final review packet include the global plan.
   - Validation: prompt backend works without model calls; live backend stores plan attempt telemetry.

3. Section Packet Consumption
   - Purpose: make section writers follow the global architecture.
   - Changes: include each section's plan in `model_section_packet`, including thesis, target shape, budget, owned obligation IDs, and omit/cross-reference guidance.
   - Validation: tests confirm section packets expose the plan and do not expose unrelated section plans.

4. Quality And Failure Checks
   - Purpose: make failures visible rather than silently producing weak prose.
   - Changes: tests for deterministic fallback, malformed model output, duplicate obligation ownership, and model plan propagation.
   - Validation: `pytest`, maintainability gate, and a representative briefing rerun.

## Acceptance Criteria

- A run writes global memo plan artifacts.
- The scaffold summary includes plan status.
- Section model packets include only the current section's global plan.
- Prompt backend still succeeds.
- Existing gates pass.
- Representative eggs rerun shows plan artifacts and no regression in briefing validation.

## Red-Team Checks

- The model may over-compress and drop obligations; deterministic validation must restore or flag them.
- The model may assign the same evidence to many sections; ownership validation must catch duplicates.
- The model may produce a polished but unsupported story; section validation and evidence anchors remain binding.
- The plan may become case-specific; tests must use generic section names and arbitrary evidence.

## Anti-Half-Done Rule

Do not leave the global plan as a written artifact only. It must be consumed by section packets in the same implementation slice, or the partial integration should be reverted.
