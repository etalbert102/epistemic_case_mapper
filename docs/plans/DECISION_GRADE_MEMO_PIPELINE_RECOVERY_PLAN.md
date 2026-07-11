# Plan: Decision-Grade Memo Pipeline Recovery

## Objective

Produce decision-grade briefing memos from arbitrary document sets and decision questions by making the pipeline preserve source-local evidence, build one authoritative decision model, and validate final prose against that model before acceptance.

The target memo should answer the decision question, expose confidence and uncertainty, preserve load-bearing evidence, handle counterweights and scope limits, cite sources cleanly, and fail visibly when the evidence or model output is insufficient.

## Current Gap

The current pipeline succeeds structurally but loses semantic quality:

- Whole-document extraction compresses sources into broad canonical claims, fusing endpoints, populations, quantities, caveats, and methods too early.
- Multiple artifacts compete for answer ownership: decision spine, decision packet, analyst adjudication, analyst decision model, memo-ready packet, and repair outputs.
- Relation building is capped by heuristic candidate retrieval rather than driven by decision hypotheses and obligations.
- Quantity handling over-retains numbers and treats descriptive noise as decision-relevant anchors.
- Memo acceptance can pass synthesis and polish while final readiness says `not_decision_ready`.
- Telemetry identifies failures but does not yet route them cleanly to the upstream stage that caused them.

Representative failure evidence from the latest eggs live run:

- `artifacts/test_runs/eggs_live_parallel_decision_model/analyst_decision_model_parallel_report.json` showed `3/8` analyst decision-model shards timed out.
- `artifacts/test_runs/eggs_live_parallel_decision_model/analyst_decision_model_report.json` still reported all `29/29` evidence rows covered.
- `artifacts/test_runs/eggs_live_parallel_decision_model/memo_packet_retention_report.json` still reported critical retained-evidence misses.
- `artifacts/test_runs/eggs_live_parallel_decision_model/final_decision_readiness_report.json` reported `not_decision_ready`.
- `artifacts/test_runs/eggs_live_parallel_decision_model/memo_quality_report.json` nevertheless reported a polished memo, showing that polish status is not a decision-quality signal.

## Non-Goals

- Do not add source collection or web research as part of this plan.
- Do not optimize for the eggs case specifically.
- Do not rely on deterministic code to make semantic decisions.
- Do not delete legacy paths until side-by-side artifacts show the new path is better.
- Do not make broad semantic gates blocking until calibrated on fixtures.
- Do not present generated artifacts as human-reviewed.

## Design Principles

- Evidence units first: source-local evidence units become the canonical substrate; claims and memo packets are projections.
- One semantic owner: a single global decision model owns answer stance, confidence, weights, counterweights, cruxes, and scope.
- Model judgment, code guardrails: models handle semantic classification and synthesis; code enforces schemas, IDs, provenance, source lists, and telemetry.
- Validation before polish: prose polish cannot certify decision quality; semantic retention and source-faithfulness checks must run before final acceptance.
- Generalizable by construction: use domain-neutral fields such as population, comparator, endpoint, evidence type, estimate, uncertainty, scope, and relation-to-answer.

## Required-Reading Implications

- `AGENTS.md`: preserve decision-relevant structure over fluent summaries; record residual risks and do not overclaim review status.
- `docs/plans/WHOLE_DOCUMENT_SOURCE_CARD_EXTRACTION_PLAN.md`: current source-card extraction improved source salience, but it still produces broad claims instead of typed evidence units.
- `docs/plans/WRITER_PACKET_SYNTHESIS_PLAN.md`: writer-packet compaction is the right direction, but the writer packet must be projected from a single global decision model rather than assembled from competing packet artifacts.
- Latest live artifacts: structural success and polished prose can coexist with `not_decision_ready`, so the next work must target semantic retention and answer ownership before more prose polish.

## Inventory And Dependency Map

Active paths to inspect before implementation:

- Extraction: `staged_semantic_whole_doc.py`, `staged_semantic_whole_doc_pipeline.py`, `staged_semantic_quote_alignment.py`.
- Claim triage and relevance: `staged_semantic_claim_triage.py`, `staged_semantic_decision_questions.py`, `staged_semantic_label_audit.py`.
- Relation building: `staged_semantic_decision_edges.py`, `staged_semantic_relation_candidates.py`, `staged_semantic_relation_prompting.py`.
- Decision modeling: `map_briefing_analyst_decision_modeling.py`, `map_briefing_analyst_decision_model_parallel.py`, `map_briefing_analyst_schemas.py`.
- Packet assembly: `map_briefing_decision_packet_stage.py`, `map_briefing_analyst_packet.py`, `map_briefing_memo_ready_packet.py`.
- Synthesis and validation: `map_briefing_memo_ready_finalization.py`, `map_briefing_validation.py`, `map_briefing_final_memo_diagnosis.py`, `map_briefing_readiness.py`.

Dependency order:

1. Evidence-unit schema and extraction.
2. Relevance classification over evidence units.
3. Relation candidate retrieval from evidence units and answer hypotheses.
4. Global decision model.
5. Writer packet projection.
6. Memo synthesis and semantic validation.
7. Legacy pruning and stage ablation.

## Workstreams

### 1. Evidence-Unit Substrate

Purpose: prevent early semantic fusion.

Changes:

- Add typed `SourceEvidenceUnit` schema with source span, proposition, evidence type, population, exposure or intervention, comparator, endpoint, estimate, uncertainty interval, method, caveat, time horizon, source quote, and quote-lineage fields.
- Add a source-local extraction path that emits evidence units before canonical claims.
- Preserve existing whole-document claim extraction as a side-by-side comparison path until the evidence-unit path is proven better.
- Extract statistical tuples during ingestion from evidence units, not from downstream prose claims.

Artifacts:

- `source_evidence_units.json`
- `source_evidence_unit_quality_report.json`
- `source_quantity_tuples.json`
- `source_evidence_unit_extraction_progress.json`

Validation:

- Exact source span exists.
- Model entailment judge agrees the quote supports the proposition.
- Statistical tuple has local endpoint, comparator, population, estimate, and uncertainty context when available.
- Unit IDs are stable across deterministic reruns.

QA:

- Fixtures with multi-endpoint studies, subgroup caveats, table-derived results, and irrelevant background text.
- Adversarial fixture where a quote is exact but does not entail the broader proposition.

Risks:

- Inference cost rises.
- Document layout and tables may be difficult.
- Too many evidence units could overwhelm later stages.

Mitigation:

- Use section-level parallelism.
- Add evidence-unit clustering and salience ranking after extraction, not during source-grounding.
- Keep a source-coverage report that distinguishes omitted source sections from intentionally downgraded evidence.

### 2. Relevance And Routing

Purpose: keep off-question evidence from consuming downstream budgets without losing indirect but decision-critical scope evidence.

Changes:

- Run model relevance classification after evidence-unit extraction.
- Use outcomes `include`, `defer`, `appendix`, and `exclude`.
- Require rationale, target decision facet, and whether the unit bears on support, counterweight, scope, mechanism, uncertainty, or missing-evidence diagnosis.
- Use deterministic code only for IDs, schema validity, source anchoring, and obvious administrative noise.

Artifacts:

- `evidence_relevance_ledger.json`
- `evidence_routing_report.json`
- `deferred_evidence_audit.json`

Validation:

- Excluded and deferred evidence remains auditable.
- Included evidence has a decision facet.
- Every source has at least one coverage status: represented, deferred, excluded, or no decision-relevant evidence found.

QA:

- Metamorphic tests adding irrelevant documents.
- Paraphrased-question tests where core evidence should remain stable.
- Tests where indirect crux evidence must survive as `defer` or `include`, not disappear.

Risks:

- False-negative relevance filtering could drop important indirect evidence.

Mitigation:

- Keep `defer` as a non-destructive state.
- Add recall audits and compare included evidence against source bottom lines.

### 3. Decision-Hypothesis Relations

Purpose: make relations useful for decision reasoning, not just topical similarity.

Changes:

- Generate candidate answers and decision obligations before relation building.
- Connect each evidence unit to answer hypotheses it supports, challenges, bounds, contextualizes, or makes uncertain.
- Retrieve claim-to-claim or unit-to-unit relations through multiple channels: semantic neighbors, shared population or endpoint, conflicting direction, method-to-finding, scope-to-finding, and explicit conditional language.
- Track candidate-retrieval recall separately from relation-adjudication precision.

Artifacts:

- `decision_hypotheses.json`
- `evidence_answer_edges.json`
- `relation_candidate_recall_report.json`
- `decision_relation_graph.json`

Validation:

- Every included evidence unit is attached to at least one answer hypothesis, scope boundary, crux, uncertainty node, or omission record.
- Relation prompts include only the local context needed for the relationship decision.
- Edge labels are model-generated and schema-validated, not deterministically inferred from vocabulary.

QA:

- Adversarial fixtures with support/counterweight pairs.
- Method-limit-to-finding dependency fixtures.
- Subgroup exception fixtures.
- LHC-style dependency-chain fixture to test non-biomedical relation quality.

Risks:

- Graph explosion and noisy relation candidates.

Mitigation:

- Use typed retrieval quotas per hypothesis and relation channel.
- Use classical ML for candidate retrieval and LLMs for semantic adjudication.

### 4. Global Decision Model

Purpose: establish one authoritative semantic object.

Changes:

- Add a `GlobalDecisionModel` schema with bounded answer, confidence, confidence reasons, weighted evidence groups, strongest support, strongest counterargument, scope boundaries, cruxes, missing evidence, uncertainty drivers, and argument plan.
- Allow parallel local summaries only as inputs to a mandatory global reconciliation pass.
- Make global reconciliation account explicitly for failed, timed-out, deferred, and downgraded shards.
- Treat this model as the only source of answer stance for writer-packet construction.

Artifacts:

- `global_decision_model.json`
- `global_decision_model_report.json`
- `global_decision_model_reconciliation_report.json`
- `global_decision_model_failure_accounting.json`

Validation:

- All included evidence units are covered, downgraded, or explicitly omitted with rationale.
- No failed semantic-owner shard is silently converted into covered evidence.
- Confidence reasons mention both positive evidence and limiting evidence.
- Strongest counterargument and scope boundaries cannot be empty when source evidence contains counterweights or scope units.

QA:

- Side-by-side comparison against current analyst decision model on eggs.
- Cross-case comparison on LHC or COVID slice.
- Partial-shard-failure fixture where the global model must report uncertainty or fail, not silently accept.

Risks:

- Migration complexity.
- Global model could over-smooth disagreement.

Mitigation:

- Run side-by-side first.
- Preserve competing reads and unresolved crux fields.
- Promote only after before/after quality improves.

### 5. Writer Packet Projection

Purpose: give synthesis a compact, coherent package instead of many overlapping packets.

Changes:

- Compile one writer packet from the global decision model and evidence units.
- Include bounded answer, ordered reasoning steps, strongest support, strongest counterweight, scope exceptions, cruxes, source-local quantities, missing evidence, and source trail.
- Give each evidence unit a primary argumentative use while allowing auditable secondary references.
- Keep full evidence ledger and traceability matrix as audit artifacts, not writing context.

Artifacts:

- `decision_writer_packet.json`
- `decision_writer_packet_quality_report.json`
- `evidence_unit_traceability_matrix.json`

Validation:

- Writer packet is smaller than the full evidence ledger.
- Writer packet retains all critical evidence obligations.
- Writer packet contains no internal telemetry IDs in model-facing prose fields.
- Source labels and source list are deterministic.

QA:

- Writer packet should be manually readable.
- Compare memo output from writer packet against flat-source baseline and current memo-ready packet path.
- Stage-value report should show writer packet improves retention or readability, not merely changes format.

Risks:

- Overcompression could drop caveats.

Mitigation:

- Keep mandatory obligations and critical units protected.
- Add packet sufficiency checks before synthesis.

### 6. Memo Synthesis And Semantic Gates

Purpose: prevent fluent but weak memos from being accepted.

Changes:

- Synthesize memo from the writer packet.
- Run semantic validation before polish.
- Validate answer/model consistency, critical-evidence retention, counterweight treatment, source attribution, confidence visibility, and quantity interpretation.
- Route failures to targeted regeneration when repair information is sufficient.
- Emit explicit `not_decision_ready` when semantic failures remain.

Artifacts:

- `memo_semantic_validation_report.json`
- `memo_acceptance_report.json`
- `memo_targeted_regeneration_report.json`

Validation:

- Final acceptance cannot be `accepted` when readiness has blocker issues.
- Memo quality and final readiness cannot silently disagree.
- Polish can improve prose only if semantic validation is not worse.

QA:

- Blinded before/after memo comparison against current pipeline and flat-source baseline.
- Tests where a memo mentions a source but drops the actual decision-relevant quantity.
- Tests where a memo lists counterevidence but does not explain whether it changes the answer.

Risks:

- Validators may overblock.

Mitigation:

- Start report-only.
- Make only high-precision blockers blocking after calibration.

### 7. Telemetry, Caching, And Parallelism

Purpose: make failures diagnosable and runs reproducible.

Changes:

- Add content-addressed cache keys that include source hash, decision question, prompt version, schema version, profile, backend, and parameters.
- Record model call attempts, timeouts, token or character budgets, parse status, retry status, and repair status.
- Partition semantic-owner work by evidence cluster rather than input order where possible.
- Require global reconciliation to account for failed shards.

Artifacts:

- `stage_dag_report.json`
- `model_call_ledger.json`
- `cache_key_report.json`
- `parallel_failure_accounting_report.json`

Validation:

- Reruns reuse cache only when all key inputs match.
- Failed semantic-owner shards are visible in final quality reports.
- Extraction and global decision modeling can resume from completed shards.

QA:

- Retry and timeout fixtures.
- Cache invalidation fixture where changing the decision question invalidates extraction or relevance cache.
- Parallelism fixture where shard order does not change the global decision model.

Risks:

- Orchestration complexity.

Mitigation:

- Implement first for evidence extraction and global decision modeling only.

## Execution Order

1. Add evidence-unit schemas and focused fixture tests.
2. Implement source-local evidence-unit extraction beside existing whole-document claim extraction.
3. Add relevance and routing over evidence units in report-only mode.
4. Build decision-hypothesis relation retrieval and relation telemetry.
5. Implement global decision model side-by-side with existing analyst decision model.
6. Compile the new writer packet from the global decision model.
7. Run memo synthesis from the new writer packet and compare to current pipeline.
8. Add semantic validation in report-only mode.
9. Promote high-confidence semantic blockers to blocking status.
10. Use stage-value ablations to decide which legacy packet and repair paths can be removed.
11. Add cache-key and parallel shard reliability hardening.

## Acceptance Criteria

- New evidence-unit extraction preserves known load-bearing eggs evidence currently missed or mangled by claim compression.
- Quantity validation distinguishes effect estimates, confidence intervals, dates, sample sizes, and descriptive percentages.
- Global decision model has one bounded answer, visible confidence, strongest support, strongest counterweight, scope limits, cruxes, and missing evidence.
- Writer packet is smaller than the old packet stack but retains all critical evidence obligations.
- Final memo passes semantic readiness or explicitly reports `not_decision_ready`.
- Eggs memo improves against the current live memo on retention, quantitative discipline, confidence visibility, and readability.
- At least one differently shaped case, preferably LHC or COVID slice, shows the same architecture works without biomedical-specific vocabulary.
- Focused tests pass after each bounded implementation slice.
- Full test suite passes before claiming the plan complete.

## Red-Team For Effectiveness

### 1. The Plan May Be Too Large For One Implementation Run

Risk:

The plan spans extraction, relevance, relations, decision modeling, synthesis, validation, telemetry, and caching. If executed as one broad goal, it could create another overlapping pipeline rather than a cleaner one.

Effect on outcome:

This would worsen maintainability and make it harder to know which change improved or degraded memo quality.

Mitigation:

Execute in bounded vertical slices. The first slice should stop at evidence-unit extraction plus quality reports and compare against current claim extraction before touching downstream stages.

### 2. Evidence Units Could Overfragment The Source

Risk:

Moving from source-level claims to source-local evidence units could create too many tiny units, overwhelming relation building and writer packet assembly.

Effect on outcome:

The memo could become more complete but less coherent, or the model could drown in details.

Mitigation:

Add a consolidation stage after evidence-unit extraction. Consolidation should preserve lineage and typed fields while grouping compatible units. Measure duplicate rate, cluster count, source coverage, and writer-packet size.

### 3. Model Entailment Checks May Not Be Reliable Enough

Risk:

A model judge may approve quote-to-proposition entailment too easily, especially in technical or statistical contexts.

Effect on outcome:

The system could still accept overbroad claims, only with more elaborate artifacts.

Mitigation:

Use deterministic quote existence as a floor, model entailment as reportable judgment, and adversarial fixtures for exact-but-not-entailing quotes. Treat low-confidence entailment as a warning until calibrated.

### 4. The Global Decision Model Could Become A New Bottleneck

Risk:

Replacing multiple semantic owners with one global model is architecturally cleaner, but a single weak global pass could flatten disagreement or omit nuanced evidence.

Effect on outcome:

The memo would become more coherent while losing epistemic uplift.

Mitigation:

Use cluster summaries as inputs, require competing reads and missing evidence fields, and validate that counterweights, scope boundaries, and cruxes survive into the model. Global reconciliation should be mandatory, but it should receive structured dissent rather than raw unbounded evidence.

### 5. Relation Rebuild May Not Improve Final Memo Quality

Risk:

Better relations may improve maps but not final memos if writer-packet construction does not use them effectively.

Effect on outcome:

The project could spend substantial effort on graph quality without improving decision support.

Mitigation:

Tie every relation type to a writer-packet use: support, challenge, dependency, scope boundary, crux, uncertainty, or missing-evidence diagnosis. Add a stage-value gate that asks whether relations changed the global decision model or memo obligations.

### 6. Semantic Validation Could Block Good Memos

Risk:

Validators may treat paraphrase, synthesis, or reasonable omission as failure.

Effect on outcome:

The system could reject readable, decision-useful memos and fall back to rigid prose.

Mitigation:

Run validators in report-only mode first. Make only high-precision failures blocking: unsupported source attribution, missing decision question, missing deterministic source list, critical evidence omission, and clear contradiction with global model stance.

### 7. Generalizability Could Still Leak Through Domain Profiles

Risk:

Even with domain-neutral schemas, existing config vocabularies and label audits may continue to route evidence using biomedical or policy vocabulary.

Effect on outcome:

The pipeline may look improved on eggs but fail on LHC or COVID.

Mitigation:

Audit generic paths for profile vocabulary use before promotion. Keep domain vocabularies as optional profile hints, not sufficiency or role owners. Require at least one non-biomedical end-to-end run before marking the plan complete.

### 8. The Plan Needs A Clear Stop Condition

Risk:

Because the plan is ambitious, implementation could keep chasing memo quality indefinitely.

Effect on outcome:

The project could fail to produce a stable, inspectable improvement.

Mitigation:

Define the first completion milestone as: evidence-unit extraction, report-only relevance routing, side-by-side writer packet, and one live memo comparison on eggs plus one non-eggs case. Defer full legacy deletion and blocking validators until after that milestone.

## Revised Implementation Slices

### Slice 1: Evidence-Unit Vertical Slice

Done when:

- `SourceEvidenceUnit` schema exists.
- At least one source can produce evidence units with source spans and typed quantities.
- Tests cover exact quote existence, non-entailing quote warning, and quantity tuple extraction.
- Existing claim extraction remains untouched as fallback.

Verification:

```bash
PYTHONPATH=src python3 -m pytest tests/test_staged_whole_doc_claim_extraction.py -q
```

### Slice 2: Evidence Routing And Quality Reports

Done when:

- Evidence units receive `include`, `defer`, `appendix`, or `exclude` routing.
- Routing is model-generated and schema-validated.
- Deterministic code records warnings but does not make semantic relevance decisions.
- Irrelevant-document metamorphic fixture passes.

Verification:

```bash
PYTHONPATH=src python3 -m pytest tests/test_staged_whole_doc_claim_extraction.py tests/test_evidence_unit_routing.py -q
```

### Slice 3: Global Decision Model Side-By-Side

Done when:

- New global model artifact is produced beside current analyst decision model.
- Global model accounts for included, deferred, downgraded, and failed-shard evidence.
- Partial shard failure no longer reports unqualified coverage.
- Eggs side-by-side report identifies whether global model improves decision ownership.

Verification:

```bash
PYTHONPATH=src python3 -m pytest tests/test_analyst_decision_modeling.py -q
```

### Slice 4: Writer Packet Projection

Done when:

- Writer packet is projected only from the global decision model and evidence-unit ledger.
- Packet contains no competing answer owner.
- Packet quality report identifies missing critical evidence before synthesis.
- Memo synthesis can run from writer packet in report-only mode.

Verification:

```bash
PYTHONPATH=src python3 -m pytest tests/test_analyst_packet.py tests/test_source_appraisal.py -q
```

### Slice 5: Semantic Memo Acceptance

Done when:

- Memo semantic validation report exists.
- Final readiness and memo acceptance cannot silently disagree.
- High-confidence blockers are enforced after report-only calibration.
- Live eggs and one non-eggs case are rerun and compared.

Verification:

```bash
PYTHONPATH=src python3 -m pytest tests/test_memo_ready_packet.py tests/test_map_briefing_readiness.py tests/test_live_enrichment_contract.py -q
PYTHONPATH=src python3 -m pytest -q
```

## Final Completion Audit

The plan is complete only when a final audit records:

- Changed files by slice.
- Tests run and outcomes.
- Latest eggs memo quality compared to the current baseline.
- Latest non-eggs memo quality compared to prior output.
- Whether semantic validation is still report-only or blocking.
- Deferred legacy paths and deletion candidates.
- Remaining risks that require human review or additional source material.
