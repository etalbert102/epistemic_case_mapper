# Plan: Canonical Writer Packet Truth Contract

## Objective
Make the canonical decision writer packet the single trustworthy semantic handoff for memo synthesis. Before a model writes prose, the packet must reconcile approved quantity meanings, overstatement constraints, source weighting, and the active citation/source universe so synthesis receives coherent context rather than conflicting instructions.

## Current Gap
The latest eggs memo shows three packet-level failures:

- A quantity meaning corrected by `analyst_quantity_binding_report` is degraded inside `canonical_decision_writer_packet` before synthesis.
- A claim that "may offer stroke protection" is promoted as load-bearing support even though the balanced answer frame says not to claim benefit or protection.
- Source weighting is flattened because too many sources are classified as driving the answer, and final source rendering can draw from a broader source universe than the active memo-ready packet.

These are not primarily final-prose failures. They are handoff-consistency failures upstream of synthesis.

## Non-Goals
- Do not add a new model call in this slice.
- Do not tune logic to eggs, cholesterol, stroke, or any domain-specific vocabulary.
- Do not weaken source, quantity, or retention validation to hide the problem.
- Do not change source extraction, relationship construction, or analyst adjudication architecture.

## Design Principles
- Fact ownership: approved quantity interpretation belongs to `analyst_quantity_binding_report`; canonical packet construction may project it but must not re-derive or degrade it.
- Models own semantic judgment; deterministic code may reconcile explicit fields and surface conflicts, not invent new semantic labels.
- The canonical packet should be internally coherent: no mandatory support claim should contradict `must_not_overstate`.
- Source weighting must expose hierarchy, not just source presence.
- Presentation must use the same active source trail that synthesis used.

## Inventory And Dependency Map
- Owner module: `src/epistemic_case_mapper/map_briefing_canonical_decision_writer_packet.py`
- Supporting modules:
  - `map_briefing_decision_writer_packet.py`: creates memo-ready quantities from analyst quantity plans.
  - `map_briefing_memo_ready_presentation.py`: renders citation trace and final source list.
  - `map_briefing_source_weight_judgments.py`: produces source-use judgments.
  - `map_briefing_argument_spine.py`: turns canonical evidence and source weighting into the writing spine.
- Focused tests:
  - `tests/test_canonical_decision_writer_packet.py`
  - `tests/test_memo_ready_presentation.py`
  - `tests/test_source_binding_validation.py`

## Workstreams
1. Quantity Truth Projection
   - Purpose: prevent stale quantity interpretations from surviving into canonical evidence rows, spine steps, and obligations.
   - Changes: build an ID/value/source-aware quantity truth index from canonical inputs, especially approved analyst binding rows and memo-ready item quantities; use it in `_brief_quantities()`.
   - Artifacts: canonical quality report warnings for conflicting quantity interpretations.
   - Validation: regression fixture where a stale item quantity says "daily consumption" but approved binding says "relative risk per exposure unit."
   - QA: verify canonical packet rows preserve value, interpretation, role, and source IDs.

2. Overstatement Conflict Guard
   - Purpose: prevent claims that contradict explicit `must_not_overstate` constraints from being promoted as mandatory support.
   - Changes: add a general conflict detector between canonical evidence claims and explicit answer-frame limits; demote or annotate conflicting support rows so they become contextual/limited rather than load-bearing support.
   - Artifacts: `quality_report` warning counts and row-level calibration notes.
   - Validation: regression fixture with a "beneficial/protective" support claim and a matching "do not claim benefit/protection" limit.
   - QA: ensure non-conflicting support stays support.

3. Source Weight Hierarchy Check
   - Purpose: make flattened source weighting visible and improve deterministic source-weight presentation without inventing source semantics.
   - Changes: add canonical quality warnings for source-weight flattening; adjust source-weighting prose to summarize hierarchy rather than repeating per-source card templates when too many sources have the same `main_use`.
   - Artifacts: `source_weight_judgment_report` and canonical quality report include flattening diagnostics.
   - Validation: fixture with five `drives_answer` sources should trigger warning and produce a grouping-oriented section.
   - QA: no domain-specific source types or labels.

4. Active Source Universe
   - Purpose: keep final sources aligned with active packet citations.
   - Changes: ensure final source-list rendering uses `memo_ready_packet.source_trail` and cited IDs only; stale scaffold sources may remain in audit artifacts but not reader-facing sources.
   - Artifacts: source-list consistency diagnostic.
   - Validation: fixture with an uncited source in upstream scaffold but not active packet source trail.
   - QA: cited active packet source must still render with URL when URL is available.

## Execution Order
1. Add the plan and baseline tests for canonical quantity and overstatement consistency.
2. Implement quantity truth projection in canonical packet construction.
3. Implement overstatement conflict annotation/demotion and quality report warnings.
4. Add source hierarchy/source-universe diagnostics and presentation consistency tests.
5. Rerun focused tests, then regenerate/evaluate the eggs memo from the existing map.

## Acceptance Criteria
- Canonical packet never replaces an approved analyst quantity interpretation with a stale or weaker item interpretation for the same item/value/source.
- A support claim that conflicts with explicit `must_not_overstate` constraints is no longer mandatory load-bearing support without a conflict note.
- Canonical quality report flags flattened source weighting when most sources share the same `main_use`.
- Final memo source list contains only active packet sources that are cited or intentionally included by the active source-trail policy.
- Focused tests pass:
  - `PYTHONPATH=src python3 -m pytest -q tests/test_canonical_decision_writer_packet.py tests/test_memo_ready_presentation.py tests/test_source_binding_validation.py`

## Red-Team Checks
- Quantity repair could over-match same numeric values from different sources. Detection: match by stable evidence item ID and source IDs before value-only matching.
- Overstatement conflict detection could become semantic keyword policing. Detection: only act when explicit upstream `must_not_overstate` and evidence claim share normalized phrases or strong lexical overlap; otherwise warn only.
- Source weighting hierarchy diagnostics could penalize legitimate many-source convergence. Detection: keep as warning/reporting, not blocking.
- Source-list pruning could hide sources used only in deterministic source list. Detection: citation trace records every inline citation and active source trail entry.

## Generalizability Checks
- The plan is expressed in terms of explicit answer-frame limits, quantity IDs/values/sources, and source-use categories, not domain vocabulary.
- Fixtures should use synthetic non-egg cases where possible.
- Reordering evidence rows or changing source labels should not change quantity matching when IDs are stable.

## Completion Audit Requirements
- Record changed files and tests run.
- Include before/after evidence for at least one canonical packet fixture.
- Note any warnings left report-only and why.
