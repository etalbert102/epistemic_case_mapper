# Decision Model Pipeline Plan

Status: `vertical-slice-implemented`

Purpose: make the final decision-relevant brief a rendering of an explicit decision model, not a direct prose summary of the whole map. The pipeline should combine deterministic contracts, classical ML ranking/selection, and LLM semantic judgment behind Pydantic-validated model-output schemas.

The plan should be implemented as a narrow vertical slice first. Do not add every layer before proving that the final brief improves.

## Design Principle

- Deterministic code owns schemas, routing, validation, invariants, artifact freshness, and accept/reject decisions.
- Classical ML owns retrieval, ranking, clustering, graph coverage, near-duplicate detection, and anomaly signals.
- LLMs own bounded semantic judgment and prose compression into explicit schemas.
- Pydantic validates shape, not truth. Every schema field must either be source-grounded, deterministically checked, used downstream, or removed.

## Success Criterion

Before broad rollout, the vertical slice must pass this acceptance test:

> On one existing realistic case and one unseen small case, the decision-model brief is better than the current map-briefing output on crux clarity, scope binding, and first-page readability, without increasing unsupported claims.

Minimum evaluation artifacts:

- current briefing output
- decision-model briefing output
- source-grounding/unsupported-claim check
- crux clarity comparison
- scope-binding comparison
- first-page readability comparison

If the decision-model path is not better, stop and revise the layer design before adding more subproblems.

## Vertical Slice First

Implement this first:

1. Pydantic relation output schema.
2. Compact decision model schema.
3. Deterministic decision model builder from existing maps and relation contracts.
4. Brief renderer that writes from the decision model.
5. Before/after eval against the current map briefing.

Defer decision-frame extraction and claim-function enrichment until this slice shows value.

Implemented vertical-slice artifacts:

- `src/epistemic_case_mapper/model_schemas.py`
- `src/epistemic_case_mapper/decision_model_slice.py`
- `tests/test_decision_model_vertical_slice.py`

The slice validates relation outputs with Pydantic, builds a compact deterministic decision model from the existing map scaffold, renders a concise decision brief, and writes a before/after eval artifact. Broader decision-frame extraction, claim-function enrichment, relation critic passes, and full baseline comparisons remain future phases.

## Phase 1: Pydantic Relation Schema

Add `src/epistemic_case_mapper/model_schemas.py`, starting with relation outputs only.

Schemas:

- `RelationClassificationOutput`
- `RelationContractOutput`
- `RelationCriticOutput`

Helpers:

- `parse_model_output(raw, schema)` using `canonical_json_output()`
- structured validation errors
- repair-friendly error summaries

Acceptance checks:

- malformed model JSON produces useful validation diagnostics
- existing relation classification can be parsed through a Pydantic schema without losing current fields
- relation contract fields are required only when `relation_type != "none"`
- schema validation failures are written to relation rejection logs

## Phase 2: Compact Decision Model

Build a deterministic decision model from existing map artifacts before adding new upstream extraction layers.

Required slots:

- answer frame
- top support reasons, capped at 3
- top counterevidence or tensions, capped at 3
- top scope boundaries, capped at 3
- top cruxes, capped at 3
- confidence drivers, capped at 3
- missing evidence, capped at 3
- decision implications, capped at 3

LLM may fill short explanatory fields, but deterministic code selects the slots from the current map, relation contracts, and quality reports.

Artifact:

- `decision_model.json`

Guardrails:

- cap all lists to avoid artifact bloat
- preserve source IDs and claim/relation IDs in machine-readable fields
- keep reader-facing prose separate from audit fields
- mark missing required slots explicitly rather than fabricating content

## Phase 3: Brief Rendering From Decision Model

Render the final memo from:

- decision model
- selected evidence packets
- relation contracts
- crux contracts

LLM output schema:

- executive answer
- main reasons
- crux table
- uncertainty and scope section
- action implications
- audit appendix

Deterministic checks:

- all required cruxes surfaced
- confidence visible
- no unsupported source IDs
- no missing high-weight evidence
- reader burden within limits

Artifact:

- `briefing_memo.md`
- `briefing_validation_report.json`

## Phase 4: Before/After Evaluation

Compare:

- current map briefing
- decision-model briefing
- flat/deep-research baseline when available

Evaluation dimensions:

- first-page answer clarity
- crux clarity
- scope binding
- load-bearing evidence visibility
- unsupported-claim count
- reader burden
- whether the added structure changed likely decision quality

Artifacts:

- `decision_model_eval.json`
- `DECISION_MODEL_EVAL.md`

## Phase 5: Relation Development Extensions

Extend the current relation pipeline.

Classical ML proposes pairs using:

- TF-IDF semantic similarity
- graph coverage and centrality
- role-template compatibility
- polarity and scope signals
- source diversity

LLM classifies only selected candidates. Pydantic validates relation outputs. Deterministic code checks endpoints, relation type, confidence, anchors, orientation, and failure conditions.

Add a relation critic pass for:

- unsupported edge
- wrong direction
- overly generic label
- missing sharper relation
- missing relation for a high-priority claim

Artifacts:

- `candidate_relation_pairs.json`
- `accepted_relations.json`
- `relation_critic_report.json`
- `relation_coverage_report.json`

## Phase 6: Decision Frame Layer

Add this only after the compact decision-model slice improves briefs.

LLM proposes:

- decision-maker
- options being compared
- outcome criteria
- time horizon
- risk tolerance or confidence need
- action context
- what counts as decision-relevant evidence

Deterministic fallback frame should be built from the user question and manifest if model output is weak. Store `frame_confidence` and `ambiguous_frame_items`.

Artifact:

- `decision_frame.json`

## Phase 7: Claim Function Layer

Add this only if evaluation shows the decision model needs more precise claim roles.

Start with four fields:

- `function`
- `direction`
- `evidence_type`
- `decision_relevance`

Avoid taxonomy bloat. Add fields only when evals show value.

Artifact:

- `claim_function_report.json`

## Phase 8: Broader Quality Evaluation

Add tests and evals for each layer:

- schema parse failure tests
- decision-frame completeness tests
- claim-function coverage tests
- relation coverage tests
- decision-model slot coverage tests
- final memo readability and coverage tests
- baseline comparison tests

Metrics:

- percent of high-priority claims connected by relations
- percent of scope claims bound to target claims
- unsupported relation-contract count
- crux coverage in final memo
- missing-evidence visibility
- brief length and table burden
- baseline-preserved distinctions recovered by the prototype

## Implementation Order

1. Add Pydantic relation output schemas and parser helper.
2. Build compact deterministic `decision_model.json` from current map artifacts.
3. Render a brief from `decision_model.json`.
4. Run before/after eval against the current briefing path.
5. Add relation critic only for narrow checks: orientation, unsupported anchors, generic labels, missing scope binding.
6. Add `decision_frame.json` only if evals show decision framing errors.
7. Add claim-function enrichment only if evals show role taxonomy is too coarse.
8. Add broader quality gates and comparison evals.

## Risk Notes

- Do not let schemas become decorative. Every model-output schema should be used by a parser or gate.
- Keep deterministic repair bounded; it should mark uncertainty and review needs, not silently upgrade weak model outputs.
- Classical ML should improve retrieval and prioritization, not replace semantic judgment.
- LLM prompts should fill slots in existing contracts, not invent new workflow structure.
- Avoid long intermediate artifacts. The decision model should force prioritization, not preserve every map detail.
- Stop implementation if before/after evals show worse readability or no decision-support gain.
