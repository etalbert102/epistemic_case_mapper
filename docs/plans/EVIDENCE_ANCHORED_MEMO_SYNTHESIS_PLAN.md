# Plan: Evidence-Anchored Natural Memo Synthesis

## Objective

Make the memo synthesis path produce natural decision-grade prose while preserving a machine-checkable trace from reader-facing claims back to evidence items, quantities, source IDs, scope limits, and caveats.

The target is not another broad prose-polish pass. The target is a synthesis contract where the model can write fluently, and deterministic code can verify that evidence survived and that unsupported claims did not enter the memo.

## Current Gap

The current memo-ready path has stronger packet construction, section-local markdown notes, source binding, deterministic source lists, retention checks, and higher output budgets. The remaining gap is that prose quality and evidence retention are still coupled inside the same generation task:

- If prompts emphasize retention too strongly, the memo reads repetitive and citation-heavy.
- If prompts emphasize prose quality too strongly, the model may omit, weaken, or distort evidence.
- Current checks mostly catch omissions and source-binding problems; they are weaker at detecting distortion, unsupported memo claims, and semantic drift.
- The model is still asked to manage prose, section role, source IDs, quantities, caveats, and traceability at once.

## Non-Goals

- Do not add source collection or retrieval.
- Do not restore legacy packet-first, section-rewrite, or deterministic fallback paths that were removed.
- Do not make deterministic code decide semantic truth.
- Do not force fixed evidence sentences into the memo unless experiments show it improves readability.
- Do not make broad auditor calls blocking until their signal is calibrated.

## Design Principles

- Stable IDs over text matching: use evidence IDs and source IDs as the trace layer.
- Semantic slots over exact wording: validate direction, quantity, population, source, and caveat survival rather than literal phrases.
- Model judgment where it is useful: synthesis, semantic equivalence, and targeted repair.
- Deterministic code where it is reliable: IDs, rendering, source lists, coverage accounting, schema validation, and trace artifacts.
- Bidirectional reconciliation: check evidence-to-memo omissions and memo-to-evidence unsupported claims.
- Report-only before blocking: new semantic checks should first produce telemetry and adversarial-test signal.

## Inventory And Dependency Map

Current anchor points:

- `map_briefing_memo_ready_packet.py`: builds the active memo-ready packet and evidence items.
- `map_briefing_canonical_decision_writer_packet.py`: canonical handoff with evidence roles, source weighting, quantities, obligations, and language contracts.
- `map_briefing_memo_ready_prompt.py`: builds the section synthesis plan.
- `map_briefing_memo_ready_section_notes.py`: renders section-local markdown notes for model synthesis.
- `map_briefing_memo_ready_section_synthesis.py`: runs parallel section calls and validates headings/source IDs.
- `map_briefing_memo_ready_finalization.py`: orchestrates synthesis, retention checks, repair, and polish.
- `map_briefing_memo_ready_presentation.py`: deterministic source rendering, citation trace, and final source list.

Useful existing mechanisms:

- `mandatory_retention_checklist`
- `source_bound_evidence_atoms`
- `quantity_binding_rows`
- `evidence_language_contracts`
- `source_weight_judgments`
- `build_memo_ready_packet_retention_report`
- `build_citation_trace_markdown`
- `high_confidence_unsupported_additions`

The plan should extend these rather than create a parallel synthesis stack.

## Workstreams

### 1. Evidence Expression Contracts

Purpose: define what must survive when an evidence item is expressed in prose.

Changes:

- Add `evidence_expression_contracts` to the canonical or memo-ready packet.
- Derive contracts from existing evidence rows, mandatory obligations, source-bound atoms, quantities, language contracts, and source weighting.
- Use a compact schema:
  - `evidence_id`
  - `source_ids`
  - `required_direction`
  - `required_quantity_atoms`
  - `population_scope`
  - `endpoint_or_measure`
  - `required_caveat`
  - `allowed_compressions`
  - `must_not_imply`
  - `primary_section`

Artifacts:

- `evidence_expression_contracts.json`
- packet quality count: total contracts, required contracts, quantity-bearing contracts, caveat-bearing contracts

Validation:

- Unit tests for contract derivation from existing packet fields.
- Tests where paraphrases pass but direction/scope/quantity changes fail.

QA:

- Golden eggs case.
- Small artificial case with one support item, one counterweight, and one scope caveat.

Risks:

- Contracts become another redundant obligation layer.
- Mitigation: derive from existing objects and keep IDs linked to source evidence, not hand-authored text.

### 2. Evidence-ID Annotated Section Synthesis

Purpose: let the model write natural prose while exposing which evidence each sentence is using.

Changes:

- Update section markdown-note prompts to ask for evidence tags after evidence-bearing sentences, such as `{E:egg_bmj_003}`.
- Keep bracketed source IDs available only as a fallback; evidence IDs become the model-facing trace during drafting.
- Require every load-bearing factual sentence to include at least one known evidence ID.
- Keep section validation for headings, markdown structure, unknown IDs, and obvious malformed tags.

Artifacts:

- section raw markdown with evidence tags
- section report fields: `known_evidence_id_count`, `used_evidence_id_count`, `unknown_evidence_ids`

Validation:

- Unknown evidence IDs fail section validation.
- Evidence tags are accepted only when they refer to known section or packet evidence.
- Source IDs still normalize deterministically at presentation time.

QA:

- Tests where the model emits source citations but no evidence tags should warn, not silently pass.

Risks:

- Tags clutter the model output and hurt prose.
- Mitigation: strip tags deterministically before reader presentation and keep citation rendering separate.

### 3. Deterministic Tag Rendering And Citation Trace

Purpose: produce a clean reader memo while preserving the trace layer.

Changes:

- Strip `{E:...}` tags from the final reader memo.
- Convert evidence tags to source citation references using the evidence contract source IDs.
- Extend `CITATION_TRACE.md` to show:
  - memo sentence or local context
  - evidence IDs used
  - source IDs and source names
  - contract slots used by that sentence

Artifacts:

- clean `BRIEFING.md`
- enriched `CITATION_TRACE.md`
- `memo_evidence_trace.json`

Validation:

- No raw evidence tags appear in final memo.
- Citation trace contains every evidence ID used in section synthesis.
- Deterministic source list remains source-of-truth for final sources.

QA:

- Round-trip test: tagged memo -> rendered memo + trace -> trace includes all tags.

Risks:

- Citation clutter returns if every evidence tag becomes a visible citation.
- Mitigation: group multiple evidence IDs by source citation cluster and keep detailed evidence trace in `CITATION_TRACE.md`.

### 4. Bidirectional Evidence Reconciliation

Purpose: catch omission and hallucination.

Changes:

- Add `memo_evidence_reconciliation_report`.
- Evidence-to-memo check:
  - required contracts have a tagged sentence or accepted compressed expression.
  - required quantities appear near the linked evidence expression.
- Memo-to-evidence check:
  - tagged evidence claims do not violate the linked contract.
  - untagged factual sentences with quantities, comparative language, causal language, or strong recommendations are flagged.

Artifacts:

- `memo_evidence_reconciliation_report.json`
- report fields: missing contract count, unsupported claim count, distortion warning count, untagged factual claim count

Validation:

- Missing evidence is detected.
- Unsupported added claim is detected.
- Quantity attached to wrong population is detected.

QA:

- Adversarial mutation tests:
  - reverse direction of effect
  - move diabetic boundary to healthy adults
  - attach `8.14 mg/dL` to the wrong endpoint
  - add unsupported “heart-healthy” conclusion

Risks:

- Deterministic reconciliation becomes semantic and brittle.
- Mitigation: deterministic code only detects IDs, quantities, source/scope surfaces, and high-risk untagged claims; semantic equivalence stays report-only or model-audited.

### 5. Back-Translation Audit

Purpose: detect distortion that slot checks miss.

Changes:

- Add optional model audit after synthesis:
  - extract factual claims from the memo;
  - map each claim to evidence IDs;
  - judge whether each claim is faithful, weakened, overstated, unsupported, or ambiguous.
- Feed the auditor only the memo, evidence contracts, and trace map, not the full packet.

Artifacts:

- `memo_backtranslation_audit.json`
- auditor prompt/raw output

Validation:

- Fake auditor tests for parser normalization and report statuses.
- Mutation tests with a fake backend showing how distortions route to warnings.

QA:

- Run report-only on saved eggs artifacts and one unrelated case before making any result blocking.

Risks:

- Expensive and noisy model call.
- Mitigation: run only when reconciliation reports high-risk issues, or behind a config flag at first.

### 6. Targeted Adversarial Auditor

Purpose: replace broad critique with a specialist loop.

Changes:

- Add an adversarial audit prompt that asks only for:
  - missing required evidence IDs;
  - weakened evidence;
  - overstated evidence;
  - unsupported claims;
  - source/quantity/scope mismatches.
- Require every issue to include `evidence_id`, `memo_span`, `failed_slot`, `severity`, and `repair_instruction`.

Artifacts:

- `memo_adversarial_audit.json`

Validation:

- Auditor output without evidence IDs is rejected or downgraded.
- Generic writing advice is ignored.

QA:

- Mutation tests where the auditor should catch planted errors.

Risks:

- Adds another broad critique under a new name.
- Mitigation: schema requires concrete evidence IDs and failed slots; no prose-only critique is actionable.

### 7. Targeted Evidence Repair

Purpose: fix factual survival failures without a whole-memo rewrite.

Changes:

- Repair only the affected section or paragraph.
- Repair prompt receives:
  - failed reconciliation/audit rows;
  - relevant evidence contracts;
  - affected section text;
  - adjacent heading context.
- Model returns replacement section with evidence tags.
- Deterministic checks rerun before accepting.

Artifacts:

- `memo_evidence_repair_prompt.txt`
- `memo_evidence_repair_raw.md`
- `memo_evidence_repair_report.json`

Validation:

- Repair cannot delete unrelated required evidence tags.
- Repair must reduce reconciliation failures.
- Repair cannot add unknown evidence IDs.

QA:

- Before/after report must show changed failure counts, not just changed prose.

Risks:

- More model calls for small improvements.
- Mitigation: trigger only on high-priority reconciliation/audit failures.

## Execution Order

0. Run a bounded experiment before production integration.
1. If the experiment shows value, implement evidence expression contracts derived from existing packet data.
2. Add evidence tags to section prompts and section validation in report-only mode.
3. Add deterministic tag stripping, citation rendering, and trace artifacts.
4. Add bidirectional reconciliation report.
5. Run saved-artifact evaluations on eggs and one unrelated case.
6. Add optional back-translation audit only after reconciliation shows clear gaps.
7. Add adversarial auditor and targeted repair only for concrete high-priority failures.
8. Promote high-precision checks to blocking after calibration.

## First Experiment Before Production Integration

Purpose: test whether evidence-anchored prose actually improves memo quality before adding new default pipeline machinery.

Scope:

- Use saved artifacts, not a full end-to-end rerun.
- Use the latest eggs `memo_ready_packet.json`.
- Use one unrelated saved `memo_ready_packet.json` if available.
- Do not change production synthesis defaults during the experiment.

Experiment design:

1. Build an experimental evidence contract view from existing memo-ready packet fields.
   - Inputs: `evidence_items`, `canonical_decision_writer_packet`, `mandatory_retention_checklist`, `source_bound_evidence_atoms`, quantity rows, source IDs, and language contracts.
   - Output: `experimental_evidence_expression_contracts.json`.

2. Render experimental markdown section notes with evidence IDs.
   - Use existing section packets.
   - Add compact evidence contract notes under each section.
   - Ask the model to write normal markdown with `{E:<id>}` tags after evidence-bearing sentences.

3. Run experimental section synthesis.
   - Save raw tagged sections.
   - Save rendered reader memo with tags stripped and source citations normalized.
   - Save trace map from evidence IDs to memo spans.

4. Run lightweight reconciliation.
   - Evidence-to-memo: required evidence IDs are tagged at least once.
   - Quantity survival: required quantities appear in or near tagged spans.
   - Source survival: tagged evidence IDs map to final visible source citations.
   - Memo-to-evidence: flag untagged high-risk factual sentences with quantities, strong comparative claims, or causal/recommendation language.

5. Compare against current production memo.
   - Retention: missing mandatory count, missing quantity count, source-binding warning count.
   - Readability: manual read and simple repetition/citation-density telemetry.
   - Decision usefulness: does the memo answer the question more directly, with less repetition and clearer source weighting?

Promotion criteria:

- Experimental memo is at least as good as current production on deterministic retention and source binding.
- Evidence tags do not visibly leak into the final reader memo.
- Citation density is not worse, or citations become easier to read.
- Manual read shows less repetition or cleaner flow in at least one major section.
- Trace artifact makes it easier to inspect why a source/evidence item was used.
- No new model call is promoted unless it demonstrably fixes a failure the deterministic trace cannot handle.

Stop criteria:

- If tags make the model write noticeably worse prose, stop and keep only the contract/reconciliation lessons.
- If the experimental memo improves traceability but not readability, do not promote synthesis changes; use reconciliation as QA only.
- If the experiment only duplicates existing retention reports, do not add a new production stage.

Experiment artifacts:

- `experimental_evidence_expression_contracts.json`
- `experimental_tagged_section_prompts.txt`
- `experimental_tagged_sections_raw.md`
- `experimental_evidence_trace.json`
- `experimental_rendered_memo.md`
- `experimental_reconciliation_report.json`
- `experimental_comparison_report.json`

Verification commands:

- Targeted tests for experiment helpers.
- Run experiment on saved eggs packet.
- Optionally run experiment on one unrelated saved packet.

## Acceptance Criteria

- `BRIEFING.md` has no raw evidence tags.
- `CITATION_TRACE.md` or `memo_evidence_trace.json` maps reader claims to evidence IDs and source IDs.
- Required evidence contracts show coverage without relying on exact wording.
- Unknown evidence IDs fail validation.
- Unsupported or untagged high-risk memo claims are surfaced.
- Eggs memo remains at zero missing mandatory items and zero source-binding warnings.
- At least one unrelated saved case runs through the same trace/reconciliation path.
- Full tests pass.

## Red-Team Checks

- The model can game tags by tagging unsupported sentences.
  - Detection: memo-to-evidence reconciliation and model audit compare sentence semantics to contract slots.
- The model avoids tags to write fluently.
  - Detection: untagged high-risk factual sentence warnings.
- The pipeline becomes too complex.
  - Detection: new stages do not change the memo or repair decisions on saved artifacts.
- The validator forces ugly prose.
  - Detection: paraphrase tests and manual read of final memo.
- The auditor creates vague critiques.
  - Detection: require evidence IDs, failed slots, and repair targets.

## Generalizability Checks

- Rename sources and evidence IDs; behavior should remain stable.
- Run on at least one non-nutrition case.
- Paraphrase evidence statements; semantic coverage should still pass.
- Remove one critical evidence item; the report should surface a gap rather than invent compensation.
- Swap source order; source rendering and trace should remain stable.

## Completion Evidence

- Plan implementation ledger in this file or a companion completion audit.
- Tests covering contracts, tag rendering, reconciliation, and mutation cases.
- Saved eggs before/after memo comparison.
- Saved unrelated-case before/after memo comparison.
- Final report summarizing whether the added trace machinery improved prose without losing evidence.

## Red-Team Review Of Plan Elegance

### What Is Elegant

- It extends the current memo-ready path instead of replacing it.
- It uses existing evidence items, source-bound atoms, quantities, language contracts, and source weighting rather than adding a new truth source.
- It separates model strengths from deterministic strengths: the model writes and judges semantic equivalence; code handles IDs, rendering, and accounting.
- It creates inspectable artifacts that can diagnose whether synthesis, validation, or packet construction is the bottleneck.

### Where It Risks Overcomplication

- Adding contracts, tags, reconciliation, back-translation, adversarial audit, and repair as separate always-on stages would make the pipeline too heavy.
- Evidence tags could become another citation syntax that the model must manage, increasing prompt burden.
- Back-translation and adversarial audit could duplicate existing retention and unsupported-addition checks if not narrowly scoped.
- Contract derivation could become a second obligation system parallel to `mandatory_retention_checklist`.

### Simplified Integration Recommendation

The most elegant version is a three-layer change, not a seven-stage always-on pipeline:

1. **Evidence contracts as a projection of existing packet fields.**
   - Do not create an independent obligation source.
   - Store them as a derived view used by synthesis and validation.

2. **Evidence-ID tags in section synthesis plus deterministic trace rendering.**
   - This is the core tangle/weave move.
   - It directly addresses readable prose plus traceability.

3. **Bidirectional reconciliation as the primary QA gate.**
   - Start deterministic/report-only.
   - Use model audit and targeted repair only when reconciliation finds high-risk failures.

Back-translation, adversarial audit, and targeted repair should be conditional extensions, not default stages.

### Revised Minimal Architecture

Default path:

```text
memo_ready_packet
  -> derived evidence_expression_contracts
  -> section markdown notes with evidence IDs
  -> parallel section synthesis with tags
  -> deterministic tag-to-citation rendering
  -> bidirectional reconciliation report
  -> presentation normalization
```

Conditional path:

```text
if reconciliation has high-risk missing/distorted/unsupported rows:
  -> model audit or targeted repair for affected sections only
  -> rerun reconciliation
```

### Final Judgment

The strategy is useful, but only if implemented as a compact traceability layer inside the existing memo-ready synthesis path. The elegant core is:

- derived semantic evidence contracts;
- evidence-ID annotated prose;
- deterministic trace rendering;
- bidirectional reconciliation.

The rest should remain conditional and report-only until it proves value. Implementing every analogy literally would overcomplicate the pipeline and likely recreate the critique/repair bloat we have been burning down.

## Implementation Ledger

Status: implemented as the single production section-synthesis path.

Implemented:

- Derived evidence expression contracts from existing memo-ready packet fields.
- Evidence-ID annotated section synthesis using the existing section-plan machinery, with the source-weighting section still using source IDs directly.
- Deterministic evidence-tag rendering to source citations.
- Evidence trace artifacts:
  - `evidence_expression_contracts.json`
  - `evidence_trace.json`
  - `evidence_reconciliation_report.json`
  - `evidence_tag_section_reports.json`
- Bidirectional reconciliation report for missing required IDs, unknown IDs, quantity warnings, and untagged high-risk sentences.
- Evidence-ID alias normalization for common zero-padding slips, such as `decision_writer_item_11` resolving to `decision_writer_item_011`.
- Final reader output artifact wiring so production runs preserve the contracts, trace, reconciliation report, and section reports.
- Removed the separate experiment module, experiment runner script, and env-flag routing branch so live and test backends use the same section synthesis implementation.

Held conditional:

- Back-translation audit.
- Adversarial auditor.
- Targeted evidence repair.

Reason: the red-team review concluded these should remain conditional/report-only until the deterministic trace layer shows a concrete unresolved failure that justifies extra model calls.

Verification:

- `PYTHONPATH=src python3 -m pytest tests/test_section_evidence_anchoring.py tests/test_parallel_section_synthesis.py tests/test_source_weighting_contract.py tests/test_memo_ready_packet_contract.py -q`
  - `31 passed`
- `PYTHONPATH=src:scripts python3 -m pytest tests -q`
  - `762 passed, 1 failed`
  - The remaining failure is the pre-existing static maintainability gate for long analyst files, not this synthesis integration.
- Eggs saved-packet probe after unifying the path:
  - output: `artifacts/semantic/eggs_unified_section_synthesis_20260716/`
  - synthesis mode: `unified_section_synthesis`
  - source-weighting fidelity: `ready`
  - reconciliation: `ready`
  - missing required evidence IDs: `0`
  - raw evidence tags in memo: `false`
  - raw evidence tags in memo: `0`
  - missing mandatory items: `0`
  - missing quantities: `0`
  - source-binding warnings: `0`
- Unrelated LHC saved-packet probe:
  - output: `artifacts/decision_model_plan_completion/lhc_evidence_anchored_integrated_probe_20260716/`
  - status: `accepted`
  - reconciliation: `ready`
  - contract count: `9`
  - trace count: `24`
  - missing required evidence IDs: `[]`
  - unknown evidence IDs: `[]`
  - raw evidence tags in memo: `0`
