# Plan: Richer Arm C Argument Moves With Decision-Ready Evidence Bundles

## Objective

Make production synthesis produce a more decision-grade memo by improving the writer packet before prose generation.

The target end state is:

- Arm C produces richer inference-level argument moves rather than broad section summaries.
- The model decides which evidence is load-bearing and how it affects the answer.
- The model selects which decision-relevant evidence bundles matter for each move when they are not already analyst-approved obligations.
- Quantities move through the system as indivisible assertion bundles, not detached numeric strings.
- Deterministic code validates selected bundle IDs and attaches exact evidence, quantity, source, and inference constraints to the selected move.
- Section synthesis receives first-class evidence, quantity, and reasoning obligations, not buried prose hints.
- The final memo becomes more analytical and decision-useful without adding a new polish call.

## Current Gap

Current production Arm C improves evidence prioritization, but the live memo still trails a strong deep-research-style answer because it does not consistently expose the numerical and inferential details that make the answer decision-grade.

The latest experiments found:

- A richer Arm C prompt produced a better intermediate argument: five specific moves instead of three broad section moves.
- The memo became somewhat less repetitive and more concise.
- Quantity context in the planner prompt was not enough. The model selected the right evidence IDs but often did not carry the numbers into the move text.
- Deterministically appending quantity anchors to `writing_job` was also insufficient because `_compact_move()` truncates `writing_job`, and section synthesis can ignore quantities that are only prose hints.
- Some important quantities exist upstream in `evidence_budget`, `quantity_obligation_plan`, and map artifacts, but are not consistently present in `memo_ready_packet.evidence_items[].quantities`.
- Existing quantity-contract machinery already binds `quantity_obligation_plan.must_retain` rows into `required_quantity_atoms`; the missing piece is precise coverage for selected but not-yet-approved quantity candidates, not a parallel contract system.
- Writer evidence items can aggregate multiple upstream claims, so selecting a writer evidence ID is not equivalent to selecting every quantity attached to its lineage.
- Arm C currently loses richer reasoning during projection because warrant, decision effect, dependencies, limitations, and counterweight disposition are compressed or truncated before section synthesis.
- Existing validators can accept a memo that contains the right number and source ID while using the number incorrectly, such as relabeling a relative risk as a hazard ratio, detaching a confidence interval from its estimate, or treating an observational association as causal.
- Numeric retention by itself is not decision usefulness. A better memo must preserve what the number measures, where it applies, what uncertainty means, and what inference is allowed.

The core problem is therefore not final prose polish. It is that model-selected evidence, quantitative meaning, and model reasoning do not always become structurally precise section contracts that the writer can render faithfully.

## Non-Goals

- Do not add a final memo repair or polish call as the primary fix.
- Do not add egg-, nutrition-, medicine-, or LHC-specific heuristics.
- Do not make deterministic code decide which evidence matters.
- Do not make deterministic code decide that a raw quantity is decision-relevant.
- Do not create a second quantity-obligation authority beside `required_quantity_atoms`.
- Do not force all upstream quantities into the memo.
- Do not split a point estimate, interval, endpoint, comparator, and population into separately selectable memo obligations when they jointly define one assertion.
- Do not restore broad overlapping packet context in section synthesis.
- Do not promote based only on a passing schema or lower prompt size.
- Do not treat more numeric density as proof of improved decision usefulness.

## Design Principles

- Model judgment owns salience, warrant, counterweight force, section role, and practical implication.
- Deterministic code owns evidence IDs, source IDs, evidence-bundle binding, schema validation, traceability, and prompt-size controls.
- Stable IDs are the bridge: deterministic code may attach exact quantity bundle content only after a bundle is already analyst-approved or explicitly selected by the Arm C model.
- Quantity meaning travels as a bundle: estimate, uncertainty, statistic type, unit or denominator, endpoint, population, exposure or comparator, time horizon, direction, source ID/span, uncertainty reading, and allowed/forbidden inference stay together.
- `evidence_expression_contracts[].required_quantity_atoms` is the canonical quantity obligation surface; section-local jobs derive from it.
- Rich reasoning fields must be preserved as structured packet fields, not only as prose in `writing_job`.
- Validation should measure memo improvement and traceability, not just artifact creation.
- Decision-usefulness validation must ask whether a reader can act on the result: applicable population, strongest support, strongest counterweight, effect size, uncertainty, action threshold, and what would change the answer.
- Broad semantic gates should stay report-only until calibrated.

## Inventory And Dependency Map

Primary code paths:

- `src/epistemic_case_mapper/pipeline/map/staged_semantic_claim_quantities.py`
  - source-extraction quantity schema and normalization;
  - canonical assertion-bundle field ownership.
- `src/epistemic_case_mapper/pipeline/map/staged_semantic_whole_doc.py`
  - whole-document extraction prompt/schema surfaces that must emit bundle-owned fields.
- `src/epistemic_case_mapper/pipeline/map/staged_semantic_evidence_units.py`
  - evidence-unit bundle formation and source-span ownership.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_analyst_evidence_ledger.py`
  - analyst evidence ledger rows and quantity lineage;
  - must become bundle-native instead of mixing structured quantities with flat recovered values.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_analyst_quantity_binding.py`
  - analyst quantity/bundle adjudication;
  - must approve bundle composition and inference bounds, not only memo use.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_canonical_decision_writer_packet.py`
  - canonical packet compilation;
  - `_brief_quantities` and related compaction must not discard bundle meaning.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_memo_ready_finalization.py`
  - production Arm C invocation in `_prepare_prioritized_argument_synthesis`;
  - production context assembly in `_prioritized_argument_inputs`.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_prioritized_argument_arm_c.py`
  - `build_arm_c_prioritization_prompt`;
  - `run_arm_c_prioritization`;
  - `build_arm_c_projection`;
  - `_arm_c_move_to_argument_move`.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_prioritized_argument_arm_b.py`
  - `build_arm_b_projection`;
  - `_section_packets`;
  - `_section_local_jobs`;
  - `_contract_for_arm_b`;
  - `_compact_move`.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_section_evidence_anchoring.py`
  - `build_evidence_expression_contracts`;
  - `contracts_for_section`;
  - quantity contract representation.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_priority_quantity_contracts.py`
  - priority quantity coverage reporting.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_artifacts.py`
  - availability of `quantity_obligation_plan`, `evidence_budget`, and related artifacts.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_memo_ready_presentation.py`
  - deterministic presentation normalization;
  - must consume final selected-bundle contract and not broaden citations.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_final_outputs.py`
  - final repair/polish/presentation/output orchestration;
  - must write and validate bundle-aware final artifacts.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_citation_trace.py`
  - reader-facing citation trace;
  - must map final sentences to bundle IDs and source spans, not only source IDs.

Data dependencies:

1. Source extraction/evidence-unit formation owns canonical assertion bundles with source span, quantity pairing, endpoint, population, comparator, time horizon, and inference bounds.
2. Analyst model freezes answer, confidence, scope, source hierarchy, and relevance judgments.
3. Analyst adjudication approves, rejects, or marks bundle composition/inference bounds for reconsideration.
4. Evidence ledger carries bundle IDs and candidate/approved/rejected status; it does not flatten structured bundle meaning into untyped `quantity_values`.
5. Memo-ready packet contains writer evidence items, lineage, and bundle references.
6. Deterministic code builds a stable evidence-bundle registry from upstream-owned bundles, analyst-approved obligations, and remaining selectable candidates.
7. Arm C selects writer evidence IDs and, where useful, evidence-bundle IDs for prioritized moves.
8. Arm C states the intended use of each selected bundle: which claim it calibrates, what decision update it warrants, how uncertainty should be read, and what language must not be implied.
9. Deterministic projection validates bundle IDs, rejects unresolved or off-lineage promotions, and writes a selected bundle report.
10. Projection builds section-owned contracts with structured bundles, quantities, inference constraints, and reasoning fields.
11. Section synthesis writes from those contracts.
12. Repair, polish, presentation normalization, citation trace, final diagnostics, and artifact assembly consume the same augmented selected-bundle production contract.
13. Reconciliation checks run after every memo mutation and on final `BRIEFING.md`.
14. A decision-usefulness rubric evaluates whether the final memo helps a reader make the decision, not merely whether it preserved more facts.

## Workstreams

### 0. Upstream Assertion-Bundle Ownership

Purpose: make bundle meaning owned at the earliest stage that has source context, instead of reconstructing it late.

Changes:

- Define one canonical assertion-bundle schema at source extraction/evidence-unit level.
- Require each bundle to include:
  - stable `evidence_bundle_id`;
  - source ID and exact source span or quote;
  - claim/evidence-unit ID;
  - estimate and paired interval where applicable;
  - statistic type;
  - unit or denominator;
  - endpoint;
  - population or subgroup;
  - exposure, intervention, comparator, or threshold;
  - time horizon;
  - direction of effect;
  - source provenance;
  - uncertainty interpretation;
  - allowed inference and forbidden inference;
  - missing-field diagnostics when the source does not support a field.
- Update source extraction and evidence-unit normalization to preserve bundle fields instead of flattening them into `quantity_values`.
- Keep flat quantity strings only as audit/search surfaces, never as the source of final memo obligations.

Artifacts:

- `source_assertion_bundles.json`
- extraction/evidence-unit diagnostics for missing bundle fields

Validation:

- Source extraction fixtures produce stable bundle IDs and exact source spans.
- Estimate/interval pairs stay together.
- Endpoint, population, comparator, and statistic type are preserved when present.
- Missing bundle fields are explicit diagnostics, not silent blanks.

Risks:

- Weaker models may omit fields.
- Mitigation: schema validation, retry, and explicit missing-field diagnostics; downstream stages can use incomplete bundles as context but not promote them as precise decision anchors.

### 0a. Bundle-Native Ledger And Analyst Authority

Purpose: ensure analyst adjudication owns bundle composition and permissible inference before Arm C uses the bundles.

Changes:

- Carry bundle IDs and candidate/approved/rejected/context-only status through the analyst evidence ledger.
- Update analyst quantity binding into analyst bundle binding:
  - approve or reject bundle composition;
  - approve estimate/interval pairing;
  - approve endpoint/population/comparator identity;
  - approve allowed and forbidden inference;
  - mark contradictions that should update answer/confidence or block production.
- Add an executable analyst reconsideration path:
  - if selected/approved bundles materially contradict frozen answer or confidence, rerun or update analyst adjudication and regenerate downstream artifacts;
  - if reconsideration cannot run, emit a blocking review packet rather than a decision-ready memo.
- Define protected evidence from analyst `must_use`, conflict sets, strongest counterarguments, and answer/confidence-changing bundles.

Artifacts:

- `analyst_bundle_binding_report.json`
- `analyst_reconsideration_report.json`
- protected evidence rows in the ledger

Validation:

- Bundle composition and inference bounds are analyst-approved before becoming final obligations.
- Contradictory bundles update answer/confidence or block with diagnostics.
- The ledger does not make flat recovered quantities authoritative.

Risks:

- Analyst adjudication may add runtime.
- Mitigation: batch by compact bundle rows; only rerun reconsideration when contradictions or protected-evidence omissions are detected.

### 1. Richer Arm C Prompt

Purpose: make the existing Arm C model call produce inference-level moves.

Changes:

- Revise `build_arm_c_prioritization_prompt`.
- Ask for 4 to 7 moves when the case warrants it.
- Require each move to specify:
  - source-weight rationale;
  - quantitative calibration where relevant;
  - counterweight disposition;
  - scope boundary;
  - practical update rule or decision implication.
- Ask the model to discriminate evidence by population, dose, endpoint, study design, measurement, mechanism, or authority when sources conflict.
- Add stable `evidence_bundle_ids` to the prompt only for compact bundles whose source, endpoint, population, comparator, uncertainty, and lineage are known.
- Ask the model to attach `evidence_bundle_ids` to a move only when the bundle is necessary to size the effect, define a threshold, bound the answer, or explain a counterweight.
- Require the model to state the selected bundle's intended use:
  - calibrated claim;
  - warranted decision update;
  - uncertainty reading;
  - allowed inference;
  - language that must not be implied.
- If selected bundles materially contradict the frozen answer or confidence, require Arm C to mark `requires_analyst_reconsideration` rather than rationalizing the conflict.

Artifacts:

- `prioritized_evidence_argument.json`
- `prioritized_argument_verification_projection_report.json`

Validation:

- Answer, confidence, and decision question do not drift.
- All evidence IDs are known writer evidence IDs after normalization.
- All evidence bundle IDs are known bundle IDs after normalization.
- Move IDs remain unique and acyclic.
- Tests verify the prompt asks for inference-level moves and not section summaries.
- Tests verify the prompt asks for evidence bundle IDs only when the bundled assertion is interpretively needed.
- Tests verify conflict/escalation language exists when selected bundles would change answer or confidence.

Risks:

- The model may still produce broad moves.
- Mitigation: record move granularity telemetry and compare move count/types before and after.
- The model may select irrelevant bundle IDs.
- Mitigation: deterministic validation checks that selected bundle IDs are linked to selected evidence lineage, and records unresolved or off-lineage IDs without promoting them.
- The model may preserve the answer by explaining away contrary evidence.
- Mitigation: conflict-set protection sends material contradictions back to analyst adjudication or emits a blocking diagnostic.

### 2. Evidence Bundle Registry And Selected Bundle Builder

Purpose: create a general bridge from model-selected evidence bundles to canonical section evidence and quantity obligations.

Changes:

- Add a helper that builds a stable `evidence_bundle_registry` from:
  - existing `memo_ready_packet.evidence_items[].quantities`;
  - `quantity_obligation_plan.rows`, including analyst relevance, source evidence ID, source IDs, endpoint, scope, and `must_retain`;
  - evidence-budget quantity rows only as candidates when they can be mapped to source evidence lineage and are not already represented in the quantity plan.
- Use memo-ready item lineage to map upstream claim/relation IDs to writer evidence IDs.
- Give each bundle a stable `evidence_bundle_id`.
- Group bundles by writer evidence ID and upstream source evidence ID.
- Mark each bundle as `approved_obligation`, `model_selectable`, `conflict_set_member`, or `context_only`.
- Treat `must_retain` or analyst-`must_use` rows as already approved obligations.
- Treat model-selected bundle IDs as proposed obligations only if they are linked to evidence selected in the same move.
- Preserve bundled fields together:
  - estimate and interval;
  - statistic type;
  - unit or denominator;
  - endpoint;
  - population or subgroup;
  - exposure, intervention, comparator, or threshold;
  - time horizon;
  - direction of effect;
  - source ID and source span or quote;
  - uncertainty interpretation;
  - allowed inference and forbidden inference.
- Include analyst rationale and source-weight judgment when available.
- Deduplicate by evidence ID plus normalized estimate plus endpoint/scope/comparator/statistic type, not by quantity text alone.

Artifacts:

- `evidence_bundle_registry.json`
- `selected_evidence_bundle_report.json`

Validation:

- Analyst-approved bundles become canonical obligations when their evidence is selected or when conflict-set rules require they be surfaced.
- Model-selected bundle IDs become obligations only when they are known, lineage-linked, and not marked `context_only`.
- Raw evidence-budget quantities are not promoted unless they become valid model-selected bundles or existing approved obligations.
- Unselected evidence does not create obligations unless it is analyst `must_use` or a protected conflict-set member.
- Duplicate upstream rows do not duplicate obligations or collapse distinct same-number/different-endpoint bundles.
- Cases with no quantitative evidence produce qualitative evidence bundles and run without failure.

Risks:

- Too many bundles for a selected evidence item.
- Mitigation: deterministic priority ordering uses approved obligations and protected conflict-set bundles first, then model-selected candidates; caps emit warnings and never silently discard approved obligations.
- Off-scope quantities could still enter the registry.
- Mitigation: registry can retain `context_only` candidates for audit while blocking their promotion.
- Bundles could become too verbose for prompts.
- Mitigation: prompt-facing bundles include compact meaning fields; full source quotes remain in artifacts and citation trace.

### 3. Projection Integration, Reasoning Retention, And Semantic Realization

Purpose: ensure richer moves, selected bundles, and reasoning roles reach the section writer structurally and are used correctly.

Changes:

- Extend `build_arm_c_projection()` with selected evidence bundles and richer move fields.
- Merge bundle quantities only into `evidence_expression_contracts[].required_quantity_atoms`.
- Add bundle-level inference constraints to evidence expression contracts:
  - statistic label;
  - endpoint label;
  - population/scope;
  - uncertainty phrase;
  - allowed inference;
  - forbidden inference.
- Keep `section_local_evidence_jobs[].required_quantities_by_evidence_id` as a derived view from contracts.
- Preserve Arm C `warrant`, `decision_effect`, `depends_on_move_ids`, limitations, counterweight disposition, and source-weight rationale as structured section-packet fields.
- Avoid storing selected bundles, quantitative meaning, or load-bearing reasoning only in `writing_job`.
- Ensure `_compact_move()` truncation cannot erase bundle obligations.
- Replace or extend `_compact_move()` so compact display text is not the only carrier for reasoning fields.
- Keep section packets slim and aligned with Arm B/Arm C prompt allowlists.
- Add semantic-realization checks over produced section text:
  - RR/HR/OR/statistic swaps;
  - detached or omitted confidence intervals;
  - omitted units or exposure increments;
  - endpoint/subgroup swaps;
  - confidence interval crossing the null described as significant;
  - observational association rendered as causal;
  - surrogate/biomarker effect converted into clinical-outcome advice without support.

Artifacts:

- `prioritized_argument_section_synthesis_packets.json`
- selected-bundle fields inside section packets
- richer-move fields inside section packets
- updated projection report with quantity-anchor counts
- `semantic_realization_report.json`

Validation:

- Section prompts include `required_quantities_by_evidence_id` for selected evidence with bundle quantities.
- Section prompts include bundle inference constraints where quantities appear.
- Section prompts include structured reasoning fields for warrant, decision effect, limitations, and counterweight disposition when present.
- Section synthesis validators flag selected bundle quantities if dropped.
- Semantic-realization validators flag quantity misuse, statistic swaps, endpoint swaps, and overclaiming.
- Existing source/citation validation does not regress.

Risks:

- Quantity anchors could overconstrain prose.
- Mitigation: anchors are required only when the related selected evidence is used; per-evidence cap limits number dumping.
- Richer packet fields could increase prompt size.
- Mitigation: include only fields needed for the section writer and emit prompt-size telemetry.
- Semantic validators could be brittle.
- Mitigation: keep exact-text checks deterministic for statistic/endpoint/unit presence, keep broader interpretation checks report-only until calibrated, and require manual/blinded review before promotion.

### 3a. Protected Counterweight And Conflict-Set Handling

Purpose: prevent the model from improving coverage by silently demoting hard evidence.

Changes:

- Identify protected evidence from analyst `must_use`, conflict sets, strongest counterarguments, and evidence that materially affects answer/confidence.
- Require Arm C to account for protected evidence as one of:
  - used in the argument;
  - explicit counterweight;
  - scope boundary;
  - missing/insufficient evidence;
  - analyst reconsideration trigger.
- Treat unexplained demotion of protected evidence as a projection issue.
- If a selected bundle contradicts the frozen answer or confidence, route to analyst reconsideration or emit a blocking diagnostic rather than forcing no drift.

Artifacts:

- `protected_evidence_accounting_report.json`
- protected-evidence rows in `selected_evidence_bundle_report.json`

Validation:

- Analyst `must_use` evidence is not silently omitted.
- Conflict-set members are surfaced or explicitly disposed.
- Contradictions between selected bundles and frozen answer/confidence are visible.
- Accounting a protected item as demoted requires a model rationale tied to source quality, scope, endpoint, population, or uncertainty.

Risks:

- Too many protected items could overload section synthesis.
- Mitigation: protected accounting can keep items in the decision model without forcing all into the main prose; final rubric checks whether the reader can see the live counterweights.

### 4. Production Wiring

Purpose: make the normal live production path use the richer, bundle-bound Arm C path.

Changes:

- Reuse the existing in-memory `memo_ready_packet` and production context instead of creating a second quantity-obligation authority.
- Extend `_prioritized_argument_inputs()` only where required to expose the canonical packet, analyst model, evidence budget, and quantity-obligation data already produced by the briefing pipeline.
- Keep `quantity_obligation_plan` canonical when it is already present in the memo-ready packet.
- Generate the evidence bundle registry immediately before Arm C prompt construction.
- Write `selected_evidence_bundle_report.json` beside Arm C artifacts.
- Write `evidence_bundle_registry.json` beside Arm C artifacts.
- Write semantic-realization and protected-evidence accounting reports beside section synthesis reports.
- Keep `ECM_PRIORITIZED_ARGUMENT_SYNTHESIS=off` as an explicit disable switch.
- Prohibit silent legacy synthesis fallback when prioritized argument construction or projection fails; if the top-level pipeline emits a non-decision-ready diagnostic artifact, label it explicitly as diagnostic.

Artifacts:

- `evidence_bundle_registry.json`
- `selected_evidence_bundle_report.json`
- `semantic_realization_report.json`
- `protected_evidence_accounting_report.json`
- updated `prioritized_argument_synthesis_report.json`
- updated `memo_ready_synthesis_report.json`

Validation:

- Production replay shows `prioritized_argument_synthesis=true`.
- The bundle registry, selected bundle report, semantic-realization report, and protected-evidence accounting report are written in production artifact directories.
- No silent legacy memo is emitted if the production path fails.
- Diagnostic fallback artifacts, if any, are visibly non-decision-ready.

Risks:

- Existing staged runs may not have `quantity_obligation_plan`.
- Mitigation: missing quantity plan should degrade visibly to existing packet quantities and model-selectable bundles only when lineage is valid; raw budget values are not promoted automatically.

### 4a. End-To-End Contract Propagation And Final Reconciliation

Purpose: prevent downstream repair, polish, presentation, and citation assembly from losing or broadening selected bundles after section synthesis.

Changes:

- Build one augmented production contract after Arm C projection:
  - selected bundles;
  - protected evidence accounting;
  - section contracts;
  - evidence trace;
  - source-span mappings;
  - semantic-realization obligations;
  - citation constraints.
- Pass this contract to:
  - section synthesis validation;
  - memo repair;
  - final polish;
  - presentation normalization;
  - final diagnostics;
  - citation trace assembly;
  - final artifact writing.
- Stop rebuilding final traceability solely from the original `memo_ready_packet` when selected-bundle contracts exist.
- Add a reconciliation ledger across all lossy transforms:
  - `source span -> evidence unit -> analyst row -> writer item -> Arm C move -> section contract -> section draft sentence -> repaired/polished sentence -> final citation`.
- Run bundle preservation checks before and after every memo mutation stage.
- Treat presentation citation dedupe/normalization as a semantics-preserving transform that must not broaden a citation from a bundle-level evidence tag to a generic source claim.
- Add cross-section coherence checks after assembling the memo:
  - practical implication follows from answer/evidence sections;
  - counterweights are not contradicted elsewhere;
  - dependencies between moves are resolved in the final order;
  - confidence and scope remain consistent.

Artifacts:

- `augmented_production_contract.json`
- `end_to_end_reconciliation_ledger.json`
- `final_bundle_realization_report.json`
- `bundle_aware_citation_trace.md`
- `citation_adjacency_report.json`
- `cross_section_coherence_report.json`

Validation:

- Every selected/protected bundle is either realized in the final memo, explicitly omitted with an approved reason, or escalated.
- Every final sentence that uses a selected bundle maps to a bundle ID and source span.
- Repair, polish, and presentation do not introduce new unsupported bundle-like claims.
- Citation trace lets a reader see why a cited source supports the specific sentence, endpoint, subgroup, and quantity.
- Final `BRIEFING.md` passes semantic realization, source-span entailment, citation adjacency, and cross-section coherence checks.

Risks:

- The final contract could become large.
- Mitigation: pass compact bundle IDs and constraints to model calls; keep full source spans in artifacts and citation trace.
- Bundle-aware final checks could produce false positives.
- Mitigation: start broad semantic gates in report-only mode, but make exact identity, statistic, endpoint, paired-interval, and citation-adjacency failures blocking once fixtures calibrate them.

### 5. Decision-Usefulness Evaluation

Purpose: prove the change improves the memo, not just internal artifacts.

Tests:

- Unit test: approved evidence bundles become `required_quantity_atoms` and inference constraints when their evidence is selected.
- Unit test: model-selected bundle IDs become obligations only when lineage-linked to selected evidence.
- Unit test: context-only and rejected bundles are never promoted.
- Unit test: unselected evidence does not create obligations unless analyst `must_use` or protected conflict rules require accounting.
- Unit test: same-number/different-endpoint bundles are not collapsed.
- Unit test: unknown bundle IDs are rejected and reported.
- Unit test: detached estimate/CI pairs are blocked.
- Unit test: RR/HR/statistic swaps are detected on representative memo text.
- Unit test: CI crossing the null cannot be described as clearly significant.
- Unit test: observational association cannot be rendered as causal without an allowed-inference field.
- Unit test: Arm C projection includes first-class bundle obligations and inference constraints.
- Unit test: richer Arm C fields survive into section packets and actual section prompts.
- Regression test: production synthesis writes selected evidence bundle artifacts.
- Regression test: final repair/polish/presentation consume the augmented production contract.
- Regression test: final citation trace maps final sentences to bundle IDs and source spans when bundles exist.
- Regression test: presentation citation dedupe does not broaden bundle-level evidence tags into unsupported source-level claims.
- Regression test: reconciliation ledger catches a bundle dropped by final polish.
- Live replay: eggs from saved synthesis-stage artifacts.
- Generalization replay: one unrelated case, preferably LHC or another non-nutrition decision question.
- Qualitative replay: one case or fixture with no meaningful quantities, to prove the bundle architecture does not overfit to numeric evidence.
- Blinded before/after review: compare old production memo, revised production memo, and direct-source baseline without labels.
- Canary matrix: multi-endpoint source, table-derived quantities, conflicting estimates, relative versus absolute effects, detached intervals, missing units, qualitative evidence, and non-action questions.

Metrics:

- `missing_mandatory_count` remains 0.
- Bundle coverage improves for protected and selected evidence.
- Zero rejected or context-only bundles are promoted.
- Zero unresolved bundle IDs become obligations.
- Zero material statistic/endpoint/significance errors in blocking semantic-realization checks.
- Protected evidence accounting has no unexplained omissions.
- Final reconciliation ledger has no unexplained selected/protected bundle loss.
- Citation adjacency errors do not increase.
- Cross-section contradiction count does not increase.
- Source binding warning count does not increase materially.
- Prompt size remains bounded.
- Memo passes a decision-usefulness rubric: a reader can identify the answer, confidence, applicable population, strongest support, strongest counterweight, effect size and uncertainty where applicable, action threshold, and what would change the answer.
- Memo does not merely become more numeric; it explains what the important evidence does to the decision.

## Execution Order

1. Add focused tests for upstream assertion-bundle schema, bundle normalization, bundle ledger carry-through, selected bundle binding, and semantic-realization failures before implementation.
2. Implement canonical assertion-bundle schema at source extraction/evidence-unit level.
3. Make the analyst evidence ledger and analyst bundle binding bundle-native.
4. Implement analyst reconsideration or blocking diagnostic for contradictions with frozen answer/confidence.
5. Implement the evidence-bundle registry and selected-bundle validator.
6. Strengthen Arm C schema/prompt to allow richer moves, `evidence_bundle_ids`, intended use, and analyst-reconsideration triggers.
7. Add protected evidence and conflict-set accounting.
8. Preserve richer Arm C fields, selected bundles, and inference constraints through projection and section prompt construction.
9. Integrate selected bundle quantities into the single canonical `required_quantity_atoms` path.
10. Build the augmented production contract and propagate it through repair, polish, presentation, final diagnostics, citation trace, and final artifact writing.
11. Add semantic-realization, citation-adjacency, cross-section coherence, and end-to-end reconciliation checks.
12. Add production artifact writing for the registry, selected bundle report, semantic-realization report, protected evidence accounting, augmented production contract, reconciliation ledger, and richer projection report.
13. Run focused unit tests.
14. Run eggs replay and compare against the current production memo.
15. Run one unrelated replay and one qualitative/no-quantity replay.
16. Run the canary matrix and blinded before/after decision-usefulness comparison.
17. Promote only if the delivered memo improves on analytical usefulness without traceability, statistical-meaning, citation, or readability regression.

## Acceptance Criteria

- Arm C prompt asks for richer inference-level argument moves.
- Arm C output still passes answer/confidence/evidence-ID validation.
- Source extraction/evidence-unit formation emits canonical assertion bundles or explicit missing-field diagnostics.
- Analyst bundle binding approves bundle composition and permissible inference before promotion.
- Arm C may select stable evidence bundle IDs, and unresolved IDs are rejected.
- Arm C records intended use for selected bundles.
- Selected/approved bundles are visible as structured obligations, not only prose hints.
- `required_quantity_atoms` is the single canonical quantity obligation surface.
- Richer move fields survive into section packets and prompt context.
- Section synthesis flags dropped selected bundle quantities.
- Semantic-realization checks detect statistic swaps, endpoint swaps, detached intervals, missing units, unsupported causality, and unsupported significance.
- Context-only or rejected raw quantity candidates are not promoted.
- Protected `must_use` and conflict-set evidence is surfaced, explained, or escalated.
- The augmented production contract is consumed by repair, final polish, presentation, citation trace, final diagnostics, and final artifact writing.
- Final `BRIEFING.md` passes bundle realization, source-span entailment, citation adjacency, cross-section coherence, and end-to-end reconciliation checks.
- Egg memo retains more decision-relevant selected bundles than current production.
- Egg memo does not become less readable or more citation-cluttered.
- Non-eggs replay does not regress traceability, readability, or decision-usefulness.
- Qualitative/no-quantity replay still produces a useful argument memo.
- Canary matrix passes the core bundle and final-artifact failure classes.
- Blinded comparison rates the revised memo better on decision usefulness, not just numeric coverage.
- No new model call is required.

## Red-Team Checks

- Failure: deterministic code makes semantic importance decisions.
  - Detection: selected bundle obligations only arise from analyst-approved obligations, protected-evidence accounting, or Arm C-selected bundle IDs linked to selected evidence.
- Failure: selected evidence drags in noisy quantities.
  - Detection: selected bundle report records blocked `context_only`, off-lineage, unresolved, capped, and rejected bundles.
- Failure: the memo preserves a number but changes its meaning.
  - Detection: semantic-realization checks for statistic swaps, endpoint/subgroup swaps, detached confidence intervals, omitted units, unsupported causality, and unsupported significance.
- Failure: quantities become more visible but decision usefulness does not improve.
  - Detection: blinded decision-usefulness rubric must improve over current production and direct-source baseline on answer, confidence, counterweight, scope, action threshold, uncertainty, and update conditions.
- Failure: Arm C silently demotes hard counterevidence.
  - Detection: protected evidence accounting requires each analyst `must_use` or conflict-set item to be used, bounded, explained, or escalated.
- Failure: prompt grows too large.
  - Detection: prompt-size telemetry before and after.
- Failure: memo includes numbers without explaining them.
  - Detection: decision-usefulness rubric and semantic-realization report evaluate interpretation, not just quantity presence.
- Failure: experiments improve eggs only.
  - Detection: unrelated replay and qualitative/no-quantity replay before promotion.
- Failure: evidence bundles disappear due to truncation.
  - Detection: assert bundles are in structured section fields, not only `writing_job`.
- Failure: richer model reasoning is lost in projection.
  - Detection: assert warrant, decision effect, limitations, dependency, and counterweight fields survive from Arm C output into section packets.
- Failure: same numeric value is attached to the wrong endpoint or subgroup.
  - Detection: bundle registry and selected bundle report preserve endpoint, scope, comparator, source, and upstream lineage.
- Failure: frozen-answer validation suppresses warranted updating.
  - Detection: material contradiction between selected bundles and frozen answer/confidence routes to analyst reconsideration or blocking diagnostic.
- Failure: final prose is traceable but inert.
  - Detection: reader rubric asks what action should change under what condition, and whether the memo explains why the conclusion follows from weighted evidence.
- Failure: late bundle registry reconstructs fields incorrectly because upstream extraction never owned them.
  - Detection: canonical source assertion bundles must exist before analyst ledger construction; missing fields become explicit diagnostics.
- Failure: packet compilation or section dedupe drops bundle fields.
  - Detection: lossy-transform audit compares bundle fields before and after canonical packet compilation, section projection, dedupe, and compaction.
- Failure: repair/polish/presentation mutates a correct section into an incorrect final memo.
  - Detection: final reconciliation checks run after every memo mutation and on delivered `BRIEFING.md`.
- Failure: citations name the correct source but support the wrong sentence-level claim.
  - Detection: bundle-aware citation trace and citation-adjacency report require final sentence -> bundle -> source span mapping.

## Generalizability Checks

- Cases with no quantitative evidence still run.
- Cases with qualitative-only counterweights still produce richer moves.
- Renaming source labels does not change bundle binding.
- Duplicate evidence does not duplicate bundle obligations.
- Conflicting estimates stay source/evidence-bound instead of being merged blindly.
- Different decision domains use the same binding mechanism through IDs and lineage.
- Reordering evidence items does not change bundle IDs or selected-bundle projection.
- Same-number/different-meaning quantities remain distinct.
- Relative effects, absolute effects, guideline thresholds, costs/resources, qualitative source judgments, and no-quantity cases all use the same bundle/contract interface.
- Source hierarchy and source-quality judgments are carried as bundle context where relevant, not reintroduced through domain-specific heuristics.
- Question-type-specific rubrics handle action questions, explanatory questions, comparison questions, and uncertainty-mapping questions without inventing an action threshold when the question does not require one.
- Bundle-aware citation trace works for qualitative claims as well as numeric estimates.

## Completion Audit

The plan is complete only when:

- implementation includes selected evidence bundle builder and projection integration;
- implementation includes canonical upstream assertion-bundle ownership;
- implementation includes a stable evidence bundle registry;
- analyst ledger and analyst adjudication are bundle-native;
- implementation includes analyst reconsideration or blocking diagnostic for answer/confidence contradictions;
- production writes selected evidence bundle reports;
- production writes evidence bundle registry artifacts;
- production writes semantic-realization and protected-evidence accounting artifacts;
- production writes augmented production contract, end-to-end reconciliation ledger, bundle-aware citation trace, citation-adjacency report, and cross-section coherence report;
- unit tests cover selected, unselected, duplicate, no-quantity, context-only, off-lineage, unknown-ID, same-number/different-endpoint, detached-interval, statistic-swap, endpoint-swap, unsupported-causality, and unsupported-significance cases;
- regression tests cover source extraction bundle formation, analyst bundle approval, canonical packet bundle preservation, repair/polish/presentation contract propagation, and final sentence-to-bundle citation mapping;
- richer Arm C reasoning fields survive into section packets;
- eggs live replay shows improved selected bundle retention and decision usefulness;
- one non-eggs replay runs without traceability/readability regression;
- one qualitative/no-quantity replay runs without forcing numeric structure;
- canary matrix covers multi-endpoint sources, tables, conflicting estimates, relative/absolute effects, detached intervals, missing units, qualitative evidence, and non-action questions;
- blinded decision-usefulness review improves over current production;
- final assessment explains whether the memo quality improved enough to keep the production change and whether any remaining gap is upstream extraction, analyst adjudication, bundle projection, section synthesis, or final presentation.
