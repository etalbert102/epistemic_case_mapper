# Plan: Canonical Decision Writer Packet Streamlining

## Objective

Make the final memo pipeline simpler and more decision-grade by replacing the current multi-surface synthesis handoff with one canonical, model-visible `canonical_decision_writer_packet_v1`.

Target pipeline:

1. Source map and analyst judgment
2. Canonical decision writer packet
3. Memo synthesis
4. Targeted validation and repair
5. Deterministic presentation, source list, and citation trace

The memo writer should receive one authoritative decision packet, not a pile of overlapping internal plans, contracts, ledgers, and audit artifacts.

## Current Gap

The current pipeline has enough evidence and traceability to support a useful memo, but final synthesis is overloaded. The writer prompt exposes or references several partially overlapping surfaces:

- `reader_brief_plan`
- `decision_interpretation_plan`
- `analytical_balance_contract`
- `decision_boundary_source_contract`
- `adaptive_memo_outline`
- `decision_evidence_table`
- `mandatory_evidence_ledger`
- memo obligations
- warning guidance
- source appraisal summaries
- source/quantity priority cards

This makes the memo evidence-retentive but not consistently decision-grade. The model is asked to resolve the decision logic while writing, and the result often reads like an evidence summary rather than a crisp decision memo.

## Non-Goals

- Do not change source acquisition, source extraction, or map construction in this plan.
- Do not remove diagnostic artifacts before proving the canonical packet path works.
- Do not make deterministic code decide semantic meaning.
- Do not tune rules to the eggs case or any other specific case.
- Do not add expensive model calls unless existing model judgment cannot supply the needed field.
- Do not weaken source retention or citation traceability to get prettier prose.

## Design Principles

- One authoritative semantic handoff to synthesis.
- Models make semantic judgments; code compiles, validates, routes, and preserves them.
- Synthesis writes from resolved decision logic instead of discovering it from internal machinery.
- Validation checks retention against the canonical packet, not every historical artifact.
- Source IDs remain the durable citation substrate until deterministic presentation.
- Old artifacts must become diagnostics or compiler inputs, not parallel writer instructions.

## Inventory And Dependency Map

Before implementation, classify every writer-adjacent artifact into one of four groups.

### Keep In Writer Context

Only fields directly needed to write the memo:

- decision question
- decision brief skeleton
- priority evidence
- counterweight dispositions
- scope boundaries
- decision cruxes
- source-weight notes
- mandatory retention checklist
- citation registry

### Compile Into Canonical Packet

Useful artifacts that should inform the canonical packet but not appear as separate writer-facing instruction surfaces:

- `reader_brief_plan`
- `decision_interpretation_plan`
- `analytical_balance_contract`
- `decision_boundary_source_contract`
- `adaptive_memo_outline`
- `source_appraisal_summary`
- `mandatory_evidence_ledger`

### Keep As Diagnostics

Artifacts that help debugging and evaluation but should not guide prose directly:

- packet QA reports
- source lineage reports
- retention reports
- stage value reports
- parse reports
- warning and repair reports
- model context audits

### Retire Or Delete

Any legacy path that still sends old multi-surface context to synthesis after the canonical packet path is accepted.

## Canonical Packet Shape

`canonical_decision_writer_packet_v1` should be compact enough for a model to reason over and explicit enough to validate.

```json
{
  "schema_id": "canonical_decision_writer_packet_v1",
  "decision_question": "...",
  "decision_brief_skeleton": {
    "direct_answer": "...",
    "scope": "...",
    "confidence": "...",
    "main_reason": "...",
    "most_important_quantity": "...",
    "strongest_counterweight": "...",
    "counterweight_disposition": "...",
    "exceptions": [],
    "decision_crux": "...",
    "practical_implication": "..."
  },
  "priority_evidence": [],
  "counterweight_dispositions": [],
  "scope_boundaries": [],
  "decision_cruxes": [],
  "source_weight_notes": [],
  "mandatory_retention_checklist": [],
  "citation_registry": []
}
```

## Workstreams

1. Canonical Packet Schema
   - Purpose: define the single production handoff to synthesis.
   - Changes:
     - Add schema/build helpers for `canonical_decision_writer_packet_v1`.
     - Add a packet quality report.
     - Add source ID validation.
   - Artifacts:
     - `canonical_decision_writer_packet.json`
     - `canonical_decision_writer_packet_quality_report.json`
   - Validation:
     - Required fields are present.
     - Every cited source ID resolves.
     - Every mandatory row has source IDs and a reader-facing claim.
   - QA:
     - Golden fixture with support, counterweight, scope, crux, and quantity.
   - Risk:
     - The canonical packet becomes an additional artifact rather than the replacement handoff.

2. Decision Brief Skeleton Compiler
   - Purpose: resolve the memo’s decision logic before synthesis.
   - Changes:
     - Compile direct answer, scope, confidence, main reason, main quantity, strongest counterweight, disposition, exceptions, crux, and practical implication.
     - Prefer existing analyst/model judgments.
     - Use deterministic code only to detect missing fields and produce warnings.
   - Artifacts:
     - `decision_brief_skeleton`
     - skeleton quality warnings
   - Validation:
     - Skeleton answers the exact decision question.
     - Skeleton contains scope and confidence when evidence is bounded.
     - Skeleton identifies the highest-priority counterweight and its disposition.
   - QA:
     - Reordering source/evidence rows should not change the skeleton.
   - Risk:
     - Generic fallback language sneaks into the skeleton.

3. Counterweight Disposition Layer
   - Purpose: turn caveats into decision logic.
   - Changes:
     - Normalize counterweights into one or more dispositions:
       - `overturns_answer`
       - `weakens_confidence`
       - `bounds_population`
       - `bounds_dose`
       - `bounds_endpoint`
       - `explains_mechanism`
       - `creates_unresolved_crux`
       - `context_only`
     - Include rationale, source IDs, and linked evidence item IDs.
   - Artifacts:
     - `counterweight_dispositions`
   - Validation:
     - Every `strongest_counterweight` has a disposition.
     - Every disposition has a source and evidence item.
   - QA:
     - Test at least one case where a counterweight should overturn rather than merely bound the answer.
   - Risk:
     - Model labels are too confident. The packet should allow uncertainty instead of forcing a false classification.

4. Source Weight Notes
   - Purpose: surface why different sources carry different decision weight.
   - Changes:
     - Compile concise notes:
       - source ID
       - evidence type
       - useful-for
       - not-enough-for
       - directness or quality limit
       - linked evidence item IDs
     - Use existing source appraisal and source-use cards where available.
   - Artifacts:
     - `source_weight_notes`
   - Validation:
     - Every load-bearing source has a note or an explicit warning that source quality is unspecified.
   - QA:
     - Check that notes are tied to decision use, not generic source-type boilerplate.
   - Risk:
     - Source appraisal becomes verbose or formulaic.

5. Writer Prompt Simplification
   - Purpose: make synthesis a writing task again.
   - Changes:
     - Replace the current multi-surface writer prompt with a short prompt using only the canonical packet.
     - Keep old artifacts out of model-visible context unless they have been compiled into canonical fields.
     - Prompt asks the model to:
       - use the skeleton as the spine
       - cite source IDs
       - preserve mandatory checklist items
       - explain counterweight disposition
       - write naturally for a decision-maker
   - Artifacts:
     - simplified `memo_ready_synthesis_prompt.txt`
     - prompt context audit
   - Validation:
     - Prompt contains one canonical packet and no direct dumps of retired artifacts.
   - QA:
     - Compare prompt token size and context surface count before/after.
   - Risk:
     - Removing too much context reduces retention. Canonical retention checks must catch this.

6. Canonical Retention And Targeted Repair
   - Purpose: keep the streamlined pipeline source-faithful.
   - Changes:
     - Retention report checks the canonical packet obligations.
     - Repair receives only:
       - current memo
       - missing obligations
       - relevant evidence rows
       - affected skeleton fields
     - Repair does not receive the full canonical packet unless needed.
   - Artifacts:
     - `canonical_packet_retention_report.json`
     - targeted repair prompt/raw/report
   - Validation:
     - Missing skeleton fields and mandatory evidence route to repair.
     - Repair cannot worsen retained skeleton fields or source citations.
   - QA:
     - Seed a memo missing the strongest counterweight and verify repair inserts it naturally.
   - Risk:
     - Repair produces awkward prose. Final polish should fix prose only, not reasoning.

7. Presentation And Citation Trace
   - Purpose: preserve and extend recent traceability gains.
   - Changes:
     - Keep deterministic source list.
     - Keep inline citation links.
     - Extend citation trace toward sentence-to-evidence mapping:
       - memo sentence
       - cited source
       - supporting evidence item IDs
       - quantities used
       - role in decision
   - Artifacts:
     - `CITATION_TRACE.md`
   - Validation:
     - Every linked source has a citation context.
     - Source list keeps external URLs.
   - QA:
     - Manual click-through review on a real memo artifact.
   - Risk:
     - Trace becomes too verbose. Keep it structured and scannable.

8. Legacy Context Cleanup
   - Purpose: actually streamline the system.
   - Changes:
     - Once the canonical packet path passes, remove old direct writer exposure of demoted artifacts.
     - Keep useful reports as diagnostics.
     - Add tests preventing audit-only fields from reaching synthesis.
   - Artifacts:
     - cleanup ledger
     - model context audit
   - Validation:
     - Writer prompt no longer includes retired artifact names.
   - QA:
     - Regression tests for prompt context boundaries.
   - Risk:
     - Hidden callers rely on old context fields. Update tests to the new contract rather than retaining compatibility paths indefinitely.

## Execution Order

1. Add the canonical packet schema and compiler while leaving existing synthesis unchanged.
2. Add quality report and tests for skeleton, counterweight, source-weight, and source-ID completeness.
3. Build a simplified synthesis prompt from the canonical packet behind a controlled path.
4. Compare current prompt vs canonical prompt on saved artifacts.
5. If retention holds and readability improves, switch production synthesis to the canonical packet.
6. Retarget retention and repair to canonical obligations.
7. Preserve deterministic presentation and citation trace.
8. Remove direct writer exposure of retired artifacts.
9. Run a full end-to-end memo and compare against current memo plus direct-source synthesis baseline.
10. Commit each verified slice.

## Acceptance Criteria

- Production synthesis receives one canonical packet as its semantic handoff.
- Writer prompt does not directly include old overlapping plans/contracts after migration.
- The memo opens with a direct answer, scope, confidence, and main reason.
- Every major counterweight says whether it overturns, weakens, bounds, or contextualizes the answer.
- Source-weight notes appear when source type affects confidence or interpretation.
- Mandatory evidence retention is no worse than the current pipeline.
- Citation trace still links inline citations to source contexts.
- Prompt token count or context surface count decreases.
- Full tests pass.
- Maintainability gate passes.
- A real eggs run produces a memo judged at least one point better on decision-grade quality.
- At least one unrelated case does not regress.

## Red-Team For Effectiveness

### Likely Strengths

- It targets the true bottleneck: the synthesis handoff, not final prose polishing.
- It should reduce instruction conflict by giving the writer one hierarchy of decision logic.
- It preserves current gains in evidence retention and citation traceability.
- It makes old artifacts prove their value as compiler inputs instead of remaining parallel prompt surfaces.
- It improves generalizability because the central artifact is decision-structure based, not case-topic based.

### Main Failure Modes

1. The canonical packet becomes another layer instead of replacing old context.
   - Detection: synthesis prompt still contains `reader_brief_plan`, `decision_interpretation_plan`, `analytical_balance_contract`, `decision_boundary_source_contract`, or `adaptive_memo_outline` as separate sections.
   - Mitigation: add a prompt-boundary test and context audit.

2. The skeleton is too generic to improve prose.
   - Detection: skeleton direct answer could apply to many questions; it lacks named option, population/scope, confidence, or main counterweight.
   - Mitigation: quality report flags generic skeleton text and routes to model refinement rather than deterministic filler.

3. Retention improves but decision usefulness does not.
   - Detection: memo contains all mandatory facts but still does not explain what to do, what changes the answer, or how counterweights affect the answer.
   - Mitigation: acceptance criteria require explicit counterweight disposition and practical implication, not only retained evidence.

4. Source-weight notes become boilerplate.
   - Detection: notes say generic things like "observational evidence has limitations" without saying what the source is useful for in this decision.
   - Mitigation: require `useful_for`, `not_enough_for`, and linked evidence item IDs.

5. The model drops nuance because the packet is too compact.
   - Detection: canonical retention report worsens, or source trace loses important boundary evidence.
   - Mitigation: include `mandatory_retention_checklist` and targeted repair using only missing obligations.

6. Counterweight dispositions are mislabeled.
   - Detection: adversarial fixture where evidence should overturn the default but packet labels it as merely contextual.
   - Mitigation: allow uncertain dispositions and require rationale; use unseen cases with different counterweight behavior.

7. The plan over-indexes on prompt/context architecture while map quality remains the real bottleneck.
   - Detection: canonical packet quality report shows weak source coverage, missing support, missing counterweights, or poor source appraisal before synthesis.
   - Mitigation: fail visibly with packet quality warnings rather than blaming synthesis.

8. The final memo is cleaner but less auditable.
   - Detection: citation trace has fewer contexts, unresolved source IDs, or missing source list entries.
   - Mitigation: keep deterministic presentation and trace tests blocking.

### Effectiveness Judgment

This plan is likely to improve the final memo if implemented as a true replacement for overlapping writer context. The highest expected gain comes from forcing an explicit decision skeleton and counterweight disposition before prose generation.

The plan will not help much if implementation only adds the canonical packet while continuing to feed all existing artifacts to the writer. The anti-half-done rule is therefore load-bearing.

The plan also depends on upstream packet quality. If the analyst decision model fails to identify the correct main support, counterweight, or source weight, the canonical packet will faithfully pass weak judgment to synthesis. The packet quality report must therefore become a visible gate, not just telemetry.

## Generalizability Checks

- Run on eggs plus at least one unrelated decision question.
- Reorder evidence rows; skeleton should remain stable.
- Remove a non-load-bearing source; direct answer should not change.
- Add an extra context-only source; it should not become load-bearing.
- Swap source labels while preserving source IDs; citation trace should remain correct.
- Use a case where counterweight overturns the answer.
- Use a case where counterweight merely bounds the answer.
- Use a case where source type matters, such as direct outcome evidence versus proxy evidence.
- Use a case with weak or missing source appraisal; packet should warn rather than invent quality.

## Anti-Half-Done Rule

The plan is not complete when the canonical packet exists. It is complete only when production synthesis uses the canonical packet as the sole semantic handoff, old writer-facing context surfaces are retired or diagnostic-only, and validation/repair target canonical obligations.

## Final Completion Audit

The final implementation should write a completion audit with:

- canonical packet path
- prompt context audit path
- canonical retention report path
- before/after memo comparison
- full test command result
- maintainability gate result
- list of retired writer context surfaces
- unresolved deferred work, if any
