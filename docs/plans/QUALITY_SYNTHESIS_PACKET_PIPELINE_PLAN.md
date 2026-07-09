# Plan: Quality Synthesis Packet Pipeline

## Objective

Make the briefing pipeline produce a high-quality model-facing synthesis packet before memo generation. The final memo should be a rendering of a clean argument packet, not a draft rescued by late repair.

Target architecture:

```text
claim map -> conservative evidence clusters -> role assignment -> quantity binding -> answer spine construction -> quality synthesis packet -> memo synthesis -> retention audit -> paragraph repair if needed -> final polish -> deterministic sources/metadata -> diagnostics
```

The central artifact is `memo_ready_packet.json`.

## Current Gap

The current packet-first path still mixes several memo-generation architectures:

- deterministic packet-first draft rendering;
- whole-memo polish before evidence repair;
- reader-packet retention repair;
- internal packet retention repair;
- deterministic source and metadata repair;
- JSON exact-edit editorial pass;
- legacy section concepts such as `Why This Read`, `Evidence Carrying the Conclusion`, `Practical Read`, and `Practical Scope and Exceptions`.

This ordering creates patched prose. The whole-memo polish can make a coherent memo, but later repair passes reinsert missing evidence and quantities after the coherence pass has already happened. The result can be more complete while reading worse.

## Core Shift

Old default:

```text
map -> draft memo -> polish -> repair dropped evidence -> final memo
```

New default:

```text
claim map -> conservative clusters -> evidence roles -> quantity bindings -> answer spine -> memo-ready synthesis packet -> memo synthesis -> retention audit -> targeted paragraph repair -> final polish -> deterministic source metadata -> diagnostics
```

The model should receive reader-ready evidence and an argument spine, not raw missing-term ledgers or legacy section drafts.

The hardest part of the pipeline is the transformation from a messy claim map into a reliable model-facing packet. A claim map is not naturally packet-shaped: it contains fragments, overlap, source-specific claims, weak claims, quantities detached from their interpretation, and relation edges whose semantics may be sparse or noisy. This plan therefore treats packet assembly as a core inference stage with its own artifacts, audits, and failure modes.

## Non-Goals

- Do not change claim extraction or relation construction in this plan.
- Do not tune the pipeline for the eggs case specifically.
- Do not require a stronger model backend for the design to work.
- Do not remove useful diagnostics until replacement diagnostics exist and are verified.
- Do not make heuristic quality gates blocking before their signal is calibrated.
- Do not preserve legacy section headings in the default memo path unless explicitly configured.

## Design Principles

- Deterministic code owns structure, stable IDs, source metadata, source URLs, quantitative normalization, deduplication, and validation.
- LLMs own semantic synthesis, salience judgment where deterministic ranking is insufficient, paragraph repair, and final prose polish.
- Classical/statistical methods can rank, cluster, dedupe, and detect repetition or near-duplicate evidence.
- Relations are useful signals for assembly, not authoritative instructions; weak relation maps must not silently determine the packet.
- Repairs should operate on memo-ready evidence items, not raw missing-term fragments.
- Final polish must happen after retention repair, not before it.
- Legacy generation paths should be isolated behind compatibility adapters or removed from the default path.

## Related Literature Strategies To Use

This pipeline should explicitly borrow from adjacent fields that solve similar evidence-to-decision problems.

### Evidence Synthesis / GRADE

Borrow the idea of evidence profiles and evidence-to-decision tables. Packet items should not only state claims; they should expose certainty and applicability factors.

Implementation implications:

- Add `evidence_profile` fields to packet items.
- Track directness, consistency, precision, applicability, and study/evidence quality when recoverable.
- Group evidence by decision-relevant outcome before writing recommendations or bottom-line claims.
- Make the answer spine name which evidence profiles actually drive the conclusion.

### Structured Intelligence Analysis / ACH

Borrow diagnosticity: evidence should be promoted when it distinguishes live answer hypotheses, not merely because it supports the likely answer.

Implementation implications:

- Generate candidate answer hypotheses before final packet assembly.
- Score each evidence cluster for support, contradiction, boundary-setting, and diagnosticity across those hypotheses.
- Promote high-diagnosticity counterevidence and cruxes even when they are not the most frequent claims.
- Add sensitivity notes for claims that would change the answer if wrong.

### Toulmin And Argument Mining

Borrow explicit argument components: claim, grounds, warrant, qualifier, backing, rebuttal, stance, and attack/support relations.

Implementation implications:

- Add `warrant`, `qualifier`, `rebuttal`, and `backing` fields where the map supports them.
- Split role assignment into component type and stance toward the answer.
- Generate cruxes from weak warrants, rebuttals, and conflicting stance assignments.
- Treat low-confidence argument relations as adjudication candidates rather than packet facts.

### Entity Resolution / Record Linkage

Borrow blocking, candidate-pair generation, conservative clustering, and false-merge accounting.

Implementation implications:

- Build blocking keys from source, outcome, population, comparator, quantity type, and evidence family before clustering.
- Cluster only within compatible blocks unless a model adjudication explicitly approves a cross-block merge.
- Record merge risk and kept-separate reasons for near duplicates.
- Track over-merge risk separately from duplicate-retention risk.

### Natural Language Generation / Data-To-Text

Borrow the separation between content determination, document structuring, microplanning, and surface realization.

Implementation implications:

- Treat packet assembly as content determination.
- Treat the answer spine as document structuring.
- Treat quantity formatting and source-label choices as microplanning.
- Treat memo synthesis and final polish as surface realization.
- Do not let final polish decide content.

### Provenance Models

Borrow explicit derivation records from provenance systems.

Implementation implications:

- Every packet item should record source entities, input claims, assembly activity, transformations, and confidence.
- Retention should check packet-item lineage rather than text overlap alone.
- Final diagnostics should identify which transformation stage introduced any weak or unsafe memo content.

## Packet Assembly Requirements

Before `memo_ready_packet.json` is built, the pipeline must produce an assembly layer that converts the claim map into candidate evidence groups.

### Conservative Evidence Clusters

- Cluster related claims using embeddings/classical similarity plus source and quantity metadata.
- Use entity-resolution-style blocking keys before clustering: source, outcome, population, comparator, intervention/exposure, quantity type, and evidence family.
- Preserve distinctions that matter for decision quality: population, outcome, comparator, intervention/exposure, dose, time horizon, adjustment model, evidence family, and source.
- Prefer under-consolidation over over-consolidation when a distinction could change the answer.
- Emit explicit reasons for every merge and every kept-separate near duplicate.
- Track false-merge risk and duplicate-retention risk separately.

### Role Assignment

Each cluster or item receives a decision role from a constrained set:

- `strongest_support`
- `strongest_counterweight`
- `quantitative_anchor`
- `scope_boundary`
- `mechanism_or_explanation`
- `decision_crux`
- `context_only`
- `uncertain_role`

Role assignment should combine deterministic signals and model judgment:

- deterministic code proposes candidate roles from claim metadata, relation types, source family, quantities, and directionality;
- the model adjudicates ambiguous roles with short rationales;
- deterministic checks reject or flag role assignments that contradict the answer spine.
- argument-mining labels are recorded separately from memo roles: component type, stance toward candidate answers, relation confidence, and attack/support/boundary relation.
- low-confidence relation labels are routed to adjudication or marked `uncertain_role`.

### Competing Answer Hypotheses And Diagnosticity

Before promoting evidence into the packet, the assembly layer should construct a small set of live answer hypotheses.

Examples of hypothesis shapes:

- option A is favored;
- option B is favored;
- neutral or underdetermined;
- answer applies only inside a named scope boundary;
- answer depends on a specific unresolved crux.

Each evidence cluster should be scored for:

- support for each hypothesis;
- contradiction of each hypothesis;
- boundary-setting value;
- diagnosticity: how much it distinguishes between live hypotheses;
- sensitivity: whether the answer would change if this evidence were wrong or downgraded.

High-diagnosticity evidence should be eligible for promotion even if it is not central by frequency, centrality, or source count.

### Quantity Binding

Quantities must be bound to the claim they qualify before synthesis:

- estimate;
- interval or uncertainty range;
- outcome;
- exposure/intervention/comparator;
- population or subgroup;
- time horizon when present;
- adjustment or model caveat when present;
- source label;
- interpretation in decision terms.

Unbound quantities remain diagnostic-only and should not be surfaced in the memo-ready packet as mandatory prose.

### Evidence Profiles

Each assembled evidence item should carry a lightweight evidence profile when inputs support it:

- evidence family or study type;
- quality or risk signal if available;
- directness to the decision question;
- consistency with other evidence;
- precision or uncertainty;
- applicability to the target population/scope;
- primary downgrade or caution reason.

The answer spine should use these profiles to avoid overconfident synthesis.

### Warrants, Qualifiers, Rebuttals, And Backing

Each item promoted beyond `context_only` should include argument fields where possible:

- `grounds`: the source-backed evidence claim;
- `warrant`: why this evidence bears on the decision question;
- `qualifier`: how strongly or narrowly it applies;
- `backing`: source or methodological support for the warrant;
- `rebuttal`: evidence or conditions that weaken the item.

Cruxes should be generated from weak warrants, important rebuttals, and conflicts between high-diagnosticity evidence items.

### Provenance Lineage

Every assembled item must preserve:

- `derived_from_claim_ids`;
- `derived_from_relation_ids` when relation edges are used;
- `derived_from_source_ids`;
- `assembly_activity`;
- `transformations_applied`;
- `assembly_confidence`;
- `lineage_warnings`.

This lineage becomes the source of truth for retention, repair, and final diagnostics.

### Assembly Audit

The assembly stage must emit:

- `packet_assembly_clusters.json`
- `packet_role_assignment_report.json`
- `diagnosticity_matrix.json`
- `quantity_binding_report.json`
- `evidence_profile_report.json`
- `packet_assembly_audit.json`

The audit must include:

- dropped claims and why;
- merged claims and why;
- kept-separate near duplicates and why;
- uncertain role assignments;
- quantities that could not be safely bound;
- relation edges used as signals;
- relation edges ignored because they were weak, ambiguous, or irrelevant;
- evidence profile downgrades;
- high-diagnosticity evidence promoted into the packet;
- low-diagnosticity evidence demoted to context-only;
- provenance warnings;
- evidence clusters that need model or human review.

## Memo-Ready Packet Requirements

`memo_ready_packet.json` must be built from the assembly layer and contain enough structured context for a model to write a decision-ready memo without reverse-engineering the map.

### Decision Frame

- Exact decision question.
- Decision type if inferable, such as belief update, policy choice, practical recommendation, or comparative option choice.
- Intended scope.
- What would count as a useful answer.

### Answer Spine

- `default_read`: likely answer.
- `confidence`: calibrated confidence.
- `why_this_read`: short reasoning path.
- `why_not_stronger`: main uncertainty or limitation.
- `what_would_change_this`: evidence that would update the answer.
- `scope_boundary`: where the answer applies and where it should not be used.
- `live_alternatives_considered`: competing hypotheses considered during assembly.
- `decisive_evidence`: high-diagnosticity items driving the answer.
- `sensitivity_notes`: which assumptions or evidence downgrades would change the answer.

### Evidence Groups

Each evidence item must have a clear role:

- `strongest_support`
- `strongest_counterweight`
- `quantitative_anchor`
- `scope_boundary`
- `mechanism_or_explanation`
- `decision_crux`
- `context_only`

### Evidence Item Schema

Each model-facing evidence item should be reader-ready:

```json
{
  "item_id": "stable id",
  "role": "quantitative_anchor",
  "reader_claim": "Total egg intake, including eggs in baked goods, was not associated with higher cardiovascular disease risk.",
  "source_label": "Drouin-Chartier et al. 2020",
  "quantities": [
    {
      "estimate": "0.97",
      "interval": "95% CI 0.93 to 1.03",
      "direction": "near null",
      "interpretation": "does not support a clear harmful association"
    }
  ],
  "decision_relevance": "Supports treating moderate egg consumption as neutral rather than meaningfully harmful.",
  "diagnosticity": "distinguishes neutral_or_low_concern from meaningfully_harmful",
  "evidence_profile": {
    "directness": "direct outcome evidence",
    "precision": "confidence interval crosses or approaches decision-relevant null threshold",
    "applicability": "generally healthy adult population"
  },
  "argument": {
    "warrant": "If total intake is near-null for CVD risk, moderate egg intake should not be treated as meaningfully harmful on CVD grounds alone.",
    "qualifier": "Applies only within the studied population and intake range.",
    "rebuttal": "Subgroups or very high intake may differ."
  },
  "lineage": {
    "derived_from_claim_ids": ["claim_..."],
    "derived_from_source_ids": ["source_..."],
    "assembly_activity": "quantity_binding_and_role_assignment"
  },
  "caveat": "Observational evidence; subgroup and diet-pattern confounding still matter.",
  "must_use": true
}
```

Raw missing-term fragments should remain diagnostic-only and should not be fed to the synthesis model as prose obligations.

## Workstreams

### 1. Build Claim-Map-To-Packet Assembly

Purpose: transform the claim map into reliable candidate evidence groups before memo-ready packet creation.

Changes:

- Add a conservative clustering stage over prioritized claims.
- Add entity-resolution-style blocking before clustering.
- Use embeddings/classical similarity to identify candidate duplicates and related claims.
- Preserve decision-relevant distinctions across population, outcome, comparator, quantity, source, and evidence family.
- Use relation edges as weighted signals rather than hard routing rules.
- Generate live answer hypotheses and a diagnosticity matrix before final role promotion.
- Add a model-assisted role adjudication pass for ambiguous clusters.
- Add deterministic role-consistency checks against the decision question and draft answer spine.
- Add quantity binding that links estimates and intervals to exact claims, outcomes, sources, and caveats.
- Add lightweight evidence profiles for directness, consistency, precision, applicability, and quality where recoverable.
- Add argument fields: grounds, warrant, qualifier, backing, and rebuttal.
- Add provenance lineage for each assembled item.

Artifacts:

- `packet_assembly_clusters.json`
- `packet_role_assignment_report.json`
- `diagnosticity_matrix.json`
- `quantity_binding_report.json`
- `evidence_profile_report.json`
- `packet_assembly_audit.json`

Validation:

- Every memo-ready evidence item has lineage back to one or more accepted claims.
- Merged claims do not cross population, outcome, comparator, or source distinctions unless the audit records why the merge is safe.
- Role assignments include rationale and confidence.
- Ambiguous role assignments are surfaced as `uncertain_role`, not silently forced.
- Quantities without safe claim binding are excluded from mandatory memo obligations and reported.
- High-diagnosticity counterevidence cannot be dropped merely because it is not frequent or central.
- Evidence profiles are allowed to be incomplete, but missing profile dimensions are reported.
- Warrant and qualifier fields are present for every mandatory evidence item, or the item is flagged.

### 2. Build `memo_ready_packet`

Purpose: create the central model-facing packet from the internal decision packet.

Changes:

- Add a packet builder that projects the assembly layer into `memo_ready_packet`.
- Preserve stable IDs for every item.
- Deduplicate overlapping obligations before synthesis.
- Normalize source labels and source URLs.
- Convert quantities into structured reader-ready fields.
- Produce reader-ready evidence claims and decision relevance statements.
- Carry forward diagnosticity, evidence profile, argument, and provenance fields.

Artifacts:

- `memo_ready_packet.json`
- `memo_ready_packet_quality_report.json`

Validation:

- No raw claim IDs, bundle IDs, source IDs, or validation language appear in reader-facing fields.
- Every mandatory quantitative item has a reader claim, source label, quantity fields, interpretation, and decision relevance.
- Every mandatory item remains traceable to internal packet IDs.
- Every evidence role is inherited from or justified by the assembly stage.
- Every mandatory item has a warrant or explicit warning that the warrant is weak/missing.
- The answer spine identifies live alternatives considered and why the default read survived.

### 3. Add Packet Quality Gates

Purpose: make packet quality visible before memo synthesis.

Checks:

- Missing answer spine.
- Missing strongest counterweight.
- Missing or weak assembly audit.
- Too many `uncertain_role` items promoted into mandatory evidence.
- Missing competing answer hypotheses or diagnosticity matrix.
- Answer spine not supported by diagnostic evidence.
- Quantity without interpretation.
- Quantity without safe binding.
- Evidence item without decision relevance.
- Mandatory item without warrant or qualifier.
- Evidence profile missing for a load-bearing item.
- Provenance lineage missing.
- Duplicate or near-duplicate evidence items.
- Missing source label.
- Unsupported reader claim not traceable to source item.
- Too many context-only items.
- Evidence groups too large for the model to use coherently.
- Answer spine not supported by the assembled evidence roles.

Artifact:

- `memo_ready_packet_quality_report.json`

Validation:

- Gates are report-only initially.
- Quality report identifies concrete item IDs and suggested fixes.
- Report distinguishes packet-quality problems from map-quality problems.
- Report distinguishes assembly failures from synthesis failures.

### 4. Replace Draft-First Synthesis

Purpose: stop using deterministic packet-first memo rendering as the main synthesis source.

Changes:

- Replace `render_packet_first_draft` as the default memo source.
- First memo-producing model call receives only `memo_ready_packet`.
- Prompt asks for natural markdown, direct answer, source labels, key quantities, cruxes, and scope boundaries.
- Prompt forbids internal packet language and legacy section names.

Artifacts:

- `memo_synthesis_prompt.txt`
- `memo_synthesis_raw.md`
- `memo_synthesis_report.json`

Validation:

- Memo includes the exact decision question.
- Memo has a clear answer, support, counterweight, cruxes, and scope.
- Memo contains source labels in evidence paragraphs.
- Memo does not contain internal IDs, packet schema terms, or legacy section names.
- Memo reflects the answer spine's live alternatives, decisive evidence, and sensitivity notes without naming internal machinery.

### 5. Unify Retention Around The Packet

Purpose: replace separate reader/internal retention audits with one audit against `memo_ready_packet`.

Retention checks:

- Mandatory evidence item represented.
- Mandatory quantity represented with interpretation.
- Source label present.
- Answer spine preserved.
- High-diagnosticity counterevidence represented.
- Warrants and qualifiers represented for load-bearing evidence.
- Scope boundary preserved.
- Strongest counterweight not erased.
- Cruxes represented as decision-relevant uncertainties, not generic questions.

Artifact:

- `memo_packet_retention_report.json`

Validation:

- Missing evidence reports stable packet item IDs.
- Quantity misses identify whether the problem is missing estimate, interval, interpretation, source, or decision relevance.
- Audit treats acceptable paraphrase differently from true omission.

### 6. Repair Paragraphs, Not Missing Terms

Purpose: make repair improve completeness without creating patched prose.

Changes:

- Replace the dual `reader_packet_repair` and `packet_repair` default stack with one memo-ready repair pass.
- Build a targeted repair packet from `memo_ready_packet`.
- Repair prompt asks the model to rewrite the affected paragraph or section naturally.
- Repair may rewrite containing paragraphs, not just append clauses.
- Repair must preserve protected source labels, quantities, and answer stance.

Artifacts:

- `memo_repair_packet.json`
- `memo_repair_prompt.txt`
- `memo_repair_raw.md`
- `memo_repair_report.json`

Validation:

- Repair improves retention without source drift.
- Repair cannot append orphan numbers without interpretation.
- Repair cannot reintroduce legacy section headings.
- Repair cannot add evidence outside the repair packet.

### 7. Final Polish After Repair

Purpose: restore coherence after evidence completeness is handled.

Changes:

- Run whole-memo polish after targeted repair.
- Final polish receives repaired memo plus protected evidence ledger from `memo_ready_packet`.
- Remove or demote the JSON exact-edit editorial pass from the default path.
- Final source section is added or normalized deterministically after polish.

Artifacts:

- `final_polish_prompt.txt`
- `final_polish_raw.md`
- `final_polish_report.json`

Validation:

- Final polish does not reduce critical retention.
- Final polish improves or preserves coherence metrics.
- Final polish does not alter the decision question, source labels, source URLs, or protected quantities.
- Final memo remains free of internal machinery language.

### 8. Remove Legacy Default Path

Purpose: prevent mixed memo architectures.

Changes:

- Retire deterministic packet-first draft as the default memo source.
- Retire dual repair stack from the default path.
- Retire JSON exact-edit editorial pass from the default path.
- Isolate legacy section machinery behind explicit compatibility adapters or delete it after dependency checks.
- Replace section-role validators with frame-neutral checks: bottom line, support, counterweight, cruxes, scope, and source grounding.

Artifacts:

- Updated `pipeline_migration_ledger.json`
- Updated runtime/stage value telemetry

Validation:

- Default final memo does not contain `Why This Read`, `Evidence Carrying the Conclusion`, `Practical Scope and Exceptions`, or `Practical Read`.
- Tests prove old compatibility paths are either unused or explicitly opted into.

### 9. Telemetry And Comparison

Purpose: prove the pipeline simplification improves output quality.

Telemetry:

- Assembly cluster count, merge count, and uncertain-role count.
- Safe quantity binding rate.
- Role assignment confidence distribution.
- Diagnosticity coverage: high-diagnosticity items represented in packet and memo.
- Evidence profile completeness for mandatory items.
- Warrant/qualifier coverage for mandatory items.
- Provenance lineage completeness.
- Critical retention.
- Source lineage.
- Quantitative rendering quality.
- Repetition and near-duplicate sentence rate.
- Final memo coherence.
- Late model call count.
- Packet quality warnings.
- Repair impact before and after final polish.

Artifacts:

- `pipeline_simplification_comparison.json`
- Updated `runtime_budget_report.json`
- Updated `stage_value_report.json`

Validation:

- Fair eggs-question synthesis improves readability without worse retention.
- At least one non-eggs case runs without domain-specific assumptions.
- Comparison identifies remaining gaps rather than declaring success from tests alone.

## Minimal Viable Packet Assembly Slice

The first implementation pass should not attempt the full architecture at once. It should build a narrow vertical slice that proves whether better packet assembly improves memo quality.

### Slice Goal

Given an existing generated claim map and decision question, produce a compact `memo_ready_packet.json` that improves synthesis quality compared with the current packet-first memo path.

### Included In The First Slice

1. Conservative clustering with blocking keys:
   - source;
   - outcome or object of claim;
   - population/scope;
   - comparator or alternative;
   - quantity type;
   - evidence family.

2. Quantity binding:
   - bind estimates and intervals to claim, source, outcome, and caveat when recoverable;
   - exclude unbound quantities from mandatory memo obligations;
   - report unbound quantities.

3. Role assignment:
   - support;
   - counterweight;
   - scope boundary;
   - decision crux;
   - context only;
   - uncertain role.

4. Diagnosticity-lite:
   - generate two to four live answer hypotheses;
   - score whether each cluster supports, weakens, bounds, or distinguishes each hypothesis;
   - promote high-diagnosticity counterevidence and cruxes.

5. Compact packet projection:
   - answer spine;
   - top support items;
   - top counterweights;
   - top quantitative anchors;
   - top scope boundaries;
   - top cruxes;
   - source trail.

6. Synthesis-only comparison:
   - run the new packet synthesis against the fair eggs question;
   - compare against current pipeline memo and direct-source baseline;
   - run one non-eggs case to check generality.

### Deferred From The First Slice

- Full GRADE-style certainty scoring.
- Full argument-mining relation taxonomy.
- Full provenance ontology modeling.
- Blocking/merge optimization beyond conservative heuristics.
- Blocking quality thresholds promoted to hard gates.
- Deleting legacy code.

Deferred items must remain in the plan, but the first slice should produce a working end-to-end packet and memo before broad cleanup.

### Slice Acceptance Criteria

- `packet_assembly_clusters.json`, `quantity_binding_report.json`, `diagnosticity_matrix.json`, and `memo_ready_packet.json` are produced from an existing map.
- At least 90% of mandatory packet items have source labels and claim lineage.
- At least 80% of mandatory quantitative anchors have a bound claim, source, outcome/comparison, and interpretation.
- No `uncertain_role` item is promoted to mandatory evidence without an explicit warning.
- The packet has no more than 18 mandatory model-facing evidence items unless the question is explicitly marked as requiring a long brief.
- The fair eggs memo preserves at least the current `20/28` critical retention baseline while reading no worse on manual review.
- The non-eggs memo completes without domain-specific vocabulary, hardcoded health categories, or legacy section headings.

## Execution Order

1. Inventory current packet, synthesis, repair, polish, and legacy section dependencies.
2. Implement the minimal viable packet assembly slice without changing the default path.
3. Run synthesis-only comparisons on eggs and one non-eggs case.
4. Use slice telemetry to decide which assembly failures most affect memo quality.
5. Add evidence profiles and warrant/qualifier/rebuttal fields for load-bearing items.
6. Add provenance lineage fields and lineage completeness checks.
7. Add packet quality report in report-only mode.
8. Add unified memo-ready retention audit.
9. Add targeted paragraph repair from `memo_repair_packet`.
10. Move final polish after repair and protect packet obligations through the polish pass.
11. Switch the default path to the new packet-first synthesis path only after the slice beats or matches current retention and improves readability.
12. Retire or isolate legacy default generation, repair, and editorial paths.
13. Run final fair eggs comparison and one non-eggs generalization run.

## Acceptance Criteria

- `memo_ready_packet.json` is the central synthesis artifact.
- Packet assembly artifacts exist and explain how claims became packet items.
- Role assignments and quantity bindings are inspectable before synthesis.
- Diagnosticity matrix exists and shows which evidence distinguishes live answer hypotheses.
- Load-bearing evidence items include evidence profiles, warrants, qualifiers, and provenance lineage or explicit warnings.
- Minimal viable packet assembly slice passes its acceptance criteria before legacy cleanup begins.
- The model receives reader-ready evidence, not raw term ledgers.
- Final memo contains a clear answer, support, counterweight, cruxes, and scope.
- Quantities are interpreted, not dumped.
- Repair rewrites coherent paragraphs rather than patching clauses.
- Final polish happens after repair.
- Final source section is deterministic.
- Eggs fair-question critical retention is no worse than the current `20/28`.
- Eggs fair-question source lineage remains at least `7/7` matched packet sources.
- Final memo no longer contains stale legacy sections.
- Verification passes:

```bash
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 scripts/maintainability_gate.py
```

- A synthesis-only eggs run and one non-eggs run complete with inspectable comparison artifacts.

## Red-Team Checks

- Does `memo_ready_packet` become a disguised deterministic memo?
- Does assembly silently over-merge claims that should stay separate?
- Does role assignment mislabel counterevidence as support?
- Does a weak relation map poison the packet by routing evidence incorrectly?
- Are unbound quantities being forced into mandatory memo obligations?
- Are high-diagnosticity counterarguments demoted because they are rare?
- Are warrants being invented beyond the evidence rather than derived from source-backed claims?
- Are evidence profiles creating false precision when quality signals are absent?
- Does provenance lineage exist but fail to catch a bad transformation?
- Does the packet over-constrain the model into checklist prose?
- Does final polish drop quantities after repair?
- Does retention reward exact-term stuffing over readable interpretation?
- Does source metadata become over-inclusive again?
- Does deleting legacy paths remove useful diagnostics?
- Does the pipeline only work on health or nutrition questions?
- Does the repair step make the memo longer without improving decision usefulness?

## Generalizability Checks

- Run on the eggs fair question and at least one unrelated case.
- Confirm packet roles are decision-generic.
- Confirm no domain vocabulary is hardcoded in packet creation or prompts.
- Confirm prompts refer to the decision question and evidence packet, not FLF, eggs, diet, CVD, or case-specific labels.
- Confirm quantitative rendering works for different quantity types, including rates, confidence intervals, proportions, durations, costs, and counts.
- Confirm assembly preserves meaningful distinctions across population, outcome, comparator, time horizon, and source in non-eggs cases.
- Confirm diagnosticity works for non-health questions where evidence is qualitative, legal, operational, or historical.
- Confirm evidence profiles degrade gracefully when formal study-quality metadata is unavailable.

## Completion Audit

The plan is complete only when a final review packet records:

- before/after memo paths;
- before/after retention metrics;
- source-lineage metrics;
- assembly audit summary;
- role-assignment and quantity-binding summaries;
- diagnosticity matrix summary;
- evidence profile and warrant coverage;
- provenance lineage completeness;
- packet-quality report;
- runtime/model-call comparison;
- manual memo-quality read;
- remaining known weaknesses;
- any intentionally retained legacy compatibility paths and why they remain.
