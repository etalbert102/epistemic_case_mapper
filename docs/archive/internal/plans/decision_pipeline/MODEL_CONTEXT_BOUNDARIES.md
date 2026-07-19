# Plan: Model Context Boundaries

## Objective

Make each model call receive only the context needed for its specific job while preserving complete inspectable records for debugging, audit, and future improvement.

The end state is a pipeline with two separate surfaces:

- Model-facing context: compact, task-specific, and free of debug-only or negative evidence leakage.
- Artifact-facing records: complete enough to reconstruct what deterministic code knew, what the model saw, what was withheld, and why validation accepted or rejected outputs.

## Current Gap

The pipeline has already improved section synthesis by introducing compact model packets, but several model calls still risk context pollution:

- Section rewrite prompts include both `model_section_packet` and overlapping validation fields.
- Prohibited repetition rows include anchor terms for evidence the model should not mention, which can prime leakage.
- The legacy whole-briefing prompt is still written as a huge artifact even though section-first synthesis is the active path.
- There is no single model-context audit artifact that records prompt sizes, model-visible keys, debug-only artifacts, and intentional omissions.

## Non-Goals

- Do not remove debug artifacts.
- Do not weaken deterministic validation.
- Do not change source retrieval or source chunking.
- Do not hard-code case-specific prompt rules.
- Do not optimize for smaller prompts by dropping required evidence obligations.

## Design Principles

- Deterministic code owns evidence identity, validation, artifacts, and context boundaries.
- Models receive positive task context, not full debug state.
- Negative constraints should be non-contentful when possible; do not show the model facts it is supposed to avoid.
- Full records belong in artifacts, not in model prompts.
- Any model-context reduction must be testable by inspecting emitted artifacts and prompt strings.

## Inventory And Dependency Map

- Claim extraction: model needs one source-span catalog, decision question, role schema, and compact quality scaffold.
- Relation classification: model needs the candidate pair or small batch, relation ontology, profile rules, and compact quality scaffold.
- Global memo planning: model needs the decision synthesis, argument model, graph summary, obligations, and allowed sections.
- Section rewriting: model needs the section thesis, owned evidence, local tensions/cruxes, quantities, section plan, validation obligations, adjacent headings, and cleaned deterministic draft.
- Reader memo edit suggestions: model needs the memo and compact edit contract, but not full source/debug state.
- Artifacts: records should keep full section packets, model packets, prompts, raw outputs, validation reports, and a model-context audit.

## Workstreams

1. Section Prompt Boundary
   - Purpose: remove duplicated and negative-content fields from live section prompts.
   - Changes: make `model_section_packet` the only substantive synthesis packet; move preservation checks into compact `validation_obligations`; keep full section packets only in artifacts.
   - Artifacts: section synthesis packet artifact continues to include debug packet and model packet.
   - Validation: tests confirm debug packet fields are not in prompts, forbidden evidence claims/anchors are absent, and required obligation validation still fires.
   - Risks: over-compression could make the model drop anchors; deterministic validation remains binding.

2. Negative Context Sanitization
   - Purpose: prevent forbidden evidence from priming model output.
   - Changes: remove `anchor_terms_to_avoid_repeating` from model-facing `prohibited_repetition`; keep only slot, owner, reference style, and instruction.
   - Artifacts: full ownership/debug records remain in section packet artifacts.
   - Validation: tests confirm forbidden claim text and anchor terms do not appear in section prompts.
   - Risks: model may repeat more; validation and repeated-evidence checks catch regressions.

3. Model Context Audit
   - Purpose: make model-call boundaries inspectable without stuffing prompts.
   - Changes: write a JSON audit summarizing prompt sizes, model-visible keys, debug-only artifacts, and section packet size ratios.
   - Artifacts: `model_context_audit.json`, linked in run summary and final review packet.
   - Validation: prompt-backend run emits the audit; tests cover audit summarization on representative packets.
   - Risks: audit becomes stale if new model calls are added; include generic utilities and clear schema.

4. Legacy Prompt Labeling
   - Purpose: prevent the oversized whole-briefing prompt from being mistaken for an active synthesis call.
   - Changes: classify it in the audit as `record_only_legacy_prompt` unless a future path actually submits it to a backend.
   - Artifacts: prompt remains saved for compatibility and historical review.
   - Validation: audit states whether each prompt is active, skipped, or record-only.
   - Risks: future code may re-enable it; tests should make active oversized prompts visible.

## Execution Order

1. Tighten section model contracts first because this is the active live model path.
2. Sanitize prohibited repetition next because it directly addresses evidence leakage.
3. Add model-context audit artifacts so reductions remain inspectable.
4. Run focused tests, full tests, maintainability gate, and a prompt-backend briefing rerun.

## Acceptance Criteria

- Section rewrite prompts do not include `section_synthesis_packet`, full `owned_elsewhere_evidence`, or forbidden anchor terms.
- Required main-memo obligations still appear in a compact preservation form and still trigger validation failures when dropped.
- The latest run writes `model_context_audit.json`.
- The audit records active versus record-only prompt status and section model/debug packet ratios.
- `pytest`, maintainability gate, and `git diff --check` pass.

## Red-Team Checks

- If a model call needs source text, verify it receives only the relevant span or owned evidence, not the whole map.
- If a prompt contains a fact the model is told not to mention, treat that as a pollution bug.
- If a debug artifact is removed to reduce prompt size, treat that as a records bug.
- If a context boundary depends on a case-specific title or domain term, treat that as overfitting.

## Generalizability Checks

- Tests should use arbitrary civic/operational examples, not only the current case study.
- Context rules should be expressed by stage and evidence role, not by domain vocabulary.
- Audit schema should work for any backend and any decision question.
- New model-call stages should be auditable by adding a record, not by changing validation logic.

## Anti-Half-Done Rule

Do not stop after shrinking prompts. The same slice must preserve full debug records and add an audit artifact proving what the model saw and what remained record-only.
