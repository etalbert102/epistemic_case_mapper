# Plan: Move Semantic Decisions Out Of Deterministic Code

## Objective

Make the epistemic mapper obey a hard boundary: model-owned or source-owned artifacts decide semantic labels, while deterministic code preserves labels, validates schema and lineage, routes by explicit labels, emits diagnostics, and refuses to silently relabel meaning.

The immediate product goal is to prevent deterministic keyword rules from turning evidence into support, counterweight, scope boundary, crux, or directional quantity interpretation in ways that degrade the final decision memo.

## Current Gap

Several stages still make semantic decisions from keyword rules:

- Candidate evidence cards infer `counterweight`, `support`, `scope`, and `limitation` from claim text.
- Packet role adjudication mutates bundle roles based on lexical heuristics.
- Argument-model crux construction promotes broad relation types such as `in_tension_with` into decision cruxes.
- Quantity binding assigns directional interpretations to quantities without local source tuples.
- Canonical answer-frame construction accepts generic artifact language as a usable decision answer.

These choices can create polished but wrong packets because downstream stages treat deterministic guesses as semantic truth.

## Non-Goals

- Do not add a new live model dependency to the default prompt/offline path.
- Do not remove existing model-backed critique/refinement hooks.
- Do not make broad source collection or extraction changes in this plan.
- Do not tune behavior to eggs-specific vocabulary.
- Do not block the pipeline solely because semantic labels are uncertain; emit diagnostics and preserve uncertainty.

## Design Principles

- Semantic labels are owned by model/source artifacts, not keyword code.
- Deterministic code may validate, route, preserve, deduplicate, count, and warn.
- Deterministic code may use structural facts such as explicit schema fields, IDs, source lineage, and local quantity tuples.
- When semantics are missing or contradictory, emit `needs_model_adjudication` or `semantic_label_warning` rather than silently correcting.
- Report-only gates come before blocking gates unless the signal is already calibrated.

## Inventory And Dependency Map

Primary modules:

- `map_briefing_context_curation.py`: candidate card role profiling.
- `map_briefing_decision_packet.py`: packet candidate role projection and must-retain importance.
- `map_briefing_role_adjudication.py`: currently mutates roles via lexical heuristics.
- `map_briefing_argument_model.py`: constructs support/counterweight/crux lists.
- `map_briefing_crux_reconstruction.py`: currently replaces weak cruxes deterministically.
- `map_briefing_quantity_binding.py`: quantity interpretation and unsafe-pairing warnings.
- `map_briefing_answer_frame.py` and `map_briefing_canonical_spine.py`: answer-frame normalization and generic-answer acceptance.

Downstream consumers:

- `map_briefing_memo_ready_packet.py`
- `map_briefing_reader_packet_contract.py`
- `map_briefing_memo_ready_finalization.py`
- packet QA and final readiness reports.

## Workstreams

1. Record semantic ownership and diagnostics
   - Purpose: establish durable rules for future work.
   - Changes: this plan document plus later audit entries.
   - Artifacts: `SEMANTIC_DECISION_BOUNDARY_PLAN.md`.
   - Validation: document exists and names concrete owners.
   - QA: plan red-team by checking every changed behavior has a test.

2. Make deterministic role adjudication report-only
   - Purpose: prevent keyword code from mutating evidence roles.
   - Changes: `adjudicate_packet_roles()` should preserve packet roles and emit `role_conflict_candidates` with `status=report_only`.
   - Artifacts: `packet_role_adjudication_report.json` remains available.
   - Validation: tests prove no role mutation occurs, while warning candidates are still emitted.
   - QA: regression for no-association, conditional support, and negated-risk claims.

3. Stop text-keyword role inference in candidate profile and packet role projection
   - Purpose: only explicit source/model fields can assign semantic roles.
   - Changes: `_candidate_profile()` uses explicit `supports_challenges_or_scopes`, explicit role fields, quantity values, and limitations; no quote-text lexical role scan. `_decision_role()` uses explicit role fields only.
   - Artifacts: candidate cards keep `semantic_role_source`/diagnostic fields where possible.
   - Validation: tests show text containing “higher risk” does not automatically become counterweight without an explicit upstream role.
   - QA: existing context schema tests updated to distinguish explicit upstream role from lexical inference.

4. Stop broad relation-to-crux promotion
   - Purpose: avoid turning topical tensions into decision cruxes.
   - Changes: argument-model cruxes should come from explicit `crux_for` relations or model/refined crux artifacts, not every `in_tension_with`, `challenges`, or `depends_on` relation.
   - Artifacts: relation items can remain evidence/context but not mandatory decision cruxes.
   - Validation: tests prove `in_tension_with` alone is not promoted to a decision crux.
   - QA: packet QA still warns if a weak crux is present.

5. Make deterministic crux reconstruction diagnostic-only
   - Purpose: deterministic code must not synthesize a new answer-changing crux.
   - Changes: weak crux detection emits a report but does not replace items.
   - Artifacts: `decision_crux_reconstruction_report` becomes a warning/status artifact rather than a semantic rewrite.
   - Validation: tests prove item list is preserved and weak crux IDs are reported.
   - QA: final packet makes missing/weak crux visible to model critique.

6. Make unbound quantity interpretation non-semantic
   - Purpose: avoid implying direction or tuple binding not present in source-local evidence.
   - Changes: unpaired quantities get neutral interpretation and no inferred direction. Local tuple IDs remain allowed.
   - Artifacts: quantity binding report preserves warnings.
   - Validation: tests prove unpaired RR/CI/sample/follow-up values are warnings, not interpreted as one estimate.
   - QA: memo-ready packet quality keeps unsafe-pairing warnings.

7. Add semantic-boundary QA
   - Purpose: prevent regression to keyword-based semantic mutation.
   - Changes: focused tests plus, if feasible, a static scan test for banned mutation patterns.
   - Artifacts: tests documenting the rule.
   - Validation: focused tests and full suite.
   - QA: run latest eggs packet path and confirm warnings point to semantic uncertainty rather than silently repaired semantics.

## Execution Order

1. Commit the already verified atomic-claim preservation baseline.
2. Record this plan.
3. Convert role adjudication to report-only and update tests.
4. Remove candidate/packet lexical role inference and update tests.
5. Narrow crux promotion and make reconstruction diagnostic-only.
6. Neutralize unbound quantity interpretation.
7. Run focused tests, full suite, and an eggs prompt pipeline run.
8. Record completion audit.

## Acceptance Criteria

- No deterministic function silently changes support/counterweight/scope/crux labels based on claim text.
- Existing explicit model/source semantic labels still flow through the packet.
- Suspect labels produce diagnostics with owning stage and item IDs.
- Focused tests cover role adjudication, candidate profiling, crux construction, and quantity binding.
- Full test suite passes.
- Latest eggs prompt run has no truncation warning and exposes unresolved semantic uncertainty as warnings rather than deterministic fixes.

## Red-Team Checks

- A keyword like “higher risk” must not by itself flip a comparator claim to counterweight.
- A phrase like “not associated” must not by itself rewrite an upstream counterweight label to support.
- An `in_tension_with` relation must not automatically become a decision crux.
- A group of quantities must not be presented as a single interpreted estimate without a local tuple.
- A generic answer frame must be flagged as low-quality or generic rather than treated as a substantive answer.

## Generalizability Checks

- Tests should use abstract or mixed-domain examples, not only eggs.
- Explicit labels from upstream model/source artifacts should remain usable across domains.
- Meaning-preserving changes in wording should not change deterministic labels.
- Removing a word like “risk” should not be required to preserve a role.

## Completion Evidence

The plan is complete when there is a committed completion audit listing:

- commits by slice;
- files changed;
- verification commands and results;
- before/after packet QA observations;
- remaining semantic decisions still requiring model ownership or future work.
