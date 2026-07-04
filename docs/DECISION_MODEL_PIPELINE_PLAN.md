# Decision Model Pipeline Execution Plan

Status: `vertical-slice-implemented-needs-full-integration`

## Goal

Make the prototype produce decision-support briefings that close the quality gap with strong Deep Research-style synthesis while preserving the mapper's core advantage: inspectable evidence structure, source anchoring, crux visibility, telemetry, and reusable documents-plus-question operation.

The target end state is not "prettier prose." The target is a reusable pipeline where the final memo renders an explicit argument/decision model built from source-grounded map artifacts, quantitative anchors, relation structure, scope boundaries, and counterargument analysis.

## Current Gap

The latest eggs briefing reaches the right broad answer, but it still trails the Deep Research baseline as a standalone memo because:

- the main prose underuses quantitative anchors that already exist in the appendix;
- evidence weight is not explicit enough in the memo itself;
- subgroup and dose boundaries are named but not synthesized as richly as the baseline;
- relation-derived material can still read mechanically;
- the memo structure is inspectable but not yet a coherent argument;
- evaluation tells us the output is valid, but not always why it is weaker than a baseline.

Existing vertical-slice artifacts:

- `src/epistemic_case_mapper/model_schemas.py`
- `src/epistemic_case_mapper/decision_model_slice.py`
- `tests/test_decision_model_vertical_slice.py`

The vertical slice proves that Pydantic schemas and a compact decision model can work. The remaining task is to integrate that approach into the full map-briefing pipeline and make the generated memo better than the current map briefing on real and unseen cases.

## Non-Goals

- Do not add source retrieval or web search. Source collection is out of scope for this prototype.
- Do not tune specifically for eggs, HEPA, COVID, LHC, or any other named case.
- Do not hard-code domain vocabulary, source names, section labels, or case-specific thresholds into generic code paths.
- Do not use deterministic cleanup to silently hide unsupported or weak model reasoning.
- Do not replace the auditable appendix with a polished flat memo.
- Do not broaden schemas unless each new field is validated, used downstream, or included in telemetry.
- Do not make every expensive check part of the fast default gate.

## Design Principles

- Deterministic code owns schemas, routing, validation, artifact assembly, exact inclusion of question/sources, source anchoring, quantitative extraction candidates, freshness checks, and accept/reject decisions.
- Classical ML/statistical methods own retrieval within the provided corpus, clustering, ranking, centrality, near-duplicate detection, topic diversity, and coverage/anomaly signals.
- LLMs own bounded semantic judgment: salience, relation/crux hypotheses, evidence-weight explanations, counterargument construction, section-level synthesis, and awkward-language edit suggestions.
- Pydantic validates shape, not truth. Truth checks must be source-grounding, quantity, relation, and unsupported-claim gates.
- The final memo must render an explicit intermediate model. The final prose must not be the only place where the reasoning exists.
- Every improvement must produce an artifact, diagnostic, test, or before/after comparison.
- If a change improves eggs but cannot explain how it transfers to an unseen document set and question, it is not complete.

## Inventory And Dependency Map

Before changing code in each slice, classify touched files as:

- `keep`: current behavior remains valid;
- `extend`: add fields or behavior without changing ownership;
- `rewrite`: current ownership is wrong or too diffuse;
- `defer`: valuable but not required for this plan;
- `forbidden`: case-specific or unrelated to this plan.

Current dependency order:

1. Shared schema and parsing utilities: `model_schemas.py`, model-output parse helpers, section parse helpers.
2. Map and evidence artifacts: generated map, quality reports, prioritized map, relation contracts, quantity ledger, graph synthesis packet.
3. Decision/argument model builder: compact model from map artifacts, quantities, relations, and scope packets.
4. Section packet builder: section-specific evidence ownership and prompt inputs.
5. Section synthesis and rewrite: model calls, retry behavior, structured edit suggestions, validation.
6. Memo assembly and appendices: deterministic question, sources, quantities, evidence trail, telemetry.
7. Evaluation and gates: before/after comparison, baseline comparison, unseen-case quality checks, maintainability tests.

Stop and update this plan if implementation creates an unexpected dependency cascade, such as synthesis code reaching into raw parser internals or source-specific prompt logic entering generic artifact assembly.

## Fact Ownership

Important facts must have one owning layer:

| Fact | Owner | Consumers | Forbidden re-derivation |
|---|---|---|---|
| Decision question | CLI/case manifest/run config | memo header, argument model, evals | inferring from generated prose |
| Source titles and source IDs | source manifest/source display utilities | memo, appendix, validation | string cleanup from prose |
| Claim identity and source anchors | map artifacts | relation builder, decision model, appendix | matching claim text only |
| Relation identity/orientation | relation contracts/accepted relations | graph packet, crux builder, argument model | re-inferring relation direction in memo rewrite |
| Quantity candidates | quantity ledger | quantitative anchors, appendix, section packets | freeform number extraction inside final rewrite |
| Evidence weight | argument model | memo sections, telemetry, eval | burying weight only in prose |
| Scope boundaries | scope-boundary packet/argument model | practical read, exceptions, cruxes | repeating generic caveats without claim IDs |
| Unsupported-claim status | validation reports | accept/reject, final evidence packet | assuming accepted prose is safe |

Prefer stable IDs over text matching. If text matching is unavoidable, the implementation must explain why no stable identity exists and add a gate that catches mismatches.

## Execution Protocol

Maintain a plan ledger while implementing. Each slice has one status:

- `not started`
- `in progress`
- `blocked`
- `complete`

Only one slice should be `in progress` unless two slices have disjoint files and no dependency relationship.

Each completed slice must record:

- files changed;
- files intentionally left behind;
- tests/gates run;
- result of each test/gate;
- known residual risk;
- commit SHA when the user asks to commit or when the slice is committed.

## Stop Conditions

Stop implementation and report instead of continuing if:

- targeted tests fail and the failure is not understood;
- full `python3 -m pytest -q` fails for reasons related to this plan;
- `scripts/maintainability_gate.py` or maintainability tests fail after this plan adds/changes a gate;
- a model-output schema field is added but not used downstream;
- source anchoring or unsupported-claim checks regress;
- the final memo becomes more fluent but less faithful;
- a broad new gate is noisy and lacks stable diagnostics;
- a subsystem is partially integrated without a deferred-work entry.

## Anti-Half-Done Rule

If a subsystem cannot be completed in its slice, choose exactly one:

- finish it in the same slice;
- remove the partial subsystem;
- record it in `docs/DECISION_MODEL_DEFERRED.md` with owner, reason, missing work, risk, and next action.

Do not leave vague TODOs as completion evidence.

## Verification Tiers And Runtime Budgets

- Focused tests: run for the slice being changed; target under 30 seconds.
- Fast default gate: `PYTHONPATH=src python3 -m pytest -q`; target under a few minutes.
- Maintainability gate: existing maintainability tests and `scripts/maintainability_gate.py`; run when changing architecture, prompt inventories, or generic pipeline ownership.
- Corpus/canary gate: eggs plus at least one unseen case; run after major synthesis changes.
- Baseline comparison gate: eggs source-held comparison against the checked-in Deep Research baseline; run after memo-quality changes.
- Deep/adversarial gate: larger chunk-budget or multi-backend runs; report-only unless the signal is stable.

Do not promote a new broad quality gate to blocking until it has run report-only, existing findings are classified, and diagnostics point to an owning stage.

## Diagnostic Quality Standard

New reports and gates should include:

- stable diagnostic code;
- failure category;
- owning stage/module;
- source, claim, relation, section, or quantity IDs where applicable;
- concise excerpt or evidence row;
- artifact path;
- fatal vs warning severity;
- suggested next action.

Opaque messages such as "brief is weak" or "rewrite failed" are not mature diagnostics.

## Slices

### Slice 1: Argument Model Contract

Status: `not started`

Purpose: create the intermediate argument model that the final memo renders.

Owns:

- `src/epistemic_case_mapper/model_schemas.py`
- new or existing argument/decision model module
- tests for schema validation and artifact shape

Must not touch:

- source retrieval;
- case-specific docs or source text;
- final prose prompts except to consume the model in later slices.

Changes:

- Define `argument_model.json` schema with:
  - decision question;
  - answer;
  - confidence and confidence reasons;
  - strongest support;
  - strongest counterargument;
  - evidence weights and evidence types;
  - quantitative anchors;
  - scope boundaries;
  - subgroup/context exceptions;
  - cruxes;
  - missing evidence;
  - known failure modes.
- Require source/claim/relation/quantity IDs where available.
- Validate missing slots explicitly instead of fabricating content.

Verification:

- focused schema tests;
- malformed JSON and missing-field diagnostics;
- no schema fields unused by downstream tests or marked as intentionally future-use.

Done when:

- `argument_model.json` can be built for an existing realistic run;
- every field has an owner and consumer;
- focused tests pass.

### Slice 2: Evidence Weighting And Quantity Promotion

Status: `not started`

Purpose: make the main memo use the evidence and numbers that are already load-bearing.

Owns:

- quantity ledger selection code;
- evidence-weighting builder;
- tests for quantitative anchor selection.

Changes:

- Tag evidence by type: RCT, cohort, meta-analysis, guideline, mechanism, expert argument, source packet summary, or other.
- Tag endpoint type: hard outcome, biomarker, surrogate, mechanism, implementation, or context.
- Score directness, population match, dose/exposure match, sample size/scale, replication breadth, and limitation severity.
- Select main-memo quantitative anchors:
  - largest relevant sample sizes;
  - central effect estimates;
  - confidence intervals;
  - dose thresholds;
  - subgroup estimates;
  - duration/follow-up windows;
  - key null and key adverse estimates.
- Record why each promoted quantity was selected or rejected.

Verification:

- eggs run promotes the central BMJ/meta-analysis quantities and diabetes/subgroup quantities when present;
- unseen case promotes relevant quantities without food/nutrition-specific logic;
- quantity appendix remains auditable.

Done when:

- main memo packets include quantitative anchors with IDs and source paths;
- rejected quantities have reasons;
- tests prove selection is domain-neutral.

### Slice 3: Scope Boundary And Counterargument Packets

Status: `not started`

Purpose: improve subgroup, dose, comparator, and "best case against" handling.

Owns:

- scope-boundary extraction/selection;
- counterargument packet builder;
- crux packet builder.

Changes:

- Build scope packets for:
  - default population;
  - caution/excluded populations;
  - dose or intensity boundaries;
  - comparator/substitution context;
  - geography/setting differences;
  - endpoint differences;
  - time-horizon limits.
- Build counterargument packets:
  - strongest case for the answer;
  - strongest case against or limiting the answer;
  - what each side explains well;
  - what each side fails to explain;
  - what evidence would flip the answer.

Verification:

- before/after comparison shows clearer subgroup boundaries on eggs;
- unseen case has non-empty scope packets when source evidence supports them;
- no generic caveat is emitted without evidence ownership.

Done when:

- argument model includes scope and counterargument packets;
- memo sections consume them without duplicating the same evidence everywhere.

### Slice 4: Section-Specific Synthesis Packets

Status: `not started`

Purpose: reduce repetition and make each section do distinct work.

Owns:

- section packet builder;
- memo slot ownership;
- section rewrite inputs.

Changes:

- Generate section-specific packets:
  - decision answer;
  - practical recommendation;
  - evidence for;
  - evidence against/tensions;
  - evidence weighting;
  - scope and exceptions;
  - cruxes;
  - limits;
  - source trail.
- Assign evidence ownership so high-weight claims do not recur without purpose.
- Add telemetry for appendix-to-main-memo leakage and repetition.

Verification:

- section rewrite report shows distinct evidence ownership;
- repetition count decreases or is explicitly justified;
- final memo still contains the decision question and source list deterministically.

Done when:

- section packets are visible artifacts;
- the memo can be regenerated from packets plus deterministic assembly.

### Slice 5: Coherence-Edit JSON Instead Of Whole-Memo Rewrite

Status: `not started`

Purpose: improve readability without letting a model rewrite away source grounding.

Owns:

- reader polish prompt;
- structured edit schema;
- edit application and validation.

Changes:

- Ask the model for JSON edit suggestions where language is awkward, transitions are missing, or paragraphs fail to answer the decision question.
- Apply only local edits that preserve source anchors, quantities, section roles, and unsupported-claim checks.
- Retry invalid JSON up to the configured attempt limit.
- Reject edits that remove required anchors or weaken caveats.

Verification:

- invalid edit JSON gets useful diagnostics and retry behavior;
- accepted edits preserve source/quantity anchors;
- readability improves in before/after eval without unsupported-claim regression.

Done when:

- whole-memo rewrite is not required for normal path polish;
- edit rejections explain the owning failure stage.

### Slice 6: Baseline And Product-Quality Telemetry

Status: `not started`

Purpose: measure whether the changes close the Deep Research gap, not just whether the pipeline runs.

Owns:

- comparison reports;
- telemetry aggregation;
- quality review packets.

Changes:

- Add comparison telemetry for:
  - answer correctness;
  - decision usefulness;
  - evidence coverage;
  - quantitative depth;
  - subgroup/scope handling;
  - crux quality;
  - readability;
  - source transparency;
  - unsupported claims;
  - repeated claims;
  - appendix-to-main-output leakage.
- Produce a `FINAL_REVIEW_PACKET.md` for major runs with artifact paths, commands, results, and residual risks.

Verification:

- run eggs against the checked-in Deep Research baseline;
- run one unseen case;
- telemetry points to the next intervention rather than only reporting a score.

Done when:

- a reviewer can tell what improved, what regressed, and what remains weaker than baseline.

### Slice 7: Integration Into Full Pipeline

Status: `not started`

Purpose: make the argument-model path the normal high-quality path without breaking existing CLI behavior.

Owns:

- `map_briefing_pipeline.py`;
- CLI plumbing if needed;
- artifact summary wiring;
- documentation.

Changes:

- Add a feature flag or config path for argument-model-backed briefing.
- Preserve current path until comparison shows the new path is better.
- Include argument model, section packets, quantity anchors, telemetry, and final review packet in `briefing_summary.json`.
- Update docs for documents-plus-question usage.

Verification:

- existing tests pass;
- current CLI still works;
- argument-model path runs on eggs and one unseen case;
- generated artifacts are discoverable from summary JSON.

Done when:

- the full realistic pipeline can go from documents plus question to a briefing using the argument model;
- fallback path and removal criteria are documented.

## Acceptance Criteria

The plan is complete only when all of these are true:

- The full pipeline emits `argument_model.json`, section packets, quantity anchors, memo, appendix, telemetry, and final review packet.
- The main memo includes the decision question and sources deterministically.
- The memo uses promoted quantitative anchors in the main prose, not only the appendix.
- Scope boundaries and counterarguments are explicit and evidence-owned.
- Before/after eval shows the argument-model memo beats the current map-briefing output on crux clarity, scope binding, first-page readability, and quantitative depth without increasing unsupported claims.
- Eggs comparison against the checked-in Deep Research baseline shows a narrowed gap, with remaining gaps named specifically.
- At least one unseen case run shows the improvements are not case-specific.
- `PYTHONPATH=src python3 -m pytest -q` passes.
- Any added maintainability or quality gate has calibrated diagnostics and is either report-only or justified as blocking.

## Red-Team Checks

- Does the memo become smoother by hiding uncertainty or weakening caveats?
- Are quantitative anchors selected because they matter, or because they are easy to parse?
- Do scope boundaries rely on domain words from the eggs case?
- Can a new document set with no nutrition vocabulary still produce useful scope and counterargument packets?
- Does every model-generated field have source IDs or a clear reason why it is interpretive?
- Are final prose edits local and auditable, or are they effectively an uncontrolled rewrite?
- Does telemetry identify an owning stage for failures?

## Generalizability Checks

Run at least:

- eggs / dietary cholesterol source-held comparison;
- HEPA or another practical intervention question;
- one unseen policy/technical decision case with different source shape;
- one case with sparse quantities to ensure quantity promotion degrades gracefully;
- one case with conflicting expert arguments to test counterargument packets.

The implementation is overfit if:

- generic code names egg, cholesterol, HEPA, COVID, LHC, or other case-specific concepts;
- prompts assume biomedical evidence types without fallback evidence categories;
- success criteria only mention eggs;
- section packet selection depends on fixed source titles;
- validation cannot run on an unseen case.

## Deferred Work Policy

Use `docs/DECISION_MODEL_DEFERRED.md` for anything intentionally left out. Each entry must include:

- owner stage;
- reason deferred;
- missing work;
- risk if ignored;
- next action;
- whether it blocks the acceptance criteria.

## Final Evidence Packet

Before declaring this plan complete, produce:

- `docs/DECISION_MODEL_COMPLETION_AUDIT.md`
- latest eggs run path;
- latest unseen run path;
- comparison against current map briefing;
- comparison against Deep Research baseline;
- tests and commands run;
- known limitations;
- deferred items;
- remaining baseline advantages;
- recommendation on whether to make the argument-model path default.
