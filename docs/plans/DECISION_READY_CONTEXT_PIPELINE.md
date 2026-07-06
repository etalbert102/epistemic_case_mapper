# Plan: Decision-Ready Context Pipeline

## Objective

Produce briefing memos where each section receives clean, decision-specific context and writes useful analysis rather than generic prose. The system should make bad context visible before model generation, preserve source traceability, and generalize across cases.

The target end state is a staged context pipeline:

1. source chunks/spans
2. `source_evidence_cards.json`
3. `source_sufficiency_report.json`
4. `candidate_evidence_cards.json`
5. `source_map_reconciliation.json`
6. `evidence_quality_report.json`
7. `memo_argument_spine.json`
8. `section_reasoning_cards.json`
9. `section_context_acceptance_report.json`
10. section markdown synthesis
11. memo-level coherence review
12. specificity and traceability validation

## Current Gap

The current section prompts are uneven:

- Some sections receive almost no concrete evidence, so the model writes generic prose.
- Other sections receive concrete evidence but also noisy or off-question obligations.
- Context is mostly claims plus instructions, not structured reasoning.
- Downstream context is derived mostly from generated map artifacts, not directly from source-document spans.
- Validation catches coverage failures but not enough decision-usefulness failures.
- Deterministic code performs role assignment and context reduction, but it does not yet produce a clean section-level argument model.

Recent eggs briefing diagnostics exposed the failure mode:

- `Why This Read` received target shape and transition guidance but no owned evidence.
- `Practical Read` received a plan but no source-backed context.
- `Evidence Carrying the Conclusion` received concrete evidence plus an irrelevant cancer-related quantitative anchor.
- `Practical Scope and Exceptions` received useful cards but still repeated comparator material and inherited noisy obligations.

## Non-Goals

- Do not add source acquisition.
- Do not assume source acquisition is available; use already configured case/source documents and generated source spans where present.
- Do not add case-specific rules for eggs, HEPA, LHC, CVD, or any other named case.
- Do not weaken evidence validation to accept prettier prose.
- Do not force the model to infer relevance from noisy obligations.
- Do not remove existing debug artifacts.

## Design Principles

- Deterministic code owns filtering, dedupe, role allocation, traceability, and gates.
- AI owns compression, salience judgment on already-curated candidates, and prose synthesis.
- Classical ML/statistics can support ranking, clustering, centrality, and near-duplicate detection.
- Every main memo section should have an explicit decision move.
- Main memo context should be source-grounded before it is map-grounded: generated claims must reconcile to source evidence cards or be demoted.
- Section packets should be small enough to reason over: prefer a few well-justified cards over broad context dumps.
- Bad context should fail visibly before section generation.
- Insufficient source corpora should produce bounded answers, not confident synthesis.
- Source-backed evidence should still be weighted by quality, directness, and decision relevance.
- Local section quality is not enough; the final memo must be checked for global coherence.
- Counterweights should be preserved as counterweights, not filtered away as inconvenience.

## Implementation Ownership Matrix

Purpose: Make the deterministic/model split explicit enough that future implementation cannot accidentally delegate source grounding, pass/fail gates, or traceability to the model.

All model outputs that enter durable artifacts must be parsed through typed schemas, preferably Pydantic models, and written with validation failures in a companion report. Invalid model output is not silently coerced into accepted context.

### Ownership Rules

| Artifact or field | Primary producer | Allowed model role | Code validation | Fallback behavior |
| --- | --- | --- | --- | --- |
| `source_id`, title, URL, source path, source type | Deterministic code from case manifest and source metadata | None | Required-field and path/URL checks | Mark source metadata incomplete; do not invent values |
| `source_span`, offsets, hashes, excerpt text | Deterministic code from source files and existing anchors | None | Hash/offset/excerpt consistency checks | Use recovered anchor with confidence label, or appendix-only |
| Quantity extraction | Deterministic code first, using regex/parsers over source text | Optional model explanation of what the quantity means | Numeric value/unit/source-span checks | Keep raw quantity with no interpretation |
| Fragment, boilerplate, duplicate, and near-duplicate flags | Deterministic code plus classical similarity methods | None initially | Threshold reports and sample diagnostics | Keep card but demote or mark risk |
| Semantic similarity, clustering, centrality, duplicate groups | Classical ML/statistics | None | Deterministic thresholds and artifact summaries | Disable ranking feature and record missing metric |
| `decision_relevance_score` | Hybrid: deterministic lexical/directness features plus optional model salience score | Suggest salience only from anchored source/card text | Score components recorded separately; no opaque single score | Use deterministic score only |
| `endpoint_match`, `population_match`, comparator/outcome fields | Hybrid: deterministic question/source overlap plus optional model classification | Classify from anchored source text using schema | Require source quote, confidence, and no unsupported labels | Mark unknown rather than infer |
| Evidence type and source quality/provenance | Deterministic metadata/rules where possible | Optional classification only when text supports it | Allowed-label schema and source-span support | Mark unspecified |
| Source sufficiency status | Deterministic code from coverage checks | Optional summary wording only | Required missing-source categories and decision-question coverage checks | Mark answer as bounded/insufficient |
| Evidence quality weight | Hybrid: deterministic provenance/directness/design indicators plus optional model classification | Explain quality limits from anchored card text | Components recorded separately; no opaque single quality score | Use unweighted card with limitation flag |
| `supports_challenges_or_scopes` / card role candidates | Hybrid | Suggest role from source card plus decision question | Must cite card IDs and role rationale; unsupported roles rejected | Preserve as uncategorized candidate |
| Candidate card inclusion/demotion | Deterministic code | None, except optional salience tie-break after filters | Demotion reason required | Keep in appendix/telemetry if uncertain |
| Argument spine candidate selection | Deterministic code plus classical ranking | Model may compress selected candidates, not select from the full map | Every load-bearing sentence must trace to selected cards | Use deterministic spine text |
| `decision_move`, `reader_question_answered`, section thesis | Hybrid: deterministic templates from spine plus model wording | Improve wording or propose section-local framing | Must remain tied to spine and decision question | Use deterministic template |
| `owned_cards`, `reference_only_cards`, `do_not_use_cards` | Deterministic code | Optional salience check on borderline assignments | Card budget, source backing, role coverage, and exclusion checks | Trim/reassign deterministically |
| `reason_for_inclusion`, `intended_role` | Hybrid | Model may draft concise rationale from accepted card and section question | Must mention section relevance and use allowed role labels | Generate deterministic rationale from role assignment |
| `excluded_near_miss_cards` and exclusion reasons | Deterministic code | Optional wording only | Reason required for each exclusion | Keep card as reference-only if exclusion confidence is low |
| Section context acceptance pass/fail | Deterministic code | None | Pydantic/schema plus rule checks | Mark `context_not_synthesis_ready` |
| Section markdown prose | Model | Full synthesis from accepted packet only | Markdown parse, source coverage, specificity, and overstatement checks | Retry, then deterministic bounded section |
| Memo-level coherence findings | Deterministic code plus optional model critique | Identify repetition, contradiction, missing throughline, and answer/body mismatch | Findings must cite sections/cards, not free-floating opinions | Keep memo with visible coherence warnings |
| Citations/source list | Deterministic code | None | Source IDs must resolve to metadata | Omit unresolved citation and record error |
| Final memo metadata/question/sources | Deterministic code | None | Exact decision question and source list checks | Insert deterministic metadata block |

### Model Call Boundaries

Each model call must receive the minimum context needed for its job:

- Source semantic extraction: one source chunk or recovered span, source metadata, and the decision question.
- Role/salience classification: anchored card text, card metadata, and the decision question; no full memo draft.
- Spine compression: selected candidate cards only, not the full map.
- Section synthesis: accepted section contract, owned cards, allowed reference cards, and local transition goal; no rejected cards except named `do_not_use_cards`.
- Memo coherence critique: final memo, section contracts, argument spine, and source-backed answer only; no new source evidence.
- Prose repair: section markdown plus validation failures; no new evidence.

### Conflict Policy

- If model salience disagrees with deterministic ranking, keep both scores in telemetry and use deterministic ranking until calibration shows the model improves held-out quality.
- If model classification adds a role, endpoint, population, or limitation not supported by the source span, reject it and record `unsupported_model_label`.
- If deterministic filters remove a model-flagged counterweight, keep it in appendix or near-miss telemetry unless it is demonstrably duplicate/off-question.
- If schema validation fails, retry only for model-generated language/classification fields. Do not retry deterministic source identity or citation fields.

## Inventory And Dependency Map

Current code surfaces:

- `map_briefing_pipeline.py`
  - Builds map/scaffold, applies atomic cards, attaches global memo plan, writes scaffold artifacts, and invokes final reader outputs.
  - Best integration point for source cards, candidate cards, source-map reconciliation, and argument spine is after `_apply_atomic_cards_to_briefing_map` and before `_attach_global_memo_plan`.
- `data/cases/*/case.yaml` and source text paths
  - Already record source IDs, titles, URLs, and local text paths. Source evidence cards should consume these files when available, not require new acquisition.
- staged semantic extraction artifacts
  - Claims may already include source IDs, spans, hashes, and excerpts. Reuse these anchors before falling back to text matching.
- `main_memo_obligations.py`
  - Builds the current obligation plan. This is useful input, but too noisy to be the model-facing context by itself.
- `map_briefing_global_plan.py`
  - Assigns obligations to sections. The new argument spine should inform or constrain this stage.
- `map_briefing_section_input_compiler.py`
  - Builds `model_section_packet`. This is the main integration point for `section_reasoning_cards`.
- `map_briefing_section_prompt_contract.py`
  - Separates model-facing packets from validation obligations. The new plan should preserve this boundary.
- `map_briefing_section_rewrite.py`
  - Prompts the model for section markdown and validates output. The new specificity checks should plug in here.
- `decision_argument_artifacts.py`
  - Already creates traceability matrices and argument artifacts. These should be reused rather than duplicated.
- `map_briefing_model_context.py`
  - Already audits prompt context. Extend it to include context-quality and card/spine visibility.

Existing artifacts to preserve:

- `global_memo_plan.json`
- `source_evidence_cards.json`
- `source_sufficiency_report.json`
- `source_map_reconciliation.json`
- `evidence_quality_report.json`
- `section_context_acceptance_report.json`
- `memo_coherence_report.json`
- `final_brief_evaluation.json`
- `runtime_budget_report.json`
- `pipeline_migration_ledger.json`
- `section_synthesis_packets.json`
- `section_rewrite_report.json`
- `main_memo_obligation_ledger.json`
- `unified_requirement_ledger.json`
- `decision_traceability_matrix*.json`
- `model_context_audit.json`

## Workstreams

### 0. Typed Schemas And Ownership Enforcement

Purpose: Turn the implementation ownership matrix into code-level contracts before adding new model-dependent stages.

Deterministic code:

- Define typed schemas for durable artifacts and model-returned structures:
  - source evidence cards
  - candidate evidence cards
  - source-map reconciliation rows
  - argument spine entries
  - section reasoning contracts
  - section context acceptance rows
  - model classification outputs
- Mark each field as:
  - deterministic-only
  - model-suggested
  - hybrid
  - model-prose-only
- Reject or quarantine model output that tries to populate deterministic-only fields.
- Record validation failures by artifact and field.

AI role:

- None.

Artifacts:

- schema definitions in code
- ownership validation failures in the relevant report artifacts

Validation:

- Every durable artifact can be validated independently.
- Every model output used downstream has a schema parse result.
- Deterministic-only fields cannot be overwritten by model output.

### 1. Source Evidence Card Construction

Purpose: Build source-grounded evidence cards from already available source documents, chunks, excerpts, spans, and source metadata before relying on generated map claims.

Deterministic code:

- Read source metadata from the case manifest when available:
  - `source_id`
  - title
  - URL
  - source path
  - source type
  - publication metadata
- Use existing generated claim anchors when present:
  - `source_id`
  - `source_span`
  - `source_start`
  - `source_end`
  - `source_text_hash`
  - `excerpt_hash`
- Create source cards with:
  - `source_card_id`
  - `source_id`
  - `source_title`
  - `source_url`
  - `source_span`
  - `source_quote_or_excerpt`
  - `span_hash`
  - `decision_relevance_score`
  - `endpoint_match`
  - `population_match`
  - `exposure_or_intervention`
  - `comparator`
  - `outcome_or_endpoint`
  - `evidence_type`
  - `quantity_values`
  - `limitations`
  - `supports_challenges_or_scopes`
  - `fragment_risk`
  - `boilerplate_risk`
- If exact spans are missing, use source-text search and chunk-local matching to recover the best available anchor, marking confidence.

AI role:

- Optional semantic extraction from source chunks when deterministic span recovery is insufficient.
- Optional classification of evidence role from already anchored source text.

Artifacts:

- `source_evidence_cards.json`
- `source_evidence_card_report.json`

Validation:

- Main-context cards must have source ID and either an exact span/hash or a clearly marked recovered anchor.
- Cards without source anchors are appendix-only unless explicitly marked as model-generated interpretation candidates.
- Source cards should include enough local text for a human judge to inspect the basis without rereading the whole document.

### 2. Source Sufficiency Gate

Purpose: Detect when the available source set cannot support a decision-ready answer before the system writes a confident memo.

Deterministic code:

- Compare the decision question against available source cards for:
  - direct answer coverage
  - relevant population/context coverage
  - intervention/exposure/comparator coverage
  - outcome/endpoint coverage
  - support/counterweight/scope coverage
  - missing crux categories
- Classify source sufficiency:
  - sufficient for decision-ready answer
  - sufficient for bounded answer
  - insufficient; map can only report what provided documents say
- Record missing-source categories without doing source acquisition.

AI role:

- Optional wording of the bounded-answer caveat from deterministic sufficiency findings.

Artifact:

- `source_sufficiency_report.json`

Validation:

- If source coverage is insufficient, the argument spine and final memo must carry a bounded-answer status.
- The memo must not imply that absent evidence was comprehensively searched if only provided documents were inspected.
- Missing-source categories must be generic and derived from the decision question, not case-specific vocabularies.

### 3. Candidate Evidence Card Curation

Purpose: Reconcile source cards with map claims, quantities, relations, obligations, and graph outputs into broad but filtered candidate evidence cards.

Deterministic code:

- Build cards with:
  - `card_id`
  - `source_card_ids`
  - `claim`
  - `source`
  - `source_ids`
  - `claim_ids`
  - `evidence_family`
  - `decision_relevance_score`
  - `endpoint_match`
  - `population_scope`
  - `role_candidates`
  - `quantity_values`
  - `fragment_risk`
  - `off_question_risk`
  - `duplicate_group_id`
- Reconcile generated claims against source evidence cards:
  - exact source span/hash match
  - source ID plus text overlap
  - quantity overlap
  - semantic similarity
  - relation/claim ID lineage
- Drop or demote:
  - truncated fragments
  - boilerplate
  - duplicate claims
  - off-question endpoints
  - unsupported source labels
- Preserve counterweights with explicit role tags instead of dropping them.
- Surface high-relevance source cards with no matching map claim as `missing_from_map_candidate`.

AI role:

- None initially.
- Optional later use: semantic relevance scoring after deterministic filters.

Artifacts:

- `candidate_evidence_cards.json`
- `candidate_card_curation_report.json`
- `source_map_reconciliation.json`

Validation:

- Cards must have source/claim traceability.
- Cards used in the main memo must trace to source evidence cards, not only generated claim text.
- Main-card set must include support, counterweight, and scope candidates when present.
- Report cards that were demoted to appendix-only and why.
- Report generated claims that lack source-card backing.

### 4. Evidence Quality Weighting

Purpose: Prevent the system from treating all source-backed cards as equally decision-relevant or equally credible.

Deterministic code:

- Add transparent quality components to cards:
  - directness to decision question
  - source type/provenance
  - evidence design indicators when available
  - recency/publication date when available
  - sample/population/context match when available
  - quantity precision and uncertainty when available
  - conflict-of-interest/funding flags when source text or metadata exposes them
  - limitation flags
- Keep components separate instead of collapsing into an opaque score.
- Use quality components to influence card ranking, argument spine confidence, and section card budgets.

AI role:

- Optional extraction/classification of design indicators, limitations, and conflict-of-interest statements from anchored source text.
- No authority to upgrade quality without source-span support.

Artifacts:

- `evidence_quality_report.json`
- quality fields on `candidate_evidence_cards.json`

Validation:

- Quality components must cite source-card IDs or metadata.
- Unknown quality fields remain unknown; they are not inferred.
- Argument spine must explain when the recommendation is driven by weak, indirect, old, or sparse evidence.

### 5. Mostly Deterministic Memo Argument Spine

Purpose: Build the central reasoning structure before section writing.

Deterministic code:

- Select candidates for:
  - default answer
  - strongest support
  - strongest counterweight
  - scope boundary
  - practical implication
  - decision cruxes
  - confidence reason
  - source sufficiency status
  - what would change the answer
- Use scoring from:
  - question relevance
  - source quality/provenance
  - source sufficiency status
  - evidence family
  - relation centrality
  - duplicate-adjusted weight
  - directness to endpoint/population

AI role:

- Compress selected candidates into concise spine language.
- Do not select from the full noisy map.
- If model output is malformed or unsupported, fall back to deterministic spine text.

Artifact:

- `memo_argument_spine.json`

Validation:

- Spine must answer the decision question.
- Spine must include source-backed support and counterweight if available.
- Spine must distinguish default answer from exceptions.
- Spine must distinguish strong recommendation, weak recommendation, bounded answer, and insufficient-source answer.
- Spine must name what would change the recommendation.
- Every load-bearing statement must trace to cards.
- Every load-bearing card must trace back to one or more source evidence cards.

### 6. Section Reasoning Contracts

Purpose: Give each section a clear decision move and the exact cards it may use.

Deterministic code:

- Build one contract per section:
  - `section`
  - `decision_move`
  - `reader_question_answered`
  - `section_thesis`
  - `owned_cards`
  - `reference_only_cards`
  - `required_counterweight`
  - `required_scope_boundary`
  - `allowed_quantities`
  - `do_not_use_cards`
  - `excluded_near_miss_cards`
  - `do_not_overstate`
  - `target_shape`
- Derive contracts from the argument spine and curated evidence cards, not raw obligations.
- Include source-card IDs in `owned_cards` so final memo traceability can explain which source spans drive each section.
- Include a short `reason_for_inclusion` and `intended_role` for each owned card:
  - support
  - counterweight
  - scope boundary
  - quantitative anchor
  - practical implication
  - uncertainty/confidence driver
- Include near-miss cards excluded from the section with exclusion reasons so context pruning can be audited.

AI role:

- Optional compression of multiple cards into section-local reasoning notes.

Artifact:

- `section_reasoning_cards.json`

Validation:

- Every generated section except low-value metadata sections must have:
  - at least one concrete owned card or an explicit reason it does not need one
  - a decision move
  - a reader implication
  - traceable source IDs
  - a clear explanation of why each owned card belongs in that section

### 7. Section Context Acceptance Test

Purpose: Decide whether each section packet is synthesis-ready before any model writes prose.

Deterministic code:

- Check each section packet for:
  - the exact decision question or section-local subquestion
  - a section thesis or decision move
  - 3-7 owned source-backed cards by default
  - an explicit justification when a section uses fewer than 3 or more than 7 owned cards
  - per-card `reason_for_inclusion`
  - per-card `intended_role`
  - source-card IDs and source anchors
  - excluded near-miss cards with reasons
  - low-value or off-question cards included in the packet
  - duplicate or overlapping cards consuming card budget
- Emit a short readiness statement:
  - `this_section_can_answer`
  - `because`
  - `missing_context`
  - `context_risk_level`

AI role:

- Optional salience check on borderline card assignments after deterministic filters.
- Optional rewrite of the readiness statement, but not ownership of pass/fail.

Artifact:

- `section_context_acceptance_report.json`

Validation:

- A packet is synthesis-ready only if the owned cards can plausibly answer the section's reader question.
- A packet with too much context must fail or be trimmed before synthesis.
- A packet with only abstract goals and no source-backed cards must fail unless the section is explicitly metadata-only.
- Each included card must have a role and inclusion reason.
- Each excluded near-miss must have an exclusion reason.
- Low-value included cards must be counted separately from high-relevance omitted cards.

### 8. Context Quality Gate

Purpose: Prevent bad prompts.

Start in report-only mode, then promote calibrated checks to blocking.

Checks:

- Missing decision object.
- Missing section decision move.
- Missing source-backed owned cards.
- Missing source-card anchors.
- Missing card inclusion reasons.
- Missing card intended roles.
- Owned card count outside budget without justification.
- Included low-value card count.
- Off-question card count.
- Fragment/truncation risk.
- Duplicate overload.
- Counterweight absent when map contains counterweight.
- Scope boundary absent when recommendation is conditional.

Artifact:

- `section_context_quality_report.json`
- `source_coverage_report.json`
- `section_context_acceptance_report.json`

Behavior:

- If severe failure in report-only mode, still run but label output.
- After calibration, block model synthesis and use deterministic fallback when context is too weak.

### 9. Section Markdown Synthesis

Purpose: Let the model write natural decision-ready prose from clean contracts.

Prompt:

- "You are an analyst producing decision-ready analysis."
- Use the section contract.
- Use only the owned cards and allowed reference cards in the accepted section packet.
- Explain what follows for the reader.
- Do not mechanically restate cards.
- Do not add facts outside cards/draft.
- Return regular markdown only.

AI role:

- Write section prose.
- Manage local transitions.
- Weigh support versus counterweight in natural language.
- Respect each card's intended role instead of reclassifying evidence.

Deterministic code:

- Parse markdown.
- Attach source links.
- Run validation.
- Repair only general formatting/citation issues, not missing reasoning.

Artifacts:

- `section_rewrite_*_prompt.txt`
- `section_rewrite_*_raw.txt`
- `section_rewrite_report.json`

### 10. Memo-Level Coherence Review

Purpose: Catch memos that have locally acceptable sections but are globally repetitive, inconsistent, or weak as decision support.

Deterministic code:

- Check the assembled memo against:
  - exact decision question appears at the top
  - opening answer matches the argument spine and body
  - section claims do not contradict the spine or each other
  - repeated evidence/cards across sections are below a configured threshold
  - every major crux in the spine appears somewhere in the memo
  - bounded-answer/source-sufficiency status is visible when applicable
  - final source list resolves all cited source IDs

AI role:

- Optional memo-level critique for narrative throughline, awkward transitions, and unresolved tensions.
- The model may propose edits, but cannot introduce new evidence or alter source-grounded conclusions.

Artifacts:

- `memo_coherence_report.json`
- optional model critique artifact

Validation:

- Coherence findings must cite section names, spine entries, cards, or source IDs.
- If the opening answer and body disagree, the memo fails finalization.
- If repetition is high, rerun section synthesis or apply deterministic dedupe before final output.

### 11. Specificity And Decision-Usefulness Validation

Purpose: Reject polished but generic prose.

Start in report-only mode, then promote calibrated checks to blocking.

Checks:

- Section mentions decision object or accepted synonym.
- Section mentions relevant endpoint/evidence family when expected.
- Section includes concrete support/counterweight/scope boundary if assigned.
- Section explains the implication for the reader.
- Section does not rely on generic filler:
  - "specific conditions"
  - "external factors"
  - "certain effects"
  - "defined criteria"
  unless anchored to cards.
- Section does not overstate evidence beyond card scope.
- Section load-bearing claims must map back to source-card IDs.
- Section does not use excluded near-miss cards.

Artifact:

- `section_specificity_report.json`

### 12. Source-Coverage Telemetry

Purpose: Make failures of source-derived context visible instead of hiding them behind polished map-derived prose.

Checks:

- High-relevance source cards omitted from the memo.
- Generated map claims without source-card backing.
- Main memo cards missing exact source anchors.
- Source cards included only through generic source labels without local span evidence.
- Off-question source cards entering main context.
- Low-value source cards included in main context.
- High-relevance source cards that never became map claims.
- Section packets that include broad context without a clear section-level use.
- Source sufficiency gaps that constrain the final answer.
- Evidence quality gaps that lower recommendation confidence.

Artifacts:

- `source_coverage_report.json`
- source section in `context_strategy_eval.md`

### 13. Pipeline Migration And Runtime Budgets

Purpose: Prevent the new context pipeline from running in parallel with the old obligation pipeline, and keep the prototype usable on realistic document sets.

Deterministic code:

- Add a migration ledger that records:
  - which old prompt/context fields still feed model calls
  - which new artifacts replace them
  - which old artifacts remain debug-only
  - any intentional compatibility shims
- Add runtime telemetry:
  - source-card extraction time
  - number of chunks inspected
  - number of model calls by stage
  - tokens or approximate prompt sizes by stage
  - cache hits/misses by source hash
  - degraded-mode triggers
- Add degraded modes:
  - skip optional model salience/classification
  - use deterministic scoring only
  - cap source chunks per document with visible omission telemetry
  - reuse cached source cards when source hash matches

AI role:

- None for migration and budget enforcement.

Artifacts:

- `pipeline_migration_ledger.json`
- `runtime_budget_report.json`

Validation:

- Model section prompts must not receive both old noisy obligations and new accepted section contracts as parallel context.
- Runtime reports must identify the most expensive stage.
- Degraded mode must preserve traceability and visibly mark reduced coverage.

### 14. Fallback Policy

Purpose: Avoid silent bad prose.

Rules:

- If context quality fails severely:
  - do not call the model;
  - write deterministic card-based section;
  - mark section as `context_not_synthesis_ready`.
- If section context acceptance fails because the packet is too broad:
  - trim or reassign cards deterministically;
  - rerun the acceptance test before model synthesis.
- If source grounding fails for a load-bearing card:
  - demote it to appendix-only or mark it as an interpretation candidate;
  - do not let it carry the answer.
- If source sufficiency fails:
  - produce a bounded answer that says what the provided documents support;
  - list missing-source categories in the memo or review packet.
- If evidence quality is weak:
  - lower recommendation strength;
  - surface the quality limitation in the spine and relevant sections.
- If model output fails coverage:
  - retry with sanitized failure reasons.
- If model output remains generic:
  - fall back to deterministic card prose.
- If deterministic fallback is also weak:
  - emit a visibly bounded section:
    "Current map supports only the following source-backed points..."
  - record the limitation in telemetry.

### 15. Final Brief Evaluation Rubric

Purpose: Evaluate the actual produced memo, not only whether pipeline artifacts passed.

Deterministic code:

- Compile an evaluation packet with:
  - final memo path
  - decision question
  - argument spine
  - section context acceptance summary
  - source sufficiency status
  - evidence quality summary
  - source coverage summary
  - coherence findings
  - baseline comparison paths when available

AI role:

- Optional rubric scoring and critique from the evaluation packet.
- Must cite memo sections/cards for each critique.

Artifact:

- `final_brief_evaluation.json`
- final brief section in `context_strategy_eval.md`

Rubric dimensions:

- Answers the decision question directly.
- Makes recommendation strength and uncertainty clear.
- Uses evidence according to quality and directness.
- Surfaces cruxes and what would change the answer.
- Preserves counterweights and scope boundaries.
- Avoids generic prose and unsupported confidence.
- Reads coherently as one memo, not stitched sections.
- Improves over baseline synthesis or clearly reports why it cannot.

Validation:

- A run is not complete until the final brief is evaluated against this rubric.
- If the memo fails to answer the decision question, artifact success does not count as prototype success.

### 16. Evaluation Harness

Purpose: Determine if this actually improves memo quality.

Run before/after on:

- eggs baseline-question case
- one unseen biomedical/nutrition case
- one non-biomedical case

Metrics:

- context sufficiency score
- off-question card count
- fragment risk count
- accepted section count
- generic prose score
- duplicate evidence count
- included low-value card count
- section packet card-budget violations
- section context acceptance pass rate
- source sufficiency status
- evidence quality limitation count
- memo coherence failure count
- source-card-to-memo traceability
- high-relevance source-card omission count
- generated-claim-without-source-card count
- runtime/model-call budget by stage
- degraded-mode trigger count
- final brief rubric score
- human-read comparison notes
- deep research gap comparison where available

Artifact:

- `context_strategy_eval.md`

## Execution Order

1. Add typed schemas and ownership validation for new durable artifacts.
2. Implement report-only source evidence card construction from existing source files/spans.
3. Add source sufficiency reporting before answer synthesis.
4. Implement source-map reconciliation and candidate evidence card curation.
5. Add evidence quality weighting in report-only mode.
6. Add context quality diagnostics to current section packets.
7. Build deterministic memo argument spine from source-backed curated cards, sufficiency status, and quality components.
8. Generate section reasoning contracts from the spine.
9. Add section context acceptance tests in report-only mode.
10. Trim or reassign cards when section packets fail because they are too broad or off-question.
11. Swap section prompts to use accepted contracts only.
12. Add memo-level coherence review.
13. Add specificity validation in warning mode.
14. Add source-coverage telemetry and deterministic fallback policy.
15. Add pipeline migration ledger and runtime budget report.
16. Add final brief evaluation rubric.
17. Rerun eggs and compare.
18. Run one unseen case.
19. Promote calibrated gates from warning to blocking.

## Acceptance Criteria

- `Why This Read` receives concrete decision context, not only target shape.
- Main section context is derived from source evidence cards reconciled with map claims.
- Main sections do not receive irrelevant off-question quantitative anchors.
- Durable artifacts validate against typed schemas, and model outputs cannot populate deterministic-only fields.
- Every model-generated durable field records schema parse status, validation status, and fallback behavior.
- Source sufficiency status is reported and constrains answer strength when the provided documents are incomplete.
- Evidence quality components are visible and influence ranking, spine confidence, and memo caveats.
- Model prompts include clean section contracts with owned cards, decision moves, card roles, and inclusion reasons.
- Each substantive section packet has 3-7 owned source-backed cards by default, or records why a different budget is appropriate.
- Section context acceptance reports explain what each section can answer, why it can answer it, what context is missing, and what near-miss cards were excluded.
- Telemetry reports both high-relevance omitted cards and low-value included cards.
- Final memo coherence review checks answer/body alignment, repetition, contradictions, crux coverage, and resolved citations.
- Pipeline migration ledger shows old noisy obligations are not still feeding model prompts alongside accepted section contracts.
- Runtime budget report shows stage costs, cache behavior, and degraded-mode triggers.
- Final brief evaluation rubric is run on the produced memo, and a memo that fails to answer the decision question is treated as a failed run.
- Memo has no truncated fragments in main sections.
- Accepted prose is decision-specific and source-grounded.
- Source-card traceability shows which cards drove each section.
- Source-coverage telemetry identifies high-relevance source cards omitted from the memo and generated claims without source-card backing.
- At least one unseen case shows the same machinery works without domain-specific rules.

## Code-Fit Red Team

### Fit Strengths

- The current code already has a stage boundary where the plan can fit:
  - `candidate_map -> prioritized_map -> scaffold -> global_memo_plan -> section packets -> section rewrite`.
- Section prompts already use compact model-facing packets via `model_facing_section_contract`.
- Full debug artifacts are already written, so adding card/spine artifacts follows existing conventions.
- Existing validation can remain binding while new context gates start in report-only mode.
- Existing traceability matrices can be extended to card IDs rather than replaced.
- Case manifests already point to local source text files, so source cards can be added without expanding source acquisition scope.

### Fit Gaps

- The current plan now reaches earlier than the active briefing code: source-card construction does not yet exist as a first-class stage.
- Typed ownership schemas do not yet exist for all new artifacts; adding model-assisted fields before schemas would recreate the current ambiguity.
- Some generated claims include source IDs but not exact usable spans; source-card construction must support recovered anchors and confidence labels.
- `main_memo_obligations.py` currently creates many obligations without enough question-specific curation. The plan must not simply wrap these obligations as cards.
- `map_briefing_global_plan.py` assigns obligation IDs before a cleaned argument spine exists. The plan should either move spine creation before global planning or make global planning consume the spine.
- `compile_model_section_packet` currently relies on `required_evidence` and section-owned obligations. Sections with no required evidence get thin packets. This is the direct cause of generic accepted prose.
- `section_main_memo_obligations` filters by allowed categories and plan IDs, which can silently remove useful concrete context while leaving abstract section goals.
- `decision_synthesis_model.json` and `graph_synthesis_packet.json` can contain fragments and off-question endpoints. Candidate card curation must run before section context is built.
- Existing traceability matrices are obligation/claim oriented, not source-card oriented; they need extension rather than replacement.
- Current section packet construction does not explain why a selected card belongs in a specific section; without this, relevance errors can pass through as "structured context."
- Current telemetry emphasizes missing coverage more than included clutter; it must count low-value included cards to prevent broad packets from weakening synthesis.
- Current memo quality telemetry can report `polished` even when human readability is weak. Specificity validation must be separate from polish validation.
- Current pipeline can pass artifact-level checks while the final memo remains redundant, internally inconsistent, or weak on the decision question.
- Existing code has no explicit source sufficiency concept; it can over-answer from an incomplete provided corpus.
- Existing artifact handoff can allow old obligation-derived prompt context to leak into section synthesis after new context artifacts are added.

### Implementation Risk

- Adding a new spine stage can duplicate `argument_model`, `decision_synthesis_model`, and `decision_argument_artifacts` unless ownership is explicit.
- Pydantic/schema work can become busywork if it only validates shape; field ownership and fallback behavior must be encoded, not just JSON types.
- Adding source-card construction can become expensive if it rereads all source text on every briefing run; cache source cards by source hash where possible.
- Source-card extraction can create false precision if recovered anchors are treated like exact spans; confidence labels must be visible.
- Card budgets can accidentally discard necessary context in complex sections; budget exceptions need explicit justifications, not silent truncation.
- Too many new artifacts can obscure rather than clarify the pipeline unless summaries link them in `briefing_summary.json` and `FINAL_REVIEW_PACKET.md`.
- Source sufficiency can be mistaken for source acquisition; keep it as a reporting/gating layer over provided documents.
- Evidence quality weighting can become domain-specific if it relies on biomedical-only hierarchy labels; keep components generic and unknown-friendly.
- Memo-level coherence review can become a rewrite stage that smuggles in new claims; it must cite existing sections/cards and propose edits only.
- Runtime caps can hide omissions unless degraded mode writes explicit coverage limitations.
- Blocking gates too early can reject acceptable concise sections; start report-only.
- Deterministic card curation can accidentally remove minority evidence; every demotion needs a reason and counterweight preservation rule.

## Red-Team Checks

- Does the spine merely launder noisy model artifacts?
- Can every model-populated field be identified from the artifact alone?
- Are deterministic-only fields protected from model overwrite?
- Do model validation failures produce fallbacks rather than partial accepted artifacts?
- Does the source-card layer actually inspect source text, or does it just re-label generated claims?
- Do source-card anchors point to the relevant span, not merely the right document?
- Does each section have the right few cards, or merely fewer cards?
- Do inclusion reasons explain section relevance rather than restating the claim?
- Are near-miss exclusions correct, or did trimming remove important counterweights?
- Are low-value included cards being counted and acted on?
- Does the system recognize when the provided documents are insufficient for the decision question?
- Are weak or indirect source-backed cards being over-weighted because they are traceable?
- Does the final memo answer match the body and the argument spine?
- Are sections locally valid but globally repetitive or contradictory?
- Are old obligation-derived prompt fields still feeding synthesis after accepted section contracts exist?
- Does degraded/runtime-capped mode make omissions visible?
- Are counterweights preserved or filtered away?
- Are rejected cards visible in appendix/telemetry?
- Does specificity validation reject good concise prose?
- Does fallback prose become too mechanical?
- Does the system overfit to biomedical evidence families?

## Generalizability Checks

- No hard-coded domain terms.
- Evidence roles are generic.
- Endpoint relevance is computed from the question and source/map roles, not fixed vocab.
- Field ownership categories are domain-independent and apply to every artifact.
- Source-card fields are generic: population, exposure/intervention, comparator, endpoint/outcome, evidence type, limitation.
- Source sufficiency categories are generated from the decision question and generic evidence roles, not fixed case vocab.
- Evidence quality components use generic attributes: directness, provenance, design indicators, recency, uncertainty, limitations, and conflicts.
- Card budgets are defaults with recorded exceptions, not domain-specific limits.
- Inclusion reasons are section-relative and question-relative, not keyed to named cases.
- Section contracts work for different case shapes:
  - policy/action decision
  - contested factual synthesis
  - representation/characterization decision
  - technical risk assessment

## Anti-Half-Done Rule

Do not stop after adding card artifacts. The source cards must be reconciled with map claims, consumed by section packets, passed through section context acceptance, validated, and reflected in a before/after memo comparison. If a slice only writes new artifacts without changing model-visible section context, mark it incomplete. If a slice adds model-assisted artifacts without typed schemas, field ownership, validation reports, and fallback behavior, mark it incomplete. If a slice adds section packets without per-card inclusion reasons, intended roles, near-miss exclusions, and low-value-card telemetry, mark it incomplete. If a slice improves section-level synthesis but does not run source sufficiency, evidence quality, memo coherence, migration/runtime, and final brief evaluation checks, mark the overall plan incomplete.
