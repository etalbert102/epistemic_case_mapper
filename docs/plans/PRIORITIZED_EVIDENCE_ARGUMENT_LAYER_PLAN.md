# Plan: Prioritized Evidence Argument Layer

## Objective

Prove the smallest synthesis-path intervention that can turn verified evidence into a compact prioritized argument before memo synthesis. The target end state is a decision memo that explains why the answer follows from the evidence, resolves the strongest counterweights, and gives each section a distinct job without losing source or quantity traceability. Production promotion comes only after an isolated experiment shows product-quality improvement and a non-eggs generalization win.

## Current Gap

The current pipeline preserves evidence identity better than it creates a decision argument. The memo can pass source, quantity, and retention checks while still repeating the same moderate-intake answer, high-intake boundary, subgroup concern, and LDL evidence across sections.

The likely bottleneck has two separable parts:

1. The synthesis interface is too broad and overlapping. Existing section prompts co-feed several semantic authorities, including `balanced_answer_frame`, `bluf_contract`, `decision_argument_contract`, analyst argument moves, decision-usefulness inventories, source weighting, reader judgments, source-bound atoms, evidence context, and retention requirements.
2. The available argument representation may not be strong enough. The repo already produces `decision_argument_contract_v1`, but it may be overinclusive and weakly prioritized.

The plan therefore starts with an ablation. First test whether a slim, disjoint projection of the existing argument contract improves the memo without another model call. Add a new prioritization model call only if that no-new-call path does not close the memo-quality gap.

## Non-Goals

- Do not add a polish-only pass as the primary fix.
- Do not let deterministic code make semantic priority judgments.
- Do not add domain-specific heuristics for eggs, nutrition, medicine, or any other current test case.
- Do not promote a new artifact only because it parses or reduces prompt size.
- Do not keep legacy packet paths as co-equal semantic authorities inside the experimental synthesis path.
- Do not globally promote a path that only improves eggs and regresses an unrelated case.
- Do not wire Arm C into production until Arm B has passed structurally and shown a repeated semantic gap.
- Do not treat LHC neutrality as sufficient for global promotion.

## Design Principles

- Separate prompt/routing cleanup from new model judgment so we can measure marginal value.
- One controlling argument view should feed each experimental synthesis path.
- Model judgment should decide salience, warrants, counterweight interpretation, redundancy, and section ownership when a model is used.
- Deterministic code should validate IDs, ownership integrity, derivable source and tuple bindings, lineage, prompt contents, and dependency structure.
- Source IDs and result tuple IDs should be derived from evidence IDs where possible, not repeated by the model.
- Quality gates should evaluate decision usefulness, not just pipeline validity.

## Inventory And Dependency Map

Before implementation, inspect these code paths and artifacts:

- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_decision_packet_stage.py`
  - current transition from analyst verification and evidence budgeting into `global_decision_model` and `decision_writer_packet`.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_decision_writer_packet.py`
  - current `global_decision_model_projection` adapter and memo-ready packet construction.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_memo_ready_prompt.py`
  - current section plan construction and broad prompt context.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_section_evidence_anchoring.py`
  - current evidence contract routing, especially roots that union required evidence across multiple semantic views.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_analyst_decision_modeling.py`
  - existing analyst-owned answer, source, quantity, counterweight, crux, and relevance judgments.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_analyst_schemas.py`
  - schema and Pydantic validation style.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_evidence_budget.py`
  - verified accounting and foreground/background evidence partitioning.
- Latest eggs memo and report artifacts:
  - `artifacts/truth_boundary_verification_eggs_live/replay_after_section_contract_fix_v3/memo.md`
  - `artifacts/truth_boundary_verification_eggs_live/replay_after_section_contract_fix_v3/report.json`
  - `artifacts/truth_boundary_verification_eggs_live/replay_after_section_contract_fix_v3/prompt.txt`
- Frozen eggs synthesis-stage inputs:
  - `artifacts/truth_boundary_verification_eggs_live/briefing/memo_ready_packet.json`
  - `artifacts/truth_boundary_verification_eggs_live/briefing/canonical_decision_writer_packet.json`
  - `artifacts/truth_boundary_verification_eggs_live/briefing/analyst_decision_model.json`
  - `artifacts/truth_boundary_verification_eggs_live/briefing/analyst_decision_model_verification_report.json`
  - `artifacts/truth_boundary_verification_eggs_live/briefing/evidence_budget.json`
  - `artifacts/truth_boundary_verification_eggs_live/briefing/evidence_accounting_report.json`
  - `artifacts/truth_boundary_verification_eggs_live/briefing/analyst_evidence_ledger.json`

Dependency order:

1. Analyst decision model remains the answer authority.
2. Analyst verifier remains the evidence-bound gate.
3. Evidence budget supplies verified accounting.
4. Arm B projects the existing `decision_argument_contract_v1` into slim disjoint section packets.
5. Arm C optionally adds a focused answer-frozen prioritization model call before the same projector.
6. Section synthesis writes only from the active argument section view.
7. Evaluation compares A, B, and C on memo quality and traceability.

## Three-Arm Ablation

### Arm A: Current Production Path

Purpose:

Freeze the current behavior as the baseline.

Changes:

- No code-path change.
- Save the latest prompt manifest, memo, report, backend settings, source map, decision question, and the actual synthesis-stage inputs.

Artifacts:

- `baseline_current_path/memo.md`
- `baseline_current_path/report.json`
- `baseline_current_path/prompt.txt`
- `baseline_current_path/run_metadata.json`
- `baseline_current_path/memo_ready_packet.json`
- `baseline_current_path/canonical_decision_writer_packet.json`
- `baseline_current_path/analyst_decision_model.json`
- `baseline_current_path/analyst_decision_model_verification_report.json`
- `baseline_current_path/evidence_budget.json`
- `baseline_current_path/evidence_accounting_report.json`
- `baseline_current_path/analyst_evidence_ledger.json`

Validation:

- Baseline artifacts are reproducible from the same frozen synthesis-stage inputs or clearly recorded as saved replay artifacts.

QA:

- Manual read records current failure modes:
  - repeated central answer;
  - repeated counterweight;
  - weak warrant explaining why the answer follows;
  - source weighting surfaced but not integrated into the argument.

Risks:

- Comparing against an unstable baseline can create false confidence.
- Mitigation: freeze run metadata before evaluating experimental arms.

### Arm B: Slim Existing-Argument Projection, No New Model Call

Purpose:

Test the simplest intervention first: make the existing `decision_argument_contract_v1` the sole argument-routing authority for section packets and remove overlapping prompt context.

Changes:

- Add an experimental slim-section adapter that projects from the existing `decision_argument_contract_v1`.
- Build section packets from:
  - immutable answer, confidence, and scope from the verified `analyst_decision_model.json`;
    - answer field: prefer `direct_answer` or `full_direct_answer` for the bounded answer, with `primary_answer` available only as the compact answer label;
    - confidence field: `confidence`;
    - scope fields: `decision_logic.scope_boundaries`;
    - overstatement limits: `decision_logic.do_not_overstate`;
  - owned argument moves;
  - compact calibration limits;
  - owned evidence contracts;
  - reference-only move summaries when explicitly available.
- Change evidence routing in the experimental path:
  - only primary-owner evidence is required in a section;
  - reference-only moves contain only `move_id` and `point`;
  - reference-only moves receive no evidence, source, quantity, or language-contract payload;
  - practical implication receives the immutable decision anchor and practical move; it receives no inferred dependency summaries because `decision_argument_contract_v1` has no dependency model.
- Suppress the default source-weighting section unconditionally in Arm B because `decision_argument_contract_v1` does not represent "source hierarchy is a decision crux."
- Remove from active experimental prompts:
  - `balanced_answer_frame`;
  - `bluf_contract`;
  - `analyst_decision_spine`;
  - broad `decision_usefulness` inventories;
  - `reader_judgment_packet`;
  - supplemental evidence inventories;
  - duplicated `required_points`, `evidence_context`, source-bound atoms, and retention requirements.
- Run Arm B outside production from frozen upstream artifacts. Do not modify `map_briefing_decision_packet_stage.py`, `map_briefing_decision_writer_packet.py`, `global_decision_model`, or production writer-packet construction in this slice.

Ownership resolver:

- Treat exact writer evidence IDs and upstream lineage references as different reference types.
- Exact writer evidence ID:
  - resolves only to the matching evidence contract;
  - zero matches is an `unknown_evidence_id` projection failure;
  - duplicate exact contracts for the same writer ID are a `duplicate_contract_id` projection failure.
- Upstream lineage reference:
  - applies to IDs such as `claim:*` and `relation:*`;
  - expands through `memo_ready_packet.evidence_items[].lineage.covered_evidence_item_ids` to every matching writer evidence contract;
  - zero matching writer contracts is an `unknown_lineage_reference` projection failure;
  - multiple matching writer contracts are valid and expected, not a failure.
- Ignore the source-weighting move when calculating normal section candidates.
- Compute section candidates after exact-ID and lineage-reference expansion.
- If a writer evidence contract appears in exactly one remaining move section, that section owns it.
- If it appears in multiple sections, use the contract's existing `primary_section` only if that section is among the candidates.
- Otherwise report `ambiguous_owner` and fail the projection.
- Define mandatory evidence from model-authored writer-item obligations, not deterministic role-derived requiredness:
  - `must_use: true`;
  - `obligation_level: must_include`;
  - explicit quantity retention marked `must_retain`;
  - explicit analyst/model inclusion status such as `must_use` or equivalent from the frozen writer packet.
- If a mandatory writer evidence contract is not referenced by any argument move after expansion, report `unowned_mandatory_evidence` and fail the projection.
- Do not reintroduce unowned evidence through retention, evidence-context, or source-bound roots.
- Do not invent dependency edges; `decision_argument_contract_v1` has no dependency model.

Frozen eggs B0 ownership expectation:

- `answer_evidence` mandatory owners: `decision_writer_item_001`, `decision_writer_item_002`, `decision_writer_item_003`, `decision_writer_item_011`.
- `counterweights` mandatory owners: `decision_writer_item_004`, `decision_writer_item_005`, `decision_writer_item_007`, `decision_writer_item_008`.
- Optional move-owned counterweight contracts include `decision_writer_item_006` and `decision_writer_item_009`.
- `practical_implication` owns no evidence contract unless its v1 move explicitly names evidence.
- `decision_writer_item_010` may remain unowned in Arm B because it is non-mandatory and only reached through the suppressed source-weighting move.
- `decision_writer_item_004` and `decision_writer_item_005` deliberately appear in both answer calibration and counterweight moves; their existing `primary_section` should resolve them to `counterweights`.

Arm B prompt/payload allowlist:

- Section packet keys allowed in B0/B1:
  - `schema_id`;
  - `section_id`;
  - `heading`;
  - `section_job`;
  - `reader_question`;
  - `decision_anchor`;
  - `calibration_limits`;
  - `owned_moves`;
  - `reference_moves`;
  - `evidence_expression_contracts`;
  - `section_local_evidence_jobs`;
  - `known_source_ids`;
  - `known_source_aliases`;
  - `citation_mode`.
- `decision_anchor` keys allowed:
  - `decision_question`;
  - `bounded_answer`;
  - `compact_answer`;
  - `confidence`;
  - `scope_boundaries`;
  - `do_not_overstate`.
- `owned_moves` keys allowed:
  - `move_id`;
  - `move_type`;
  - `point`;
  - `writing_job`;
  - `section_id`;
  - `evidence_item_ids`;
  - `quantities`;
  - `disposition`;
  - `would_change_if`.
- `reference_moves` keys allowed: exactly `move_id` and `point`.
- Disallowed prompt/payload roots include:
  - `balanced_answer_frame`;
  - `bluf_contract`;
  - `analyst_decision_spine`;
  - broad `decision_usefulness` inventories;
  - `reader_judgment_packet`;
  - `source_weighting_contract`;
  - `source_weighting_flow_audit`;
  - supplemental evidence inventories;
  - `required_points`;
  - `evidence_context`;
  - `source_bound_evidence_atoms`;
  - broad retention requirement roots.

Artifacts:

- `arm_b_slim_existing_argument/section_synthesis_packets.json`
- `arm_b_slim_existing_argument/section_prompt_manifest.json`
- `arm_b_slim_existing_argument/section_contract_overlap_report.json`
- `arm_b_slim_existing_argument/projection_evaluation_packet.json`
- `arm_b_slim_existing_argument/prompt_submission_audit.json`
- `arm_b_slim_existing_argument/warning_adjudication_report.json`
- `arm_b_slim_existing_argument/memo.md`
- `arm_b_slim_existing_argument/report.json`
- `arm_b_slim_existing_argument/comparison_to_current.json`

Validation:

- Active-path report shows `decision_argument_contract_v1` is the sole argument-routing authority for section packets.
- The analyst decision model remains the answer/scope authority; evidence contracts remain the factual and traceability authority.
- Final prepared prompts, not only serialized section packets, contain only allowed Arm B keys.
- Prompt auditing covers every string actually submitted to the model, including prompts rebuilt by `_prepare_sections()` and retry prompts produced by `_section_retry_prompt()`.
- Saved Arm B reports either include the submitted prompt text or include stable hashes plus an allowlist audit proving the submitted prompts contain no disallowed context.
- Required evidence ownership is disjoint across sections.
- Prompt-context audit confirms legacy semantic frames are absent from experimental section payloads.
- Source IDs and result tuple IDs are derived deterministically from owned evidence IDs.
- Citation and quantity binding do not regress relative to Arm A.
- There are zero unknown exact IDs, unknown lineage references, duplicate exact contract IDs, ambiguous owners, missing required evidence IDs, source mismatches, and unsupported quantities.
- Every mandatory evidence contract has exactly one owner or produces an explicit projection failure.
- The intersection of required evidence IDs across all Arm B section packets is empty.
- Practical implication receives no evidence contracts unless its owned move explicitly references them.
- Source-binding and priority-quantity warnings have explicit dispositions: `fixed`, `accepted_with_reason`, `baseline_only`, `arm_b_regression`, or `requires_upstream_fix`.
- Arm B is not considered complete while any warning disposition is `unadjudicated`.

QA:

- Replay eggs with identical backend and decoding settings.
- Compare Arm A vs Arm B on:
  - section distinctness;
  - repeated central claim count;
  - counterweight repetition;
  - load-bearing evidence explanation;
  - factual and quantity correctness;
  - source-binding warnings;
  - prompt tokens and latency.
- Treat current source-binding and priority-quantity warning classes as adjudication targets rather than acceptable baseline noise.
- If the backend cannot use a fixed seed, run at least three synthesis samples per arm before attributing quality differences to representation rather than sampling noise.

Implementation slices:

- B0 deterministic projection:
  - load frozen synthesis-stage artifacts;
  - verify the analyst report is accepted and decision question agrees across frozen inputs;
  - verify all writer evidence IDs are unique;
  - build exact-ID and lineage-reference indexes;
  - confirm lineage fan-out is preserved;
  - produce exactly three section packets: `answer_evidence`, `counterweights`, and `practical_implication`;
  - assert the frozen eggs ownership expectation above;
  - render or intercept prepared prompts with a fake backend;
  - force one retry path so `_section_retry_prompt()` submissions are audited;
  - verify default production section-plan behavior is unchanged.
- B1 live synthesis experiment:
  - run Arm A and Arm B from the same frozen inputs and backend settings;
  - collect three samples per arm when fixed-seed reproducibility is unavailable;
  - adjudicate every source-binding and priority-quantity warning;
  - compare memo quality with paired or blinded review.
- Arm C remains deferred until B1 shows zero structural failures plus the same named semantic deficiency in at least two Arm B synthesis runs under frozen inputs.

Risks:

- The existing argument contract may be too weak, so slim projection may only make a shorter weak memo.
- Mitigation: treat this as a stage-value test. If Arm B cleans repetition but leaves shallow warrants, proceed to Arm C.

### Arm C: Focused Prioritization Model Call Plus The Same Slim Projector

Purpose:

Measure whether a new model call adds decision-quality value beyond prompt cleanup.

Changes:

- Add an answer-frozen prioritization model call after:
  - analyst decision model;
  - analyst decision model verifier;
  - evidence budget.
- It replaces `global_decision_model` and `decision_writer_packet` for active synthesis in this experimental path. Those older paths remain only as Arm A baseline or rollback.
- Initially run Arm C outside production from frozen `analyst_decision_model`, verifier, evidence-budget, and ledger artifacts. Do not wire it into `map_briefing_decision_packet_stage.py` until Arm C wins the experiment.
- The call receives only:
  - analyst answer, confidence, scope, cruxes, update triggers, and overstatement limits;
  - compact verified foreground and counterweight evidence records;
  - source hierarchy or source-weight judgments already present in the verified analyst model;
  - quantity relevance judgments and result tuple bindings already available at that point;
  - explicit background or routed-away accounting rows.
- If model source-weighting currently occurs later in the pipeline, do not rely on it in the first Arm C slice unless it is moved earlier explicitly.

The model output should include only semantic choices that are not derivable:

- `argument_thesis`
- ordered `moves`
- `proposition`
- `warrant`
- `decision_effect`
- optional `alternatives_discriminated`
- conditional `counterweight_disposition`
- `evidence_item_ids`
- `primary_section`
- `depends_on_move_ids`
- `limitations`
- `required`
- `evidence_accounting`
- `planning_gaps`

Fields derived by deterministic code, not model output:

- `schema_id`
- `input_lineage`
- `source_ids`
- `result_tuple_ids`
- `section_plan`
- immutable answer/confidence envelope

Artifacts:

- `arm_c_prioritized_argument/prioritized_evidence_argument.json`
- `arm_c_prioritized_argument/prioritized_argument_verification_projection_report.json`
- `arm_c_prioritized_argument/section_synthesis_packets.json`
- `arm_c_prioritized_argument/section_prompt_manifest.json`
- `arm_c_prioritized_argument/memo.md`
- `arm_c_prioritized_argument/report.json`
- `arm_c_prioritized_argument/comparison_to_arm_b.json`

Validation:

- The planner cannot change analyst answer or confidence.
- All evidence IDs are known.
- Source IDs and tuple IDs derived from selected evidence match verified ledger data.
- Move IDs are unique.
- Dependencies are acyclic.
- Each required evidence item has one primary owner.
- Foreground and counterweight evidence is owned, appendixed, or explicitly demoted with rationale.
- Practical action moves name dependencies, but semantic action support remains a review/evaluation check rather than a deterministic proof.

QA:

- Fixture with quantitative evidence.
- Fixture with qualitative evidence and no result tuples.
- Fixture with redundant evidence that should be demoted.
- Fixture with counterweight evidence that must be explicitly disposed or marked unresolved.

Risks:

- The new call could create another unused artifact.
- Mitigation: Arm C must use the same slim projector, and active-path telemetry must prove section packets derive from the prioritized argument.
- The model may produce plausible but shallow warrants.
- Mitigation: compare against Arm B; if it does not improve decision usefulness, do not promote.

Authorization gate:

- If Arm B has projection or traceability failures, fix Arm B and do not authorize Arm C.
- If Arm B results vary across synthesis samples, repeat or stabilize the evaluation and do not infer a representation gap from one sample.
- Authorize Arm C only if Arm B has zero structural projection failures and paired review identifies the same semantic deficiency in load-bearing selection, warrant quality, or counterweight force.

## Deterministic And Model Responsibilities

Deterministic code owns:

- schema parsing;
- answer/confidence freezing;
- known evidence ID checks;
- exact writer evidence ID resolution;
- upstream lineage-reference expansion into writer evidence contracts;
- derivable source ID and result tuple ID binding;
- move uniqueness;
- dependency-cycle detection;
- section ownership integrity;
- prompt-context audits;
- final prepared prompt allowlist audits, including retry prompts;
- citation projection;
- telemetry and comparison reports.

Model judgment owns:

- which evidence is load-bearing;
- which evidence is redundant or background;
- the warrant connecting evidence to answer;
- how counterweights affect the answer;
- whether source hierarchy is itself a decision crux;
- section ownership when Arm C is active;
- planning gaps or unresolved tensions.

Report-only semantic checks own:

- action support adequacy;
- counterweight disposition adequacy;
- unsupported causal overstatement;
- whether a demotion seems questionable.
- thesis drift between a model-produced `argument_thesis` and the frozen analyst answer.
- whether a demotion rationale is justified rather than merely present.

These are not deterministic blockers until calibrated.

## Evaluation Design

Use a frozen evidence base and identical backend/settings where possible.

Primary comparison:

- Arm A vs Arm B: does slim projection improve the memo without new inference?
- Arm B vs Arm C: does the new prioritization call add marginal value?

Quantitative diagnostics:

- prompt character/token size;
- call count and latency;
- evidence reuse and cross-section overlap;
- repeated central claim count;
- source-binding warnings;
- quantity-binding warnings;
- missing mandatory evidence;
- untagged high-risk sentences;
- selected move retention;
- source-weighting surfacing where source hierarchy is relevant.

Decision-quality rubric:

- Answers the decision question directly.
- Identifies the load-bearing evidence.
- Explains why the answer follows from that evidence.
- Resolves or preserves counterweights with the right force.
- Distinguishes scope boundaries from answer reversals.
- Gives each section a distinct role.
- Avoids generic restatement.
- Preserves factual, source, and quantity correctness.
- Helps a reader decide what to do or how to update.

Comparison protocol:

- Use side-by-side or blinded labels where practical.
- Record the reviewer identity: human, model-as-judge, or both.
- Treat prompt-size reduction and evidence-reuse reduction as diagnostics, not promotion criteria.
- Require no traceability regression.
- Use factual error, source or quantity regression, unsupported causal overstatement, or unsupported action advice as hard vetoes.
- Require at least one paired/blinded review when deciding whether Arm B or Arm C improved decision usefulness.

## Execution Order

1. Freeze Arm A baseline artifacts, synthesis-stage inputs, and metadata.
2. Implement B0 deterministic projection as an isolated experiment behind an explicit flag or command, not as a production route.
3. Verify B0 on eggs from frozen `memo_ready_packet.json`, `canonical_decision_writer_packet.json`, verified analyst model, verifier report, evidence budget, and ledger artifacts without live model synthesis.
4. Commit B0 only after resolver, ownership, prompt-submission audit, allowlist, and unchanged-production-path tests pass.
5. Implement B1 live synthesis evaluation only after B0 passes.
6. Run Arm A and B1 from the same frozen inputs and backend settings.
7. Compare Arm A vs B1.
8. If B1 closes the major gap, stop and promote only after unrelated-case validation.
9. If B1 passes structurally but repeatedly remains shallow on warrants, load-bearing selection, or counterweight force, implement Arm C focused prioritization call as an experiment from frozen artifacts.
10. Run Arm C on eggs using the same slim projector.
11. Compare B1 vs Arm C.
12. Run the winning experimental path on LHC as the first unrelated case.
13. If LHC improves and traceability holds, consider promotion.
14. If LHC is neutral, keep the path experimental and test another differently shaped case.
15. If LHC regresses, keep the path experimental and diagnose the regression rather than adding an applicability trigger.

## Acceptance Criteria

Pipeline validity:

- B0 produces section packets, prompt manifest, projection evaluation packet, prompt-submission audit, and report without a live model call.
- B0 produces exactly these section IDs: `answer_evidence`, `counterweights`, and `practical_implication`.
- B0 records frozen input hashes and verifies they match the files actually loaded.
- B0 verifies the analyst decision model verifier is accepted.
- B0 verifies the decision question matches across memo-ready packet, analyst model, evidence budget, and ledger.
- B0 confirms all writer evidence IDs are unique.
- B0 confirms lineage fan-out is preserved rather than reported as ambiguity.
- B0 verifies the frozen eggs ownership expectation listed in Arm B.
- B0 verifies `source_weighting` is absent from packets, prepared prompts, and model-call manifests.
- B0 verifies the practical implication section has zero evidence contracts when its v1 move has no evidence IDs.
- B1 produces memo, synthesis report, warning adjudication report, and comparison artifacts.
- Arm B active prompts use `decision_argument_contract_v1` as the only argument-routing authority, with analyst-model answer/scope fields and evidence contracts as the only non-routing authorities.
- Arm B loads frozen synthesis-stage inputs, not only the saved memo/prompt/report.
- Arm B final prepared prompts pass the allowed-key audit.
- Arm B prompt-submission audit captures or hashes every actual prompt sent to the model, including retry prompts.
- Arm C, if implemented, produces a prioritized argument and verification/projection report.
- All referenced evidence IDs are known.
- Source and tuple bindings are derived deterministically.
- Required evidence ownership is disjoint across sections.
- Citation and quantity correctness do not regress.
- Unknown exact IDs, unknown lineage references, duplicate exact contract IDs, ambiguous owners, unowned mandatory evidence, source mismatches, unsupported quantities, and missing required evidence are explicit failures.
- Current source-binding and priority-quantity warning classes are reported and adjudicated, not silently treated as acceptable.

Product quality:

- Arm B is better than Arm A or provides clear evidence that prompt cleanup alone is insufficient.
- Arm C is authorized only if B1 has zero structural failures and the same named semantic deficiency appears in at least two Arm B synthesis runs under frozen inputs and paired review; Arm C is promoted only if it is better than Arm B on decision usefulness.
- The winning path does not merely shorten prompts; it improves the reasoning read of the memo.
- An unrelated LHC replay improves on decision quality and traceability before global promotion. LHC neutrality keeps the path experimental.

Operational quality:

- Added call count and latency are recorded.
- Prompt-size and overlap diagnostics are recorded but not treated as sufficient success.
- Failures are visible rather than silently falling back to the older path.
- At least three synthesis samples per arm are used when fixed-seed reproducibility is unavailable.

## Red-Team Checks

- Failure mode: Arm B appears successful only because it omits evidence.
  - Detection: compare factual, source, quantity, and missing-mandatory reports against Arm A.
- Failure mode: Arm B silently reintroduces old context at runtime.
  - Detection: audit every submitted prompt from `_prepare_sections` and `_section_retry_prompt`, not only section packet JSON or combined comparison prompts.
- Failure mode: Arm B treats lineage references as exact IDs or treats valid lineage fan-out as an alias collision.
  - Detection: exact writer IDs resolve one-to-one; upstream `claim:*` and `relation:*` references expand through writer-item lineage; zero matches fail, multiple lineage matches are allowed before ownership resolution.
- Failure mode: Arm B hides unresolved writer-item, claim, or relation references.
  - Detection: unknown exact IDs, unknown lineage references, and duplicate exact contract IDs fail projection.
- Failure mode: Arm B invents dependencies that v1 does not support.
  - Detection: reference-only moves may include only `move_id` and `point`; no invented dependency edges.
- Failure mode: Arm B reduces repetition but produces a shallow memo.
  - Detection: decision-quality rubric checks whether warrants explain why the answer follows.
- Failure mode: Arm C creates another artifact that does not control synthesis.
  - Detection: active-path report proves section packets derive from Arm C artifact.
- Failure mode: Arm C overrules the analyst answer.
  - Detection: answer/confidence freeze blocks drift.
- Failure mode: the model demotes important counterevidence.
  - Detection: every foreground/counterweight item must be accounted for; questionable demotions are surfaced for semantic review.
- Failure mode: deterministic validation overclaims semantic proof.
  - Detection: action support and counterweight adequacy remain report-only unless a calibrated semantic reviewer is added.
- Failure mode: eggs-specific success hides poor generalization.
  - Detection: LHC must improve before promotion; if LHC is neutral, test another differently shaped case; COVID origins is the next adversarial unresolved-evidence check.

## Generalizability Checks

- Reordering evidence should preserve section ownership and selected moves when model nondeterminism is controlled or evaluated qualitatively.
- Renaming source labels should not change deterministic validation or citation projection.
- Duplicating support should produce redundancy accounting or trace-only handling, not duplicate prose.
- Cases without quantities should still produce valid sections.
- Cases with unresolved counterweights should preserve uncertainty rather than force a clean thesis.
- Cases where source hierarchy is not a crux should not get a standalone source-weighting section.
- Cases where source hierarchy is a crux should surface it as part of the relevant argument move or a justified standalone section in Arm C or later, not Arm B.

## Promotion Rule

Do not promote after eggs-only success. Promote only after:

- the winning path beats the current path on eggs;
- Arm C, if included, beats Arm B enough to justify the added model call;
- citation and quantity traceability do not regress;
- LHC improves on decision quality;
- active prompts are controlled by one argument authority;
- legacy semantic frames are absent from active synthesis context.

## Completion Audit

The plan is complete only when the repo contains:

- frozen Arm A baseline artifacts;
- frozen synthesis-stage input copies;
- Arm B slim-projection implementation and evaluation;
- Arm C implementation only if Arm B leaves a demonstrated gap;
- comparison artifacts for A vs B and, if applicable, B vs C;
- prompt-context audits showing one active argument authority;
- final prepared prompt allowlist audits for all submitted initial and retry prompts;
- traceability reports showing no citation or quantity regression;
- at least one LHC generalization check that improves, not merely passes neutrally;
- a final memo-quality assessment explaining whether the prioritized argument path improved decision usefulness enough to promote.
