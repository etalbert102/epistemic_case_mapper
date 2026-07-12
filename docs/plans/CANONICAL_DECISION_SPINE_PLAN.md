# Plan: Canonical Decision-Support Spine

Status note: references to the old section-rewrite synthesis path are historical. Current final synthesis should consume the memo-ready packet path; do not restore the deleted section-rewrite path.

## Objective

Build one validated canonical decision model before prose generation, then make every briefing section a projection of that model. The goal is to prevent the BLUF, evidence sections, scope sections, limits, and validation reports from disagreeing with each other.

The intended end state is a pipeline where:

- The default answer, exception cases, evidence boundaries, missing slots, and confidence are represented once.
- Every reader-facing section is generated from a section-specific projection of that same source of truth.
- The system fails visibly before prose when the decision model is internally inconsistent or insufficient.

## Current Gap

The current pipeline has improved validation and drift checks, but it still lets section-local context drive synthesis. This creates several recurring failure classes:

- The memo can answer for a default population while the Limits section says the default population is missing.
- Dose or intensity guidance can conflict across sections.
- Exceptions or counterevidence can dominate the BLUF instead of being represented as exceptions to the default answer.
- Some sections are marked `not_synthesis_ready` because they lack clean owned context.
- Textual obligations can be satisfied even when the memo is weak as decision support.

The root issue is that section generation is not yet governed by a single validated decision-support spine.

## Non-Goals

- Do not add source collection.
- Do not make egg-specific or biomedical-specific fixes.
- Do not rely on final prose polish to repair structural contradictions.
- Do not remove validation gates just because they fail.
- Do not collapse all evidence into a single opaque mega-scaffold.

## Design Principles

- One canonical answer model should control all reader-facing sections.
- Deterministic code owns schema validation, traceability, slot accounting, consistency checks, and section projection.
- Classical ML and graph/statistical methods own ranking, clustering, centrality, coverage scoring, duplicate detection, and outlier detection.
- Models own judgment-heavy synthesis: salience, framing, concise explanation, and prose.
- Model-produced claims must be selected from or grounded in pre-validated candidates.
- Missing evidence should be represented once in the spine, then projected only where relevant.
- Every major stage should write an artifact that explains what was accepted, rejected, repaired, or left unresolved.

## Inventory And Dependency Map

Before implementation, classify the existing artifacts into four groups:

- Spine inputs:
  - `evidence_weighting_ledger`
  - `curated_evidence_packets`
  - `candidate_evidence_cards`
  - `quantity_ledger`
  - `source_coverage_report`
  - `decision_model`
  - `decision_synthesis_model`
  - `argument_model`
  - `source_sufficiency_report`
- Candidate replacement artifacts:
  - `decision_synthesis_model`
  - current section synthesis packets
- Validation artifacts to move earlier:
  - briefing validation
  - evidence drift validation
  - section context acceptance
  - final brief evaluation
- Legacy/prose-only artifacts:
  - reader rewrite reports
  - whole-memo polish reports
  - final memo diagnosis

Current code path:

1. `run_map_briefing` in `map_briefing_pipeline.py` prepares and prioritizes the map.
2. `briefing_scaffold` calls `build_decision_support_model` in `map_briefing_decision_support_model.py`.
3. `build_decision_support_model` builds ledgers, quantities, graph synthesis, current decision model, decision synthesis, argument model, and argument artifacts.
4. `_attach_decision_ready_context_reports` in `map_briefing_pipeline.py` calls `build_decision_ready_context_bundle` in `map_briefing_context_curation.py`.
5. `build_decision_ready_context_bundle` builds source evidence cards, candidate cards, source-map reconciliation, evidence quality, and source coverage.
6. `_attach_decision_spine_bundle` builds the canonical spine, projection packets, and section context decision packets.
7. `rewrite_reader_memo_by_section` builds section packets from those canonical context packets and calls the model section by section.

The canonical spine should initially be inserted between steps 4 and 6:

```text
briefing_scaffold
  -> _apply_atomic_cards_to_briefing_map
  -> _attach_decision_ready_context_reports
  -> _attach_classical_evidence_selection
  -> _attach_slot_eligibility_audit
  -> _attach_canonical_decision_spine
  -> _attach_spine_projection_packets
  -> _attach_section_context_decision_packets
  -> section synthesis
```

Do not bury the first implementation inside `build_decision_support_model`. That function runs before source-card context exists, while the canonical spine needs both the decision model and the decision-ready context bundle. Once the spine is proven, some upstream artifacts can be migrated or simplified.

Target dependency order:

1. Map and evidence artifacts.
2. Decision support model artifacts.
3. Decision-ready context artifacts.
4. Classical evidence selection signals.
5. Slot eligibility audit.
6. Canonical decision spine.
7. Spine consistency and repair.
8. Section projections.
9. Section prose.
10. Final BLUF and memo assembly.
11. Whole-memo validation.

Recommended new modules:

- `map_briefing_classical_selection.py`
- `map_briefing_slot_eligibility.py`
- `map_briefing_canonical_spine.py`
- `map_briefing_spine_projection.py`
- `map_briefing_spine_validation.py`

Recommended changed modules:

- `map_briefing_pipeline.py`: attach the new spine artifacts after context curation.
- `map_briefing_artifacts.py`: write spine, selection, eligibility, projection, and validation artifacts.
- `map_briefing_section_input_compiler.py`: prefer spine projection packets when present, falling back to current section reasoning cards during migration.
- `map_briefing_memo_ready_finalization.py`: consume memo-ready packet obligations during final synthesis, retention checks, repair, polish, and presentation normalization.
- `map_briefing_validation.py`: validate final memo against the canonical spine when present.

## Workstreams

### 1. Evidence Eligibility Audit Layer

Purpose: Fix the current false-missing-slot failure before creating the spine.

Changes:

- For each required or expected decision slot, produce accepted candidates, rejected candidates, and rejection reasons.
- Inspect all relevant upstream sources before declaring a slot missing:
  - curated evidence cards
  - evidence ledger
  - quantity ledger
  - source coverage report
  - near-miss candidate cards
- Distinguish deterministic rejection from model-assisted rejection.

Artifacts:

- `slot_eligibility_audit.json`
- `slot_eligibility_audit.md`

Validation:

- A slot cannot be marked missing unless the audit names the checked candidate pools.
- A slot with accepted candidates cannot appear in `missing_decision_slots`.
- Tests cover narrower-than-question evidence, exception evidence, comparator evidence, and hard-outcome evidence.

Risks:

- Over-relaxing eligibility could promote off-question evidence.
- Mitigation: keep mismatch evidence appendix-only unless it is explicitly classified as scope, exception, or limitation context.

### 2. Classical Evidence Selection Layer

Purpose: Use statistical and graph-based methods to improve candidate ordering before either deterministic spine construction or model arbitration.

Changes:

- Compute relevance scores between the decision question and candidate evidence using lexical overlap and TF-IDF-style similarity.
- Cluster near-duplicate claims so repeated extraction does not overweight a position.
- Use graph centrality over claim/relation networks to identify load-bearing support, counterevidence, bridge claims, and crux candidates.
- Score coverage across sources, evidence families, quantities, populations, endpoints, comparators, mechanisms, and limits.
- Flag outlier quantities or isolated high-impact claims for caution rather than automatic promotion.
- Provide these signals as inputs to the slot eligibility audit and spine builder, not as final decisions.

Artifacts:

- `classical_evidence_selection_report.json`
- `claim_cluster_report.json`
- `evidence_centrality_report.json`
- `coverage_balance_report.json`
- `quantity_outlier_report.json`

Validation:

- Near-duplicate clusters reduce duplicate promotion into the spine.
- Centrality scores identify relation-connected claims without excluding low-centrality but slot-critical evidence.
- Coverage scoring flags underfed slots before prose generation.
- Quantity outlier flags are explainable and source-linked.

Risks:

- Classical scores can look objective while encoding shallow lexical similarity.
- Mitigation: use scores for ranking and diagnostics only; deterministic eligibility and source provenance still gate inclusion.
- Graph centrality can overweight noisy relation maps.
- Mitigation: combine centrality with source backing, evidence role, and section eligibility.

### 3. Canonical Decision Spine Schema

Purpose: Define the single source of truth.

Fields:

- `decision_question`
- `default_answer`
- `exception_answers`
- `dose_or_intensity_boundaries`
- `population_boundaries`
- `strongest_support`
- `strongest_counterevidence`
- `mechanism_or_proxy_evidence`
- `comparator_or_substitution`
- `evidence_quality_limits`
- `missing_decision_slots`
- `confidence`
- `source_anchors`

Each evidence-backed field must include:

- `field_id`
- `claim`
- `role`
- `source_ids`
- `candidate_card_ids`
- `claim_ids`
- `quantity_ids`
- `confidence`
- `limits`

Artifacts:

- `canonical_decision_spine.json`
- `canonical_decision_spine_validation.json`

Validation:

- Pydantic schema validation.
- No orphan prose fields.
- Every evidence-backed field has source traceability.
- Every quantity is linked to an allowed quantity anchor or source excerpt.

Risks:

- The spine could become a mega-scaffold that simply centralizes existing noise.
- Mitigation: only include decision-bearing fields with role justification and provenance.

### 4. Spine Builder

Purpose: Construct the canonical spine from existing artifacts.

Deterministic responsibilities:

- Pull candidate fields from audited eligible evidence.
- Rank candidates by source backing, role, question fit, evidence weight, source diversity, classical relevance scores, duplicate-cluster status, centrality, coverage contribution, and quantity-outlier flags.
- Preserve conflicting candidates instead of silently collapsing them.
- Attach source and candidate IDs before any model synthesis.

Model responsibilities:

- Choose among pre-validated candidates when salience is ambiguous.
- Produce short field-level synthesis from allowed candidate IDs.
- Explain why a candidate is default, exception, boundary, or limitation.

Artifacts:

- `canonical_decision_spine_raw_candidates.json`
- `canonical_decision_spine_selection_features.json`
- `canonical_decision_spine_model_prompt.txt`
- `canonical_decision_spine_model_raw.txt`
- `canonical_decision_spine.json`

Validation:

- Model output must reference allowed candidate IDs.
- Unsupported IDs or new source labels are rejected.
- Deterministic fallback creates a conservative spine when the model fails.

Risks:

- Model-written spine fields could drift from evidence.
- Mitigation: validate every model field against candidate IDs and source anchors.
- Classical ranking could hide important low-frequency evidence.
- Mitigation: require coverage constraints and slot-critical override paths in the selection features.

### 5. Spine Consistency And Repair Gate

Purpose: Fail or repair contradictions before prose.

Checks:

- Default answer cannot rely on a slot marked missing.
- Limits cannot mark a supported spine field as missing.
- Exception answers cannot replace the default answer.
- Dose boundaries must be unified or explicitly represented as conflicting source-specific guidance.
- Population boundaries must be explicit when the question asks about a population.
- Missing slots must have an eligibility audit trail.
- Quantities and source labels must be supported.

Repair order:

1. Deterministic repair:
   - demote unsupported defaults
   - move exception-led claims to exceptions
   - split conflicting dose boundaries
   - remove unsupported quantities
2. Model arbitration:
   - only for unresolved conflicts among validated candidates
3. Fail visibly:
   - if contradictions remain

Artifacts:

- `decision_spine_consistency_report.json`
- `decision_spine_repair_report.json`

Validation:

- Contradiction count is zero before section projection.
- If contradiction count is nonzero, section synthesis is blocked.

Risks:

- The gate could catch problems but not improve the memo.
- Mitigation: failed gates must feed a repair loop, not just reporting.

### 6. Section Projection Layer

Purpose: Derive section-specific packets from the canonical spine.

Projection rules:

- `Decision Brief`: default answer, confidence, strongest support, strongest caveat.
- `Why This Read`: reasoning chain from support and counterevidence to answer.
- `Evidence Carrying the Conclusion`: source-backed evidence grouped by role.
- `Practical Read`: dose, intensity, implementation, comparator, and practical implications.
- `Practical Scope and Exceptions`: population boundaries, exceptions, transfer limits.
- `Decision Cruxes`: conditions that would change the answer.
- `Limits of the Current Map`: missing slots and evidence-quality limits only.

Artifacts:

- `section_projection_packets.json`
- `section_projection_readiness_report.json`

Validation:

- Projections are deterministic and testable.
- BLUF projection cannot include missing slots as confident claims.
- Limits projection cannot repeat supported spine fields as missing.
- Scope projection must receive exceptions and boundaries when present.
- Evidence projection must receive source-backed support and counterevidence.

Risks:

- Projections could make prose formulaic.
- Mitigation: projections lock factual content, while the model still writes narrative reasoning from the projection.

### 7. Projection-Based Section Prose

Purpose: Let the model write readable sections without polluted context.

Prompt inputs:

- One section projection.
- Allowed source anchors for that section.
- Section-specific style and role instruction.
- Adjacent section titles only, not full memo context.

Prompt exclusions:

- Full scaffold.
- Global obligation ledger.
- Raw map artifacts.
- Other sections, except when generating the BLUF last.

Validation:

- Section preserves projection claims.
- Section does not add source labels, quantities, or unsupported claims.
- Section does not contain raw IDs.
- Section does not import missing-slot language outside the Limits projection.

Artifacts:

- section prompts
- section raw outputs
- section validation reports

Risks:

- Model may produce dull or overly cautious prose.
- Mitigation: allow narrative synthesis and transitions, but keep factual claims locked to projection fields.

### 8. Final Memo Assembly

Purpose: Compose the memo deterministically from accepted sections.

Changes:

- Generate body sections first from accepted projections.
- Generate BLUF last from:
  - accepted body sections
  - canonical spine default answer
  - canonical exceptions
- Append decision question and source list deterministically.
- Do not let model rewrite source list or decision question.

Artifacts:

- `BRIEFING.md`
- `briefing_validation_report.json`
- `final_brief_evaluation.json`

Validation:

- Final memo uses the canonical default answer first.
- Exception answers appear as exceptions, not the default.
- Sources are present and deterministic.
- Final memo fails if spine or projection readiness failed.

Risks:

- BLUF could still drift.
- Mitigation: BLUF validation compares against canonical spine, not just body text.

### 9. Telemetry And Before/After Evaluation

Purpose: Prove whether the spine improves the output.

Metrics:

- contradiction count
- false missing-slot count
- section readiness status
- source-anchor coverage per spine field
- duplicate-cluster promotion rate
- coverage balance across sources and evidence families
- centrality/source-backing disagreement count
- quantity outlier count
- unsupported quantity count
- unsupported source-label count
- raw-ID leakage count
- dose/population consistency
- memo readability and decision usefulness

Artifacts:

- `spine_quality_report.json`
- `before_after_briefing_comparison.md`
- `spine_completion_audit.md`

Validation:

- Compare the current pipeline and spine pipeline on the same generated map.
- Run at least one non-egg unseen case.
- Record whether failures are source-set limitations, extraction failures, eligibility failures, spine failures, projection failures, or prose failures.

## Execution Order

1. Add artifact write paths and summary links for the new reports, with empty placeholder builders.
2. Add the classical evidence selection reports in parallel with existing context curation.
3. Add the slot eligibility audit using existing candidate cards and classical selection features.
4. Add the canonical spine schema and validation tests.
5. Build a deterministic spine from existing artifacts, slot audit, and classical selection features.
6. Add spine consistency and repair reports in report-only mode.
7. Add section projections from the spine, still report-only.
8. Update `compile_model_section_packet` to consume section context decision packets and spine projections.
9. Add model-assisted spine arbitration behind strict provenance validation.
10. Make projection readiness blocking once report-only telemetry is calibrated.
11. Generate the BLUF from accepted body sections plus the spine.
12. Rerun eggs and one non-egg unseen case.
13. Remove retired global-planning and ad hoc section-reasoning compatibility paths once the spine path is better supported by tests.
14. Tighten reliable report-only gates into blocking gates.

## Acceptance Criteria

- No memo says a slot is both missing and used in the main answer.
- Default answer and exception answer are separate in the spine and memo.
- Dose or intensity guidance is either unified or explicitly represented as conflicting source-specific guidance.
- `section_context_acceptance_status` is no longer `not_synthesis_ready` unless the final memo is marked unacceptable.
- No invented source labels, raw IDs, or unsupported quantities appear in final memo prose.
- Every spine evidence field has source traceability.
- Classical selection reports explain which evidence was promoted, clustered, downweighted, or flagged as an outlier.
- Duplicate extraction does not cause duplicate spine promotion.
- Slot-critical low-centrality evidence can still enter the spine when the eligibility audit justifies it.
- Slot false-missing count decreases on the eggs case.
- The eggs memo improves on coherence and decision usefulness compared with the current output.
- At least one non-egg case runs through the same spine pipeline without case-specific code.

## Red-Team Checks

- Does the spine become an opaque mega-object?
- Are model-written spine fields drifting from source anchors?
- Are missing slots over-reported because eligibility is too strict?
- Are off-question claims promoted because eligibility is too loose?
- Are classical similarity scores overweighting shallow lexical matches?
- Is graph centrality amplifying noisy or sparse relation maps?
- Are rare but decision-critical claims being suppressed as outliers?
- Are sections coherent but formulaic?
- Does schema validity hide poor decision support?
- Does the pipeline fail loudly when it should, or does it produce a polished weak memo?

## Generalizability Checks

- Test on biomedical/nutrition, technical safety, and policy-style cases.
- Confirm no validators assume eggs, LDL, CVD, dietary advice, or nutrition.
- Confirm arbitrary document/question packages can produce a valid spine or fail visibly.
- Confirm better model backends improve synthesis without changing deterministic contracts.
- Confirm classical selection features remain advisory and do not become hidden domain-specific heuristics.
- Confirm source-limited cases are labeled as source-limited rather than synthesis failures.

## Deferred Work Policy

Any slice that cannot be completed must record:

- the unmet acceptance criterion
- the artifact showing the failure
- the suspected owner stage
- the next smallest implementation step

Deferred work should go in the completion audit, not in prose comments or chat history.

## Final Completion Audit

The plan is complete only when the repo contains:

- `canonical_decision_spine.json` for at least eggs and one non-egg case
- `slot_eligibility_audit.json`
- `classical_evidence_selection_report.json`
- `claim_cluster_report.json`
- `coverage_balance_report.json`
- `decision_spine_consistency_report.json`
- `section_projection_packets.json`
- `section_projection_readiness_report.json`
- `before_after_briefing_comparison.md`
- passing unit tests for schema, eligibility, consistency, projection, and final validation
- a final memo whose validation failures, if any, are attributable to source limitations rather than pipeline contradictions
