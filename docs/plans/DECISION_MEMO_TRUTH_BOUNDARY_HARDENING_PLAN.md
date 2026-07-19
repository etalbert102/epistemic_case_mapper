# Plan: Decision Memo Truth-Boundary Replacement And Ablation

## Objective

Make the pipeline reliably produce decision-useful memos by replacing the current lossy stack of overlapping semantic authorities with one evidence-bound analyst decision model, immutable source facts, deterministic writer views, and monotonic readiness lineage.

The target end state is not more polish. It is a memo pipeline where:

- source truth is stable and inspectable;
- model judgment is concentrated in the analyst stage and verified before writing;
- writer prompts receive only the relevant slice of that judgment;
- readiness cannot pass after upstream failure;
- reviewers can tell which evidence was load-bearing, which was considered but relegated, and which source universe the memo covers.

This revised plan incorporates the architectural review in `artifacts/codex_56_pipeline_eval_latest.md` and the `gpt-5.6-sol` critique in `artifacts/codex_56_truth_boundary_plan_review.md`.

## Current Gap

The architecture is directionally right: source map first, analyst judgment second, writing third. The implementation problem is that analyst judgment is projected through too many competing artifacts while hard source invariants remain weak.

Observed failure classes:

- Quantitative evidence can lose estimate-interval-endpoint identity and recombine numbers incorrectly.
- QA/readiness can certify a memo even when synthesis, repair, or polish failed upstream.
- Useful analyst judgment exists but is diluted across `global_decision_model`, `decision_writer_packet`, `memo_ready_packet`, `canonical_decision_writer_packet`, `balanced_answer_frame`, `argument_spine`, `bluf_contract`, `reader_judgment_packet`, and related views.
- The active source universe can diverge from the reader-visible source list.
- Evidence accounting rewards coverage where the reader memo needs prioritization.
- Deterministic keyword logic still makes semantic role/direction decisions in parts of the production path.
- Automated QA is better at artifact structure and lexical retention than semantic correctness.

## Non-Goals

- Do not add a new independent `AnalystDecisionContract` artifact on top of the existing stack.
- Do not add another polish-only stage as the main fix.
- Do not restore obsolete packet-first, old section-rewrite, or fallback memo paths.
- Do not add domain-specific egg, nutrition, medical, or source-family heuristics.
- Do not make broad semantic decisions with deterministic keyword logic.
- Do not optimize against the eggs case alone.
- Do not promote broad semantic blockers until they are calibrated on at least one unrelated case.

## Design Principles

- Upgrade the existing `AnalystDecisionModel` into the canonical v2 contract rather than creating a parallel contract.
- Source truth owns stable IDs, source spans, active evidence universe, and immutable result tuples.
- The analyst model owns semantic judgment: evidence role, source weight, independence implications, counterweight disposition, cruxes, scope, confidence, and practical implications.
- Deterministic code owns projection, accounting, lineage, citations, source-list rendering, hard invariant validation, and artifact packaging.
- Downstream writer views are one-way projections from source truth plus `AnalystDecisionModel v2`.
- Compatibility objects require removal criteria and must not remain independent semantic authorities.
- Readiness is append-only and monotonic: later formatting cannot erase fatal upstream status.

## Phase Zero Baseline

Before implementation, freeze a current-HEAD baseline so later changes are measured against the actual current system, not an older saved memo.

Required baseline record:

- commit SHA;
- dirty-worktree status;
- backend/model;
- prompt versions;
- case/region/question;
- source file hashes or map input hash;
- run configuration;
- memo path;
- lineage/readiness reports;
- quantity/source-universe/counterweight observations;
- current model-call count, prompt size, latency if available.

Artifacts:

- `truth_boundary_phase_zero_baseline.json`
- fresh current-HEAD eggs replay or documented backend blocker
- one compact manual memo-quality note

Gate:

- No broad refactor begins until the baseline exists.

### 2026-07-18 Bounded-Slice Execution Record

This execution is limited to phase zero plus the two P0 truth-boundary fixes and
their focused tests. The result-level quantity tuple and `AnalystDecisionModel
v2` workstreams remain out of scope unless these slices are complete and
verified first.

Required-reading implications recorded before implementation edits:

- `README.md`: the useful output is auditable decision structure rather than a
  polished narrative, so a reader-visible memo must not be labeled ready when
  its synthesis lineage is unaccepted.
- `docs/archive/internal/WORKFLOW_SPEC.md`: synthesis must consume preserved
  structure, so final readiness should carry upstream stage state rather than
  re-derive success from the final prose.
- `docs/protocols/epistemic_case_map_v0.md`: sources and claims require stable,
  recoverable identity; the reader source list must therefore be restricted to
  active cited-source identities and must not infer the whole case universe.
- `docs/archive/internal/CODEX_GOAL_FLF_PROTOTYPE_CRITERIA.md`: verification must
  be reproducible, residual risks must be explicit, and agent review must not be
  described as human review.
- `docs/archive/internal/plans/flf_winning_submission_worked_regions_plan.md`:
  the eggs worked region intentionally uses seven required sources rather than
  the full case corpus, making it the concrete regression shape for source-list
  over-expansion.
- `data/cases/eggs/case.yaml`: eggs is source-grounded and has twelve recorded
  sources, but remains draft/in progress; the baseline and tests must preserve
  that scope and review-status distinction.
- This plan: phase zero is a gate before broad refactoring, and unaccepted or
  unknown synthesis/repair/polish lineage must fail closed even when a readable
  memo exists.

Execution roles for this slice: `developer` for implementation and test edits,
`verifier` for focused pytest and artifact checks, and `reviewer` for manual
inspection of baseline lineage/source-universe observations. This is agent
review only, not human review.

Initial worktree note: pre-existing edits in
`map_briefing_gap_closer_experiment.py`,
`map_briefing_section_evidence_anchoring.py`,
`tests/test_memo_gap_closer_experiment.py`, and the untracked
`map_briefing_role_bound_citations.py` are user-owned and must not be reverted or
folded into these slices.

Bounded-slice outcome:

- Slice 1 — complete with documented replay limitation. Created
  `artifacts/truth_boundary_phase_zero/truth_boundary_phase_zero_baseline.json`
  and `truth_boundary_baseline_memo_review.md` from the latest complete eggs
  replay. The record contains hashes, configuration, model/backend, prompt and
  runtime telemetry, manual observations, and the fact that the saved run
  predates current HEAD. A clean live replay was blocked because the managed
  sandbox cannot reach the local Ollama endpoint.
- Slice 2 — complete. Final lineage now records packet, synthesis, repair,
  polish, and presentation acceptance. Missing, unknown, or explicitly false
  acceptance fails closed; a truly unneeded repair is recorded as not
  applicable. Inspectable reader output is reported separately from
  `decision_ready`, and blocked synthesis stops later semantic stages.
- Slice 3 — complete. Reader source rendering uses active source identities
  from the memo-ready packet, explicit active cited IDs, or packet rows marked
  active. If no active identity set exists, an existing/model-provided source
  section is removed instead of expanding to all case sources.
- Slice 4 — complete. Focused unit and integration regressions cover unknown and
  unaccepted statuses, output/readiness separation, the seven-active versus
  twelve-case-source shape, unavailable active-source identity, and final
  artifact paths.

Verification log:

- `PYTHONPATH=src python3 -m pytest -q tests/test_map_briefing_readiness.py tests/test_reader_memo_metadata.py tests/test_measurement_audit.py tests/test_map_briefing.py tests/test_map_briefing_decision_contracts.py`
  passed: 52 tests.
- `python3 -m json.tool artifacts/truth_boundary_phase_zero/truth_boundary_phase_zero_baseline.json`
  passed.
- `PYTHONPATH=src python3 -m py_compile` on the five changed production modules
  passed.
- Saved-eggs fault replay through the new builders produced
  `lineage_status=blocked`, `decision_ready=false`,
  `reader_output_available=true`, and exactly seven reader source rows.
- The first attempted command using `./.venv/bin/python` did not run because the
  repository has no local `.venv`; the documented `python3` fast path was used.

Residual risks for these slices:

- No fresh current-HEAD live model replay was possible, so production artifact
  generation of `final_lineage_report.json` and `source_universe_report.json`
  is verified by fake-backend integration runs and saved-report replay rather
  than a new eggs run.
- Source-list identity currently relies on existing packet-to-original source ID
  projection. Full evidence-universe propagation from CLI context remains a
  later workstream.
- These deterministic gates prevent false readiness but do not validate the
  memo's result-level quantity semantics or counterweight judgment.

Deferred work:

- Owner: future truth-boundary implementation slice
  Reason: the user limited this run to the safest P0 slices.
  Risk: estimate/interval/endpoint identity can still drift or recombine.
  Next action: execute Workstream 3 with result-level records and mutation tests.
- Owner: future truth-boundary implementation slice
  Reason: `AnalystDecisionModel v2` depends on the P0 baseline and gates completed
  here and was explicitly excluded from this bounded run.
  Risk: multiple derived semantic authorities and missing counterweight
  disposition remain.
  Next action: begin Workstream 4 only after a fresh replay is available and the
  quantity slice is complete.

## Replacement Architecture

Target flow:

```text
Evidence store
  source IDs + source spans + evidence units + result-level quantity tuples + evidence universe
        |
        v
AnalystDecisionModel v2
  answer, confidence, evidence dispositions, source hierarchy, dependency notes,
  counterweight dispositions, cruxes, update triggers, quantity decisions,
  do-not-overstate constraints, practical implications, appendix accounting
        |
        v
Evidence-bound verifier
  checks analyst moves against source/evidence/tuple IDs before writing
        |
        v
Deterministic writer views
  section-local packets derived from the verified analyst model
        |
        v
Memo writer
  section-local synthesis + bounded coherence pass
        |
        v
Append-only lineage/readiness
  hard invariant gates + report-only semantic QA + compact review packet
```

Primary owned integration points:

- `src/epistemic_case_mapper/cli_semantic.py`
- `src/epistemic_case_mapper/pipeline/map/staged_semantic_pipeline_runner.py`
- `src/epistemic_case_mapper/pipeline/map/staged_semantic_whole_doc.py`
- `src/epistemic_case_mapper/pipeline/map/staged_semantic_evidence_units.py`
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_analyst_decision_modeling.py`
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_analyst_schemas.py`
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_decision_packet_stage.py`
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_decision_writer_packet.py`
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_memo_ready_prompt.py`
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_memo_ready_section_synthesis.py`
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_final_outputs.py`
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_readiness.py`
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_memo_metadata.py`

## Workstreams

### 1. Phase-Zero Replay And Evaluation Harness

Purpose: ensure later changes are judged against current HEAD.

Changes:

- Add a small script or CLI helper to record the baseline metadata above from a saved run or fresh replay.
- Include a manual review template for memo quality observations.

Artifacts:

- `truth_boundary_phase_zero_baseline.json`
- `truth_boundary_baseline_memo_review.md`

Validation:

- Baseline references the current commit and exact artifact paths.
- Baseline records whether the run used full case or worked region.

### 2. Monotonic Readiness And Source-List P0 Fixes

Purpose: fix high-severity false acceptance and source-universe mismatch before deeper refactors.

Changes:

- Require `accepted == true` for synthesis readiness unless an explicitly named recovery stage has its own accepted semantic verification.
- Treat unknown unaccepted statuses as unaccepted by default.
- Pass synthesis, repair, polish, packet, and presentation lineage into final readiness.
- Separate `reader_output_available` from `decision_ready`.
- Stop source-list fallback from using all case sources when active cited sources are unavailable.
- Make cited-source list a subset of active source trail.

Artifacts:

- `final_lineage_report.json`
- updated `final_decision_readiness_report.json`
- `source_universe_report.json`

Validation:

- Fault-inject unaccepted synthesis statuses and verify no `decision_ready`.
- Saved blocked-synthesis eggs artifact must fail readiness.
- Seven-source worked-region memo must not list all twelve case sources.

### 3. Replace Loose Quantity Tuples With Result-Level Records

Purpose: prevent invalid recombination of estimates, intervals, endpoints, and populations.

Changes:

- Replace the existing loose `source_quantity_tuples` meaning with result-level records.
- Do not create a parallel tuple schema unless it is explicitly a migration artifact with deletion criteria.
- Update whole-document source-card schema to ask for result-level statistical records where present.
- Carry stable content/source-anchor tuple IDs through evidence units, analyst quantity decisions, memo obligations, writer views, and final validation.
- Let model extraction interpret tuple semantics; deterministic code validates identity, quote/span, propagation, and non-recombination.

Required tuple fields:

- `result_tuple_id`
- `source_id`
- `claim_id` or evidence-unit ID
- `population`
- `exposure_or_intervention`
- `comparator`
- `endpoint`
- `design`
- `estimate_type`
- `estimate`
- `interval_type`
- `interval_low`
- `interval_high`
- `units`
- `time_horizon`
- `source_quote`
- `source_span`

Artifacts:

- upgraded `source_quantity_tuples.json` or renamed canonical tuple artifact
- `quantity_tuple_binding_report.json`
- `quantity_tuple_mutation_eval.json`

Validation:

- Correct HR/RR/CI pairings pass independently.
- Swapped intervals, detached endpoints, substituted estimate types, and biomarker-to-outcome mismatches fail.
- Qualitative-only cases pass with a non-applicable tuple report.

### 4. Upgrade `AnalystDecisionModel` To Canonical v2

Purpose: make one existing model-owned object the semantic authority.

Changes:

- Extend `AnalystDecisionModel` schema rather than adding `AnalystDecisionContract`.
- Add explicit fields for:
  - active evidence universe reference;
  - evidence dispositions and foreground/background budgeting;
  - result tuple IDs;
  - source hierarchy and dependency notes;
  - counterweight disposition;
  - cruxes and update triggers;
  - practical implications with source-backed action basis;
  - confidence and confidence reasons;
  - do-not-overstate constraints;
  - appendix/background accounting.
- Mark `global_decision_model`, `balanced_answer_frame`, `argument_spine`, `bluf_contract`, and similar artifacts as derived compatibility views or remove their writer authority.
- Update writer packet construction to read from `AnalystDecisionModel v2` first.

Artifacts:

- `analyst_decision_model.json` with v2 schema fields
- `analyst_decision_model_v2_quality_report.json`
- `semantic_authority_audit.json`

Validation:

- No production writer prompt has multiple independent controlling answer frames.
- Counterweight disposition, confidence, scope, and do-not-overstate constraints survive into section views.
- Existing tests updated to assert v2 schema behavior.

### 5. Add Evidence-Bound Analyst Verifier

Purpose: prevent bad analyst judgment from becoming authoritative.

Changes:

- Add a verifier stage immediately after `AnalystDecisionModel v2`.
- Verify each primary evidence move, counterweight disposition, action recommendation, causal phrase, confidence/scope claim, and result tuple reference against source/evidence/tuple IDs.
- Use deterministic checks for IDs, tuple consistency, and source-span existence.
- Use model judgment for semantic entailment, overstatement, action support, and counterweight disposition adequacy.
- Block writing when verifier finds fatal defects; report noisy semantic checks until calibrated.

Artifacts:

- `analyst_decision_model_verification_report.json`
- `analyst_verifier_prompt.txt`
- `analyst_verifier_raw.txt`

Validation:

- Known flawed analyst claims such as unsupported “safety ceiling” or invented monitoring advice are flagged.
- Clean controls do not trigger corresponding fatal defects.
- Fatal verifier status prevents memo synthesis.

### 6. Evidence Universe Propagation

Purpose: make case scope and source coverage explicit from the CLI through final memo.

Changes:

- Pass `region_id`, full-case/worked-region status, required sources, analyzed sources, omitted sources/reasons, selected chunks, and permitted generalization into `run_map_briefing`.
- Build `evidence_universe` from run context, not final prose.
- Distinguish analyzed sources from cited sources.
- Consume case metadata such as `source_independence.md` as explicit input, model context, or report-only hints with clear precedence.

Artifacts:

- `evidence_universe.json`
- `source_dependency_report.json`
- `active_cited_source_report.json`

Validation:

- Worked-region and full-case runs are visibly distinguishable.
- Reader source list equals active cited sources.
- Source dependency uncertainty is represented as `unknown` rather than invented independence.

### 7. Evidence Budgeting And Accounting

Purpose: reduce checklist prose and force explicit prioritization without hiding evidence.

Changes:

- Use analyst model judgment to classify evidence into load-bearing, counterweight, scope/crux, quantitative anchor, appendix/background, and routed-away categories.
- Deterministic code accounts for all evidence but only foregrounded evidence becomes writer obligation.
- Fixed foreground counts are telemetry only, not pass/fail rules.
- Retention checks should not fail for appendix-only evidence that is explicitly accounted for.

Artifacts:

- `evidence_budget.json`
- `evidence_accounting_report.json`
- `foreground_evidence_report.json`

Validation:

- Foreground evidence is smaller than total accounted evidence unless the analyst explicitly justifies broad foregrounding.
- Omitted-but-accounted evidence is visible in audit artifacts.
- Memo repetition decreases without losing load-bearing evidence.

### 8. Section Synthesis From Verified Contract Views

Purpose: improve narrative ownership while retaining traceability.

Changes:

- Build section-local packets from verified `AnalystDecisionModel v2`, active evidence atoms, result tuple IDs, and source IDs.
- Use default section roles:
  - best current answer and why;
  - what bounds or could change it;
  - practical implication.
- Allow the analyst model to alter section roles for different answer shapes.
- Integrate source weighting where evidence is used instead of forcing a standalone source-weighting inventory unless the analyst model requires it.
- Keep final coherence pass bounded: it can improve transitions and remove repetition but cannot introduce new evidence.

Artifacts:

- `section_contract_packets/*.json`
- `section_synthesis_report.json`
- `section_repetition_report.json`

Validation:

- No section prompt receives competing answer authorities.
- Counterweights appear in the appropriate section with disposition.
- Source weighting is attached to claims rather than presented only as an inventory.

### 9. Retire Legacy Semantic Authorities And Deterministic Semantic Fallbacks

Purpose: ensure the replacement architecture actually replaces the old system.

Changes:

- Audit production writer dependencies on:
  - `global_decision_model`
  - `balanced_answer_frame`
  - `argument_spine`
  - `bluf_contract`
  - `reader_judgment_packet`
  - deterministic role/direction helpers
- Remove, demote, or mark as derived any artifact that can contradict `AnalystDecisionModel v2`.
- Retire deterministic semantic fallbacks from production paths:
  - `_typed_fields`
  - `_lexically_supported`
  - `_decision_factor`
  - `_direction`
  - `_decision_role`
  - `_finding_signal`
  - deterministic quantity memo-use approval
- If model semantic judgment is unavailable, fail loudly or mark evidence unclassified.

Artifacts:

- `semantic_authority_audit.json`
- `legacy_semantic_fallback_retirement_report.json`

Validation:

- Production writer does not consult retired authorities as controlling semantic input.
- Tests prove unavailable model judgment does not silently trigger keyword semantic classification.

### 10. Relation-Value And Reviewer-Effort Ablations

Purpose: prove expensive or complex stages improve decision support.

Changes:

- Compare no graph, current graph, and decision-targeted relations.
- Measure whether relations improve crux preservation, scope dependency, counterweight disposition, and unsupported tension detection.
- Create a compact review packet and compare reviewer effort against the large artifact directory.

Artifacts:

- `relation_value_ablation_report.json`
- `reviewer_effort_ablation_report.json`
- compact review packet

Validation:

- Relation stage must demonstrate downstream decision value or stop producing memo obligations.
- Compact review packet lets a reviewer locate source universe, strongest counterweight, unresolved crux, and quantity binding faster than the full artifact set.

### 11. Adversarial Semantic QA

Purpose: catch semantic failures that structural telemetry misses.

Changes:

- Add report-only adversarial checks for:
  - quantity tuple swaps;
  - endpoint drift;
  - causal overstatement from non-causal evidence;
  - source outside active universe;
  - polarity reversal;
  - missing confidence/scope/crux;
  - missing counterweight disposition;
  - internal ID leakage.
- Promote only hard invariant checks early; keep semantic checks report-only until multi-case calibration.

Artifacts:

- `adversarial_memo_qa_report.json`
- `memo_mutation_eval.json`

Validation:

- Known flawed memos trigger expected warnings.
- Clean controls measure false positives.
- Multi-case calibration precedes blocking semantic gates.

## Execution Order

1. Record phase-zero current-HEAD baseline.
2. Patch fail-closed lineage and source-list fallback as isolated P0 fixes.
3. Replace loose quantity tuple representation with result-level records and mutation tests.
4. Upgrade `AnalystDecisionModel` to v2.
5. Add evidence-bound verifier before writer packet construction.
6. Run current stack vs `AnalystDecisionModel v2` vs v2-plus-verifier ablation.
7. Only if v2-plus-verifier improves quality, remove legacy authority paths and deterministic semantic fallbacks.
8. Add evidence-universe propagation from CLI/run context.
9. Calibrate evidence budgeting and section synthesis from verified contract views.
10. Run relation-value and reviewer-effort ablations.
11. Add adversarial semantic QA in report-only mode.
12. Run fresh eggs replay and at least one unrelated case.
13. Tune prose/presentation only after semantic invariants pass.

## Acceptance Criteria

- Phase-zero baseline exists and is tied to a commit, backend, run config, and artifact paths.
- No final artifact can claim `decision_ready` after unaccepted synthesis, repair, polish, packet, verifier, or fatal lineage status.
- Reader source list is derived from active cited sources and cannot fall back to all case sources.
- Quantity mutation tests catch invalid estimate/interval/endpoint recombinations.
- Existing loose tuple representation is replaced or explicitly marked as a temporary migration artifact with deletion criteria.
- `AnalystDecisionModel v2` is the only production semantic authority for answer, scope, confidence, evidence role, counterweight disposition, and source weighting.
- Evidence-bound verifier blocks fatal unsupported analyst moves before writing.
- Writer prompts no longer receive multiple independent controlling answer frames.
- Legacy deterministic semantic fallbacks are removed from production paths or made non-semantic/report-only.
- Contract ablation shows v2-plus-verifier improves factual correctness, calibration, counterweight handling, or decision usefulness against current stack.
- Eggs plus at least one unrelated case pass hard invariant checks.
- Exposed review packet is compact; internal diagnostics are nested or archived.

## Stronger Release Gate

Before calling the plan complete:

- All injected tuple, source-universe, polarity, status, and endpoint mutations are caught.
- Clean controls do not trigger corresponding fatal defects.
- Frozen corpus has zero known critical factual errors.
- Blinded pairwise review on eggs plus at least one differently shaped case shows material preference on factual correctness, calibration, counterweight handling, and decision usefulness.
- Reviewer time to locate strongest counterweight, unresolved crux, source universe, and quantity binding improves.
- Model calls, prompt size, latency, and exposed artifact count decrease or have explicit justified budgets.
- Production writer has no dependency on legacy semantic authorities.
- Human review status remains explicit; model QA does not count as human validation.

## Red-Team Checks

- The v2 analyst model could still become a dumping ground unless old authorities are removed.
- The verifier could be too weak with small local models or too noisy to block.
- Quantity tuple extraction may fail on tables, PDFs, or qualitative evidence.
- Evidence budgeting may hide minority evidence.
- Source dependency judgments may be overconfident.
- Section simplification may improve prose but reduce methodological transparency.
- Ablations may overfit to eggs unless an unrelated case is included early.

Detection:

- Audit downstream writer prompts for competing authority fields.
- Compare v2 foreground evidence against appendix evidence manually.
- Run mutation tests and clean controls.
- Run current-stack vs v2 vs v2-plus-verifier ablation.
- Inspect at least one unrelated memo manually.

## Generalizability Checks

- Run on a qualitative case with no numeric tuple obligations.
- Run on a case with dependent reviews, guidance, and primary studies.
- Run on a small case and a larger case.
- Confirm no domain-specific vocabulary is needed.
- Confirm active source universe and readiness lineage work even when synthesis fails.
- Confirm `AnalystDecisionModel v2` can express different answer shapes: confident yes/no, bounded neutral, insufficient evidence, tradeoff frontier, and option comparison.

## Completion Audit

The plan is complete only when the repo contains:

- phase-zero baseline record;
- implementation commits or explicit deferred-work records for each workstream;
- tests for readiness lineage, source universe, quantity tuple mutation, verifier blocking, and legacy semantic fallback retirement;
- current-stack vs v2 vs v2-plus-verifier ablation report;
- fresh eggs replay using current HEAD after implementation;
- one unrelated case replay or documented blocker;
- before/after memo-quality comparison;
- compact reviewer packet;
- final audit explaining fixed failures, report-only warnings, open risks, and any deferred items.

### 2026-07-18 Full-Plan Implementation Audit

Implementation status: the codeable production slices in this plan have been
implemented and committed. The empirical release-gate items remain explicit
validation work rather than silent success claims.

Implemented commits:

- `76baca5 Harden decision memo truth boundary`
  - recorded the phase-zero baseline and added fail-closed final lineage plus
    active-source reader rendering.
- `aa13962 Add result-level quantity tuple artifacts`
  - added source-result quantity tuple records, binding reports, and mutation
    checks.
- `fb214ef Promote analyst decision model verifier`
  - upgraded `AnalystDecisionModel` to the v2 contract and added a hard
    evidence-bound verifier.
- `1fa23f6 Add verified evidence budgeting reports`
  - added deterministic evidence-universe, budget, source-dependency, and
    foreground/accounting projections.
- `8c243fc Remove deterministic semantic fallbacks`
  - removed keyword-based semantic backfill from evidence-unit and source
    bottom-line production paths.
- `14b76a0 Add report-only semantic QA ablations`
  - added relation-value, reviewer-effort, compact-review, adversarial memo QA,
    and memo mutation reports in report-only mode.

Verification completed after implementation:

- `PYTHONPATH=src python3 -m pytest -q tests/test_source_evidence_units.py tests/test_analyst_decision_model_verifier.py tests/test_evidence_budget.py tests/test_plan_qa_reports.py tests/test_source_bottom_lines.py tests/test_map_briefing_decision_contracts.py tests/test_map_briefing_readiness.py tests/test_reader_memo_metadata.py tests/test_analyst_schemas.py tests/test_analyst_decision_modeling.py tests/test_decision_writer_packet.py`
  passed: 103 tests.
- `git diff --check` passed before the final audit edit.
- Focused artifact checks confirmed the partial current-HEAD eggs replay wrote
  schema-valid source evidence units and quantity tuple reports.

Fresh current-HEAD eggs replay status:

- Command shape:
  `semantic staged brief --region eggs_observational_vs_rct --backend ollama:gemma4:12b-mlx`
  with constrained source/chunk/claim/relation budgets.
- The old source-held replay command in
  `docs/baselines/deep_research/eggs/prototype_run_gemma4_12b_mlx/RUN_NOTES.md`
  no longer applies directly because its replay workspace path is absent and
  its `--max-claims-per-chunk` flag has been replaced by
  `--max-claims-per-source`.
- The native root-package run selected seven sources, completed whole-document
  claim extraction, completed deterministic claim consolidation, completed
  relation triage, and wrote:
  - `source_evidence_units.json` with 29 units;
  - `source_quantity_tuples.json` with 31 result tuples;
  - `quantity_tuple_binding_report.json` with zero issues;
  - `quantity_tuple_mutation_eval.json` with all three injected mutations
    detected;
  - `accepted_claims.json` with 29 accepted and zero rejected claims;
  - `claim_relation_triage_report.json` with 25 final-map claims.
- The run did not reach briefing artifacts before it was stopped after several
  minutes of no stdout and no new progress beyond relation triage. This counts
  as a live replay blocker for final memo-quality evaluation, not as a passing
  end-to-end replay.

Deferred empirical gates:

- True current-stack versus v2 versus v2-plus-verifier memo ablation remains
  unrun as a full live comparison. The repo now emits report-only relation and
  reviewer-effort ablation artifacts, but those are not a substitute for a
  complete blinded or pairwise memo-quality comparison.
- At least one unrelated case replay remains required to claim broad
  generalization.
- Broad semantic QA checks remain report-only until calibrated against clean
  controls and unrelated cases.
- A model-based entailment/NLI verifier for causal overstatement, polarity
  reversal, and action-support drift is still outside this code slice; the hard
  verifier currently blocks unsupported IDs and source/tuple identity failures,
  while semantic concerns are surfaced as warnings.

Plan-close assessment:

- Fully implemented by code criteria: source truth stabilization, quantity
  tuple identity, analyst v2 schema, evidence-bound hard verifier, deterministic
  evidence budgeting, source-universe/accounting artifacts, semantic fallback
  retirement, and report-only QA/ablation artifacts.
- Not fully complete by release criteria: full eggs replay, unrelated-case
  replay, live comparative ablation, and human/blinded memo-quality review are
  still open.
