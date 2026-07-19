# Plan: Decision Boundary And Source Trail Contract

## Objective
Make final decision memos more decision-grade by giving the writer model a compact contract that makes boundaries, source roles, source-specific cautions, and quantity priorities explicit before synthesis.

## Current Gap
The current writer model context contains useful evidence, source appraisal, quantity, and role judgments, but they are spread across several tables. The writer can preserve mandatory items while still:

- under-stating population, dose, endpoint, setting, and missing-evidence boundaries;
- using source labels without explaining what each source contributes;
- over-upgrading observational or indirect evidence into stronger causal language;
- dropping decision-weight and scope quantities even when retention checks pass.

## Non-Goals
- Do not add a new model call.
- Do not hardcode domain vocabularies or case-specific source names.
- Do not ask deterministic code to decide whether evidence is true, supportive, or harmful.
- Do not replace the existing memo-ready packet, writer packet, or audit artifacts.

## Design Principles
- Reuse existing model judgments: analyst roles, answer relations, global decision logic, source appraisals, and quantity-binding output.
- Let deterministic code compile and validate the contract, not make fresh semantic judgments.
- Make source use purposeful: each visible source should have a small card saying what it can support, what cautions apply, and which quantities matter.
- Make boundary coverage inspectable before final prose.
- Keep validation report-only until the signal is calibrated across cases.

## Workstreams
1. Boundary Contract Builder
   - Purpose: turn existing scope, counterweight, crux, and missing-evidence judgments into writer-visible obligations.
   - Changes: add a reusable contract module that builds `boundary_obligations`.
   - Artifacts: `decision_boundary_source_contract` in the writer interface and writer model context.
   - Validation: unit tests with non-domain fixtures.

2. Source-Use Cards
   - Purpose: make each source's memo job explicit.
   - Changes: group visible evidence by source label and list use roles, key claims, retained quantities, and source-appraisal cautions.
   - Artifacts: `source_use_cards` inside the contract.
   - Validation: source cards preserve labels, quantities, and wording cautions without raw source dumps.

3. Quantity Priority Cards
   - Purpose: help synthesis keep high-value numbers while avoiding statistical clutter.
   - Changes: rank already-retained quantities by existing role, quantity role, and item priority.
   - Artifacts: `quantity_priority_cards` inside the contract.
   - Validation: decision anchors appear before supporting/context quantities.

4. Prompt Routing
   - Purpose: make the model use the contract naturally.
   - Changes: include the contract in `writer_model_context` and adjust the synthesis prompt to use it as the boundary/source/quantity guide.
   - Artifacts: prompt contains `decision_boundary_source_contract`.
   - Validation: prompt test confirms the contract is visible and raw packet internals remain excluded.

5. QA And Evaluation
   - Purpose: detect whether the fix improves memo quality.
   - Changes: add quality warnings for missing boundary/source/quantity contract rows.
   - Artifacts: writer interface quality report warnings.
   - Validation: focused tests, full test suite, and a targeted eggs rerun or saved-artifact prompt inspection.

## Execution Order
1. Add the contract builder and unit tests.
2. Wire the contract into writer interface and writer model context.
3. Update the synthesis prompt to point the model at the contract.
4. Add quality-report checks.
5. Verify with focused tests, full tests, and a targeted memo/prompt evaluation.

## Acceptance Criteria
- `writer_decision_interface` includes `decision_boundary_source_contract`.
- `writer_model_context` includes the same contract.
- Contract contains boundary obligations, source-use cards, quantity-priority cards, and language-discipline guidance when the inputs support them.
- Contract builder uses only existing packet/model judgments and source-appraisal fields.
- Focused and full tests pass.
- Rerun or artifact inspection shows the final writer sees boundary/source/quantity guidance in one compact place.

## Red-Team Checks
- If boundary cards are too generic, the memo may still miss actual scope limits. Detect with boundary count and source-linked boundary cards.
- If source-use cards are too long, they can crowd out synthesis. Detect with bounded row and field lengths.
- If quantity priority ranking is too rigid, it can omit useful numbers. Detect by preserving all retained quantities in source cards while only ranking a top subset.
- If source-appraisal cautions become boilerplate, they can reduce readability. Detect by only emitting cautions when upstream appraisal fields explicitly supply them.

## Generalizability Checks
- No domain words or case-specific source labels in source code.
- Works when a case has no quantities, no explicit scope rows, or no source-appraisal cautions.
- Works when source labels are sparse by falling back to visible source labels from evidence items.
- Does not change evidence selection; it only changes how selected evidence is presented to synthesis.
