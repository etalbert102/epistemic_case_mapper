# Plan: Use Analyst Judgments As Controlling Pipeline Structure

## Objective

Make the existing global analyst judgments control the final decision packet and memo more strongly without adding new model calls. The target end state is that the analyst model's source hierarchy, crux/update-trigger judgments, quantity relevance, and argument blueprint survive as structured obligations in downstream writer packets instead of becoming weak prose hints.

## Current Gap

The pipeline already produces useful judgments, but some are softened downstream:

- `source_hierarchy` is preserved, while `source_weighted_answer_frame` is mostly rebuilt from projected writer-interface roles.
- `decision_logic` uses the first support and first counterweight group, so richer counterweight and crux reasoning can be dropped.
- `what_would_change_the_answer` is not strongly requested by the global answer-frame task and role-level crux judgments are not fully reused.
- `argument_blueprint.source_weighting_move` becomes a required point, but it is not always bound tightly to the evidence rows and source lanes it should govern.

## Non-Goals

- Do not add new model calls.
- Do not tune to the eggs case or any domain vocabulary.
- Do not make deterministic code invent semantic judgments; deterministic code should preserve, route, normalize, and validate model judgments.
- Do not weaken source anchoring, citation identity, or quantity binding.
- Do not keep fallback behavior that silently hides missing analyst judgments.

## Design Principles

- LLM/model work owns semantic judgment: answer frame, evidence role, quantity relevance, source hierarchy, crux/update triggers, and argument blueprint.
- Deterministic code owns stable identity, schema normalization, projection, section-local routing, and fidelity reports.
- Source hierarchy should be controlling when present, with deterministic projection only filling gaps.
- Cruxes and counterweights should flow into `decision_logic`, `balanced_answer_frame`, section packets, and synthesis prompts as structured obligations.
- Every new or expanded field must be used downstream or tested.
- QA must check behavior, not only schema validity.

## Inventory And Dependency Map

- Extend:
  - `map_briefing_analyst_decision_model_global_task_prompts.py`
  - `map_briefing_analyst_decision_model_global_tasks.py`
  - `map_briefing_canonical_decision_writer_packet.py`
  - tests covering global task assembly and canonical source weighting.
- Keep:
  - existing model call count and backend configuration.
  - existing citation/source identity projection.
  - existing memo-ready canonical handoff shape unless a field is needed to preserve analyst judgment.
- Dependency order:
  1. Global prompt/schema asks for richer answer-frame judgment.
  2. Global task assembly preserves crux/counterweight/source hierarchy judgment in `decision_logic`.
  3. Canonical packet uses source hierarchy as source-weight lane override.
  4. Prompt/section packets expose the resulting source-weighted frame and crux logic.
  5. Tests verify the judgments influence downstream artifacts.

## Workstreams

1. Richer global answer-frame contract
   - Purpose: capture what would change the answer and why counterweights do or do not change it.
   - Changes: add schema fields for `counterweight_weighting`, `what_would_change_the_answer`, and list-valued practical implications.
   - Artifacts: updated global task prompt schema.
   - Validation: prompt-focused test checks fields are present.
   - QA: fake backend emits the new fields so downstream tests catch regressions.

2. Decision logic preservation
   - Purpose: prevent global judgments from collapsing to first support/counterweight snippets.
   - Changes: build `decision_logic` from answer frame, evidence-role cruxes, all counterweight groups, and source hierarchy thesis.
   - Artifacts: richer `analyst_decision_model.decision_logic`.
   - Validation: unit test checks counterweight weighting and cruxes survive assembly.
   - QA: no invented cruxes when the model does not provide them.

3. Source hierarchy as controlling weighting structure
   - Purpose: ensure source hierarchy controls source weighting when present.
   - Changes: in canonical writer packet, map source IDs and evidence IDs from analyst hierarchy lanes into canonical source-weight lanes before falling back to projected role lanes.
   - Artifacts: source-weighted frame rows include hierarchy-derived `source_weight_role` and reason.
   - Validation: test with intentionally conflicting row role vs hierarchy lane; hierarchy wins.
   - QA: report should still warn if hierarchy is missing or incomplete.

4. Section-local obligation strengthening
   - Purpose: make section packets carry source hierarchy and crux obligations close to the evidence they govern.
   - Changes: include hierarchy-derived source weighting in section packets and ensure crux/update-trigger logic is visible in the relevant section context.
   - Artifacts: section writer packets with source weighting and crux obligations.
   - Validation: prompt contract tests inspect section packet content.
   - QA: no raw source titles or unnormalized source labels leak into model prompt.

## Execution Order

1. Implement Workstreams 1 and 2 together because the new answer-frame fields only matter if decision logic consumes them.
2. Implement Workstream 3 because it improves use of an already-produced global source hierarchy without changing model calls.
3. Implement Workstream 4 only if tests show section-local packets still underexpose the improved judgment artifacts.
4. Run focused tests after each slice and the maintainability gate after the final slice.

## Acceptance Criteria

- Global task prompt schema asks for counterweight weighting and answer-changing cruxes.
- `build_analyst_decision_model_from_global_tasks` preserves answer-frame and evidence-role cruxes in `decision_logic`.
- Canonical source weighting uses analyst source hierarchy lanes when present, even if projected row role would choose a different lane.
- Tests cover the above behavior with case-neutral fixtures.
- `PYTHONPATH=src python3 -m pytest tests/test_global_task_analyst_decision_model.py tests/test_canonical_decision_writer_packet.py -q` passes.
- `PYTHONPATH=src python3 scripts/maintainability_gate.py` passes before final completion.

## Red-Team Checks

- Failure: deterministic code makes new semantic judgments.
  - Detection: new lane override may only use explicit `source_hierarchy` lane membership by source ID or evidence item ID.
- Failure: richer schema fields are captured but unused.
  - Detection: tests fail unless fields change downstream `decision_logic`.
- Failure: hierarchy override overfits to source IDs and misclassifies multi-role sources.
  - Detection: preserve row-level role where no explicit hierarchy lane matches; include reason lineage.
- Failure: prompt grows noisier.
  - Detection: section prompt tests confirm only compact source weighting/crux fields are exposed.

## Generalizability Checks

- Use case-neutral source IDs and evidence IDs in tests.
- Test conflicting role vs hierarchy to prove the mechanism relies on explicit analyst hierarchy, not domain terms.
- Test absent hierarchy to ensure deterministic role projection still works.
- Treat new checks as behavior-level tests rather than snapshot tests tied to exact prose.

## Execution Status

Status: `implemented-and-verified`

Completed slices:

- Added richer global answer-frame judgment fields for counterweight weighting, answer-changing cruxes, and multiple practical implications.
- Updated global task assembly so `decision_logic` preserves model-provided counterweight weighting, role-level crux judgments, and multiple support/counterweight summaries.
- Added source IDs to writer-interface evidence rows so downstream source hierarchy projection can use stable identity.
- Added `map_briefing_source_hierarchy_projection.py` so canonical source weighting can use explicit analyst hierarchy lanes before falling back to writer-role projection.
- Added regression tests for prompt contract, decision-logic preservation, and hierarchy-over-projected-role source weighting.

Verification:

- `PYTHONPATH=src python3 -m pytest tests/test_global_task_analyst_decision_model.py tests/test_canonical_decision_writer_packet.py tests/test_decision_writer_relevance.py -q` passed: 19 tests.
- `PYTHONPATH=src python3 scripts/maintainability_gate.py` passed, including full pytest: 789 tests.

Deferred:

- No separate section-local packet rewrite was needed in this slice because section packets already consume canonical `source_weighting`; future memo-quality testing should verify whether those section packets now produce visibly better source-weighted prose.
