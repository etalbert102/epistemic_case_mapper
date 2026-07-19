# Review: Richer Arm C Quantity Binding Plan

Reviewer: `codex exec -m gpt-5.6-sol`
Mode: read-only architectural review

## Verdict

**Revise before implementation.** The plan targets the correct pipeline boundary, between Arm C prioritization and section synthesis, but it is not yet the strongest production design. It duplicates existing quantity-contract machinery, risks bypassing the analyst quantity-binding gate, and does not address the lossy projection that currently discards much of the proposed richer reasoning.

## Strong Points

- Correctly avoids a polish call and treats the writer contract as the intervention point.
- Keeps evidence salience and warrants model-owned while reserving identity, lineage, validation, and projection for deterministic code.
- Uses section-owned structured obligations, which fits Arm B/C's slim-packet architecture.
- Includes fail-loud behavior, artifacts, prompt-size controls, and a non-eggs replay.
- Recognizes that putting quantities in `writing_job` is insufficient.

## Gaps And Risks

- Raw quantities may bypass semantic approval. The plan proposes ingesting `evidence_budget.rows[].quantity_values` directly. That conflicts with the existing rule that only semantically approved bindings become memo obligations. The saved eggs budget contains off-scope values such as `2 years and older`; selecting an aggregated writer item does not make that quantity relevant.
- The proposed bridge partly already exists. `build_evidence_expression_contracts()` already merges memo-item quantities and `quantity_obligation_plan.must_retain` rows into `required_quantity_atoms`. `_section_local_jobs()` already derives `required_quantities_by_evidence_id` from those contracts, and section validation already retries when quantities are dropped. The plan should identify the precise missing coverage rather than introduce a parallel contract system.
- Evidence selection is not quantity selection. Writer items aggregate multiple upstream claims. Binding every quantity associated with a selected writer ID makes deterministic code perform an implicit semantic promotion and risks attaching an estimate to the wrong endpoint, subgroup, comparator, or claim.
- Richer Arm C output is currently projected lossily. `_arm_c_move_to_argument_move()` combines warrant and decision effect into one field while dropping dependencies and alternatives. `_compact_move()` then truncates `writing_job` to 420 characters. A richer prompt alone therefore will not reliably produce a richer writer packet.
- Insertion points remain ambiguous. The plan says to populate `required_quantity_atoms` "or" job-level quantities. These should not become competing authorities; `required_quantity_atoms` should be canonical, with jobs derived from it.
- Production wiring is overstated. Arm C is already enabled from analyst model plus evidence budget, already has the disable switch, and already receives the active in-memory packet. The packet already carries `quantity_obligation_plan`; adding a second context copy risks stale dual authority.
- Dedupe by normalized quantity text is too weak. It can collapse equal numbers with different meanings or retain semantic duplicates such as an estimate and the same estimate plus confidence interval. A report-only cap can also silently remove the most important anchor.
- "No fallback memo" does not match the top-level pipeline's explicit inspectable, non-decision-ready fallback behavior. The requirement should prohibit silent legacy synthesis fallback, not all fallback output.

## Recommended Revisions

1. Choose the quantity authority explicitly.
   - Safest simple version: bind only existing `must_retain` or analyst-`must_use` quantity-plan rows.
   - Stronger version: expose stable quantity candidate IDs to the existing Arm C call and add `quantity_anchor_ids` per move. The model selects semantic quantity relevance; deterministic code validates IDs and attaches exact value, endpoint, comparator, scope, source, and upstream lineage.

2. Use one exact projection path.
   - Normalize and validate quantity IDs in `run_arm_c_prioritization()`.
   - Build `selected_quantity_anchor_report` inside `build_arm_c_projection()`.
   - Pass anchors to `build_arm_b_projection()`.
   - Merge them only into `evidence_expression_contracts[].required_quantity_atoms`; derive section-local jobs from those contracts.
   - Write the report through `_write_prioritized_argument_projection_artifacts()` and expose it in the normal artifact/review inventory.

3. Fix reasoning retention in the same slice.
   - Preserve `warrant`, `decision_effect`, `depends_on_move_ids`, relevant limitations, and counterweight disposition as first-class Arm C prompt fields, or add a direct Arm C projector instead of compressing into the v1 Arm B move shape.

4. Add missing tests.
   - Rejected or context-only quantity is never promoted.
   - One writer item covering multiple upstream claims receives only explicitly selected or approved anchors.
   - Lineage fan-out, same-number/different-endpoint, conflicting estimates, semantic duplicates, deterministic cap ordering, missing source IDs, and unresolved quantity IDs are covered.
   - Rich move fields and quantities survive into the actual initial and retry prompts.
   - Unknown IDs in `evidence_accounting` are rejected.
   - Missing quantity plan degrades visibly without promoting raw budget values.
   - Reordered inputs and renamed source labels are metamorphic invariants.

5. Tighten promotion evidence.
   - Require zero rejected-quantity promotions, zero unmatched anchors, zero new source or unsupported-quantity warnings, multiple samples when decoding is nondeterministic, and blinded/manual comparison on eggs plus an unrelated case.

## Production Effectiveness Assessment

As written, the plan is likely to improve numeric retention but has a material chance of reducing epistemic correctness through noisy or mis-scoped quantity promotion. Its richer-prompt benefit is also constrained by the current lossy move projection.

With model-selected quantity IDs, a single canonical quantity contract, and end-to-end preservation of richer move fields, this becomes a strong production intervention: no additional model call, good architecture fit, auditable failures, and substantially better odds of improving decision usefulness rather than merely increasing numeric density.

Review was read-only; no files were edited or tests run by the reviewer.
