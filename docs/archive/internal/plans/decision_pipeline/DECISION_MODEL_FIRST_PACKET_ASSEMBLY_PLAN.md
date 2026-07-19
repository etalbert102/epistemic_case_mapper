# Plan: Decision-Model-First Packet Assembly

## Objective

Replace the current row-trimming packet builder with a decision-model-first packet assembler. The final packet should be a reusable decision case file that preserves the evidence a competent analyst needs to answer a decision question: candidate answers, assumptions, cruxes, load-bearing evidence, quantitative anchors, counterevidence, evidence quality, scope limits, source-quality cautions, source lineage, and named gaps.

Slots remain useful, but they are not the top-level abstraction. The top-level abstraction is a decision obligation graph derived from the question and grounded against the available evidence. Slots are the implementation layer used to fill and present that graph.

The ideal packet architecture is:

```text
decision question
-> decision facets and candidate answers
-> source evidence graph
-> decision obligation graph
-> evidence-to-answer matrix
-> packet view compiler
-> synthesis / audit / trace / QA views
```

## Current Gap

The current path in `src/epistemic_case_mapper/pipeline/briefing/map_briefing_decision_packet.py` builds:

```text
candidate rows -> role labels -> trim -> bundles -> must-retain ledger
```

This causes evidence loss because:

- quantity evidence enters through side channels but does not reliably become first-class bundles;
- deterministic eligibility can block semantic evidence, especially through lexical relevance checks;
- dedupe keeps earlier or thinner rows over richer rows;
- coverage checks happen after evidence has already been lost;
- must-retain obligations can mask the absence of corresponding evidence bundles;
- section views inherit whatever survived trimming rather than what the decision question requires.

The latest eggs packet exposed the concrete failure mode: quantitative evidence existed in the quantity ledger and argument model, but the final packet retained zero `quantitative_anchor` bundles.

The broader architectural failure is that the system asks "which evidence rows should we keep?" before it asks "what decision model would a competent analyst need to reason with?"

## Non-Goals

- Do not rewrite source extraction.
- Do not tune specifically to the eggs case.
- Do not make live model calls mandatory for baseline packet construction.
- Do not remove current telemetry until the replacement path proves equal or better.
- Do not let deterministic code make blocking semantic relevance decisions.
- Do not optimize final prose before packet retention and decision structure improve.
- Do not collapse all packet views into one artifact; synthesis, audit, and source-trace views can have different needs.

## Design Principles

- Decision-model-first: identify decision facets, candidate answers, and obligations before selecting evidence.
- Slot-derived, not slot-led: slots are generated from the decision model and available evidence, not fixed globally as the primary architecture.
- Two-graph architecture: maintain a source evidence graph and a decision obligation graph, then build packet views from their join.
- Candidate-answer explicitness: evidence should be mapped against competing plausible answers, not only the normalized default answer.
- Evidence quality is first-class: study design, endpoint directness, applicability, precision, consistency, source independence, and bias/confounding risk should be preserved when available.
- Compression has invariants: exact quantities, directionality, source identity, applicability limit, and uncertainty qualifiers must survive.
- Packet budgets are obligation-aware: space is allocated to load-bearing evidence, counterevidence, quantities, scope, and uncertainty according to decision need, not arbitrary role caps.
- Faceted problem typing: decision problems can have multiple facets rather than one exclusive label.
- Evidence can fill multiple obligations when it legitimately serves multiple decision functions.
- Deterministic code scores, preserves, validates, and reports; it does not semantically veto.
- Classical ML/statistics can help with similarity, diversity, clustering, centrality, and redundancy.
- LLMs are used for semantic judgment: problem typing, obligation generation, relevance, crux identification, role fit, and compression.
- Schema validity, source lineage, quantity preservation, and coverage accounting remain deterministic.
- Model/code boundary is explicit: models propose semantic structure and edits; deterministic code validates IDs, quantities, source grounding, schema, coverage, and invariant preservation.
- Broad model judgments start report-only and become blocking only after calibration.
- Warnings beat silent loss.
- Packet quality is measured by decision usefulness, retained obligations, and traceable evidence, not bundle count.

## Inventory And Dependency Map

### Existing Primary Modules

- `map_briefing_decision_packet.py`
  - Current packet builder, candidate pool, bundle trimming, must-retain ledger, source trail, and builder report.
- `map_briefing_answer_frame.py`
  - Answer frame normalization.
- `map_briefing_packet_eligibility.py`
  - Current deterministic packet eligibility checks, including lexical quantity-anchor mismatch.
- `map_briefing_packet_coverage.py`
  - Packet coverage report.
- `map_briefing_packet_sufficiency.py`
  - Sufficiency, quantity obligation ledger, role coverage, compression loss.
- `map_briefing_section_views.py`
  - Section views built from bundles and retain ledger.
- `map_briefing_packet_refinement.py`
  - Optional critique/refinement layer.
- `map_briefing_argument_model.py`
  - Existing argument model scaffold, currently not strong enough to own the full decision obligation graph.
- `map_briefing_quantities.py`
  - Quantity ledger and top quantitative anchors.
- Existing source-card, evidence-role, quality, centrality, and relation artifacts
  - Candidate inputs for a stable source evidence graph.

### Existing Relevant Tests

- `tests/test_decision_briefing_packet.py`
- `tests/test_decision_packet_eligibility.py`
- `tests/test_decision_packet_section_routing.py`
- `tests/test_quantity_obligation_ledger.py`
- `tests/test_quantitative_retention_packet.py`
- `tests/test_packet_qa.py`
- `tests/test_memo_ready_packet.py`

### New Likely Modules

- `map_briefing_decision_problem.py`
  - Faceted decision problem typing and candidate-answer enumeration.
- `map_briefing_source_evidence_graph.py`
  - Stable source evidence graph over claims, source cards, quantities, relations, quality metadata, and source lineage.
- `map_briefing_decision_obligations.py`
  - Decision obligation graph builder.
- `map_briefing_evidence_answer_matrix.py`
  - Maps source evidence graph nodes to candidate answers, obligations, roles, strengths, uncertainties, and scope.
- `map_briefing_decision_slots.py`
  - Derives fillable packet slots from the obligation graph.
- `map_briefing_slot_filling.py`
  - Fills derived slots from candidate evidence, quantity anchors, source bottom lines, argument model entries, and named gaps.
- Optional: `map_briefing_candidate_richness.py`
  - Scores candidate rows for dedupe and retention without making semantic blocking decisions.
- Optional: `map_briefing_packet_views.py`
  - Builds synthesis, audit, source-trace, and QA views over the same owner graphs and evidence-to-answer matrix.

### Fact Ownership

- Decision question: owned by packet root and passed through every packet stage.
- Decision facets: owned by `decision_problem_report`.
- Candidate answers: owned by `candidate_answer_set`.
- Source evidence graph: owned by `source_evidence_graph`.
- Evidence quality metadata: owned by source evidence graph nodes and quality reports.
- Candidate answers and assumptions: owned by `decision_obligation_graph`.
- Cruxes and evidence obligations: owned by `decision_obligation_graph`.
- Evidence-to-answer roles: owned by `evidence_answer_matrix`.
- Derived slots: owned by `decision_slot_inventory`.
- Slot fills: owned by `decision_slot_fill_report`.
- Answer frame: owned by `map_briefing_answer_frame.py`, then reconciled with the decision obligation graph.
- Quantities: owned by `quantity_ledger` and preserved into packet bundles and retain ledger.
- Source lineage: owned by source IDs/cards and preserved deterministically.
- Sufficiency status: owned by packet sufficiency and coverage reports, not by synthesis prose.

Downstream stages should consume these owner artifacts rather than re-deriving facts from prose, ordering, or formatting.

## Model And Code Responsibility Split

Model-owned semantic proposals:

- propose or critique decision facets;
- propose candidate answers and conditional answer variants;
- propose or critique decision obligations;
- map evidence to candidate answers when semantic role is ambiguous;
- identify cruxes, missing perspectives, and applicability limits;
- compress evidence into readable packet text subject to deterministic invariants;
- critique whether the packet would let an analyst answer the decision question.

Deterministic code-owned guarantees:

- preserve stable source, claim, relation, quantity, obligation, slot, and candidate-answer IDs;
- validate model output schemas;
- reject or downgrade ungrounded candidate answers and obligations;
- preserve exact quantities, source IDs, source labels, directionality, uncertainty qualifiers, and applicability limits;
- compute source lineage and traceability;
- run dedupe, centrality, similarity, diversity, and budget allocation;
- emit coverage, sufficiency, compression, and invariant diagnostics;
- keep broad semantic gates report-only until calibrated.

Classical ML/statistics-owned support:

- candidate similarity and near-duplicate grouping;
- cluster diversity;
- evidence centrality;
- source diversity;
- outlier quantity detection;
- redundancy scoring for packet budget allocation.

Do not replace model semantic judgment with brittle deterministic keyword vetoes. Do not trust model semantics without deterministic grounding, schema, and lineage checks.

## Workstreams

### 1. Decision Facets And Candidate Answers

Purpose:

- Identify what kinds of reasoning the question requires and enumerate plausible candidate answers before generating obligations or slots.

Changes:

- Add `map_briefing_decision_problem.py`.
- Define generic decision facets:
  - `empirical_effect_or_association`
  - `intervention_or_policy_choice`
  - `risk_assessment`
  - `causal_attribution`
  - `forecast_or_prediction`
  - `threshold_or_compliance_judgment`
  - `preference_sensitive_tradeoff`
  - `comparative_option_choice`
  - `information_sufficiency_or_due_diligence`
  - `mixed_or_unclear`
- Allow multiple facets per question with confidence and rationale.
- Enumerate candidate answers:
  - direct candidate answers named or implied by the question;
  - polarity alternatives where the question implies a range;
  - conditional answers where subgroup, comparator, time horizon, or uncertainty may change the answer.
- Deterministic baseline infers broad facets and obvious answer alternatives from question shape and available map signals.
- Optional LLM pass can propose or revise facets and candidate answers in report-only mode with rationale.

Artifacts:

- `decision_problem_report.json`
- `candidate_answer_set.json`
- problem-facet and candidate-answer summary in `briefing_summary.json`

Validation:

- Generic fixtures classify at least empirical, risk, causal, and policy-style facets sensibly.
- Ambiguous questions produce `mixed_or_unclear` plus named uncertainty rather than forced specificity.
- Questions with explicit alternatives produce candidate answers matching those alternatives.
- Polarity questions produce distinct positive, negative, neutral, and conditional candidate answers when appropriate.

QA:

- Metamorphic test: small wording changes should not wildly change facets or candidate answers.

Risks:

- Taxonomy may become too broad or too brittle. Keep facets generic and allow mixed classifications.
- Candidate answers may be model-invented. Require every candidate answer to link to question text, answer frame, or evidence signals.

### 2. Source Evidence Graph

Purpose:

- Preserve source-grounded evidence as a stable graph before projecting it into decision obligations.

Changes:

- Add `map_briefing_source_evidence_graph.py`.
- Build graph nodes for:
  - sources;
  - source cards/excerpts;
  - extracted claims;
  - quantities;
  - relations;
  - source bottom lines;
  - evidence quality metadata when available.
- Build graph edges for:
  - source-to-card;
  - card-to-claim;
  - claim-to-quantity;
  - claim-to-claim relation;
  - source-to-quality;
  - source-bottom-line-to-source.
- Preserve stable IDs from upstream artifacts.
- Add quality fields where available:
  - study design;
  - endpoint directness;
  - population applicability;
  - precision;
  - consistency;
  - source independence;
  - bias/confounding risk;
  - evidence-quality unknown flags.

Artifacts:

- `source_evidence_graph.json`
- `source_evidence_graph.md`
- source graph summary in `briefing_summary.json`

Validation:

- Every packet evidence bundle can trace back to source graph nodes.
- Quantity nodes preserve exact quantity text and source lineage.
- Missing evidence quality is explicit, not treated as high quality.

QA:

- Fixture with claim, quantity, source card, and relation verifies all edges survive.
- Source-label removal still preserves source IDs.

Risks:

- Source graph can become a parallel artifact that downstream ignores. Packet builder must consume it as the evidence owner.

### 3. Decision Obligation Graph

Purpose:

- Make the packet answer the question by first modeling what a good answer requires.

Changes:

- Add `map_briefing_decision_obligations.py`.
- Build an obligation graph from:
  - decision question;
  - decision facets;
  - candidate answer set;
  - answer frame;
  - argument model;
  - source evidence graph summaries;
  - available evidence-role and quantity summaries.
- Represent:
  - candidate answers;
  - assumptions;
  - cruxes;
  - required evidence obligations;
  - counterargument obligations;
  - quantitative obligations;
  - applicability and scope obligations;
  - source-quality cautions;
  - named gaps.
- Each obligation gets stable ID, obligation type, rationale, requiredness, and expected evidence features.
- Every obligation must link to at least one of:
  - question text;
  - candidate answer ID;
  - answer frame field;
  - source evidence graph node;
  - named uncertainty/gap.
- Model-proposed obligations without grounding become suggestions, not active graph nodes.

Artifacts:

- `decision_obligation_graph.json`
- `decision_obligation_graph.md` for human inspection

Validation:

- The eggs question creates obligations for neutral/harmful/beneficial reads, CVD evidence, quantitative estimates, subgroup exceptions, and guideline interpretation.
- Non-eggs canary creates a different but sensible obligation structure.
- Ungrounded model-proposed obligations are rejected or marked `suggested_only`.

QA:

- Model-generated obligations are report-only initially.
- Deterministic validation checks IDs, required fields, duplicate obligations, and source-free invented specifics.

Risks:

- The model may invent obligations not supported by the question. Validation should flag unsupported or over-specific obligations.
- Bad obligation graphs can make the downstream packet coherent but wrong. Graph quality must be evaluated independently before relying on filled slots.

### 4. Evidence-To-Answer Matrix

Purpose:

- Make evidence weight and direction explicit against each plausible answer.

Changes:

- Add `map_briefing_evidence_answer_matrix.py`.
- Join source evidence graph nodes to candidate answers and obligations.
- For each row, represent:
  - evidence node IDs;
  - candidate answer IDs;
  - obligation IDs;
  - evidence role for that answer;
  - directionality;
  - strength or salience;
  - uncertainty;
  - quantitative anchors;
  - applicability/scope limits;
  - evidence quality summary;
  - source IDs and source labels.
- Deterministic code preserves IDs, exact quantities, and lineage.
- LLM can judge semantic role and strength in report-only mode initially.
- Matrix rows must distinguish:
  - salience: how decision-relevant the evidence is;
  - evidential strength: how much the evidence should shift belief;
  - quality: how trustworthy/direct/applicable the evidence is;
  - uncertainty: what limits interpretation.
- Matrix rows must include a `role_basis` explaining whether the role came from model judgment, source metadata, deterministic relation signals, or a fallback.

Artifacts:

- `evidence_answer_matrix.json`
- `evidence_answer_matrix.md`
- `evidence_answer_matrix_quality_report.json`

Validation:

- Load-bearing evidence maps to at least one candidate answer.
- Counterevidence maps to the answer it challenges.
- Quantitative evidence maps with exact quantity text and source IDs intact.
- Matrix rows with model-assigned roles preserve the model rationale and deterministic grounding checks.
- Matrix rows with unknown evidence quality remain usable but carry explicit `quality_unknown` warnings.

QA:

- Fixture where the same evidence supports one answer and limits another.
- Fixture where an evidence item has low quality but high salience; both facts survive.
- Fixture where model role assignment conflicts with deterministic directionality signal; result is a warning or repair path, not silent acceptance.
- Human-readable matrix sample is manually inspected in the vertical slice.

Risks:

- Matrix rows can overstate strength. Keep strength labels calibrated and distinguish salience from evidential quality.
- Matrix quality is the likely highest-risk stage. The vertical slice must evaluate matrix role accuracy before expanding packet views.

### 5. Derived Decision Slot Inventory

Purpose:

- Convert the obligation graph into fillable packet slots without making flat slots the architecture's root.

Changes:

- Add `map_briefing_decision_slots.py`.
- Derive slot types from obligations and evidence-answer matrix rows, using generic slot categories:
  - `answer_support`
  - `counterevidence`
  - `quantitative_anchor`
  - `scope_boundary`
  - `decision_crux`
  - `mechanism_or_context`
  - `source_quality_caution`
  - `named_gap`
- Slots carry:
  - linked obligation IDs;
  - linked candidate answer IDs;
  - expected evidence features;
  - requiredness;
  - allowed evidence roles;
  - multiplicity;
  - compression guidance.

Artifacts:

- `decision_slot_inventory.json`
- slot inventory summary in `briefing_summary.json`

Validation:

- Every required obligation has at least one derived slot or a named reason it is intentionally not fillable.
- Empty or weak evidence produces named gaps rather than silent omission.

QA:

- Metamorphic test: reordering candidate rows does not change required slot inventory.

Risks:

- Slot taxonomy may still drift toward health examples. Keep categories decision-function based and obligation-derived.

### 6. First-Class Quantitative Anchor Bundles

Purpose:

- Stop treating top quantities as checklist obligations only.

Changes:

- Promote top quantity groups from `_top_quantity_anchor_groups()` into protected `quantitative_anchor` candidates before bundle trimming.
- Ensure each top quantity group can become:
  - an evidence bundle;
  - a slot fill;
  - a must-retain item;
  - a section-view input.
- Downgrade `quantity_anchor_question_mismatch` from blocking to warning.
- Preserve source IDs, source labels, claim IDs, quantity IDs, exact quantity text, and source excerpt when available.
- Link quantitative anchors to obligation IDs when they fill quantitative or answer-support obligations.
- Link quantitative anchors to candidate answer IDs through the evidence-to-answer matrix.

Artifacts:

- `decision_briefing_packet.json` includes `quantitative_anchor` bundles when quantities exist.
- `packet_sufficiency_report.json` reports top quantity retention from the same ledger.
- `decision_slot_fill_report.json` records quantitative slot fills.

Validation:

- The eggs case should no longer have `quantitative_anchor: 0` in bundle role counts.
- Top quantities should appear in evidence bundles, slot fills, and must-retain obligations.

QA:

- Regression fixture where candidate cards have no quantities but the quantity ledger does.

Risks:

- Quantity anchors can be off-question or surrogate-only. They should be included with warnings and decision-axis metadata, not blocked.

### 7. Richness-Aware Dedupe

Purpose:

- Prevent thin early rows from suppressing richer later rows.

Changes:

- Replace first-seen `_dedupe_pool()` behavior with group-then-select.
- Group by stable identity:
  - quantity IDs first when present;
  - claim IDs;
  - source card IDs;
  - candidate card ID when truly unique;
  - normalized claim fallback.
- Select the richest row by deterministic richness score:
  - has quantity values;
  - source grounded;
  - has source labels;
  - has source excerpt;
  - high decision relevance score;
  - explicit role;
  - section candidates;
  - source evidence graph node IDs;
  - evidence-to-answer matrix rows;
  - linked obligation IDs or slot IDs;
  - non-noisy claim;
  - direct source/claim IDs.
- Preserve merge provenance in a report rather than discarding silently.

Artifacts:

- `candidate_dedupe_report.json`
- richer rows survive into `decision_briefing_packet.json`

Validation:

- Fixture: thin context row and rich quantity row share claim ID; rich row survives.
- Reordering candidates does not change selected representative.

QA:

- Metamorphic order-invariance test.

Risks:

- Over-merge could erase legitimate nuance. Prefer conservative grouping and report kept-separate near duplicates.

### 8. Slot Filling Layer

Purpose:

- Select evidence to satisfy decision obligations, not arbitrary role budgets.

Changes:

- Add `map_briefing_slot_filling.py`.
- For each derived slot, select ranked candidate evidence.
- Allow one candidate to fill multiple slots with explicit `slot_ids`, `obligation_ids`, and `candidate_answer_ids`.
- Use deterministic ranking for:
  - source grounding;
  - quantity presence;
  - role compatibility;
  - source diversity;
  - centrality or diagnosticity signals when available;
  - exact source linkage;
  - obligation fit features.
  - evidence quality, without letting quality metadata erase direct relevance.
- Optional model refinement can run in report-only mode to flag role-fit and missing-perspective concerns.

Artifacts:

- `decision_slot_fill_report.json`
- packet bundles include `slot_ids` and `obligation_ids`
- unfilled required obligations become `named_gap` objects

Validation:

- Every required slot is either filled or explicitly named as a gap.
- Counterevidence and scope boundaries are retained if available.

QA:

- Fixture with available counterevidence under low lexical overlap still fills counterevidence slot.

Risks:

- Multi-slot evidence may increase repetition downstream. Section views should reference slot use, not duplicate full evidence text.

### 9. Compression Invariants And Packet View Compiler

Purpose:

- Make packet compression useful without losing the evidence features needed for decision support.

Changes:

- Add compression invariants used by all packet views:
  - exact quantity text survives;
  - directionality survives;
  - source ID and source label survive;
  - applicability limit survives;
  - uncertainty qualifier survives;
  - candidate answer linkage survives;
  - obligation and slot IDs survive;
  - evidence quality warning survives when present.
- Redundant prose, repeated background, and non-load-bearing framing can be compressed.
- Packet views are compiled from source evidence graph plus decision obligation graph plus evidence-answer matrix.
- Add an obligation-aware packet budget allocator:
  - reserve space for answer frame and candidate answers;
  - reserve space for top load-bearing evidence;
  - reserve space for strongest counterevidence;
  - reserve space for quantitative anchors and exact estimates;
  - reserve space for scope/applicability limits;
  - reserve space for unresolved cruxes and named gaps;
  - allocate remaining space to source-quality cautions, mechanisms, and context by marginal decision value.
- Budget allocation should be inspectable and should not silently evict required obligations.

Artifacts:

- `packet_compression_report.json`
- `packet_budget_allocation_report.json`
- compression invariant warnings in `qa_packet.json`

Validation:

- Any compressed packet item can be traced back to full source graph nodes.
- Compression never drops exact top quantities or source IDs.
- Required obligations are either represented in the synthesis packet or named as omitted with reason and downstream risk.
- Budget decisions distinguish omitted-because-represented, omitted-because-low-value, and omitted-because-over-budget.

QA:

- Fixture with redundant prose and one exact quantity verifies prose compresses while quantity/source/uncertainty survive.
- Fixture with too many candidate evidence items verifies the allocator preserves quantities, counterevidence, and scope before general context.

Risks:

- Compression may become too conservative and overstuff the synthesis packet. Use view-specific budgets after invariants are met.
- Budget allocation can hide value judgments. Emit explicit rationale and make broad budget heuristics report-only until calibrated.

### 10. Packet Views Over The Same Decision Model

Purpose:

- Avoid forcing synthesis, audit, and source traceability to share one overloaded packet shape.

Changes:

- Optionally add `map_briefing_packet_views.py`.
- Build multiple views from the same underlying source graph, obligation graph, evidence-answer matrix, and slot fills:
  - `synthesis_packet`: compact, decision-ready evidence and reasoning structure.
  - `audit_packet`: fuller evidence, gaps, warnings, and rejected candidates.
  - `source_trace_packet`: source IDs, source labels, excerpts, and lineage.
  - `qa_packet`: coverage metrics and diagnostics.
- Keep `decision_briefing_packet.json` as the compatibility envelope.

Artifacts:

- `synthesis_packet.json`
- `audit_packet.json`
- `source_trace_packet.json`
- `qa_packet.json`

Validation:

- All packet views reference the same obligation, slot, candidate answer, source, claim, and quantity IDs.

QA:

- ID consistency test across views.

Risks:

- Too many views can create drift. All views must be projections of the same owner graphs and matrix, not separately assembled artifacts.

### 11. Packet Builder Refactor Around Decision Model

Purpose:

- Make `build_decision_briefing_packet_bundle()` assemble a case file from decision facets, candidate answers, source evidence graph, obligation graph, evidence-answer matrix, slot fills, and packet views.

Changes:

- Keep the public packet shape compatible where possible.
- Add:
  - `decision_problem_report`
  - `candidate_answer_set`
  - `source_evidence_graph`
  - `decision_obligation_graph`
  - `evidence_answer_matrix`
  - `decision_slots`
  - `slot_fill_report`
  - `named_gaps`
  - `candidate_dedupe_report`
- Build `evidence_bundles` from slot-filled evidence and evidence-answer matrix rows.
- Build section views from slot and obligation needs rather than raw role buckets.
- Keep source trail and answer frame unchanged except where IDs are added.

Artifacts:

- Updated `decision_briefing_packet.json`
- Updated `decision_briefing_packet_report.json`
- Updated `section_views`

Validation:

- Existing packet tests pass.
- New decision-model and slot-based tests verify routing and retained quantities.

QA:

- Before/after comparison on eggs and one unrelated case.

Risks:

- This is the main integration slice. Keep old report fields until downstream consumers are migrated.

### 12. Obligation-Centered Coverage And Sufficiency

Purpose:

- Make telemetry measure actual decision support rather than post-hoc bundle counts.

Changes:

- Coverage report should distinguish:
  - candidate answer represented;
  - source graph node represented;
  - required obligation filled;
  - required obligation unfilled with named gap;
  - derived slot filled;
  - top quantity retained in bundle;
  - top quantity retained only in ledger;
  - counterevidence available but omitted;
  - high-priority candidate represented by another bundle;
  - high-priority candidate truly lost.
- Sufficiency should read from the obligation graph, slot inventory, and slot fills.
- Evidence quality sufficiency should distinguish unknown quality from weak quality.

Artifacts:

- Enhanced `packet_sufficiency_report.json`
- Enhanced `coverage_report`
- `obligation_coverage_report.json`
- `slot_coverage_report.json`
- `candidate_answer_coverage_report.json`
- `evidence_quality_coverage_report.json`

Validation:

- No contradictions between coverage and sufficiency counts.
- High-priority omitted count separates represented vs truly lost evidence.

QA:

- Regression where a high-priority candidate is represented by a merged richer bundle should not count as truly lost.

Risks:

- New telemetry may be noisy. Keep broad gates report-only until calibrated.

### 13. QA And Regression Harness

Purpose:

- Prevent recurrence of the evidence-loss and weak-decision-model failure classes.

Changes:

- Add fixtures for:
  - quantity row competing with thin claim row;
  - counterevidence under lexical mismatch;
  - source bottom line with no matching candidate card;
  - off-question evidence that should warn but not block;
  - duplicated evidence filling multiple obligations;
  - reorder-invariant candidate pool;
  - empirical question vs policy question producing different facet sets and obligation graphs;
  - ambiguous question producing mixed facets and named uncertainty.
  - evidence supporting one candidate answer while challenging another;
  - source graph quality unknown vs weak quality;
  - compression preserving quantities, source IDs, directionality, and uncertainty.

Validation Commands:

```bash
PYTHONPATH=src python3 -m pytest tests/test_decision_briefing_packet.py tests/test_quantity_obligation_ledger.py tests/test_decision_packet_eligibility.py tests/test_decision_packet_section_routing.py -q
PYTHONPATH=src python3 -m pytest -q
```

QA:

- Canary packet build on eggs.
- Canary packet build on a non-eggs case.
- Manual packet read after automated checks.

Risks:

- Metrics can improve without memo quality improving. Keep final memo read as part of all-up evaluation.

### 14. Vertical Slice First

Purpose:

- Prove the architecture improves packet usefulness before building all views and broad integrations.

Changes:

- Implement a minimal vertical slice before full refactor:
  - decision facets;
  - candidate answers;
  - source evidence graph for claims/quantities/sources;
  - decision obligations;
  - evidence-to-answer matrix;
  - first-class quantitative bundles;
  - richness-aware dedupe;
  - one synthesis packet view;
  - obligation/quantity/source QA.
- Run on eggs plus one non-eggs canary.
- Only after the slice improves real packet quality should the plan proceed to multiple views and broader coverage refactors.

Artifacts:

- `vertical_slice_packet_report.json`
- eggs vertical-slice packet and memo
- non-eggs canary vertical-slice packet and memo

Validation:

- Eggs improves the observed failure mode.
- Non-eggs canary does not show obvious overfit.
- Final memo has better evidence retention or the failure is traced to synthesis rather than packet construction.

QA:

- Manual packet and memo read.
- Before/after packet metrics.

Risks:

- The vertical slice may expose that source extraction is too weak. Record that as out of scope unless a small integration fix can route existing source evidence graph inputs better.

### 15. Before/After Evaluation

Purpose:

- Verify that packet changes improve decision support, not just internal metrics.

Changes:

- Add or update a comparison report that records old vs new packet quality.
- Evaluate:
  - decision facet quality;
  - candidate answer set quality;
  - source evidence graph coverage;
  - obligation graph plausibility;
  - evidence-to-answer matrix quality;
  - quantitative-anchor bundle count;
  - retained top quantities;
  - filled required obligation count;
  - unfilled named gap count;
  - true high-priority loss count;
  - counterevidence retention;
  - low-question-fit primary evidence count;
  - final memo readability and evidence retention;
  - downstream decision usefulness compared to direct source synthesis.

Artifacts:

- `decision_model_packet_before_after_report.json`
- updated eggs briefing artifact
- at least one non-eggs canary briefing artifact
- direct-source-synthesis baseline artifact for the same question and source set
- packet-vs-direct-synthesis comparison report

Validation:

- Eggs improves on the current failure mode.
- Non-eggs canary does not regress or become case-specific.
- Final memo can trace load-bearing claims to packet obligations and sources.
- Packet-based synthesis improves at least one decision-usefulness dimension over direct source synthesis without losing source faithfulness:
  - clearer answer alternatives;
  - better retained quantities;
  - better counterevidence;
  - better scope/applicability limits;
  - clearer named gaps;
  - better traceability.

QA:

- Manual read of final memo and packet after automated checks.
- Side-by-side read of packet-based synthesis vs direct source synthesis.

Risks:

- A cleaner packet may still not produce a better memo if synthesis prompt is weak. If so, record as a synthesis-stage failure, not a packet-stage failure.
- If packet-based synthesis does not beat direct synthesis on any decision-usefulness dimension, stop broad implementation and diagnose whether the failure is source evidence graph, matrix quality, budget allocation, or synthesis.

## Execution Order

1. Add faceted decision problem typing as a report-only artifact.
2. Add candidate answer set as a report-only artifact.
3. Add minimal source evidence graph for claims, quantities, source cards, and source lineage.
4. Add decision obligation graph as a report-only artifact.
5. Add evidence-to-answer matrix as a report-only artifact.
6. Derive slot inventory from the obligation graph and matrix.
7. Promote quantitative anchors to first-class protected candidates.
8. Replace first-seen dedupe with richness-aware dedupe.
9. Add slot filling while preserving current packet outputs.
10. Run the vertical slice on eggs and one non-eggs canary.
11. Add packet views only after the vertical slice improves packet quality.
12. Refactor packet builder to assemble from decision model and slot fills.
13. Refactor section views to derive from obligations and slot fills.
14. Rework coverage and sufficiency around obligations.
15. Add regression and metamorphic tests.
16. Run before/after evaluation and update artifacts.

## Slice Protocol

Each implementation slice must include:

- scope;
- owned files;
- forbidden files if broad refactors are risky;
- expected artifacts;
- focused verification command;
- full verification command for structural slices;
- done condition;
- commit after verification.

Stop rather than continuing if:

- focused tests fail;
- full suite fails after a structural slice;
- artifact schema changes break downstream consumers without compatibility;
- a partial subsystem is left without a deferred-work entry;
- packet behavior changes outside the planned scope;
- decision-model artifacts are produced but not wired into diagnostics or verification.
- the vertical slice does not improve packet quality and no root cause is recorded.

## Acceptance Criteria

- Final packet has explicit faceted `decision_problem_report`.
- Final packet has explicit `candidate_answer_set`.
- Final packet has a source evidence graph that owns source/claim/quantity/quality lineage.
- Final packet has a decision obligation graph with candidate answers, assumptions, cruxes, evidence obligations, and named gaps.
- Final packet has an evidence-to-answer matrix linking source evidence to candidate answers and obligations.
- Evidence-to-answer matrix rows distinguish salience, evidential strength, evidence quality, and uncertainty.
- Final packet has `decision_slots` derived from obligations, not manually hard-coded as the root design.
- Top quantitative anchors are represented as evidence bundles, not only retain obligations.
- Dedupe prefers richer evidence over earlier thin rows.
- Deterministic semantic blocking is removed or converted to warnings.
- Section views derive from obligation and slot needs.
- Coverage distinguishes represented evidence from truly lost evidence.
- Eggs packet no longer has zero quantitative-anchor bundles when quantity evidence exists.
- At least one non-eggs case satisfies the same decision-model-first invariants.
- Compression invariants protect quantities, directionality, source identity, applicability, uncertainty, and evidence quality warnings.
- Packet budget allocation is obligation-aware and inspectable.
- Packet-based synthesis is compared against direct source synthesis on the same question and source set.
- Model/code responsibility split is reflected in implementation: model semantic outputs are validated by deterministic grounding and lineage checks.
- Full test suite passes.

## Red-Team Checks

- Does decision problem typing overfit to health or nutrition questions?
- Does faceted typing avoid forcing a single misleading category?
- Are candidate answers explicit and grounded in the question or evidence?
- Does the source evidence graph become a disconnected artifact?
- Do generic decision questions produce sensible obligation graphs?
- Does the obligation graph become too elaborate for simple cases?
- Does allowing multi-obligation evidence create repetition downstream?
- Do warnings become too noisy to act on?
- Does slot filling preserve source IDs and exact quantities?
- Does the evidence-to-answer matrix assign roles accurately?
- Does the matrix conflate salience with evidence quality?
- Does budget allocation preserve the evidence needed for decision usefulness?
- Does final memo quality improve, or only internal metrics?
- Does the system make missing evidence explicit instead of inventing coverage?
- Does deterministic code still make hidden semantic decisions?
- Does the model invent obligations or candidate answers not grounded in the question?
- Are packet views projections from one graph, or are they drifting into separate parallel artifacts?
- Does compression preserve the features needed for decision support?
- Does the vertical slice prove value before broad architecture expansion?
- Does packet-based synthesis actually beat direct source synthesis on at least one decision-usefulness dimension?

## Generalizability Checks

- Run on eggs and at least one unrelated case.
- Reorder candidate rows and confirm obligation graph and slot fills are stable within expected tolerance.
- Paraphrase the decision question and confirm decision facets and core obligations remain stable.
- Paraphrase the decision question and confirm candidate answers remain stable when meaning is preserved.
- Remove source labels from a fixture and confirm source IDs still preserve lineage.
- Add an off-question quantitative estimate and confirm it becomes a warning or named gap, not silent deletion.
- Add duplicate evidence with different richness and confirm the richer representation survives.
- Run an empirical-effect question and a policy-choice question and confirm they produce different obligation patterns.
- Run a mixed empirical/policy question and confirm multiple facets are preserved.

## Completion Audit

The plan is complete only when a final review packet records:

- completed slices and commit SHAs;
- files changed;
- verification commands and results;
- new invariants and tests;
- decision problem typing quality;
- candidate answer quality;
- source evidence graph coverage;
- obligation graph quality;
- evidence-to-answer matrix quality;
- before/after packet metrics;
- final eggs packet and memo quality read;
- non-eggs canary result;
- known limitations and deferred work.
