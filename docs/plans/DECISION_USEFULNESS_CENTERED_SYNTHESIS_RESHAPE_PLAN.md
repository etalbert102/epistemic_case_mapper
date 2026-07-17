# Plan: Decision-Usefulness-Centered Synthesis Reshape

## Objective

Reshape the memo pipeline so the final brief is governed by a decision argument plan, not by an evidence checklist. The target memo should answer:

- what the current answer is;
- why that answer beats plausible alternatives;
- what evidence actually drives the answer;
- what counterweights bound, weaken, or would overturn it;
- what a reader should do differently under different scopes or thresholds;
- what source limitations and update triggers matter.

The analyst decision model is already supposed to provide much of this judgment. This plan makes that judgment the primary synthesis contract and uses evidence contracts as source-discipline scaffolding around it.

## Current Gap

The latest live eggs replay shows that evidence retention has improved: section synthesis accepted on the first attempt, missing required evidence was zero, and section quantity warnings were zero. But the memo still reads like an evidence synthesis rather than a decision-grade brief.

The diagnosis from current artifacts and code inspection:

- `analyst_decision_logic`, `analyst_source_hierarchy`, and `analyst_source_weight_judgments` contain useful judgment.
- The canonical writer packet preserves some of this, but the final section packets still emphasize evidence contracts, retention requirements, source weighting notes, and markdown notes.
- `analyst_section_spine` can arrive as an empty shell in section packets when the compacted canonical pathway lacks owned moves.
- The final synthesis prompt rewards coverage and citation discipline more strongly than decision usefulness.
- Validators can declare success even when the memo does not clearly explain why the answer beats alternatives.

The recurring failure is therefore not missing evidence. It is weak argument ownership.

## Non-Goals

- Do not add a second production synthesis path.
- Do not weaken evidence tags, source IDs, quantity checks, or citation traceability.
- Do not add case-specific wording, health-specific categories, or nutrition-specific rules.
- Do not rely on deterministic code to choose the answer, rank semantic importance, or decide which counterweight matters most.
- Do not add broad new blocking gates until their signal has been calibrated.
- Do not solve source collection or source extraction in this plan.

## Design Principles

- The analyst model owns semantic judgment: answer frame, alternatives, source hierarchy, counterweight disposition, cruxes, and practical implications.
- Deterministic code owns IDs, schema validation, source binding, quantity preservation, routing, telemetry, and presentation normalization.
- The final writer should receive a compact argument plan first, then evidence contracts that support that plan.
- Section packets should state the section's decision job and owned argument moves before listing evidence.
- QA must measure decision usefulness, not just successful synthesis or retained facts.
- Existing model calls should be reused before adding new calls.

## Inventory And Dependency Map

### Existing Owner Artifacts

- `analyst_decision_logic`
  - Bounded answer, support summary, counterweight weighting, scope boundaries, cruxes, practical implications, overstatement limits.
- `analyst_source_hierarchy`
  - Driver, calibrator, counterweight, context, and source-use hierarchy.
- `analyst_source_weight_judgments`
  - Per-source main use, confidence effect, reader-facing limits, and source-use cautions.
- `analyst_argument_plan`
  - Section-level model argument steps where available.
- `canonical_decision_writer_packet_v1`
  - Current synthesis handoff containing balanced answer frame, argument spine, source weighting, mandatory retention, and reader judgment packet.
- `evidence_expression_contract_v1`
  - Strict source/quantity/evidence-tag constraints used during section synthesis.

### Current Loss Points

- `analyst_argument_plan` is not promoted as the controlling synthesis plan.
- `analyst_decision_spine` is built through `writer_decision_interface`, but section packets may receive empty `analyst_section_spine` shells.
- `evidence_weighted_argument_spine` exists, but final section synthesis still treats it as one context object among many rather than the governing contract.
- Section-level prompts do not consistently phrase each section as a decision-usefulness move.
- Validation does not ask whether the memo explains why the answer is decision-relevant or how the evidence changes action.

### Primary Files

- `src/epistemic_case_mapper/map_briefing_analyst_decision_spine.py`
- `src/epistemic_case_mapper/map_briefing_canonical_decision_writer_packet.py`
- `src/epistemic_case_mapper/map_briefing_argument_spine.py`
- `src/epistemic_case_mapper/map_briefing_memo_ready_prompt.py`
- `src/epistemic_case_mapper/map_briefing_memo_ready_section_notes.py`
- `src/epistemic_case_mapper/map_briefing_section_evidence_anchoring.py`
- `src/epistemic_case_mapper/map_briefing_memo_ready_finalization.py`

### Primary Tests To Extend

- `tests/test_canonical_decision_writer_packet.py`
- `tests/test_parallel_section_synthesis.py`
- `tests/test_analyst_decision_spine.py`
- `tests/test_decision_usefulness_synthesis.py`

## Workstreams

### 1. Create A Canonical Decision Argument Contract

Purpose:

- Convert existing analyst outputs into one compact, inspectable `decision_argument_contract_v1`.

Changes:

- Add a builder that compiles:
  - decision question;
  - direct answer;
  - plausible alternatives or answer states;
  - why the selected answer beats alternatives;
  - answer-driving evidence moves;
  - counterweight disposition;
  - scope boundaries;
  - practical implications;
  - cruxes and update triggers;
  - source hierarchy thesis and source-use limits.
- Prefer model-produced fields from `analyst_decision_logic`, `analyst_argument_plan`, `analyst_source_hierarchy`, and `analyst_source_weight_judgments`.
- Use deterministic projection only to normalize shape, preserve IDs, and fill obvious owner links.

Artifacts:

- `decision_argument_contract` inside `canonical_decision_writer_packet`.
- `decision_argument_contract_report` with coverage and warning fields.

Validation:

- Contract exists for memo-ready packets with a canonical writer packet.
- Contract has at least one answer move, one support move, one counterweight/scope move when such evidence exists, and one practical/use move when practical implications exist.
- Every move has stable `move_id`, `section_id`, `point`, `writing_job`, and trace IDs where available.

QA:

- Synthetic tests for a policy choice, factual read, threshold question, and insufficient-evidence case.
- Report-only warnings for missing alternatives, missing counterweight disposition, or generic move points.

Risks:

- The contract could become another duplicated artifact. Mitigation: make section packet construction consume this contract directly and add telemetry proving prompt use.

### 2. Make Section Packets Argument-First

Purpose:

- Ensure the section writer receives its decision job before evidence details.

Changes:

- In `_section_synthesis_packets`, attach `decision_argument_section` from the canonical contract to each section.
- The section packet should expose:
  - `section_decision_job`;
  - `owned_argument_moves`;
  - `why_this_section_matters`;
  - `must_answer_reader_question`;
  - `evidence_ids_for_each_move`;
  - `source_ids_for_each_move`;
  - `required_quantities_for_each_move`.
- Keep `source_bound_evidence_atoms` and evidence contracts, but treat them as support for owned moves rather than the organizing structure.

Artifacts:

- Section packets with non-empty `decision_argument_section` for answer, counterweight, source-weighting, and practical sections.

Validation:

- Each generated section prompt contains a `### Decision argument for this section` block before evidence contracts.
- `analyst_section_spine` is either populated or deliberately replaced by the new section argument contract.

QA:

- Prompt tests verify argument block appears before evidence contracts.
- Replay prompt inspection verifies the eggs counterweight section gets counterweight disposition and update-trigger moves, not just evidence jobs.

Risks:

- Too much argument context could pollute model prompts. Mitigation: compact section-local moves and keep full contract in artifacts, not prompts.

### 3. Reframe Evidence Contracts As Anchors For Argument Moves

Purpose:

- Preserve source discipline while preventing evidence contracts from becoming the memo's structure.

Changes:

- Add `argument_move_id` or `argument_job_id` to evidence expression contracts where an evidence item is owned by a move.
- Section-local evidence jobs should be derived from argument moves first, then from generic evidence features only when the move link is absent.
- Retry prompts should say which argument move failed, not just which evidence contract failed.

Artifacts:

- Evidence contracts with argument-move linkage.
- Reconciliation reports grouped by argument move.

Validation:

- Missing evidence reports identify both `evidence_id` and `argument_move_id`.
- Quantity warnings identify the move whose sentence omitted the quantity.

QA:

- Unit test where a required quantity is omitted confirms the retry prompt contains the relevant argument move point.

Risks:

- Bad move linkage could force evidence into the wrong section. Mitigation: keep report-only warnings and allow evidence to support multiple moves when the analyst model says it has multiple functions.

### 4. Add Decision-Usefulness Telemetry

Purpose:

- Detect the recurring failure directly: evidence retained but decision usefulness weak.

Changes:

- Add `decision_usefulness_surface_report_v1` for final memos.
- Check for:
  - answer stated;
  - alternatives or answer states addressed when present;
  - why selected answer beats alternatives;
  - counterweight disposition present;
  - scope boundary present;
  - practical implication present;
  - update trigger/crux present when available;
  - source hierarchy visible;
  - required analyst moves surfaced.
- Keep this report non-blocking initially.

Artifacts:

- Report attached to synthesis report and saved replay artifacts.

Validation:

- A memo that merely lists evidence but omits counterweight disposition receives a warning.
- A memo that includes all required evidence but no practical implication receives a warning.

QA:

- Golden weak memo fixture and golden good memo fixture.
- Differential comparison against the latest accepted eggs memo.

Risks:

- Deterministic checks may be too lexical. Mitigation: check for move IDs and source/evidence coverage where possible, and keep semantic score report-only.

### 5. Revise Section Synthesis Prompt Ordering

Purpose:

- Make the model write from a decision argument, with evidence as support.

Changes:

- For evidence-tagged section prompts, render in this order:
  1. section role and reader question;
  2. decision argument for this section;
  3. paragraph flow / section-local argument jobs;
  4. evidence expression contracts;
  5. source and quantity discipline rules.
- Remove duplicate or weaker context blocks that restate the same evidence without argument role.
- Keep prompt instructions positive and natural.

Artifacts:

- Prompt context audit showing argument block precedes evidence contracts.

Validation:

- Prompt tests assert ordering.
- Fake-backend tests confirm generated sections can pass strict retention with the new prompt.

QA:

- Live replay on eggs with same saved packet, compared against previous accepted memo.
- One unrelated saved packet replay to check generality.

Risks:

- Prose could improve while evidence retention regresses. Mitigation: strict evidence reconciliation remains blocking.

### 6. Evaluate Whether The Analyst Stage Is Delivering Value

Purpose:

- Confirm that the analyst decision model is not just producing unused artifacts.

Changes:

- Add a stage-value report comparing:
  - analyst decision moves produced;
  - moves promoted into canonical contract;
  - moves rendered in section prompts;
  - moves surfaced in final memo.
- Attribute failures to:
  - missing analyst output;
  - projection loss;
  - prompt omission;
  - synthesis nonuse;
  - final polish drift.

Artifacts:

- `analyst_judgment_utilization_report_v1`.

Validation:

- Latest eggs replay should show whether the analyst source hierarchy and counterweight disposition are present in the prompt and memo.

QA:

- Regression test with an analyst move that should appear in counterweights.
- Regression test with a move that should remain out of practical implication.

Risks:

- Report could become noisy. Mitigation: start with required moves only: answer, source hierarchy, strongest support, strongest counterweight disposition, scope, practical implication, crux/update trigger.

## Execution Order

1. Build the canonical `decision_argument_contract_v1` from existing artifacts and attach reports.
2. Wire section packets to consume `decision_argument_contract_v1`.
3. Change section prompt ordering to put decision argument before evidence contracts.
4. Link evidence expression contracts to argument moves where possible.
5. Add decision-usefulness and analyst-utilization telemetry.
6. Run focused tests and a saved-packet replay on eggs.
7. Run at least one unrelated saved packet replay.
8. Compare final memo against:
   - previous accepted eggs memo;
   - raw-source synthesis baseline where available;
   - decision-usefulness report.

## Acceptance Criteria

- Every production memo-ready packet with a canonical writer packet has a non-empty `decision_argument_contract`.
- Every synthesis section packet has a non-empty `decision_argument_section` or a recorded reason why no section argument applies.
- Evidence-tagged prompts render `### Decision argument for this section` before `### Evidence expression contracts`.
- The eggs replay still has zero missing required evidence and zero missing required quantities.
- The eggs memo improves on at least two decision-usefulness dimensions: counterweight disposition, why the answer beats alternatives, practical actionability, source hierarchy clarity, or update-trigger clarity.
- `analyst_judgment_utilization_report_v1` can attribute whether any analyst move was lost before synthesis.
- Existing targeted tests pass:
  - `PYTHONPATH=src python3 -m pytest -q tests/test_canonical_decision_writer_packet.py tests/test_parallel_section_synthesis.py tests/test_analyst_decision_spine.py tests/test_decision_usefulness_synthesis.py`

## Red-Team Checks

- Failure: The new contract just restates existing evidence.
  - Detection: move points lack answer-comparison, disposition, scope, or practical language.
  - Response: strengthen the contract builder to prefer `analyst_decision_logic` over evidence-row claims.

- Failure: The final memo still reads generic.
  - Detection: decision-usefulness report passes coverage but manual memo comparison shows weak answer discrimination.
  - Response: add a model-authored section-specific argument note from existing analyst fields before adding any new model call.

- Failure: The model drops evidence after the prompt becomes argument-first.
  - Detection: evidence reconciliation warnings increase.
  - Response: keep evidence contracts strict and retry by argument move plus evidence contract.

- Failure: Deterministic code starts making semantic decisions.
  - Detection: new code uses domain keywords or lexical rules to decide the answer, source importance, or counterweight disposition.
  - Response: move that choice into analyst model output or report-only telemetry.

- Failure: The plan overfits eggs.
  - Detection: fields mention nutrition, biomarkers, eggs, cholesterol, or health-specific thresholds as core schema concepts.
  - Response: keep schemas generic: answer, alternatives, support, counterweight, scope, crux, practical implication, source hierarchy.

## Generalizability Checks

- Reorder source documents and verify argument move IDs and section ownership remain stable.
- Rename source IDs and verify the final memo remains equivalent after deterministic citation normalization.
- Add an irrelevant source and verify it is excluded or contextualized without changing the answer.
- Test a non-health case where the decision question is policy or operational rather than empirical.
- Test a belief/read question where there is no action recommendation; practical section should become "how to use this read" rather than forced advice.

## Slice Ledger

Each implementation slice must record:

- files changed;
- exact verification command;
- artifact path for any replay;
- whether decision usefulness improved, regressed, or was unchanged;
- whether evidence retention regressed;
- any deferred work.

Suggested slices:

1. Contract builder and tests.
2. Section packet integration and prompt ordering tests.
3. Evidence-contract argument linkage and retry prompt tests.
4. Decision-usefulness and analyst-utilization telemetry.
5. Eggs replay and unrelated-case replay.
6. Cleanup of obsolete sidecar fields if the new path proves stronger.

### Completed Slices

1. Contract builder and canonical attachment
   - Files changed:
     - `src/epistemic_case_mapper/map_briefing_decision_argument_contract.py`
     - `src/epistemic_case_mapper/map_briefing_canonical_decision_writer_packet.py`
     - `tests/test_analyst_decision_spine.py`
   - Verification:
     - `PYTHONPATH=src python3 -m pytest -q tests/test_canonical_decision_writer_packet.py tests/test_parallel_section_synthesis.py tests/test_analyst_decision_spine.py tests/test_decision_usefulness_synthesis.py`
   - Result:
     - `36 passed`.
   - Notes:
     - The contract is built after source-ID projection to avoid source projection mutating section IDs.

2. Section packet integration and prompt ordering
   - Files changed:
     - `src/epistemic_case_mapper/map_briefing_memo_ready_prompt.py`
     - `src/epistemic_case_mapper/map_briefing_memo_ready_section_notes.py`
     - `tests/test_parallel_section_synthesis.py`
   - Verification:
     - Same focused test command above.
   - Result:
     - Section prompts now render `### Decision argument for this section` before evidence lists and contracts.

3. Evidence-contract argument linkage
   - Files changed:
     - `src/epistemic_case_mapper/map_briefing_section_evidence_anchoring.py`
     - `tests/test_parallel_section_synthesis.py`
   - Verification:
     - Same focused test command above.
   - Result:
     - Evidence expression contracts carry `argument_move_ids`; section-local evidence jobs prefer analyst argument moves before generic fallback grouping.

4. Decision-usefulness and analyst-utilization telemetry
   - Files changed:
     - `src/epistemic_case_mapper/map_briefing_memo_ready_finalization.py`
     - `tests/test_decision_usefulness_synthesis.py`
     - `tests/test_parallel_section_synthesis.py`
   - Verification:
     - Same focused test command above.
   - Result:
     - Synthesis reports now include `decision_usefulness_surface_report_v1` and `analyst_judgment_utilization_report_v1`.

5. Eggs replay and posthoc evaluation
   - Artifact:
     - `artifacts/replay/eggs_decision_argument_contract_live_v3_20260717/BRIEFING_READER.md`
     - `artifacts/replay/eggs_decision_argument_contract_live_v3_20260717/posthoc_decision_argument_evaluation.json`
   - Verification:
     - Live synthesis using `ollama:gemma4:12b-mlx` against the saved eggs memo-ready packet.
     - Posthoc telemetry recomputed after finalization learned to build the decision argument contract from older saved canonical packets.
   - Result:
     - Synthesis status: `accepted_with_evidence_tag_warnings`.
     - Required evidence retention: `ready`, `missing_mandatory_count = 0`.
     - Decision usefulness surface: `ready`, `missing_move_count = 0`.
     - Analyst utilization: `ready`, no utilization issues.
   - Remaining limitation:
     - Source-binding/citation-care warnings remain (`source_binding_warning_count = 11`), so citation presentation still needs a separate polish/hardening pass.

6. Unrelated current-shape regression check
   - Verification:
     - Constructed the non-eggs `Should option A be adopted?` packet through the current decision-writer adapter with an analyst decision model, then built the production section synthesis plan and decision-usefulness telemetry.
   - Result:
     - `decision_argument_contract_v1` was present.
     - Argument move count: `7`.
     - Section packets produced: `source_weighting`, `answer_evidence`, `counterweights`, `practical_implication`.
     - All section packets carried section-local decision argument moves.
     - Decision usefulness surface telemetry: `ready`.
     - Analyst utilization telemetry: `ready`.
   - Notes:
     - Older saved non-eggs artifacts were inspected but not counted as proof because they predate the current canonical analyst packet shape and cannot exercise this path without compatibility backfill.

## Completion Audit

The plan is complete only when:

- [x] the canonical contract exists and is consumed by production section synthesis;
- [x] telemetry shows analyst moves are not lost before synthesis;
- [x] strict evidence reconciliation still passes;
- [x] the latest eggs memo is manually judged more decision-useful than the pre-plan memo;
- [x] at least one unrelated current-shape case does not regress;
- [x] any remaining gap is recorded with an owning stage rather than hidden behind a successful synthesis status.

Remaining owned gap:

- Citation/source-binding presentation still belongs to the memo finalization and citation-normalization layer, not the decision-usefulness contract. The latest eggs replay retained required evidence and surfaced analyst moves, but still had `source_binding_warning_count = 11`.
