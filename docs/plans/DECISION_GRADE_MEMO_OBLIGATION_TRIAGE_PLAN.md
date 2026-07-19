# Plan: Decision-Grade Memo Obligation Triage

## Objective

Make the pipeline produce a decision-grade memo by improving the intermediate writer packet, not by adding more prose polish. Given a decision question and source documents, the system should build a compact, prioritized, source-grounded decision packet that a model can synthesize into a readable memo without dropping load-bearing evidence.

The central architecture change is reuse-first:

```text
raw evidence units
  -> existing analyst adjudication, global decision model, and quantity binding calls
  -> deterministic decision-obligation contract derived from those model judgments
  -> report-only writeability telemetry
  -> model-written memo
  -> code validation against selected obligations
```

Only add a new model call when telemetry shows the existing model judgments do not contain enough information to build a writeable decision contract. The default implementation path should spend saved inference budget on better synthesis and targeted repair, not on duplicating semantic judgments already made upstream.

This replaces the current failure mode:

```text
raw evidence units
  -> all non-context items mandatory
  -> all copied quantities retained
  -> model struggles to write a natural memo
```

## Current Gap

The live eggs end-to-end run at `artifacts/semantic/eggs_real_contract_e2e_20260711/` showed:

- `decision_writer_active` worked.
- The final memo was readable but `not_decision_ready`.
- Strict synthesis produced `accepted_with_retention_warnings`.
- Repair reduced missing obligations from `8` to `7`, but still returned `partial_retention_improvement_applied_with_warnings`.
- `memo_packet_retention_report.json` reported `7` missing mandatory obligations and `61` missing quantities.
- `memo_quality_report.json` still scored the memo as polished, proving prose polish is not the same as decision readiness.
- `decision_writer_packet_quality_report.json`, `packet_sufficiency_report.json`, and `packet_quality_gate_report.json` said ready, but final readiness said not decision-ready. The upstream gates are not measuring packet writeability.

Observed root causes:

- The actual run used the broad case question, not the narrower baseline decision question.
- Claim extraction produced `33` claims and the map quality report flagged high claim count and near duplicates.
- Relation extraction accepted only `5` relations and rejected `13`, leaving weak argument structure for synthesis.
- `decision_writer_packet_to_memo_ready_packet` makes every non-context writer unit a `must_use` item.
- `build_memo_obligation_packet` makes required obligations mostly by role, not by model-owned decision salience.
- Quantity handling copies all source quantity values into writer units, then treats many as load-bearing.
- Some obligations require impossible or reader-hostile quantity retention, such as dozens of p-values, confidence intervals, heterogeneity percentages, and repeated quantities.
- The current run already pays for useful model judgments that are not being fully exploited:
  - `global_decision_model.json` separates strongest support, strongest counterarguments, scope boundaries, decision cruxes, contextual evidence, and an argument plan.
  - `analyst_adjudication.json` contains `memo_use`, `importance_rank`, and rationale fields for individual claims.
  - `analyst_quantity_binding_report.json` already judges whether quantities should appear in the memo, but is too permissive and still lets deterministic quantity extraction behave like semantic selection.

Therefore the first fix is not “add another planner.” It is to convert the existing model outputs into the actual writer contract and improve only the weak existing calls.

## Non-Goals

- Do not add egg-, cholesterol-, HEPA-, COVID-, or LHC-specific rules to generic code.
- Do not solve source collection or retrieval.
- Do not make deterministic code decide semantic relevance.
- Do not hide missing evidence by weakening validation.
- Do not treat final prose polish as a substitute for packet quality.
- Do not delete legacy paths until the new path has report-only and live-run evidence.

## Design Principles

1. **Models judge semantics.** Evidence importance, evidence role, quantity relevance, crux status, and waiver or demotion reasons should be model-owned.
2. **Code enforces structure.** Deterministic code should validate schemas, preserve provenance, count coverage, track IDs, assemble artifacts, and report disagreements.
3. **No silent semantic repair.** Code can flag, compare, and route; it should not silently decide that a claim or quantity is semantically irrelevant.
4. **Writeability is a first-class quality target.** A packet is not ready unless it can plausibly produce a readable decision memo.
5. **Generalize by artifact roles, not domain terms.** Prompts and schemas should talk about decision anchors, counterweights, quantities, cruxes, and scope boundaries rather than case-specific concepts.
6. **Report-only before blocking.** New model-judgment gates should run report-only until calibrated.
7. **Reuse existing model judgments before adding calls.** If analyst adjudication, global decision modeling, or quantity binding already answered a semantic question, downstream code should consume that answer instead of asking a second model to re-decide it.

## Inventory And Dependency Map

Primary current code paths:

- Active writer packet adapter: `src/epistemic_case_mapper/pipeline/briefing/map_briefing_decision_writer_packet.py`
- Memo obligations: `src/epistemic_case_mapper/pipeline/briefing/map_briefing_memo_obligations.py`
- Synthesis prompt: `src/epistemic_case_mapper/pipeline/briefing/map_briefing_memo_ready_prompt.py`
- Synthesis, retention, and repair: `src/epistemic_case_mapper/pipeline/briefing/map_briefing_memo_ready_finalization.py`
- Decision packet stage wiring: `src/epistemic_case_mapper/pipeline/briefing/map_briefing_decision_packet_stage.py`
- Full final-output orchestration: `src/epistemic_case_mapper/pipeline/briefing/map_briefing_final_outputs.py`

Key artifacts to inspect before and after each implementation slice:

- `decision_writer_packet.json`
- `decision_writer_packet_quality_report.json`
- `memo_ready_packet.json`
- `memo_obligations.json` or `memo_ready_packet.memo_obligations`
- `memo_ready_synthesis_prompt.txt`
- `memo_ready_synthesis_report.json`
- `memo_ready_repair_report.json`
- `memo_packet_retention_report.json`
- `final_decision_readiness_report.json`
- `memo_semantic_acceptance_report.json`

Dependency order:

1. Preserve the exact decision question.
2. Inventory and normalize existing semantic judgments from analyst adjudication, global decision model, and quantity binding.
3. Derive the memo obligation contract from those existing judgments.
4. Tighten quantity binding so it selects reader-facing quantities instead of approving raw extracted quantities by default.
5. Add writeability telemetry and gates.
6. Simplify synthesis input around the cleaned decision contract.
7. Replace broad repair with targeted obligation resolution.

## Workstreams

### 1. Decision Question Control

Purpose: ensure the pipeline answers the actual decision question.

Changes:

- Add `decision_question_contract_v1`.
- Pass the exact decision question into source extraction, analyst adjudication, global decision model, writer packet, synthesis, and repair.
- Record whether each stage used the exact question or a derived question.
- Add warnings when a broad case question overrides a user-provided decision question.

Model responsibilities:

- Judge evidence relevance to the provided decision question.
- Explain why each included evidence item matters for that question.

Code responsibilities:

- Preserve the exact question string.
- Include the exact question deterministically in the final memo.
- Emit a stage-by-stage question-flow audit.

Artifacts:

- `decision_question_contract.json`
- `decision_question_flow_report.json`

Validation:

- Regression test where broad case question and narrow user question differ.
- Final memo includes the exact decision question.

Risks:

- Prompt text may include both broad and narrow questions and confuse the model.
- Mitigation: prompts should label exactly one `decision_question` field as authoritative.

### 2. Reuse-First Evidence Obligation Planning

Purpose: replace “every non-context unit is required” with an obligation plan derived from model judgments the pipeline already produces.

Changes:

- Add `decision_obligation_plan_v1` as a deterministic adapter over existing model outputs, not initially as a new model call.
- Primary inputs:
  - `global_decision_model.json`
  - `analyst_decision_model.json`
  - `analyst_adjudication.json`
  - `decision_writer_packet.json`
- Map existing roles into obligation levels:
  - strongest support, strongest counterargument, crux, and decisive scope boundary can become `must_include` or `should_include`.
  - contextual evidence normally becomes `optional_context`.
  - evidence with low relevance or no memo use becomes `audit_only`.
- Each evidence unit gets:
  - `evidence_unit_id`
  - `obligation_level`: `must_include | should_include | optional_context | audit_only`
  - `memo_function`: `answer_anchor | counterweight | scope_boundary | subgroup_exception | crux | background`
  - `include_reason`
  - `demotion_reason`
  - `required_quantity_ids`
  - `source_labels`

Model responsibilities:

- Already decided upstream: evidence role, memo use, importance, counterweight status, crux status, and scope status.
- If existing outputs conflict or leave high-importance evidence unclassified, a fallback model call may adjudicate only those ambiguous rows.

Code responsibilities:

- Join model judgments by stable evidence IDs.
- Validate allowed enum values.
- Ensure every evidence unit has a disposition.
- Ensure every `must_include` item is source-bound.
- Report counts by obligation level and memo function.
- Report judgment conflicts, missing IDs, and rows that would require a fallback adjudication call.

Artifacts:

- `decision_obligation_plan.json`
- `decision_obligation_plan_report.json`
- `decision_obligation_plan_conflicts.json`

Validation:

- Current eggs packet should not mark all 19 non-context obligations as mandatory.
- A non-eggs case should produce a plausible distribution of `must_include`, `should_include`, `optional_context`, and `audit_only`.
- With existing eggs artifacts, the plan should be buildable without a new model call except for explicitly reported ambiguity cases.

QA:

- Adversarial fixture where a strong counterweight must not be demoted without a reason.
- Metamorphic test with reordered sources: obligation levels should remain stable.
- Consistency fixture where the same evidence appears in both global support and analyst background; adapter must report the conflict rather than silently choosing.

Risks:

- Model may demote inconvenient evidence.
- Existing upstream labels may be noisy.
- Mitigation: code requires a disposition for every evidence unit, reports high-priority demotions, and routes only conflicting or missing high-salience rows to fallback adjudication.

### 3. Tighten Existing Quantity Binding

Purpose: stop raw quantity lists from becoming impossible memo obligations by upgrading the existing quantity-binding call instead of adding a parallel quantity planner.

Changes:

- Keep the current quantity candidate extraction.
- Replace permissive binding behavior with a stricter `quantity_obligation_plan_v1` emitted by the existing `analyst_quantity_binding_report` stage.
- For each source-bound quantity candidate, model assigns:
  - `quantity_id`
  - `quantity_role`: `decision_anchor | supporting_detail | study_descriptor | statistical_detail | audit_only`
  - `must_retain`
  - `retention_phrase`
  - `why_quantity_matters`
  - `demotion_reason`
  - `source_label`
  - `source_evidence_item_id`
- Add `required_for_memo_reason` only when `must_retain` is true.
- Add `safe_to_omit_reason` when a quantity is `audit_only` or `statistical_detail`.

Model responsibilities:

- Decide whether a quantity is decision-load-bearing.
- Convert raw statistics into reader-facing retention phrases.
- Distinguish effect sizes, denominators, uncertainty intervals, dates, subgroup descriptors, p-values, and heterogeneity statistics.
- Use the decision question and global decision model answer when judging whether a number is reader-facing.

Code responsibilities:

- Extract quantity candidates mechanically.
- Preserve source bindings.
- Validate every quantity has a role.
- Check final memo only against `must_retain` quantities and their retention phrases.
- Report dropped or demoted quantities.
- Do not mark a quantity as mandatory solely because deterministic extraction found it.
- Emit an overload warning when approved quantities greatly exceed what a normal memo can retain.

Artifacts:

- `quantity_obligation_plan.json`
- `quantity_obligation_plan_report.json`
- updated `analyst_quantity_binding_report.json`

Validation:

- No obligation should require 20+ raw quantities unless the model explicitly marks it as a table or appendix obligation.
- The Zhong/Drouin-Chartier failure should become a small number of retained anchors, not dozens of raw values.
- Existing eggs artifacts should show a substantial drop from the previous `168` approved quantities while preserving the truly load-bearing effect sizes and uncertainty ranges.

QA:

- Golden fixture where one effect size is the crux and must remain retained.
- Fixture with many p-values and dates that should be audit-only or supporting detail.

Risks:

- Model may drop important uncertainty intervals.
- Mitigation: code reports all non-retained confidence intervals and asks the model for demotion reasons.

### 4. Deterministic Writeability Telemetry And Conditional Fallback

Purpose: make packet readiness predict memo readiness.

Changes:

- Add `writer_packet_writeability_report_v1`.
- Report:
  - mandatory obligation count
  - mandatory quantity count
  - maximum quantities per obligation
  - redundant obligation clusters
  - unsupported answer leaps
  - relation support available for synthesis
  - expected memo length band
  - recommended synthesis strategy: `single_pass | sectioned | table_assisted | needs_packet_repair`
- Add `fallback_needed` reasons:
  - missing high-salience obligation disposition
  - conflicting upstream judgments
  - excessive mandatory quantities after quantity binding
  - unsupported answer frame
  - no source-bound counterweight despite analyst finding one
- Add the fallback model call only for the narrow missing piece identified by telemetry.

Model responsibilities:

- No default new call.
- If telemetry routes to fallback, judge only the specific ambiguous rows or unwritable packet issue.

Code responsibilities:

- Compute count and size metrics.
- Validate reused artifact shapes.
- Warn when packet is structurally unwritable.
- Keep gate report-only until calibrated.
- Record whether a new model call was avoided, invoked, or recommended but skipped.

Artifacts:

- `writer_packet_writeability_report.json`
- `writer_packet_fallback_requests.json`
- `writer_packet_fallback_report.json` only when fallback is invoked

Validation:

- Current eggs packet should warn before synthesis because it has excessive raw quantity obligations.
- A compact packet should pass.
- If the reused artifacts are sufficient, no writeability model prompt should be generated.

QA:

- Stage-value check: a packet that passes writeability should have fewer final retention failures than one that fails.

Risks:

- Gate may become another noisy validator.
- Mitigation: initially report-only; do not block until its signal predicts final memo quality.

### 5. Relation Map Improvement For Memo Use

Purpose: give the memo an argument structure, not just a claim bag.

Changes:

- Add synthesis-facing relation roles:
  - `supports_answer`
  - `weakens_answer`
  - `qualifies_scope`
  - `explains_conflict`
  - `same_claim_variant`
  - `endpoint_mismatch`
  - `population_exception`
- Use embeddings and graph heuristics to propose candidate pairs.
- Use model adjudication for relation semantics.
- Preserve rejected relation reasons.

Model responsibilities:

- Decide relation semantics.
- Explain why the relation matters for the decision.

Code responsibilities:

- Generate candidate pairs with embeddings, centrality, source diversity, and novelty heuristics.
- Validate relation schema.
- Track accepted and rejected reasons.

Artifacts:

- `decision_relation_candidates.json`
- `decision_relation_adjudication_report.json`
- `decision_relation_value_report.json`

Validation:

- Relation yield should improve from the current 5 accepted relations without accepting obvious junk.
- The decision model should cite relation structure when forming the answer.

QA:

- Golden relation pairs for support, challenge, scope, endpoint mismatch, and population exception.
- Metamorphic test with duplicated near-identical claims.

Risks:

- More accepted relations could lower quality.
- Mitigation: use relation-value report and semantic tests, not count alone.

### 6. Synthesis From A Clean Reused-Judgment Decision Contract

Purpose: have the model write from a compact decision contract instead of noisy packet internals.

Changes:

- Build `decision_memo_contract_v1` from:
  - exact decision question
  - bounded answer
  - confidence and confidence reasons
  - `must_include` obligations derived from global decision model and analyst adjudication
  - quantity obligations derived from the tightened quantity-binding stage
  - strongest counterweights
  - scope boundaries
  - cruxes
  - missing evidence
  - deterministic source trail
- Stop feeding raw packet internals to synthesis unless needed for source grounding.

Model responsibilities:

- Write natural decision analysis.
- Weigh evidence and explain implications.
- Use required retention phrases when they are supplied.

Code responsibilities:

- Assemble the clean contract.
- Append deterministic source list after synthesis.
- Validate memo against selected obligations only.

Artifacts:

- `decision_memo_contract.json`
- `decision_memo_contract_prompt.txt`
- `decision_memo_contract_synthesis_report.json`
- `decision_contract_source_judgment_lineage.json`

Validation:

- Final memo should reduce missing strict obligations to zero or produce explicit unresolved-obligation warnings.
- Readability should remain high without quantity stuffing.
- Contract lineage should show which existing model artifact supplied each obligation and quantity decision.

QA:

- Compare old writer-packet prompt versus clean-contract prompt on saved eggs artifacts.
- Use one non-eggs case before promoting.

Risks:

- Contract may omit source context needed to write faithfully.
- Mitigation: include source excerpts for `must_include` obligations and retain full packet for audit.

### 7. Targeted Obligation Resolution Repair

Purpose: make repair fix specific missing obligations rather than rewriting blindly.

Changes:

- Replace broad repair prompt with structured targeted repair.
- Repair packet includes:
  - missing obligation
  - source excerpt
  - required retention phrase
  - candidate insertion location
  - current memo paragraph context
  - whether the model may waive with reason
- Repair output includes:
  - `edits`
  - `resolved_obligation_ids`
  - `waived_obligation_ids`
  - `waiver_reasons`
  - `revised_memo`

Model responsibilities:

- Decide how to integrate or waive missing obligations.
- Produce targeted edits.

Code responsibilities:

- Validate structured repair output.
- Apply edits or use returned full memo only after validation.
- Recheck relevant obligations.
- Report unresolved obligations.

Artifacts:

- `targeted_obligation_repair_prompt.txt`
- `targeted_obligation_repair_raw.txt`
- `targeted_obligation_repair_report.json`

Validation:

- Repair is not considered improved unless it resolves, waives, or correctly demotes obligations.
- Quantity-only improvement does not count.

QA:

- Regression test from the strict writer-packet repair bug where quantity-only retention improved but missing obligations stayed constant.

Risks:

- Edit application may create markdown damage.
- Mitigation: keep existing markdown-structure validation and fallback to original memo when structure is damaged.

## Execution Order

1. Add an artifact inventory report over the latest eggs run showing which needed obligation fields are already present in `global_decision_model.json`, `analyst_adjudication.json`, and `analyst_quantity_binding_report.json`.
2. Implement `decision_obligation_plan_v1` as a reuse-first adapter over existing model outputs, in report-only mode.
3. Tighten the existing quantity-binding stage so it emits `quantity_obligation_plan_v1` and stops treating mechanically extracted quantities as semantic memo obligations.
4. Add deterministic `writer_packet_writeability_report_v1`, including conditional fallback reasons and model-call avoidance telemetry.
5. Run saved-artifact evaluation on eggs to confirm the reused judgments can build a cleaner contract with fewer mandatory obligations and quantities.
6. Run eggs and one non-eggs live case to calibrate report-only artifacts.
7. Switch strict retention to reused model-owned obligations and selected quantity obligations.
8. Update synthesis to use `decision_memo_contract_v1` with judgment lineage.
9. Replace broad repair with targeted obligation-resolution repair.
10. Add a narrow fallback adjudication call only for unresolved conflicts or missing high-salience dispositions found by telemetry.
11. Rerun eggs and one non-eggs case end to end.
12. Compare against the previous memo and the checked-in deep research baseline.

## Acceptance Criteria

- Packet has a manageable mandatory obligation count.
- Mandatory quantities are semantically selected, not raw-copied.
- The first implementation path reuses existing model judgments and avoids adding a broad new planner call.
- Any new model call is narrow, telemetry-routed, and justified by a missing or conflicting upstream judgment.
- Final memo is `decision_ready`, or gives explicit unresolved-obligation warnings with source-bound reasons.
- Memo answers the exact decision question.
- No generic code contains case-specific concepts such as egg, cholesterol, HEPA, COVID, or LHC.
- Eggs run improves over `artifacts/semantic/eggs_real_contract_e2e_20260711/` on:
  - missing obligations
  - missing mandatory quantities
  - readability
  - source grounding
  - decision usefulness
- At least one non-eggs run does not regress.
- Full test suite and maintainability gate pass.
- Completion audit reports model-call count before and after, including which calls were reused, removed, or added.

## Red-Team Checks

- **Failure:** model demotes inconvenient counterevidence.
  - Detection: every evidence unit must have a disposition and demotion reason; report high-priority demotions.
- **Failure:** reused upstream judgments are too noisy to support downstream obligations.
  - Detection: conflict report, missing disposition counts, and before/after comparison of final retention failures.
- **Failure:** quantity triage drops important numbers.
  - Detection: golden fixture where a key effect size is the crux.
- **Failure:** quantity binding remains too permissive and approves raw statistical clutter.
  - Detection: mandatory quantity count, max quantities per obligation, and reader-facing retention phrase coverage.
- **Failure:** packet becomes prettier but less faithful.
  - Detection: source-excerpt grounding and model-as-judge source-faithfulness check.
- **Failure:** validation becomes too permissive.
  - Detection: corrupted and missing-obligation fixtures.
- **Failure:** prompts overfit eggs.
  - Detection: non-eggs run and scan for domain-specific vocabulary in generic code.
- **Failure:** writeability gate gives false confidence.
  - Detection: compare gate output to final readiness across multiple saved runs.

## Generalizability Checks

- Use at least one case outside nutrition/health before declaring success.
- Reorder sources and confirm obligation planning is stable.
- Add irrelevant source material and confirm it is demoted with reasons.
- Rename source labels and confirm source grounding still works.
- Run with a different model backend and compare obligation/quantity triage disagreements.
- Keep semantic judgments model-owned and auditable; deterministic code should not encode domain-specific relevance.
- Confirm reuse-first adapters work on artifacts produced by a different backend, or report exactly which fields are missing.
- Confirm fallback adjudication is triggered by artifact quality, not by case domain.

## Completion Audit

When the plan is implemented, create `docs/plans/DECISION_GRADE_MEMO_OBLIGATION_TRIAGE_COMPLETION_AUDIT.md` with:

- Commits for each slice.
- Verification commands and results.
- Before/after comparison against `artifacts/semantic/eggs_real_contract_e2e_20260711/`.
- At least one non-eggs run summary.
- Remaining failure modes and deferred work.
- Whether the new writeability gate predicts final memo readiness.
- Model-call accounting: existing calls reused, new calls added, calls avoided, and net effect on runtime.
