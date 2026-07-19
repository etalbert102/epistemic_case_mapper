# Whole-Pipeline Review: Richer Arm C Evidence Bundle Plan

Reviewer: `codex exec -m gpt-5.6-sol`
Mode: read-only whole-pipeline review

## Prompt

Review the revised `docs/plans/RICHER_ARM_C_QUANTITY_BINDING_PLAN.md`. Assume the plan is implemented faithfully. Look specifically for ways the plan is still too local to Arm C / quantity bundles and fails to consider the whole production pipeline from source extraction through analyst adjudication, evidence ledger, packet assembly, section synthesis, validation, citation presentation, and final memo usefulness.

## Verdict

**Revise before implementation.** The revised plan resolves most issues identified in the two prior reviews, but remains centered on Arm C-to-section projection. Faithful implementation could produce a semantically correct section draft while the delivered memo loses, rewrites, miscites, or weakens the new bundle obligations downstream.

The missing design unit is an end-to-end fact-ownership and reconciliation contract from source span to final cited sentence.

## Whole-Pipeline Blind Spots

| Stage | Remaining blind spot |
|---|---|
| Source extraction | The proposed bundle fields are not owned upstream. The current extraction schema lacks explicit population, comparator, statistic pairing, time horizon, and inference limits. A late registry cannot reliably reconstruct them. |
| Evidence ledger | The ledger still mixes structured claim quantities with flat, heuristically recovered `quantity_values`. A claim lineage can contain distinct HR/RR material; the quantity plan can therefore retain a point estimate with the wrong statistic label or interval before Arm C starts. |
| Analyst adjudication | Analysts decide memo use and interpretation, but do not explicitly approve bundle composition, estimate-interval pairing, endpoint/population/comparator identity, or permissible inference. Arm C selecting and interpreting its own bundles is partly self-adjudication. "Route to reconsideration" lacks an executable analyst update loop. |
| Packet assembly | Clustering, selection, canonical packet compilation, caps, and compaction remain outside the plan's invariants. `_brief_quantities()` drops much of the proposed bundle meaning, while `_dedupe_section_quantity_obligations()` deduplicates by the first numeric token, independently of the registry's richer dedupe rule. |
| Section synthesis | Preserving `depends_on_move_ids` does not make parallel writers resolve cross-section premises, conflicting estimates, or recommendation logic. Field survival is not argument coherence. |
| Finalization | After section synthesis, production runs memo repair, presentation normalization, final polish, and another presentation pass using the original memo-ready packet. The selected bundle contracts are not made authoritative for those stages. Section-level semantic checks therefore do not protect the final memo. |
| Citation presentation | Evidence tags become source-level citations, and `CITATION_TRACE.md` is rebuilt from the original packet rather than `evidence_trace` or selected bundles. A citation may name the correct source while supporting the wrong endpoint, subgroup, or quantity; source spans and bundle identity remain invisible. |
| Final usefulness | The rubric tests whether elements are identifiable, not whether the recommendation follows from weighted evidence, alternatives, costs/preferences, and unresolved gaps. "Action threshold" may also be inapplicable or invented for non-action questions. One unrelated and one qualitative replay are insufficient coverage of the failure classes. |

## Why They Matter For Decision Usefulness

- Downstream traceability cannot repair an upstream mispaired estimate, interval, endpoint, or comparator.
- The final reader may receive more precise-looking prose with greater false confidence.
- A correct section draft can regress during existing repair or polish calls without any bundle-aware final gate noticing.
- Source-level citations make audit burdensome precisely where quantitative specificity requires claim-level verification.
- Parallel sections can each be locally correct while the final recommendation remains contradictory or unsupported.
- A checklist-complete memo can still fail the real task: telling the reader what to do, for whom, why, under what uncertainty, and what evidence would change that choice.

## Recommended Plan Revisions

1. Move bundle ownership upstream. Define one canonical assertion-bundle schema at source extraction/evidence-unit level, with stable ID, exact source span/quote, estimate-interval pairing, statistic, unit, endpoint, population, comparator/exposure, horizon, and provenance. Missing fields should become explicit gaps, not late inference.
2. Make the ledger bundle-native. Carry bundle IDs and candidate/approved/rejected status through the evidence ledger and quantity adjudication. Add an end-to-end reconciliation ledger: `source span -> evidence unit -> analyst row -> writer item -> Arm C move -> section contract -> final sentence/citation`.
3. Add real analyst reconsideration. Require analyst approval for bundle composition and inference bounds. Contradictions must either update answer/confidence and regenerate downstream artifacts or block production with a review packet, not merely emit an Arm C flag.
4. Audit every lossy transform. Include clustering, canonical packet compilation, selection caps, compact projections, section dedupe, repair, polish, and presentation in the inventory. Require bundle-preservation invariants and before/after reconciliation at each boundary.
5. Propagate one augmented production contract. Repair, final polish, presentation, final diagnostics, citation trace, and artifact assembly must consume the projected selected-bundle contract, not the original packet.
6. Validate the delivered artifact. Run semantic realization, source-span entailment, estimate/interval pairing, citation adjacency, cross-section contradiction, and decision-model coherence checks after every memo mutation and on the final `BRIEFING.md`.
7. Make citations bundle-aware. Preserve sentence-to-bundle-to-source-span mappings in the reader-facing trace. Validate that presentation normalization and citation dedupe do not broaden a citation beyond the evidence tag that generated it.
8. Strengthen product evaluation. Use question-type-specific rubrics and a canary matrix covering multi-endpoint sources, tables, conflicting estimates, relative versus absolute effects, detached intervals, missing units, qualitative evidence, and non-action questions. Require independent human review with blocking error categories.

## Implementation Priority

1. **P0:** Canonical upstream bundle schema, analyst authority, and end-to-end reconciliation ledger.
2. **P0:** Propagate selected contracts through repair, polish, presentation, citation assembly, and final validation.
3. **P1:** Remove downstream lossy dedupe/compaction and add cross-section coherence checks.
4. **P1:** Bundle-level citation trace and final sentence-to-span audit.
5. **P2:** Broader canary matrix and independent decision-usefulness review protocol.

Read-only review; no files were edited and no tests were run by the reviewer.
