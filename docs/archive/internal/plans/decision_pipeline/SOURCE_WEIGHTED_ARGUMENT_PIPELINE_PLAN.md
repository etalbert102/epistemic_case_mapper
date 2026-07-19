# Plan: Source-Weighted Argument Pipeline

## Objective

Make the pipeline produce decision memos that explain why the evidence hierarchy implies the answer, not just preserve evidence and citations. The final memo should be less repetitive, more source-weighted, and easier to trace from source map to analyst judgment to argument spine to memo.

## Current Gap

- Source weighting is currently inserted after synthesis, so it is visible but does not strongly shape the memo's reasoning.
- The synthesis prompt receives several parallel packet sections and checklists, which encourages coverage but also repetition.
- Source-weight reasons are too procedural, for example "upstream role is strongest_support", rather than analytical, for example "direct clinical endpoint evidence in the target population should carry the bottom-line answer."
- The canonical writer packet can be rebuilt for the prompt but is not consistently persisted as a saved artifact for every active packet path.
- Repetition is mostly detected after the memo is written instead of being prevented by assigning each evidence item a clear primary memo job.

## Non-Goals

- Do not add another broad final rewrite stage.
- Do not make deterministic code decide semantic evidence meaning.
- Do not tune generic code to nutrition, eggs, cardiovascular disease, or any other case-specific vocabulary.
- Do not weaken citation/source-ID traceability.
- Do not keep legacy packet paths alive unless they are still actively used.

## Design Principles

- Model judgment owns semantic source weight; deterministic code owns identity, schema validation, traceability, and consistency checks.
- One evidence item may appear in multiple places only when its memo function changes.
- The memo should render an argument model; it should not discover the argument while writing prose.
- Quality gates should diagnose the stage that caused the issue.
- All source-weight judgments must be inspectable as artifacts.

## Inventory And Dependency Map

- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_decision_packet_stage.py`: active memo-ready packet promotion.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_analyst_packet.py`: analyst memo-ready packet construction.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_decision_writer_packet.py`: global writer packet adapter.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_canonical_decision_writer_packet.py`: canonical synthesis handoff.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_memo_ready_prompt.py`: final synthesis prompt.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_memo_ready_presentation.py`: deterministic reader presentation.
- `src/epistemic_case_mapper/pipeline/briefing/map_briefing_context_reports.py` and telemetry modules: coherence and repetition diagnostics.
- Tests to extend: `tests/test_analyst_packet.py`, `tests/test_canonical_decision_writer_packet.py`, `tests/test_memo_ready_packet.py`, `tests/test_memo_ready_presentation.py`.

## Workstreams

1. Persist Canonical Writer Packet Everywhere
   - Purpose: make runtime synthesis and saved artifacts match.
   - Changes: attach `canonical_decision_writer_packet` and its quality report to both active memo-ready packet paths.
   - Artifacts: non-empty `canonical_decision_writer_packet.json` and `canonical_decision_writer_packet_quality_report.json`.
   - Validation: prompt context audit and saved canonical artifact agree that `canonical_decision_writer_packet_v1` was present.
   - QA: regression test for the analyst-adjudicated active path.
   - Risks: duplicated canonical-building calls; avoid by centralizing around existing builder.

2. Add Source Weight Judgment Model
   - Purpose: make source credibility and decision role explicit before synthesis.
   - Changes: add `source_weight_judgments` to the canonical writer packet.
   - Fields: `source_id`, `source_labels`, `source_type`, `decision_directness`, `population_fit`, `endpoint_fit`, `main_use`, `why_weight_this_way`, `what_not_to_use_it_for`, `evidence_item_ids`.
   - Artifacts: `source_weight_judgment_report.json`.
   - Validation: every cited or memo-facing source has a judgment or explicit omission reason.
   - QA: synthetic case with support, counterweight, guidance, and contextual source.
   - Risks: generic judgments; require rationale to mention endpoint, population, directness, limitation, or memo use.

3. Build Evidence-Weighted Argument Spine
   - Purpose: turn scattered evidence into one ordered decision argument.
   - Changes: add `evidence_weighted_argument_spine` to the canonical writer packet.
   - Structure: answer, because, primary drivers, calibrators, counterweights, counterweight disposition, scope boundaries, practical implication.
   - Artifacts: `argument_spine_quality_report.json`.
   - Validation: each mandatory evidence item has a primary memo job; repeated same-role evidence is reported.
   - QA: metamorphic tests for reordered sources, renamed source IDs, irrelevant source addition, and duplicate claim addition.
   - Risks: spine drops minority evidence; detect via mandatory item without memo job.

4. Replace Checklist-Centric Synthesis Prompt
   - Purpose: reduce repetition and improve logical flow.
   - Changes: prompt should lead with decision question, answer frame, source-weight judgments, evidence-weighted argument spine, grouped evidence by memo function, and protected quantities/source IDs.
   - Artifacts: prompt context audit showing no raw debug/audit fields and one primary argument spine.
   - Validation: synthesis prompt contains the argument spine and asks for paragraph-level roles rather than checklist restatement.
   - QA: before/after prompt diff and memo quality comparison on eggs plus one unrelated case.
   - Risks: model drops evidence; retention report remains the backstop.

5. Render Source Weighting From The Same Source Of Truth
   - Purpose: ensure the visible `How to Weight the Evidence` section summarizes the same upstream judgments used for synthesis.
   - Changes: presentation normalization should summarize `source_weight_judgments` and `evidence_weighted_argument_spine` before falling back to lane reconstruction.
   - Artifacts: memo section with source-specific decision-use explanations.
   - Validation: each source mentioned in the section appears in `CITATION_TRACE.md`.
   - QA: idempotence and citation-link regression tests.
   - Risks: late deterministic prose becomes too long; cap per lane and prefer concise source-use clauses.

6. Add Stage-Value Telemetry
   - Purpose: make failures diagnosable.
   - Reports: `source_weight_judgment_report.json`, `argument_spine_quality_report.json`, `evidence_role_reuse_report.json`, `memo_source_weight_explanation_report.json`.
   - Metrics: repeated same-role evidence count, cited source without weight explanation, counterweight without disposition, source-weight claim without source ID, mandatory item with no memo job.
   - Validation: reports point to owning stage and artifact paths.
   - QA: report-only gates first; promote only after signal is calibrated.
   - Risks: telemetry noise; keep routine tests focused and place expensive corpus checks outside the fast path.

## Execution Order

1. Persist canonical writer packets in all active memo-ready packet paths.
2. Add source-weight judgment schema, builder, report-only validation, and tests.
3. Build the evidence-weighted argument spine and its quality report.
4. Change synthesis prompt ordering to make the argument spine the primary semantic handoff.
5. Update deterministic presentation to summarize source weighting from upstream judgments.
6. Add telemetry reports and regression/metamorphic tests.
7. Rerun eggs and one unrelated case; compare against the prior memo and raw-source synthesis baseline.

## Acceptance Criteria

- `canonical_decision_writer_packet.json` is non-empty for live runs.
- Final synthesis prompt uses `evidence_weighted_argument_spine` as the primary handoff.
- Every final memo source has a `source_weight_judgment` or omission reason.
- Evidence-role reuse report has no unjustified repeated same-role evidence.
- Latest memo passes decision answer, uncertainty, source grounding, and source-weight visibility checks.
- The repetition warning is reduced or replaced by a more specific diagnostic with an owning stage.
- Full test suite passes.

## Red-Team Checks

- If the model invents source credibility, the schema must expose missing source IDs or missing evidence item IDs.
- If source weighting is generic, the judgment report must flag rationales that lack endpoint, population, directness, limitation, or memo-use language.
- If argument spine drops minority evidence, mandatory evidence without a memo job must be visible.
- If deterministic code starts making semantic decisions, the implementation should be revised so code validates and routes only.
- If QA only proves artifact existence, add product-quality checks on memo readability and decision usefulness.

## Generalizability Checks

- Run on a non-nutrition decision question.
- Reorder documents and verify answer/source roles remain stable.
- Rename source IDs and verify traceability still works.
- Add an irrelevant source and verify it is omitted with a reason.
- Add near-duplicate evidence and verify it is consolidated or assigned distinct roles.

## Slice Protocol

Each implementation slice must state scope, owned files, verification commands, and done conditions before committing. A slice is not complete unless focused tests pass, relevant artifacts or reports are inspectable, and any deferred work is recorded here or in a follow-up plan.

## Completion Audit

The final implementation pass should record completed slices, commit SHAs, verification commands, quality deltas on eggs and one unrelated case, new artifacts, promoted fixtures, remaining limitations, and deferred items.
