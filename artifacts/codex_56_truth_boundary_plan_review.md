## Verdict

The plan has the right diagnosis and several correct architectural moves, but it is not yet production-ready as an executable plan. It largely restates the evaluation’s recommendations without fully resolving how to simplify the existing architecture, migrate current representations, or prove semantic improvement.

Overall production-worthiness: **5/10 — strong design direction, insufficient implementation and validation discipline.**

| Dimension | Rating | Assessment |
|---|---:|---|
| Problem coverage | 7/10 | Covers the two P0 defects and most P1/P2 issues |
| Architectural simplicity | 4/10 | Risks adding another authority and 20-plus artifacts |
| Code/model judgment split | 6/10 | Mostly right, but quantity extraction and dependency semantics need correction |
| Validation quality | 4/10 | Good mutation ideas, but weak baselines and insufficient independent evaluation |
| Execution readiness | 3/10 | Missing migration map, central integration points, removal criteria, and calibrated gates |

## What the plan gets right

The two highest-severity workstreams are justified by current code, not just the saved evaluation.

- Failure lineage is genuinely broken. [`_memo_ready_synthesis_failed()`](/Users/eli/Documents/Experiments/epistemic_case_mapper/src/epistemic_case_mapper/map_briefing_final_outputs.py:343) returns failure only for three recognized statuses after seeing `accepted != true`; an unknown or newly added rejected status therefore continues through repair and presentation. [`build_final_decision_readiness_report()`](/Users/eli/Documents/Experiments/epistemic_case_mapper/src/epistemic_case_mapper/map_briefing_readiness.py:46) receives no synthesis, repair, or polish lineage at all. The saved run demonstrates the result: [synthesis was blocked](</Users/eli/Documents/Experiments/epistemic_case_mapper/artifacts/fresh_eggs_20260718_000324/briefing/memo_ready_synthesis_report.json>), while [final readiness said `decision_ready`](</Users/eli/Documents/Experiments/epistemic_case_mapper/artifacts/fresh_eggs_20260718_000324/briefing/final_decision_readiness_report.json>) and [memo quality scored 100](</Users/eli/Documents/Experiments/epistemic_case_mapper/artifacts/fresh_eggs_20260718_000324/briefing/memo_quality_report.json>). Workstream 1 directly addresses this.

- Immutable result identity is the correct fix for the wrong estimate/CI pairing in [BRIEFING.md](/Users/eli/Documents/Experiments/epistemic_case_mapper/artifacts/fresh_eggs_20260718_000324/briefing/BRIEFING.md:8). Current extraction turns quantities into independent values in [`_quantity_rows_for_claim()`](/Users/eli/Documents/Experiments/epistemic_case_mapper/src/epistemic_case_mapper/map_briefing_quantities.py:436). Even the artifact named `source_quantity_tuples.json` is misleading: [`_quantity_tuples_for_unit()`](/Users/eli/Documents/Experiments/epistemic_case_mapper/src/epistemic_case_mapper/staged_semantic_evidence_units.py:188) creates one “tuple” per loose value, not one estimate–interval–endpoint result. The plan correctly treats this as a data-model defect.

- The evidence-universe diagnosis is also precise. [`ensure_reader_memo_metadata()`](/Users/eli/Documents/Experiments/epistemic_case_mapper/src/epistemic_case_mapper/map_briefing_memo_metadata.py:11) falls back from cited sources to every entry in `source_display_names`. Meanwhile [`_source_titles_for_region()`](/Users/eli/Documents/Experiments/epistemic_case_mapper/src/epistemic_case_mapper/cli_semantic.py:691) returns all case sources, not the region’s required sources. That is exactly how a seven-source active packet produced a twelve-source list.

- Evidence budgeting and simpler section jobs are directionally right. The saved analyst packet considered 15 of 16 groups foreground while still reporting `ready`. Current deterministic budgeting in [`apply_obligation_budget()`](/Users/eli/Documents/Experiments/epistemic_case_mapper/src/epistemic_case_mapper/map_briefing_decision_diagnosticity.py:87) only limits `must_include`; it does not force the analyst to make a genuinely sparse foreground selection.

- The plan correctly rejects deterministic keyword semantics in principle. The evaluation’s examples remain in production code, including [`_typed_fields()` and `_lexically_supported()`](/Users/eli/Documents/Experiments/epistemic_case_mapper/src/epistemic_case_mapper/staged_semantic_evidence_units.py:155), [`_decision_factor()` and `_direction()`](/Users/eli/Documents/Experiments/epistemic_case_mapper/src/epistemic_case_mapper/decision_argument_artifacts.py:578), and role inference in the decision packet. [SUMMARY_OF_FINDINGS.md](/Users/eli/Documents/Experiments/epistemic_case_mapper/artifacts/fresh_eggs_20260718_000324/briefing/SUMMARY_OF_FINDINGS.md:21) shows the resulting polarity errors.

## Major architectural gaps

### 1. `AnalystDecisionContract` risks becoming another packet

The repo already has an object close to the proposed contract: [`AnalystDecisionModel`](/Users/eli/Documents/Experiments/epistemic_case_mapper/src/epistemic_case_mapper/map_briefing_analyst_schemas.py:346). It already contains the direct answer, confidence, evidence groups and dispositions, quantity decisions, source hierarchy, update conditions, decision logic, and argument plan.

That model is currently projected through:

1. [`global_decision_model`](/Users/eli/Documents/Experiments/epistemic_case_mapper/src/epistemic_case_mapper/map_briefing_global_decision_model.py:59)
2. [`decision_writer_packet`](/Users/eli/Documents/Experiments/epistemic_case_mapper/src/epistemic_case_mapper/map_briefing_decision_writer_packet.py:184)
3. `memo_ready_packet`
4. [`canonical_decision_writer_packet`](/Users/eli/Documents/Experiments/epistemic_case_mapper/src/epistemic_case_mapper/map_briefing_canonical_decision_writer_packet.py:43)
5. `reader_synthesis_packet`
6. section packets

The proposed new contract could simply become stage seven. The mitigation at plan line 155—read it first and later demote old fields—is too weak.

A simpler architecture is:

```text
Evidence store
  source spans + evidence units + immutable result tuples + evidence universe
        ↓
AnalystDecisionModel v2
  one model-owned answer, evidence dispositions, weights, counterweights,
  cruxes, scope, actions, and do-not-overstate rules
        ↓
Evidence-bound verifier
        ↓
Deterministic section views → memo writer
        ↓
Append-only lineage/readiness state
```

The existing `AnalystDecisionModel` should be upgraded to v2 and made authoritative. Compatibility objects should be one-way views with explicit removal dates. The production writer should stop reading `global_decision_model`, `balanced_answer_frame`, `argument_spine`, `bluf_contract`, and similar authorities independently.

This matters because the current prompt still calls several structures “controlling” or “primary” simultaneously in [`build_canonical_decision_writer_packet_synthesis_prompt()`](/Users/eli/Documents/Experiments/epistemic_case_mapper/src/epistemic_case_mapper/map_briefing_memo_ready_prompt.py:133).

### 2. The plan assumes the analyst contract itself is trustworthy

The saved [analyst_decision_model.json](</Users/eli/Documents/Experiments/epistemic_case_mapper/artifacts/fresh_eggs_20260718_000324/briefing/analyst_decision_model.json>) already contains unsupported or overstated judgments such as “safety ceiling” and an invented LDL monitoring recommendation. Making that artifact authoritative would faithfully propagate bad judgment.

The architectural evaluation explicitly recommends testing “compact contract plus verifier.” The plan omits a distinct contract-verification stage.

Add an evidence-bound verifier that evaluates:

- Each primary evidence move against cited evidence-unit and result-tuple IDs.
- Each action recommendation against a source-backed action or guidance claim.
- Causal language against evidence design.
- Counterweight disposition against its cited evidence.
- Scope and confidence against omissions and unresolved dependency judgments.
- New semantic claims not represented in the evidence store.

For production, verifier rejection should block the contract before writing. A downstream memo QA pass is too late.

### 3. Quantity ownership is phrased incorrectly

“Deterministic code owns exact quantity tuples” is only partly right.

A model or human must extract the semantic tuple from prose or tables: population, comparator, endpoint, estimate type, and time horizon require interpretation. Deterministic code should own:

- Immutable identity after extraction.
- Schema and allowed-field validation.
- Exact quote/span verification.
- Prevention of cross-tuple recombination.
- Stable propagation and citation.
- Detection of mutations or detached fields.

The existing whole-document model already extracts structured quantity objects through [`source_card_json_schema()`](/Users/eli/Documents/Experiments/epistemic_case_mapper/src/epistemic_case_mapper/staged_semantic_whole_doc.py:255), but that schema permits independent quantity values. The plan should explicitly replace that schema with result-level objects and migrate or delete the existing `source_quantity_tuples` representation. Creating a parallel `result_tuples.json` would leave two competing meanings of “tuple.”

Tuple IDs should also be content/source-anchor stable, not ordinal IDs like `qt001` or `..._q001`, which change under reordering.

### 4. Evidence-universe provenance is missing from the briefing interface

The staged mapper knows `region_id`, required sources, selected chunks, and omitted chunks. That information is recorded in the map run summary, but [`run_map_briefing()`](/Users/eli/Documents/Experiments/epistemic_case_mapper/src/epistemic_case_mapper/map_briefing_pipeline.py:81) receives only the map, question, and source lookup dictionaries.

The plan needs an input-contract change:

- Pass `region_id`, full-case/worked-region status, required sources, analyzed sources, omitted sources and reasons, and permitted generalization into `run_map_briefing`.
- Do not reconstruct this later from source labels or the final memo.
- Build the final source list from stable citation IDs before display-name replacement.
- Separately report “analyzed sources” and “cited sources”; otherwise a writer can appear correct simply by dropping citations.

The existing human-authored [source independence notes](/Users/eli/Documents/Experiments/epistemic_case_mapper/data/cases/eggs/metadata/source_independence.md:1) are not consumed by the active pipeline. The plan needs to say whether such metadata is authoritative input, model context, or only a hint.

### 5. It does not retire deterministic semantic fallbacks

The non-goal “do not make broad semantic decisions with deterministic keyword logic” does not remove the current ones. The completion audit should name a retirement list and prove the production path no longer calls them.

At minimum, address:

- `_typed_fields`
- `_lexically_supported`
- `_decision_factor`
- `_direction`
- `_decision_role`
- `_finding_signal`
- deterministic quantity memo-use approval

If model semantic judgment is unavailable, production should fail or mark evidence unclassified—not silently substitute those heuristics.

### 6. Two evaluation recommendations disappear

The plan omits:

- Relation-value ablation. The evaluation recommends comparing no graph, current graph, and decision-targeted relations. The current [relation_value_report.json](</Users/eli/Documents/Experiments/epistemic_case_mapper/artifacts/fresh_eggs_20260718_000324/briefing/relation_value_report.json>) calls the graph useful largely from structural properties. The plan should either make relations prove downstream value or remove them from memo obligations.

- Artifact productization and reviewer-effort testing. The evaluation found over 200 top-level artifacts. The plan adds roughly two dozen more named artifacts. That worsens the problem unless diagnostics are nested and the exposed production packet is restricted to memo, analyst contract, evidence/trace appendix, readiness status, run manifest, and human-review form.

## Validation would not yet prove improvement

The mutation and fault-injection proposals are good, but the all-up criteria remain vulnerable to artifact churn.

Specific weaknesses:

- The plan schedules the current-HEAD replay after implementation. The evaluation explicitly says the saved memo predates two relevant commits. A current-HEAD replay must be **phase zero**, before changes, with commit SHA, model/backend, prompt versions, input hashes, and run configuration frozen.

- “Improves or at least does not regress” is too weak after a large rewrite. No change could satisfy it.

- “One unrelated case passes hard invariants” proves generality of schema checks, not improved decision memos.

- Fixed foreground counts such as 3–5 support items should be telemetry, not success criteria. Cases vary, and count compliance can be gamed.

- “Known flawed memos trigger warnings” needs clean controls and false-positive measurement. Otherwise a QA model can flag everything.

- The plan lacks blinded contract ablation, even though the evaluation proposes comparing current stack, compact contract, and compact contract plus verifier.

A stronger release gate would require:

- All injected tuple, source-universe, polarity, status, and endpoint mutations caught.
- Clean controls do not trigger the corresponding fatal defect.
- Zero known critical factual errors on the frozen corpus.
- Blinded human pairwise review on eggs plus LHC and COVID—or similarly different cases—shows a material preference on factual correctness, calibration, counterweight handling, and decision usefulness.
- Reviewer time to locate the strongest counterweight, unresolved crux, source universe, and quantity binding improves.
- Model calls, prompt size, latency, and exposed artifact count decrease or have an explicit justified budget.
- No production writer dependency on legacy semantic authorities.
- Human review status remains explicit; model QA does not count as human validation.

## Recommended execution revision

1. Freeze and replay current HEAD before implementation.
2. Patch fail-closed status propagation and source-list fallback as isolated P0 fixes.
3. Replace the existing loose `source_quantity_tuples` schema with result-level records; do not add a parallel schema.
4. Upgrade `AnalystDecisionModel` to the canonical v2 contract and add the evidence-bound verifier.
5. Run the current-stack vs compact-contract vs contract-plus-verifier ablation.
6. Only if the compact path wins, remove legacy authority projections and deterministic semantic fallbacks.
7. Add evidence-universe propagation from CLI/map-run context.
8. Calibrate evidence budgeting and section synthesis.
9. Run relation-value and reviewer-effort ablations.
10. Promote semantic gates only after multi-case calibration; keep noisy checks report-only.
11. Ship a compact review packet and archive internal stage diagnostics separately.

One execution detail also needs correction: the plan names `map_briefing_analyst_decision_model.py`, which does not exist. The live implementation is centered on [`map_briefing_analyst_decision_modeling.py`](/Users/eli/Documents/Experiments/epistemic_case_mapper/src/epistemic_case_mapper/map_briefing_analyst_decision_modeling.py:56), with orchestration in [`map_briefing_decision_packet_stage.py`](/Users/eli/Documents/Experiments/epistemic_case_mapper/src/epistemic_case_mapper/map_briefing_decision_packet_stage.py:132). The latter, plus `cli_semantic.py`, should be explicit owned integration points.

In short: the plan identifies the right truth boundaries, but it needs to become a replacement-and-ablation plan rather than another layer-building plan. No files were changed and no human source review was performed.