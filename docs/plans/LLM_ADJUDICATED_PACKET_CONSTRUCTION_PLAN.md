# Plan: LLM-Adjudicated Decision Packet Construction

## Objective

Make the decision packet genuinely easy for a model to synthesize from by adding an LLM analyst-adjudication stage before final memo writing.

The target end state is a clean, source-grounded synthesis packet that tells the memo model:

- what the answer is;
- why that answer is currently best supported;
- which evidence is load-bearing;
- what the strongest counterweight is;
- what limits the scope or confidence;
- which evidence is background rather than mandatory;
- which important evidence has been accounted for but deliberately not foregrounded.

The intended architecture is:

```text
source map / source cards
-> analyst evidence ledger
-> LLM analyst adjudication
-> deterministic accounting and targeted repair
-> analyst answer frame
-> analyst synthesis packet
-> memo synthesis
-> retention / warning / source / quantity validation
-> final memo
```

This plan targets packet construction, not final prose polish. The final memo should improve because the packet has become an analyst-grade reasoning object, not because a later model pass rescues a noisy packet.

## Current Gap

The current packet preserves more evidence than earlier versions, but it still does not sufficiently adjudicate meaning. The eggs live run exposed the failure:

- `answer_frame.default_answer` already contains an awkward answer: it says eggs are neutral but immediately pivots to replacing half an egg with egg whites.
- `memo_ready_packet.json` marks too many items as mandatory, so the model writes a stitched inventory rather than a clean decision memo.
- Evidence roles are too crude; guideline context can be treated like a strongest counterweight.
- The decision synthesis contract is too abstract; it says what the model should do but does not provide a clean enough reasoning hierarchy.
- Warning routing now makes omissions visible, but it does not solve the upstream problem that the packet itself is not a clean synthesis substrate.

The core problem is not only final synthesis prompting. The system is underusing the LLM in packet construction, where semantic judgment is most needed.

## Non-Goals

- Do not make the LLM the sole source of evidence truth.
- Do not remove deterministic coverage, quantity, source, lineage, and warning telemetry.
- Do not tune specifically to eggs, diet, cardiovascular disease, LHC, HEPA, or any named case.
- Do not require all evidence to appear in the final memo.
- Do not treat a prettier memo as sufficient proof if accounting shows high-priority evidence disappeared.
- Do not promote new broad validators to blocking before their signal is calibrated.
- Do not remove existing packet architecture until the new adjudicated packet path demonstrates equal or better downstream quality.

## Design Principles

- LLMs own semantic judgment: salience, role, grouping, decision relevance, answer framing, crux quality, and tradeoff reasoning.
- Deterministic code owns accounting: stable IDs, schema validation, source lineage, quantity retention, coverage, warning routing, and repair targeting.
- Classical ML/statistics can support clustering, similarity, deduplication, diversity, and centrality, but it must not make final semantic decisions.
- Every important evidence item must be accounted for, not necessarily included in final prose.
- "Accounted for" means used, grouped under a broader proposition, placed in background, or explicitly downgraded with a reason.
- The final memo model should write from an analyst synthesis packet, not a raw evidence ledger or mechanically projected role list.
- Stable IDs should carry evidence through every transformation; text matching is only a fallback diagnostic.
- QA must test stage value and memo quality, not only artifact existence.

## Comparison Against Previous Related Plans

### `QUALITY_SYNTHESIS_PACKET_PIPELINE_PLAN.md`

What it got right:

- Identified that final memos should be rendered from clean packets rather than rescued by late repair.
- Separated content determination, document structuring, microplanning, and surface realization.
- Added evidence profiles, diagnosticity, provenance, quantity binding, and role-aware packet assembly.

Why it still failed to produce consistently strong memos:

- The memo-ready packet remained largely a deterministic projection from clusters and roles.
- The model was used mostly in later prose and repair stages, not as the owner of the core semantic transform from evidence ledger to decision reasoning.
- The packet retained too many mandatory items and did not force a compact argument hierarchy.

How this plan differs:

- Adds an explicit LLM analyst-adjudication stage before memo-ready synthesis.
- Requires the model to classify every high-value evidence item into a memo-use role with rationale.
- Requires deterministic accounting from ledger to adjudication to synthesis packet.
- Makes "background but accounted for" a first-class result, reducing pressure to stuff all relevant evidence into prose.

### `DECISION_MODEL_FIRST_PACKET_ASSEMBLY_PLAN.md`

What it got right:

- Moved from row trimming toward decision-model-first artifacts.
- Introduced source evidence graph, decision obligation graph, evidence-to-answer matrix, candidate answers, and packet views.
- Explicitly split model-owned semantic proposals from deterministic guarantees.

Why it still failed to solve the current memo weakness:

- The completed implementation proved artifact construction and quantity retention, but much of the evidence-to-answer and slot machinery remained broad/report-oriented.
- The final memo still consumed a packet whose answer frame and mandatory evidence set could be awkward.
- The LLM semantic refinement called for in the plan was not the primary implemented path for the final synthesis packet.

How this plan differs:

- Treats LLM adjudication as the main path, not optional refinement.
- Converts the broad decision-model artifacts into a compact synthesis packet with explicit memo-use decisions.
- Adds acceptance criteria tied to final memo answer directness and evidence accounting, not just successful artifact generation.

### `PACKET_CONSTRUCTION_REPAIR_PLAN.md`

What it got right:

- Correctly identified packet construction as the bottleneck rather than final prose.
- Named role misclassification, shallow cruxes, unsafe quantity blobs, and weak answer frames as failure classes.
- Proposed packet QA, role adjudication, balanced selection, and crux reconstruction.

Why it was not enough:

- It still framed improvement as repairing packet construction after deterministic packet assembly.
- It risked adding more diagnostics and targeted fixes while leaving the central transform under-specified: how the system turns evidence into an analyst reasoning plan.
- It did not sufficiently reduce the mandatory evidence burden by distinguishing load-bearing, background, and accounted-but-not-used evidence.

How this plan differs:

- Builds the central artifact around an LLM-produced analyst adjudication table.
- Makes every evidence item's memo-use status explicit.
- Uses repair only after accounting finds gaps in adjudication, not as the main way to recover from a bad packet.

### `DECISION_READY_CONTEXT_PIPELINE.md`

What it got right:

- Made context quality the bottleneck.
- Required model calls to receive only relevant context.
- Defined a strong deterministic/model ownership matrix.
- Emphasized source-grounded context before synthesis.

Why it did not solve the present issue:

- It focused on section context and section synthesis, while the current pipeline is now packet-first.
- Section-local context can still fail if the global answer frame and evidence hierarchy are weak.

How this plan differs:

- Applies the same context-boundary discipline to the packet-first architecture.
- Makes the global synthesis packet the object of adjudication before any memo section or whole memo is written.

### Garner `agent_plan_quality_guide.md`

Lessons adopted:

- Make it hard to stop halfway while appearing done.
- Define fact ownership.
- Prefer identity over text matching.
- Require bounded slices with verification and commits.
- Require stop conditions and anti-half-done rules.
- Add diagnostic quality standards.
- Treat cross-stage interaction bugs as first-class test targets.
- Require a final evidence packet and completion audit.

How this plan incorporates those lessons:

- Each workstream has owned artifacts, validation, QA, and risks.
- New semantic model outputs must be parsed through typed schemas.
- Every evidence transformation is checked by stable IDs.
- Broad gates begin report-only.
- Completion requires a recorded audit and before/after memo comparison, not just passing unit tests.

## Why This Plan Avoids Prior Failure Modes

Prior plans mostly failed in one of three ways:

1. They improved preservation and telemetry but did not make the packet semantically easier to write from.
2. They added downstream repair to compensate for upstream packet weakness.
3. They created broad decision-model artifacts but did not force a compact analyst-grade synthesis packet.

This plan addresses those directly:

- The LLM is used at the semantic bottleneck: adjudicating item roles, importance, grouping, and answer framing.
- Deterministic code audits the LLM's accounting rather than trying to make semantic judgments itself.
- The final synthesis packet has fewer mandatory obligations and an explicit hierarchy.
- Background evidence remains traceable but does not burden the memo.
- The plan's acceptance criteria require improved memo quality and evidence accounting together.

## Inventory And Dependency Map

### Current Owner Artifacts To Reuse

- `decision_briefing_packet.json`
  - Current evidence bundles, must-retain ledger, source trail, coverage report.
- `source_evidence_graph.json`
  - Source, claim, quantity, and relation lineage.
- `evidence_answer_matrix.json`
  - Existing broad mapping from evidence to answer candidates.
- `decision_obligation_graph.json`
  - Current decision obligations and candidate answer structure.
- `memo_warning_packet.json`
  - Calibrated warnings for important evidence at risk of omission.
- `quantity_ledger.json`
  - Quantity ownership and top quantitative anchors.
- `memo_ready_packet.json`
  - Current model-facing packet; initially useful for comparison and fallback, not the new owner.

### New Owner Artifacts

- `analyst_evidence_ledger.json`
  - Owns normalized evidence items for model adjudication.
- `analyst_adjudication.json`
  - Owns model semantic judgments for each evidence item.
- `analyst_adjudication_accounting_report.json`
  - Owns deterministic coverage from ledger to adjudication.
- `analyst_answer_frame.json`
  - Owns clean direct answer and reasoning frame.
- `analyst_evidence_groups.json`
  - Owns compressed propositions and covered evidence item IDs.
- `analyst_synthesis_packet.json`
  - Owns final model-facing packet for memo synthesis.
- `analyst_packet_quality_report.json`
  - Owns quality, coverage, warning, and accounting status.
- `analyst_packet_completion_audit.md`
  - Owns final evidence that the plan was completed.

### Fact Ownership

- Source identity, labels, URLs, and local paths: deterministic source metadata.
- Evidence item identity: `analyst_evidence_ledger`.
- Model semantic role, importance, and memo-use decision: `analyst_adjudication`.
- Evidence grouping and coverage: `analyst_evidence_groups`.
- Direct answer and reasoning frame: `analyst_answer_frame`.
- Final synthesis inputs: `analyst_synthesis_packet`.
- Warning status: `memo_warning_packet` plus analyst packet accounting.
- Quantity ownership: `quantity_ledger`, preserved into analyst artifacts by stable IDs.
- Final source list and decision question: deterministic final-output layer.

Downstream stages must consume owner artifacts rather than re-deriving facts from prose, item order, source labels, or headings.

## Model And Code Responsibility Split

### Model-Owned Work

- Decide the actual decision role of each evidence item.
- Decide whether an item is load-bearing, background, duplicative, or not decision-relevant.
- Group overlapping evidence into source-backed propositions.
- Produce a clean answer frame that directly answers the decision question.
- Identify the strongest counterweight and explain whether it changes the answer.
- Identify decision cruxes and what evidence update would change the answer.
- Explain downgrade decisions in plain language.

### Deterministic Code-Owned Work

- Build the evidence ledger from existing artifacts.
- Preserve stable IDs, source labels, source IDs, claim IDs, relation IDs, and quantity IDs.
- Validate model output with Pydantic.
- Check every ledger item is adjudicated or explicitly marked for repair.
- Check every high-priority item is used, grouped, backgrounded, or downgraded.
- Check quantities and warning items are not silently lost.
- Route missing or invalid adjudications to targeted repair.
- Emit report-only diagnostics before blocking broad gates.
- Save artifacts and summaries.

### Classical ML / Statistics-Owned Support

- Similarity candidate generation for grouping.
- Duplicate and near-duplicate detection.
- Source diversity summaries.
- Centrality and coverage features to include in the evidence ledger.
- Candidate grouping hints for the model.

Classical methods may suggest grouping and priority features, but they must not make final semantic use decisions.

## Workstreams

### 1. Analyst Evidence Ledger

Purpose:

- Create a stable, normalized input that contains every evidence item the model may adjudicate.

Changes:

- Add `map_briefing_analyst_evidence_ledger.py`.
- Build rows from decision bundles, high-priority omitted candidates, warning packet rows, quantity anchors, and source evidence graph nodes.
- Each row includes:
  - `evidence_item_id`
  - `source_ids`
  - `source_labels`
  - `claim_ids`
  - `quantity_ids`
  - `quantity_values`
  - `current_role`
  - `current_priority`
  - `source_excerpt`
  - `decision_question`
  - `existing_warning_codes`
  - `current_packet_location`

Artifacts:

- `analyst_evidence_ledger.json`

Validation:

- Every retained bundle has a ledger row.
- Every memo warning has a ledger row.
- Every top quantity anchor maps to at least one ledger row or a visible gap.
- No duplicate ledger ID.

QA:

- Unit tests for eggs-style high-priority omitted warning rows.
- Unit tests for an unrelated risk/catastrophe case.
- Metamorphic test: source order changes do not change ledger IDs or count.

Risks:

- Ledger becomes too broad. Mitigation: ledger can be broad, but downstream adjudication distinguishes load-bearing from background.

### 2. Pydantic Schemas For Analyst Adjudication

Purpose:

- Make model output parseable, repairable, and auditable.

Changes:

- Add schemas for:
  - `AnalystAdjudication`
  - `EvidenceAdjudicationRow`
  - `AnalystAnswerFrame`
  - `EvidenceGroup`
  - `AnalystSynthesisPacket`
  - `AnalystPacketQualityReport`
- Allowed memo-use labels:
  - `load_bearing_primary_support`
  - `load_bearing_counterweight`
  - `quantitative_anchor`
  - `scope_or_applicability`
  - `decision_crux`
  - `mechanism_or_context`
  - `background_only`
  - `covered_by_group`
  - `not_decision_relevant`
  - `needs_human_or_model_review`

Artifacts:

- Schema definitions in code.
- Parse reports saved with raw model output.

Validation:

- Invalid model output creates a targeted repair prompt.
- The parser never silently coerces missing evidence IDs.

QA:

- Tests for valid output, missing row, invalid role, unknown evidence ID, missing rationale, and malformed JSON.

Risks:

- Schema too rigid for useful judgment. Mitigation: allow `needs_human_or_model_review` and free-text rationale while keeping IDs strict.

### 3. LLM Analyst Adjudication

Purpose:

- Use the model where it is strongest: deciding how evidence bears on the decision.

Changes:

- Add `map_briefing_analyst_adjudication.py`.
- Model receives:
  - decision question;
  - candidate answer set or current answer frame;
  - compact evidence ledger rows;
  - grouping hints from similarity/centrality;
  - warning rows;
  - instructions to classify every item.
- Model returns:
  - one adjudication row per evidence item;
  - memo-use label;
  - importance rank;
  - concise rationale;
  - source-backed grouping suggestion;
  - downgrade reason when not foregrounded;
  - `covered_by` IDs when compressed.

Artifacts:

- `analyst_adjudication_prompt.txt`
- `analyst_adjudication_raw.txt`
- `analyst_adjudication.json`
- `analyst_adjudication_parse_report.json`

Validation:

- Every ledger item must be adjudicated or included in a repair request.
- Every high-priority item must have `memo_use != not_decision_relevant` unless rationale is source-grounded and accepted.
- Every `covered_by` target must exist.

QA:

- Golden packet cases for support, counterweight, scope, background, duplicate, warning, and off-question evidence.
- Metamorphic test: renaming source labels should not alter memo-use decisions.
- Adversarial mutation: swapped deterministic roles should be corrected or flagged by model adjudication.

Risks:

- Model drops rows. Mitigation: deterministic row coverage and repair.
- Model over-foregrounds everything. Mitigation: require rank and `background_only` budget telemetry.

### 4. Deterministic Accounting And Targeted Repair

Purpose:

- Make model judgment useful without allowing silent evidence loss.

Changes:

- Add `map_briefing_analyst_packet_accounting.py`.
- Compare:
  - ledger -> adjudication;
  - adjudication -> evidence groups;
  - groups -> synthesis packet;
  - warning packet -> synthesis packet;
  - quantity ledger -> synthesis packet.
- Add targeted repair prompt for missing adjudications, missing warning items, missing quantities, invalid covered-by links, and unsupported downgrades.

Artifacts:

- `analyst_adjudication_accounting_report.json`
- `analyst_packet_repair_prompt.txt`
- `analyst_packet_repair_raw.txt`
- `analyst_packet_repair_report.json`

Validation:

- No critical warning item unaccounted.
- No top quantity unaccounted.
- No high-priority item lost without model rationale and deterministic accounting status.

QA:

- Tests for missing high-priority evidence.
- Tests for source-list-only warning false satisfaction.
- Tests for invalid `covered_by` IDs.
- Tests for a model that marks everything background.

Risks:

- Accounting becomes a semantic veto. Mitigation: accounting flags missing IDs, missing quantities, missing rationales, and missing warning handling; it does not decide truth.

### 5. Analyst Answer Frame

Purpose:

- Replace awkward mechanical answer frames with a clean direct answer and reasoning summary.

Changes:

- Model produces:
  - `direct_answer`
  - `confidence`
  - `why_this_read`
  - `strongest_counterargument`
  - `why_counterargument_does_or_does_not_change_answer`
  - `scope`
  - `what_would_change_the_answer`
  - `must_not_overstate`
  - source-backed evidence IDs for each field.

Artifacts:

- `analyst_answer_frame_prompt.txt`
- `analyst_answer_frame_raw.txt`
- `analyst_answer_frame.json`
- `analyst_answer_frame_quality_report.json`

Validation:

- Direct answer must answer the decision question without leading with incidental evidence.
- Every answer-frame claim must cite adjudicated evidence IDs.
- The frame must name at least one counterweight or explicitly say the evidence set lacks a serious counterweight.

QA:

- Regression test for the eggs failure: direct answer should not lead with egg substitution if the question asks harmful/neutral/beneficial.
- Unrelated case test where the answer is not neutral.
- Metamorphic paraphrase of the question should preserve answer stance.

Risks:

- Model writes fluent but unsupported answer. Mitigation: evidence-ID requirements and source lineage checks.

### 6. Evidence Grouping And Compression

Purpose:

- Reduce repetition without losing accounting.

Changes:

- Model groups related adjudicated items into propositions.
- Code provides grouping hints using similarity and source/quantity metadata.
- Each group includes:
  - `group_id`
  - `proposition`
  - `memo_role`
  - `covered_evidence_item_ids`
  - `source_ids`
  - `quantity_ids`
  - `applicability_limits`
  - `rationale`

Artifacts:

- `analyst_evidence_groups_prompt.txt`
- `analyst_evidence_groups_raw.txt`
- `analyst_evidence_groups.json`
- `analyst_group_accounting_report.json`

Validation:

- Every `covered_by_group` item resolves to a group.
- Quantities remain attached to the correct source-backed proposition.
- Groups cannot merge evidence with conflicting population, outcome, comparator, or direction without an explicit conflict note.

QA:

- Duplicate evidence test.
- Near-duplicate but materially different evidence test.
- Quantity binding test.
- Conflict group test.

Risks:

- Over-compression hides important distinctions. Mitigation: conflict notes and under-consolidation preference for material differences.

### 7. Analyst Synthesis Packet Assembly

Purpose:

- Produce the actual packet the memo model should write from.

Changes:

- Build `analyst_synthesis_packet` with:
  - `decision_question`
  - `bottom_line`
  - `primary_reasoning_chain`
  - `main_counterweights`
  - `decision_cruxes`
  - `scope_and_applicability`
  - `quantitative_anchors`
  - `background_context`
  - `must_not_overstate`
  - `warnings_to_address`
  - `source_notes`
  - `evidence_accounting_summary`

Artifacts:

- `analyst_synthesis_packet.json`
- `analyst_packet_quality_report.json`

Validation:

- Mandatory memo obligations are limited to load-bearing evidence, not all relevant evidence.
- Background evidence is available but not forced into prose.
- The packet includes a concise answer hierarchy.

QA:

- Compare mandatory count against current memo-ready packet.
- Require explicit background accounting for non-load-bearing high-priority evidence.
- Validate source and quantity lineage.

Risks:

- Packet becomes too sparse. Mitigation: quality report checks for missing support, missing counterweight, missing quantitative anchor when available, missing scope.

### 8. Memo Synthesis Integration

Purpose:

- Route final memo synthesis through the analyst synthesis packet.

Changes:

- Add `run_analyst_packet_memo_synthesis`.
- Prefer `analyst_synthesis_packet` when present and quality status is usable.
- Keep existing memo-ready path as fallback during rollout.
- Preserve deterministic final question and source-list insertion.

Artifacts:

- `analyst_memo_synthesis_prompt.txt`
- `analyst_memo_synthesis_raw.txt`
- `analyst_memo_synthesis_report.json`
- final `BRIEFING.md`

Validation:

- Memo answers the question in the first paragraph.
- Memo uses source labels from the packet.
- Memo does not introduce sources outside the packet.
- Memo retains warning/accounting-critical evidence or reports why not.

QA:

- Before/after comparison against current packet path.
- Comparison against direct-source baseline.
- Manual read of eggs and one unrelated case.

Risks:

- Better packet still produces weak prose with a weak backend. Mitigation: compare packet quality separately from memo quality and run at least one stronger or alternate backend where available.

## Execution Order

1. Add `analyst_evidence_ledger` and tests.
2. Add Pydantic schemas and parse/repair scaffolding.
3. Implement LLM analyst adjudication with prompt backend support and saved prompts/raw outputs.
4. Add deterministic adjudication accounting and targeted repair.
5. Implement analyst answer-frame generation and validation.
6. Implement evidence grouping and compression with stable ID accounting.
7. Assemble `analyst_synthesis_packet`.
8. Route memo synthesis through the analyst packet behind a feature flag or quality-gated default.
9. Run eggs end-to-end with prompt backend and live backend.
10. Run one unrelated case end-to-end.
11. Produce completion audit with before/after memo comparison.

## Bounded Slice Protocol

Each slice must record:

- files changed;
- artifacts added or changed;
- tests run;
- command results;
- residual risks;
- whether the slice is committed.

Each slice should be committed after verification when the user asks for execution in bounded commits.

## Stop Conditions

Stop and diagnose before continuing if:

- Pydantic schemas require broad coercion to parse model output;
- ledger-to-adjudication accounting cannot identify missing evidence by stable IDs;
- the model routinely drops rows even after repair;
- warning or quantity accounting regresses relative to the current path;
- full suite or maintainability gate fails;
- the new analyst packet produces a memo that is less direct and no more complete than the current memo;
- implementation creates unexpected dependency cascades outside packet construction and final synthesis.

## Anti-Half-Done Rule

If a subsystem cannot be completed in the current slice, it must be:

- finished;
- removed; or
- recorded in a deferred-work section with owner stage, reason, risk, and next action.

No vague TODOs and no invisible fallback paths.

## Verification Strategy

### Fast Focused Tests

- Ledger construction tests.
- Schema parse and repair tests.
- Adjudication accounting tests.
- Warning and quantity preservation tests.
- Answer-frame directness tests.
- Synthesis packet assembly tests.

### Cross-Stage Tests

- Ledger -> adjudication -> synthesis packet accounting.
- Warning packet -> analyst packet -> memo retention.
- Quantity ledger -> analyst packet -> memo retention.
- Answer frame -> memo first paragraph.

### End-To-End Checks

- Eggs case with prompt backend.
- Eggs case with live backend.
- One unrelated case with prompt backend.
- One unrelated case with live backend if runtime permits.

### Manual Artifact Inspection

- Inspect `analyst_synthesis_packet.json`.
- Inspect final `BRIEFING.md`.
- Compare against current packet memo and direct-source baseline.

## Acceptance Criteria

- `analyst_evidence_ledger.json` exists and accounts for retained bundles, warnings, and top quantities.
- `analyst_adjudication.json` validates and covers every ledger row or produces targeted repair.
- `analyst_answer_frame.json` directly answers the question without incidental evidence contamination.
- `analyst_synthesis_packet.json` has a compact reasoning hierarchy.
- Mandatory memo obligations are fewer and more load-bearing than the current `memo_ready_packet` obligations.
- High-priority evidence is either used, grouped, backgrounded, or explicitly downgraded with a reason.
- Warning evidence is either incorporated, bounded, or explicitly treated as background with rationale.
- Quantitative anchors retain source and quantity lineage.
- Eggs final memo reads better than the current live memo on answer directness, throughline, and evidence integration.
- At least one unrelated case runs without case-specific rules.
- Full test suite passes.
- A completion audit records commands, artifacts, known limitations, and before/after quality comparison.

## Red-Team Checks

- Model silently drops evidence.
  - Detection: ledger-to-adjudication accounting.
  - Response: targeted repair; if repeated, mark adjudication backend insufficient.
- Model marks too much as background.
  - Detection: high-priority background share and missing load-bearing roles.
  - Response: repair prompt requiring downgrade rationales and role reassessment.
- Model creates fluent but unsupported answer frame.
  - Detection: every answer-frame field must cite adjudicated evidence IDs.
  - Response: reject or repair unsupported fields.
- Model over-compresses conflicting evidence.
  - Detection: group conflict checks for population, comparator, outcome, direction, quantity.
  - Response: split group or add conflict note.
- Deterministic accounting becomes semantic veto.
  - Detection: accounting failures must be limited to IDs, sources, quantities, warning statuses, and missing rationales.
  - Response: move semantic judgment back to model adjudication.
- New path looks better on eggs only.
  - Detection: unrelated case and metamorphic checks.
  - Response: keep current path as fallback and refine generic adjudication prompts.

## Generalizability Checks

- Run a non-health decision question.
- Run a case with conflicting evidence.
- Run a case with mostly background/context evidence.
- Shuffle source order and verify adjudication coverage and core memo-use decisions remain stable.
- Rename source labels and verify decisions remain stable.
- Remove a major source and verify answer confidence or answer frame changes visibly.
- Add irrelevant evidence and verify it is classified as background or not decision-relevant.

## Final Completion Audit Requirements

The completion audit must include:

- completed slices;
- commit list;
- artifacts added;
- tests and command results;
- live/backend runs performed;
- before/after memo comparison;
- evidence accounting deltas;
- warning and quantity retention deltas;
- remaining limitations;
- deferred work with owner, risk, and next action.

## Final Assessment Of This Plan Versus Earlier Plans

This plan is stronger than the previous packet plans because it changes the owner of the key semantic transform. Earlier work built the graph, ledger, slots, telemetry, and memo-ready packet machinery, but final quality remained limited because the system still asked deterministic projection and downstream prose repair to do too much semantic work.

The plan can still fail if the available model cannot reliably adjudicate rows or if source extraction quality is too weak. But if it fails, the failure should be visible at the adjudication/accounting stage rather than hidden inside a polished but weak memo.
