# Plan: Packet-First Briefing Pipeline

Status note: this plan is historical. The packet-first, section-rewrite, old final-editor, and warning-repair memo paths it references have been superseded by the memo-ready packet path. Do not restore those deleted paths; use `memo_ready_packet` and `map_briefing_memo_ready_finalization.py` for final synthesis.

## Objective

Replace the default section-by-section model rewrite path with a packet-first synthesis path. The model budget should improve the decision briefing packet: evidence prioritization, role assignment, quantities, cruxes, source retention, and salience. The memo should then be assembled deterministically and polished with one whole-memo pass.

The desired end state is:

1. Existing map artifacts are converted into a compact, decision-shaped packet.
2. A model improves that packet as structured JSON, not prose.
3. Deterministic code creates a memo plan and first draft from the refined packet.
4. One whole-memo model pass improves coherence and readability.
5. Packet-based audits check whether key evidence, quantities, source labels, and caveats survived.

This shifts inference from repeated section-local prose repair into the stage where model judgment is most valuable: making the context better before synthesis.

## Current Gap

The codebase already contains most of the needed machinery, but the responsibilities are spread across many artifacts:

- `main_memo_obligations.py` selects required memo obligations.
- `map_briefing_section_input_compiler.py` builds section-local model packets.
- `map_briefing_evidence_role_matrix.py` assigns evidence roles and working sets.
- `map_briefing_memo_ready_finalization.py` synthesizes, checks retention, repairs, polishes, and normalizes the final memo from the memo-ready packet.
- The deleted section rewrite path used to spend many model calls rewriting individual sections.

The missing layer is a single `decision_briefing_packet.json` that becomes the source of truth for both synthesis and validation.

Recent full-map experiments exposed the same issue from the other direction:

- Feeding the raw full map exceeded backend context limits.
- Feeding a compact full-map inventory produced a readable but shallow memo.
- The compact full-map memo dropped decision-critical details that the map contained.

The failure mode is not just prompt size. The model needs a decision-shaped package that preserves key facts and roles, not a dump of artifacts or a tiny generic summary.

## Non-Goals

- Do not change source acquisition.
- Do not change claim extraction or relationship construction unless packet telemetry identifies a specific upstream failure.
- Do not add domain-specific vocabularies.
- Do not restore the deleted section rewrite fallback; unsupported callers should assemble `memo_ready_packet.evidence_items`.
- Do not make uncalibrated validators blocking. New gates should start report-only unless they check hard invariants such as schema validity, source IDs, or exact required quantities.
- Do not ask the model to invent source labels, quantities, or evidence not present in the packet.

## Design Principles

- Deterministic code owns artifact assembly, stable IDs, coverage accounting, source labels, quantity extraction, traceability, and hard validation.
- Classical ML/statistics own similarity, clustering, ranking support, duplicate pressure, centrality, and coverage pressure.
- The model owns semantic judgment over bounded records: role refinement, salience, crux naming, duplicate consolidation, and concise natural-language rationale.
- The packet is the durable interface between map construction and prose generation.
- The memo writer should receive less total context than the full map but more decision-relevant context than a generic curated packet.
- Every retained evidence bundle needs a decision role, source anchor, directionality, key quantity when available, limit/caveat, and section use.
- Missing packet content should fail visibly through telemetry and warnings before the memo is treated as good.

## Inventory And Dependency Map

Existing integration points:

- `map_briefing_pipeline.py`
  - Best insertion point is after `_attach_decision_ready_context_reports(...)` and `_attach_decision_spine_bundle(...)`, before prompt/scaffold artifacts and final reader outputs.
- `map_briefing_spine_bundle.py`
  - Already creates classical selection, canonical spine, slot reconciliation, section projection packets, section context packets, evidence role matrix, and working sets.
- `main_memo_obligations.py`
  - Should be upgraded to consume `decision_briefing_packet` rather than independently reconstructing obligations from scattered artifacts.
- `map_briefing_section_input_compiler.py`
  - Should consume packet section views if present, with current working sets as fallback.
- `map_briefing_final_outputs.py`
  - Routes generation through the memo-ready packet synthesis path and fails clearly when `memo_ready_packet.evidence_items` is absent.
- `map_briefing_memo_ready_finalization.py`
  - Validates retention, performs targeted repair, runs final polish, and normalizes presentation against packet obligations.

Existing artifacts to reuse:

- `candidate_evidence_cards.json`
- `source_evidence_cards.json`
- `quantity_ledger.json`
- `graph_synthesis_packet.json`
- `canonical_decision_spine.json`
- `argument_model.json`
- `evidence_role_matrix.json`
- `section_evidence_working_sets.json`
- `decision_traceability_matrix*.json`
- `main_memo_obligation_ledger.json`

New artifacts:

- `decision_briefing_packet.json`
- `packet_sufficiency_report.json`
- `packet_critique_prompt.txt`
- `packet_critique_raw.txt`
- `packet_critique_report.json`
- `decision_briefing_packet_refinement_prompt.txt`
- `decision_briefing_packet_refinement_raw.txt`
- `decision_briefing_packet_refinement_report.json`
- `memo_plan.json`
- `memo_packet_retention_report.json`
- `packet_first_comparison_report.json`

## Target Packet Shape

The packet should be structured by decision function, not artifact origin:

```json
{
  "schema_id": "decision_briefing_packet_v1",
  "decision_question": "...",
  "answer_frame": {
    "default_answer": "...",
    "confidence": "low|medium|high",
    "scope": "...",
    "main_uncertainty": "..."
  },
  "must_retain_ledger": [
    {
      "item_id": "retain_001",
      "decision_role": "quantitative_anchor",
      "statement": "...",
      "required_terms": ["..."],
      "source_ids": ["..."],
      "claim_ids": ["..."],
      "quantity_ids": ["..."],
      "importance": "critical|high|medium",
      "section_targets": ["Evidence Carrying the Conclusion"],
      "omission_policy": "must_include|may_appendix|warn_if_missing"
    }
  ],
  "evidence_bundles": [
    {
      "bundle_id": "bundle_001",
      "decision_role": "strongest_support|counterweight|scope_boundary|mechanism|crux|context",
      "claim": "...",
      "source_ids": ["..."],
      "source_labels": ["..."],
      "quantity_values": ["..."],
      "why_it_matters": "...",
      "limits": ["..."],
      "tension_with_bundle_ids": ["..."],
      "section_use": "..."
    }
  ],
  "section_views": [
    {
      "section": "Evidence Carrying the Conclusion",
      "section_job": "...",
      "primary_bundle_ids": ["..."],
      "contrast_bundle_ids": ["..."],
      "boundary_bundle_ids": ["..."],
      "must_retain_item_ids": ["..."]
    }
  ],
  "source_trail": [
    {
      "source_id": "...",
      "source_label": "...",
      "used_for": ["..."],
      "appears_in_packet": true
    }
  ],
  "coverage_report": {
    "high_priority_omitted_count": 0,
    "source_label_missing_count": 0,
    "quantity_missing_count": 0,
    "warnings": []
  }
}
```

## Workstreams

### 1. Deterministic Decision Briefing Packet Builder

Purpose: Create the source-of-truth packet from existing scaffold artifacts.

Changes:

- Add `map_briefing_decision_packet.py`.
- Build a broad pre-trim candidate pool from candidate evidence cards, source evidence cards, section evidence working sets, argument model rows, graph tensions, canonical spine fields, and quantity ledger cards.
- Prefer source-grounded cards and mechanically extracted quantities over generated claim text whenever they conflict.
- Build initial evidence bundles only after the broad pool is inventoried.
- Preserve stable IDs from source cards, candidate cards, claims, relations, and quantities.
- Build source trail deterministically from source metadata.
- Build a must-retain ledger from high-priority bundles and quantities.
- Emit packet sufficiency telemetry before and after trimming, so compression failures are visible.

Artifacts:

- `decision_briefing_packet.json`
- `decision_briefing_packet_report.json`
- `packet_sufficiency_report.json`

Validation:

- Packet schema is valid.
- Every `source_id` resolves to known source metadata.
- Every required quantity comes from `quantity_ledger`.
- Every must-retain item points to at least one evidence bundle or records why it cannot.
- Every high-priority pre-trim candidate is either retained, demoted with a reason, or listed in `packet_sufficiency_report.json`.

Risks:

- If bundle construction is too broad, the packet becomes another full-map dump.
- If bundle construction is too narrow, important counterevidence gets dropped before the model can judge it.
- If compression happens before sufficiency checks, the packet can silently discard the exact details the memo needs.

### 2. Packet Quality Ranking And Coverage Pressure

Purpose: Make packet selection generalizable before the model sees it.

Changes:

- Use existing classical ML helpers and deterministic scores to rank bundles.
- Include diversity constraints by source, evidence role, decision slot, and quantity type.
- Detect near-duplicate bundles and mark duplicate pressure without over-consolidating.
- Detect high-priority omitted evidence before synthesis.
- Add `packet_sufficiency_report.json` as the hard diagnostic for whether the packet is good enough to synthesize from.
- Score packet quality along separate dimensions: source anchoring, role coverage, quantity retention, directionality preservation, decision relevance, source diversity, counterweight preservation, and compression loss.
- Record source-grounding conflicts where generated claims, argument-model rows, or model-refined roles diverge from source evidence cards.

Artifacts:

- `decision_briefing_packet_quality_report.json`
- `packet_bundle_cluster_report.json`
- `packet_sufficiency_report.json`

Validation:

- Packet contains support, counterweight, scope/boundary, quantity, and crux candidates when present in the map.
- High-relevance omitted cards are listed with reasons.
- No domain-specific terms are needed for ranking.
- `packet_sufficiency_report.json` distinguishes `ready`, `usable_with_warnings`, and `not_sufficient_for_synthesis`.
- The report names which missing role or quantity would most likely weaken the final memo.

Risks:

- Overweighting centrality can suppress isolated but decision-critical counterevidence.
- Overweighting quantities can overpromote weak numeric claims.
- A packet can satisfy surface coverage while still losing directionality, such as turning a counterweight into support or a subgroup boundary into a general conclusion.

Required sufficiency checks:

- `high_priority_omitted_evidence`: candidate/source cards above the relevance threshold that did not enter any packet bundle.
- `role_coverage`: whether support, counterweight, scope/boundary, crux, mechanism/proxy, and quantity roles are represented when available.
- `quantity_retention`: whether top quantity ledger anchors appear in must-retain items or have a demotion reason.
- `source_diversity`: whether retained bundles over-rely on one source when multiple relevant sources are available.
- `counterweight_preservation`: whether opposing or limiting evidence survives trimming.
- `directionality_consistency`: whether each bundle preserves support/challenge/scope direction from source cards and relations.
- `source_grounding_precedence`: whether source-card facts override generated claim or model-refined packet text when they conflict.
- `compression_loss`: whether records removed during trimming include unique quantities, unique source labels, unique endpoints, or unique population boundaries.
- `unsupported_or_weakly_anchored_bundles`: whether packet bundles lack source card anchors or rely only on generated map claims.
- `over_merge_risk`: whether proposed duplicate clusters include different sources, populations, outcomes, or evidence roles.

### 3. Model Packet Critique And Adjudication

Purpose: Give the model enough flexibility to challenge whether the deterministic packet is the right representation of the evidence before the system refines or writes from it.

This is a structured critique pass, not a prose synthesis pass. The model should identify packet-level analytic failures that deterministic code may miss, such as a wrong answer frame, missing crux, misassigned evidence role, over-weighted proxy evidence, under-weighted counterevidence, or a section plan likely to produce a bad memo.

Changes:

- Add a model call that receives the deterministic packet plus `packet_sufficiency_report.json`.
- The model returns a structured critique/adjudication JSON object.
- The critique can propose repairs but cannot directly mutate the packet.
- Deterministic code accepts only recommendations tied to existing bundle, source, claim, relation, quantity, or section IDs.
- Recommendations not grounded in existing IDs become source/map insufficiency warnings, not new facts.

Critique schema:

```json
{
  "schema_id": "packet_critique_v1",
  "packet_sufficiency_judgment": "ready|needs_repair|not_sufficient",
  "bad_answer_frame_risks": [
    {
      "risk": "...",
      "affected_bundle_ids": ["..."],
      "why_it_matters": "...",
      "recommended_action": "..."
    }
  ],
  "missing_decision_functions": [
    {
      "decision_function": "counterweight|scope_boundary|crux|mechanism|quantity|comparator",
      "evidence_ids_that_suggest_gap": ["..."],
      "recommended_action": "..."
    }
  ],
  "misassigned_roles": [
    {
      "bundle_id": "...",
      "current_role": "...",
      "recommended_role": "...",
      "rationale": "..."
    }
  ],
  "overweighted_bundles": ["..."],
  "underweighted_bundles": ["..."],
  "missing_or_weak_cruxes": ["..."],
  "section_plan_risks": ["..."],
  "recommended_packet_edits": [
    {
      "edit_type": "promote|demote|split|merge|relabel|add_warning",
      "target_ids": ["..."],
      "rationale": "..."
    }
  ]
}
```

Artifacts:

- `packet_critique_prompt.txt`
- `packet_critique_raw.txt`
- `packet_critique_report.json`
- `packet_critique_adjudication_report.json`

Validation:

- Pydantic/schema validation.
- Every referenced ID must exist in the deterministic packet or be recorded as unsupported.
- Critique cannot introduce new evidence, source labels, quantities, or claims.
- Accepted critique edits are recorded separately from rejected/report-only edits.
- If the model says `not_sufficient`, the pipeline should continue only with visible warnings or fallback behavior.

Risks:

- Model critique may hallucinate missing evidence. Treat unanchored claims as insufficiency warnings only.
- Model critique may overreact to uncertainty and block useful synthesis. Start with report-only gating except for schema and ID validity.
- Model critique may favor narrative neatness over evidentiary weight. Deterministic adjudication must preserve source-grounding and quantity constraints.

### 4. Model Packet Refinement

Purpose: Spend inference on improving the packet, not rewriting sections.

Changes:

- Add one model call that receives the deterministic packet, `packet_sufficiency_report.json`, and accepted critique/adjudication recommendations, then returns validated JSON.
- The model may merge duplicate bundles, improve decision-role labels, identify load-bearing quantities, rank cruxes, and mark low-weight or contextual items.
- The model may not add new sources, new quantities, or new claims unsupported by bundle IDs.
- The model is asked to resolve visible weaknesses rather than freely rewriting the package.
- The model must preserve or explicitly demote every critical/high must-retain item; silent deletion is invalid.

Artifacts:

- `decision_briefing_packet_refinement_prompt.txt`
- `decision_briefing_packet_refinement_raw.txt`
- `decision_briefing_packet_refinement_report.json`
- updated/refined `decision_briefing_packet.json`

Validation:

- Pydantic/schema validation.
- All model-retained IDs must exist in the deterministic packet.
- Unsupported additions are rejected or recorded as warnings.
- Pre/post report shows what was merged, promoted, demoted, or left unresolved.
- Any model-proposed merge crossing source, population, outcome, or role boundaries requires an explicit rationale and remains report-only unless deterministic checks accept it.

Risks:

- Model over-merges distinct evidence.
- Model makes the packet prettier but less faithful.
- Model rankings become opaque unless the report records rationale and ID-level changes.
- Model refinement may mask deterministic packet insufficiency. The pre-refinement sufficiency report must remain visible and cannot be overwritten.

### 5. Main Memo Obligation Refactor

Purpose: Make the packet the source of truth for retention.

Changes:

- Update `main_memo_obligations.py` so `build_main_memo_obligation_plan()` prefers `scaffold["decision_briefing_packet"]`.
- Preserve current argument/quantity/evidence-family obligation logic as fallback.
- Add obligation categories that directly mirror packet roles.

Artifacts:

- `main_memo_obligation_ledger.json`
- `UNIFIED_REQUIREMENT_LEDGER.md`

Validation:

- Required packet items become memo obligations.
- Existing obligation tests still pass.
- Known high-value quantities and source labels are retained on current eggs artifacts without hardcoding eggs.

Risks:

- If the packet is weak, obligations become weak. The packet quality report must make that visible.

### 6. Deterministic Memo Planner

Purpose: Convert the refined packet into a memo plan and deterministic draft.

Changes:

- Add `map_briefing_memo_plan.py`.
- Build `memo_plan.json` from packet section views.
- Assign every must-retain item to one primary section and optional cross-reference sections.
- Render a deterministic first draft that is complete but intentionally plain.

Artifacts:

- `memo_plan.json`
- `packet_first_draft.md`

Validation:

- Every `must_include` item is assigned to a section.
- Each section has a distinct job and distinct primary bundles.
- No unresolved source IDs or quantity IDs appear in the draft.

Risks:

- Deterministic draft may be stiff. That is acceptable if the final whole-memo pass can improve prose without dropping facts.

### 7. Single Whole-Memo Writer

Purpose: Replace default section-by-section model rewrite with one model pass over the packet and memo plan.

Changes:

- Add packet-first path in `map_briefing_final_outputs.py`.
- Keep `rewrite_reader_memo_by_section()` behind a fallback/config flag.
- Prompt the model with the refined packet, memo plan, and deterministic draft.
- Ask for one coherent decision-ready memo, not separate section rewrites.

Artifacts:

- `packet_first_memo_prompt.txt`
- `packet_first_memo_raw.md`
- `BRIEFING.md`

Validation:

- One memo is produced.
- It answers the decision question directly.
- It cites source labels from the packet.
- It preserves required quantities and counterweights.

Risks:

- One-pass prose may still drop details. Packet-based retention audit handles this.

### 8. Packet-Based Audit And Repair

Purpose: Ensure polished prose remains faithful to the packet.

Changes:

- Add `memo_packet_retention_report.json`.
- Update final memo polish/judge/repair to use packet obligations.
- Repair prompt receives only missing packet items, local source/quantity context, and current memo.

Artifacts:

- `memo_packet_retention_report.json`
- `packet_repair_prompt.txt`
- `packet_repair_raw.md`

Validation:

- Missing critical items produce warnings or targeted repair.
- Directionality checks catch reversed support/counterweight roles.
- Source labels and exact quantities are checked deterministically where possible.

Risks:

- Validators may become clumsy if they rely on exact text matching. Prefer stable IDs, required terms, and source/quantity anchors.

### 9. Comparison And Default Switch

Purpose: Prove whether packet-first is better before making it default.

Changes:

- Run current section-rewrite path and packet-first path on the same map/question/documents.
- Compare runtime, model calls, required-item retention, source coverage, quantity retention, repetition, and readability.
- Keep packet-first behind a flag until it wins or exposes clear next work.

Artifacts:

- `packet_first_comparison_report.json`
- before/after `BRIEFING.md`

Validation:

- Packet-first must reduce model calls materially.
- Packet-first must retain at least as many critical obligations as section rewrite.
- Packet-first memo must be at least as readable by manual review.

Risks:

- It may improve efficiency but reduce memo polish. If so, keep packet refinement but retain final prose pass improvements.

## Execution Order

1. Build deterministic `decision_briefing_packet.json`.
2. Add packet quality and coverage reports.
3. Add model packet critique/adjudication behind a flag.
4. Add model packet refinement behind a flag and feed it accepted critique recommendations.
5. Refactor main memo obligations to consume the packet with fallback.
6. Add deterministic memo planner and draft renderer.
7. Add packet-first whole-memo writer behind a flag.
8. Add packet-based retention audit and warning repair.
9. Run current vs packet-first comparison on eggs.
10. Run at least one unrelated case to check generalizability.
11. Make packet-first the default only if comparison reports support it.

## Implementation Record

Status: implemented in bounded slices.

Committed slices:

1. `3a619d8` - recorded this packet-first briefing pipeline plan.
2. `3821518` - added deterministic `decision_briefing_packet.json`, pre/post `packet_sufficiency_report.json`, and scaffold artifact wiring.
3. `adb1756` - added structured model packet critique, deterministic ID adjudication, and packet refinement.
4. `336d4bd` - made main memo obligations prefer packet `must_retain_ledger` items with fallback to prior obligation logic.
5. `0ef71d7` - added deterministic packet memo plan/draft artifacts and routed final memo generation through packet-first draft plus one whole-memo pass by default when a packet exists.
6. `28642bf` - added `memo_packet_retention_report.json` and final-summary wiring.
7. `89137fd` - added `packet_first_comparison_report.json` with model-call and retention accounting.
8. `b05b4c2` - added targeted `packet_repair_prompt.txt`, `packet_repair_raw.md`, and `packet_repair_report.json`; repairs are accepted only when deterministic packet-retention metrics improve.

Completion notes:

- Section-by-section rewrite remains available as fallback when no `decision_briefing_packet` is present.
- Packet-first is the default route when the pipeline has a populated packet.
- Comparison reports use an estimated legacy section-rewrite baseline unless a live legacy run report is available; this avoids claiming a live A/B run when only the packet-first route was executed.
- The new retention and repair checks are warning/report oriented except for hard schema and ID validation in packet refinement.
- Verification for the final implementation slice passed with `PYTHONPATH=src python3 -m pytest -q`.

## Acceptance Criteria

- The pipeline writes `decision_briefing_packet.json`, `memo_plan.json`, `memo_packet_retention_report.json`, and `packet_first_comparison_report.json`.
- The pipeline writes `packet_sufficiency_report.json` before model refinement and after refinement.
- The pipeline writes `packet_critique_report.json` and `packet_critique_adjudication_report.json` before model refinement.
- The packet includes high-priority support, counterweight, scope/boundary, crux, quantity, and source-trail records when present in the input artifacts.
- The packet sufficiency report explicitly accounts for high-priority omitted evidence, major role coverage, quantity retention, source diversity, counterweight preservation, directionality, source-grounding conflicts, and compression loss.
- The packet critique pass can flag bad answer-frame risks, missing decision functions, misassigned roles, overweighted/underweighted bundles, weak cruxes, and section-plan risks without directly mutating the packet.
- Source-grounded cards and mechanical quantities take precedence over generated claims or model refinements when conflicts are detected.
- The final memo preserves more critical must-retain items than the current section-rewrite path, or preserves the same amount with materially fewer model calls.
- Packet-first does not depend on domain-specific vocabulary.
- Existing section rewrite remains available as fallback.
- Full tests pass with:

```bash
PYTHONPATH=src python3 -m pytest -q
```

## Red-Team Checks

### Failure: The Packet Is Just A Smaller Full-Map Dump

Detection:

- Packet word/char budget exceeds target.
- Many bundles lack `decision_role`, `why_it_matters`, or `section_use`.
- Memo repeats source summaries instead of reasoning.

Mitigation:

- Enforce bundle budgets by decision role.
- Require every bundle to carry a decision function.
- Demote unassigned context to source trail or appendix telemetry.

### Failure: The Packet Drops The Key Information Before Synthesis

Detection:

- `decision_briefing_packet_quality_report.json` shows high-priority omitted cards.
- `packet_sufficiency_report.json` shows compression loss, missing role coverage, or missing high-priority quantities.
- Required quantities in `quantity_ledger` do not appear in must-retain ledger.
- Counterweight/source diversity is missing.
- Source-grounded evidence is demoted while generated claims remain load-bearing.

Mitigation:

- Add pre-synthesis hard warnings for omitted high-priority cards.
- Add role coverage requirements.
- Include a small `near_miss_or_omitted_high_priority` section in the packet.
- Delay trimming until broad candidate coverage has been measured.
- Keep source-grounded counterweights and unique quantities unless there is an explicit demotion reason.

### Failure: Model Refinement Makes The Packet Less Faithful

Detection:

- Refined packet references IDs not present in deterministic packet.
- Bundle merge report shows distinct sources or opposing roles collapsed.
- Must-retain item count drops without explicit demotion rationale.
- Refined packet improves prose labels but worsens `packet_sufficiency_report.json`.

Mitigation:

- Validate all IDs.
- Allow model to propose merges but deterministic code accepts/rejects them.
- Keep pre-refinement packet and diff report.
- Compare pre/post sufficiency and fail visibly if refinement reduces source anchoring, directionality consistency, or critical retention.

### Failure: Model Critique Is Too Constrained To Improve The Packet

Detection:

- Critique only repeats deterministic sufficiency warnings.
- Critique never flags answer-frame risks, missing decision functions, role mistakes, crux weakness, or section-plan risks.
- Packet quality does not improve after accepted critique recommendations are applied.

Mitigation:

- Prompt critique as an adversarial packet review, not as validation prose.
- Give it the packet, sufficiency report, and compact artifact inventory so it can challenge the frame.
- Require structured critique fields that cover answer frame, decision functions, roles, weights, cruxes, and section-plan risks.

### Failure: Model Critique Is Too Flexible And Drifts

Detection:

- Critique references sources, quantities, or claims absent from the packet.
- Critique recommends new evidence rather than identifying source/map insufficiency.
- Critique changes the decision answer without anchored bundle IDs.

Mitigation:

- Treat critique as propose-only.
- Deterministic adjudication accepts only ID-grounded edits.
- Unanchored recommendations become insufficiency warnings, not packet mutations.

### Failure: The Packet Measures Retention But Not Decision Usefulness

Detection:

- Packet retains names and numbers but lacks `why_it_matters`, `limits`, or `tension_with_bundle_ids`.
- Bundles do not say what would change the answer.
- Memo preserves facts but still reads like a flat source list.

Mitigation:

- Require each high/critical bundle to include `why_it_matters`, `limits`, and `section_use`.
- Require crux bundles to include a decision-changing condition.
- Include packet quality dimensions for decision relevance and evidentiary weight, not just term retention.

### Failure: Packet Is Good But Memo Still Drops Facts

Detection:

- `memo_packet_retention_report.json` flags missing critical items.
- Required source labels or quantities absent from final memo.
- Counterweights are present in packet but absent from prose.

Mitigation:

- Targeted repair call with missing packet items.
- Do not accept final polish as successful if critical packet items are missing; report warnings if repair cannot fix.

### Failure: Packet-First Saves Calls But Produces Bland Prose

Detection:

- Memo reads like a list of bundles.
- Coherence/readability reports or manual review show weak narrative.
- One-pass writer preserves facts but lacks decision reasoning.

Mitigation:

- Improve memo plan transitions and answer frame.
- Keep one whole-memo polish pass.
- Do not return to section-by-section rewrites unless packet-first cannot reach acceptable prose.

## Generalizability Checks

- Run on eggs plus at least one unrelated decision question.
- No code path should mention egg, cholesterol, HEPA, LHC, or any case-specific content.
- Packet roles should be abstract: support, counterweight, boundary, mechanism, crux, quantity, source trail.
- Ranking should use general fields: relevance, source anchoring, quantity presence, evidence role, centrality, contradiction/tension, quality, and section coverage.
- If a case lacks quantities, the packet should not force quantitative anchors.
- If a case lacks clear counterevidence, the packet should record that absence rather than fabricating balance.

## Stop Conditions

- Stop before default switch if packet-first fails to retain critical items on the known eggs comparison.
- Stop before default switch if the model refinement stage routinely returns invalid or unsupported packet edits.
- Stop before default switch if runtime/call savings are achieved only by making the memo materially worse.

## Completion Audit

The plan is complete only when a final audit records:

- implemented files and artifacts,
- pre-refinement and post-refinement `packet_sufficiency_report.json`,
- `packet_critique_report.json` and `packet_critique_adjudication_report.json`,
- count of accepted, rejected, and warning-only critique recommendations,
- old path vs packet-first model call counts,
- old path vs packet-first retention comparison,
- packet sufficiency comparison and compression-loss summary,
- memo quality comparison,
- at least one non-egg generalizability run,
- remaining warnings and whether packet-first is default or still experimental.
