# Plan: Packet Construction Repair

## Objective

Make `memo_ready_packet.json` reliably express the decision structure before memo synthesis. A good packet should let a model write a decision-ready memo because the packet already contains a clean answer frame, correct evidence roles, useful decision cruxes, normalized quantities, enriched evidence profiles, and balanced model-facing evidence.

This plan targets packet construction, not final prose polish. The current live backend can write a readable memo from the packet, but the packet still gives it a weak reasoning structure.

## Current Gap

The live egg-case run with `ollama:gemma4:12b-mlx` showed that the final memo improved after adding a decision synthesis contract, but packet construction remains the bottleneck.

Observed packet failures:

- The memo-ready packet had an imbalanced role mix: 8 `strongest_counterweight`, 7 `scope_boundary`, 1 `strongest_support`, 1 `quantitative_anchor`, and 1 `decision_crux`.
- Some support-like evidence was mislabeled as counterweight, especially claims that no association has generally been found.
- The single crux was a shallow claim tension rather than an answer-changing uncertainty.
- Quantity binding warned about unsafe pairings but still passed effect estimates, confidence intervals, sample size, estimate count, exposure threshold, and follow-up duration in one blob.
- Evidence profiles frequently used placeholder fields such as `not_assessed_in_minimal_slice`.
- High-priority evidence was omitted or misplaced before synthesis.
- The answer frame could enter the packet as a stringified/truncated structure.
- Broken extracted claims, such as truncated fragments, can still reach memo-ready packet construction.

## Non-Goals

- Do not tune for eggs, cholesterol, diabetes, cardiovascular disease, or any other domain-specific vocabulary.
- Do not add source collection.
- Do not make uncalibrated validators block synthesis.
- Do not rely on a stronger model to hide weak packet construction.
- Do not replace the whole briefing pipeline.
- Do not remove existing telemetry until replacement telemetry covers the same failure class.

## Design Principles

- Deterministic code owns schema validity, stable IDs, provenance, source labels, quantity typing, routing, budgets, and report-only gates.
- Classical ML/statistical methods own similarity, deduplication, diversity, centrality, and coverage balancing when those signals are useful.
- Models own semantic judgments that deterministic code is poor at: role adjudication, crux quality, salience, and decision-changing uncertainty.
- Every semantic correction must preserve source IDs and claim IDs.
- Report-only warnings should precede blocking gates unless the signal has already been calibrated.
- Packet improvement must be measured by downstream memo quality and packet diagnostics, not by cleaner-looking JSON alone.
- Quality assurance should test packet semantics directly, before final memo prose can mask upstream defects.

## Inventory And Dependency Map

Current active flow:

```text
source_bottom_line_cards
  -> build_decision_briefing_packet_bundle
  -> run_packet_critique_and_refinement
  -> build_quality_synthesis_packet_bundle
  -> build_memo_ready_packet
  -> run_memo_ready_packet_synthesis
  -> repair / final polish / retention checks
```

Primary files:

- `src/epistemic_case_mapper/map_briefing_pipeline.py`: orchestration.
- `src/epistemic_case_mapper/map_briefing_decision_packet.py`: candidate pool, roles, trimming, answer frame, must-retain ledger.
- `src/epistemic_case_mapper/map_briefing_packet_refinement.py`: model critique and refinement.
- `src/epistemic_case_mapper/map_briefing_memo_ready_packet.py`: clustering, role projection, diagnosticity, evidence profile, memo-ready selection.
- `src/epistemic_case_mapper/map_briefing_quantity_binding.py`: quantity object construction and unsafe-pair warnings.
- `src/epistemic_case_mapper/map_briefing_reader_packet_contract.py`: synthesis contract attached to model-facing packets.

Dependency order:

1. Establish packet QA fixtures and stage-value telemetry before making broad semantic changes.
2. Normalize answer frame before semantic role/crux work.
3. Improve role adjudication before balanced packet selection.
4. Normalize quantities before memo-ready synthesis prompt construction.
5. Improve memo-ready selection before crux reconstruction is judged downstream.
6. Rebuild cruxes after roles and evidence profiles are cleaner.
7. Upgrade critique/refinement after the improved schema gives the model better handles.

## Workstreams

### 0. Packet QA Harness

Purpose: make packet-construction failures visible directly, before they appear as weak final memo prose.

Changes:

- Add a packet QA harness that can run against saved `decision_briefing_packet.json` and `memo_ready_packet.json` artifacts.
- Create a small golden packet corpus for known failure classes:
  - neutral/default evidence that should support the current read rather than count as counterweight
  - subgroup caveat that should become a scope boundary
  - answer-changing crux versus mere topical tension
  - detached or mixed quantity blob requiring typed quantity slots
  - truncated/broken claim that should be excluded or warning-visible
  - high-priority omitted evidence that requires an explicit omission reason
- Add metamorphic packet tests:
  - shuffled source order
  - renamed source labels
  - irrelevant evidence added
  - duplicate claim added
  - lightly paraphrased decision question
  - weak counterweight added
- Add adversarial packet mutation tests:
  - swapped support/counterweight roles
  - stringified answer frame
  - missing source IDs
  - truncated claim
  - detached quantities
  - fake crux created from unrelated claims
- Add stage-value gates that compare each stage's input and output against the targeted failure class.

Artifacts:

- `packet_qa_report.json`
- `golden_packet_cases/`
- `packet_mutation_report.json`
- `metamorphic_packet_report.json`
- `stage_value_report.json` extensions for packet-construction stages

Validation:

- Golden cases assert semantic packet properties, not exact final memo prose.
- Metamorphic tests should preserve core roles/cruxes when meaning-preserving transformations are applied.
- Adversarial mutations should be caught by diagnostics or repaired only when source-safe.
- Stage-value gates should show which stage improved, degraded, or left unchanged each packet-quality metric.

Risks:

- QA can become superficial artifact-existence testing.
- Mitigation: every QA case must assert at least one semantic property of packet content.
- Metamorphic expectations can be too strict for genuinely ambiguous cases.
- Mitigation: classify assertions as `hard`, `warning`, or `manual_review_needed`.

### 1. Answer Frame Normalization

Purpose: prevent malformed or stringified answer frames from polluting downstream packet stages.

Changes:

- Add a deterministic answer-frame normalizer before `decision_briefing_packet.answer_frame` is emitted.
- Parse dict-like strings when possible.
- Preserve raw input in a report.
- Emit clean fields: `default_answer`, `classification`, `confidence`, `scope`, `conditions`, and `main_uncertainty` where available.
- Fall back to plain text when parsing fails.

Artifacts:

- `answer_frame_normalization_report.json`

Validation:

- Unit tests for dict input, stringified dict input, truncated dict input, plain text input, missing input, and hostile malformed input.
- Regression check that final `decision_briefing_packet.json` never contains a visible stringified dict in `answer_frame.default_answer`.
- Golden packet QA case for stringified answer frame should pass.

Risks:

- Over-normalization could erase uncertainty.
- Mitigation: keep the raw field and report every fallback.

### 2. Role Adjudication Layer

Purpose: correct support/counterweight/scope/crux labels before they drive memo-ready packet construction.

Changes:

- Add deterministic role diagnostics for each bundle using:
  - decision question
  - normalized answer frame
  - claim text
  - current role
  - directionality
  - source role
  - population/scope cues
  - endpoint cues
- Identify high-impact conflicts, such as a no-association claim labeled as counterweight against a neutral default stance.
- Add optional model adjudication only for ambiguous or high-impact conflicts.
- Apply accepted role updates through an auditable report.

Artifacts:

- `packet_role_adjudication_report.json`
- `role_conflict_candidates.json`

Validation:

- Unit tests where evidence supporting a neutral/default stance is not mislabeled as counterweight.
- Unit tests where subgroup caveats become scope boundaries rather than global counterweights.
- Live egg packet should no longer classify the AHA no-association claim as a strongest counterweight if the answer frame is neutral/moderate-consumption.
- Metamorphic role checks should remain stable under source order and source label changes.
- Adversarial swapped-role mutation should be caught by diagnostics or routed to model adjudication.

Risks:

- Deterministic text cues can become brittle.
- Mitigation: keep diagnostics report-only except for high-confidence cases; route ambiguous cases to model adjudication with an allowed-role schema.

### 3. Balanced Memo-Ready Selection

Purpose: avoid flooding synthesis with one role class after role projection.

Changes:

- Replace `mandatory[:18] + context[:8]` with explicit decision slots:
  - default-stance support
  - strongest counterweight
  - quantitative anchor
  - scope/subgroup boundary
  - decision crux
  - mechanism or causal explanation
  - source-diversity context
- Add role budgets with an escape hatch when the evidence genuinely supports a one-sided packet.
- Emit overflow and omission reasons for high-priority evidence.
- Keep important omitted items available in `context_overflow`, not silently dropped.

Artifacts:

- `memo_ready_selection_report.json`

Validation:

- Unit tests for role-dominated packets.
- Report should explain every high-priority omitted evidence item.
- Live egg memo-ready packet should not be dominated by counterweights and scope boundaries unless the report justifies that dominance.
- Stage-value gate should show fewer unjustified role-dominance warnings after selection.
- Duplicate-claim metamorphic test should not distort role balance.

Risks:

- Artificial balancing can hide real asymmetry.
- Mitigation: allow `dominant_role_justified` with evidence and source diversity checks.

### 4. Decision-Crux Reconstruction

Purpose: replace shallow claim tensions with decision-changing uncertainties.

Changes:

- Add a crux schema:
  - `crux_question`
  - `current_best_read`
  - `would_change_answer_if`
  - `evidence_for_current_read`
  - `evidence_against_current_read`
  - `affected_scope`
  - `source_ids`
  - `claim_ids`
- Generate deterministic crux candidates from opposing roles, endpoint differences, study-design differences, population differences, and quantity disagreements.
- Use a model pass to convert candidates into source-backed decision cruxes.
- Reject cruxes that are merely topical contrast without answer-changing implications.

Artifacts:

- `decision_crux_reconstruction_report.json`

Validation:

- Crux must cite at least one source-backed reason for the current read and one source-backed reason it could change when available.
- Crux must state the answer-changing condition.
- Live egg crux should shift from “diabetes vs omega-3 eggs” to a more decision-relevant uncertainty such as hard-outcome evidence vs dietary-cholesterol dose-response evidence, or LDL-marker evidence vs hard-outcome evidence.
- Golden crux QA case should reject topical tensions that do not change the answer.
- Fake-crux adversarial mutation should be detected.

Risks:

- Model may invent elegant cruxes.
- Mitigation: require claim IDs/source IDs and reject unsupported crux components.

### 5. Quantity Normalization

Purpose: prevent raw quantity blobs from confusing synthesis.

Changes:

- Split quantity values into typed slots:
  - `effect_estimate`
  - `interval`
  - `sample_size`
  - `follow_up`
  - `dose_or_exposure`
  - `estimate_count`
  - `absolute_risk_or_difference`
  - `other_quantity`
- Attach each quantity slot to source IDs, claim IDs, and local tuple IDs when available.
- Provide safe verbalization hints for unsafe pairings.
- Keep raw values and warnings for auditability.

Artifacts:

- `quantity_slot_report.json`

Validation:

- Unit tests for common numerical patterns without domain-specific terms.
- Unsafe pairings should not disappear, but memo-ready packets should no longer present every number as an equal claim-bearing quantity.
- Live memo should not overstate an unsafe effect/interval pairing.
- Detached-quantity adversarial mutation should be warning-visible and should not become a mandatory unqualified anchor.
- Stage-value gate should show reduced unsafe quantity presentation, not just unchanged warnings in a new shape.

Risks:

- Regex typing may misclassify quantities.
- Mitigation: preserve raw values and set confidence per slot.

### 6. Evidence Profile Enrichment

Purpose: give synthesis structured guidance about evidence quality and applicability.

Changes:

- Replace placeholder profile fields where possible with generic evidence dimensions:
  - `study_design`
  - `endpoint_type`
  - `population_fit`
  - `directness`
  - `precision`
  - `consistency`
  - `confounding_or_bias_caution`
  - `surrogate_endpoint_caution`
  - `guideline_or_primary_evidence`
- Use deterministic extraction from existing metadata and claim/source text.
- Route ambiguous high-impact items to model classification when a live backend is available.

Artifacts:

- `evidence_profile_enrichment_report.json`

Validation:

- Fewer `not_assessed_in_minimal_slice` profiles for mandatory memo-ready items.
- Profiles must remain generic across health, policy, legal, technical, and organizational decisions.
- Golden cases should include at least one non-health evidence profile to prevent biomedical overfitting.

Risks:

- Evidence-profile categories can become biomedical.
- Mitigation: use generic dimensions and allow `unknown` rather than forced classification.

### 7. Packet Critique And Refinement Upgrade

Purpose: make model critique/refinement actually repair the packet rather than only produce mostly rejected recommendations.

Changes:

- Revise critique prompt to focus on:
  - role errors
  - missing or weak decision cruxes
  - malformed answer frame
  - unsafe quantity presentation
  - high-priority omitted evidence
  - broken/truncated claims
- Revise refinement schema to allow bounded updates to:
  - roles
  - selection priority
  - answer-frame fields
  - crux records
  - quantity presentation hints
  - unusable/broken claim flags
- Deterministically adjudicate model recommendations before applying.

Artifacts:

- improved `packet_critique_report.json`
- improved `packet_critique_adjudication_report.json`
- improved `decision_briefing_packet_refinement_report.json`

Validation:

- Live critique on the known flawed egg packet should produce actionable recommendations.
- Accepted recommendations should materially change packet fields.
- Rejected recommendations should have concrete rejection reasons.
- Model-as-judge QA should compare critique recommendations with deterministic diagnostics and flag disagreement for review.

Risks:

- Model refinement could over-edit evidence.
- Mitigation: allow only bounded field updates with existing source IDs/claim IDs.

## Execution Order

1. Implement packet QA harness scaffolding with golden-case, metamorphic, adversarial, and stage-value report schemas.
2. Add initial golden cases for the currently observed packet failures.
3. Implement answer-frame normalization and tests.
4. Implement deterministic role diagnostics and report-only role conflict candidates.
5. Add bounded role adjudication for high-confidence conflicts, with tests.
6. Implement quantity-slot normalization and connect it to memo-ready packet items.
7. Replace memo-ready item selection with role-aware decision slots and selection telemetry.
8. Implement decision-crux reconstruction using cleaned roles and evidence profiles.
9. Enrich evidence profiles for mandatory packet items.
10. Upgrade packet critique/refinement prompts and schemas.
11. Run before/after packet comparison on the egg case with prompt backend.
12. Run blinded before/after memo comparison from old and new packets.
13. Run differential backend QA on prompt fallback and at least one live backend.
14. Run live backend on the egg case and evaluate memo quality.
15. Run at least one unseen non-egg case to check generalizability.

## Acceptance Criteria

- Packet QA harness exists and runs golden, metamorphic, adversarial, and stage-value checks.
- Golden packet cases assert semantic properties of packet content, not only artifact existence.
- `answer_frame.default_answer` is clean plain text in final packet artifacts.
- Role-adjudication telemetry exists and identifies role conflicts.
- High-confidence role fixes are applied with source-preserving audit records.
- Memo-ready packet selection report explains role budgets, omissions, and overflows.
- Decision cruxes are answer-changing, source-backed, and not merely topical contrasts.
- Quantity slots separate effect estimates, intervals, sample sizes, follow-up, dose/exposure, and count-like values.
- Mandatory memo-ready evidence items have fewer placeholder evidence profiles.
- Final live egg memo has a stronger crux and no unsafe quantity overstatement.
- At least one unseen case passes packet-quality checks without domain-specific exceptions.
- Differential backend QA shows packet improvements help at least one weaker/fallback path, not only a stronger model.
- Blinded before/after memo comparison rates the new packet's memo as at least as grounded and more decision-useful.

## Red-Team Effectiveness Assessment

### Likely High-Value Parts

The plan is likely to improve final memo quality because it targets the stages that directly produced the observed memo weaknesses:

- Bad crux in memo maps directly to weak crux construction in the packet.
- Over-counterweighted memo structure maps directly to role imbalance in `memo_ready_packet.json`.
- Overstated quantity language maps directly to unnormalized quantity blobs.
- Thin reasoning about evidence quality maps directly to placeholder evidence profiles.

The highest expected ROI is from answer-frame normalization, role adjudication, balanced selection, and crux reconstruction. Those four changes should alter the actual information and structure passed to synthesis, not just add diagnostics.

### Main Risks

The plan could fail if it only creates more reports while leaving `memo_ready_packet.json` mostly unchanged. The completion criteria therefore need to check changed packet fields, not just generated artifacts.

The plan could also fail if role adjudication becomes a brittle deterministic classifier. The safest version uses deterministic code for candidate detection and provenance, then uses model adjudication for ambiguous semantic calls.

Balanced selection could make the packet artificially symmetrical. Some questions really are one-sided. The plan mitigates this with a `dominant_role_justified` escape hatch, but that must be implemented as a real report field, not a comment.

Crux reconstruction could become another model-written decorative layer. It will only help if cruxes are required to be answer-changing and source-backed.

Quantity normalization may be less impactful than role/crux work because the live model already handled the quantity warnings fairly well. It is still worth doing because it prevents future weaker backends from leaking warnings or pairing numbers incorrectly.

Evidence profile enrichment is useful, but it is likely slower to pay off unless synthesis prompts and packet contracts actually use the enriched fields. This should not be implemented as passive metadata only.

QA harness work is high leverage, but only if its assertions are semantic. It will not help if the tests merely check that reports exist or that counts changed. Golden and mutation cases should be small enough to inspect by hand and strict enough to catch regressions in role, crux, quantity, and omission behavior.

Differential backend QA can be misleading if stronger models simply compensate for packet defects. Treat improvements on weaker or fallback paths as stronger evidence that packet scaffolding improved.

### Failure Modes To Detect

- `memo_ready_packet.json` still has one role dominating without a justification.
- `decision_cruxes` still read like “claim A in tension with claim B.”
- The final memo still contains weak crux language despite a better crux report, indicating the synthesis contract is not using the crux artifact.
- Quantity slots exist but the model still receives raw quantity blobs first.
- High-priority omitted evidence remains unexplained.
- The unseen case passes tests but only because the tests check artifact existence rather than content quality.
- Golden packet cases pass but live memo quality does not improve, indicating the fixtures are too narrow.
- Metamorphic tests fail under harmless source renaming, indicating hidden dependence on labels rather than evidence meaning.
- Adversarial mutations are detected but not connected to packet repair or synthesis warnings.

### Probability Of Improving The Memo

Estimated effectiveness if fully implemented:

- Moderate-to-high chance of improving decision usefulness.
- High chance of improving telemetry and debuggability.
- Moderate chance of improving prose quality indirectly.
- Low chance of matching a strong deep-research baseline unless source coverage and map extraction are also strong.

The plan attacks the right bottleneck, but final quality will remain bounded by source-map quality. If extracted claims are incomplete, fragmented, or semantically weak, better packet construction can only triage and structure the available material.

Adding QA raises the likelihood that implementation improves the end product because it creates direct pressure on packet semantics. It also lowers the risk of overfitting to the egg memo by requiring metamorphic and unseen-case checks.

## Generalizability Checks

- Run on at least one health/nutrition case, one policy/infrastructure case, and one technical or organizational decision.
- Search the implementation for domain-specific vocabulary before commit.
- Ensure role adjudication uses decision stance, claim direction, endpoint type, population fit, and source role rather than topic words.
- Ensure crux construction works with any competing evidence pattern, not only biomedical study conflicts.
- Ensure quantity normalization handles generic numbers and marks unknowns rather than forcing domain-specific interpretations.
- Metamorphic checks should pass under source renaming and source ordering changes.
- Adversarial mutations should be generic packet corruptions, not egg-specific perturbations.
- Golden corpus should include at least one non-health case before the plan is considered complete.

## Completion Audit

The plan is complete only when a final audit artifact records:

- before/after role distribution
- before/after crux quality assessment
- answer-frame normalization status
- quantity-slot coverage and warning count
- evidence-profile placeholder rate
- high-priority omitted evidence count and reasons
- golden packet QA pass/fail summary
- metamorphic packet QA pass/fail summary
- adversarial mutation QA pass/fail summary
- stage-value gate summary
- differential backend QA summary
- blinded before/after memo comparison
- live memo quality assessment
- unseen-case packet-quality result
- final verification commands and test results
