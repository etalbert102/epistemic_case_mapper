# Investigator Challenge Demonstration Plan

Status: active plan

## Goal

Demonstrate the Epistemic Case Mapper in its strongest current role: an epistemic debugger and handoff layer for serious investigations.

The completed demonstration should let a judge start with a capable flat research answer, use the map to interrogate hidden dependencies and disagreements, review or correct one local object, incorporate a held-out source, and regenerate a reader-facing view without rebuilding the investigation.

The result must be inspectable without accepting the project's scoring judgments on trust. Every task, source span, raw model output, score, correction, and update should remain available to the judge.

## Product Position

The prototype is not primarily a better summary generator. Its intended place in the workflow is:

```text
Bounded source packet or Deep Research output
        -> source-anchored claims and relations
        -> interrogation of dependencies, disagreements, and cruxes
        -> local review, correction, and update
        -> prose generated as one view of the accepted structure
```

The central competition claim is correspondingly narrow:

> Deep Research helps produce an answer. Epistemic Case Mapper helps determine what that answer depends on, what it flattened, how to challenge it, and how to update it without starting over.

## Current Gap

The repository contains worked maps, flat and blinded baselines, erosion audits, reviewer packets, a new-source update example, and reproducibility gates. These show artifact depth and make several reasoning gains visible.

What is still missing is a single end-to-end use demonstration that measures product behavior:

- answering adversarial follow-up questions;
- locating the source and inference responsible for an answer;
- correcting one bad claim or relation locally;
- identifying the impact of new evidence;
- preserving unaffected work during an update;
- rendering a new reader-facing answer from the revised structure.

## Non-Goals

- Do not claim scientific validation, statistical significance, or expert consensus.
- Do not claim that the mapper produces better prose than Deep Research.
- Do not optimize the challenge for maximum map victory.
- Do not use weak or intentionally careless flat baselines.
- Do not acquire a broad new corpus unless the existing cases cannot support a fair held-out-source test.
- Do not change the core schema or decision-memo architecture merely to improve demonstration scores.
- Do not mark any artifact `human-reviewed` without explicit human review.
- Do not modify unrelated user-authored changes, including `scripts/experiment_richer_prioritized_argument.py`.

## Design Principles

1. Use a strong baseline. The value proposition is auditability beyond capable prose, not victory over a straw man.
2. Measure tasks, not artifact counts. The primary outputs are answers, source traces, corrections, and updates.
3. Freeze tasks and rubrics before running comparison conditions.
4. Equalize source access and token budgets wherever the comparison requires it.
5. Preserve raw outputs and mixed or negative results.
6. Keep mechanical validity separate from semantic usefulness.
7. Prefer stable claim, relation, source, task, and mutation IDs over text matching.
8. Make the judge the final adjudicator by providing compact evidence packets rather than opaque aggregate scores.

## Inventory And Dependency Map

### Existing inputs to reuse

- Strong worked regions:
  - `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`
  - `examples/eggs/worked_region_observational_vs_rct_map.md`
  - `examples/covid_origins_slice/worked_region_bayesian_disagreement_map.md`
- Strong comparison surfaces:
  - eight blinded local-model baselines for LHC and eggs;
  - `docs/baselines/deep_research/deep_research_eggs_Claude_Opus4.8.md`;
  - `docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md`.
- Update and review infrastructure:
  - `docs/NEW_SOURCE_UPDATE_DEMO.md`;
  - `docs/review/*_HUMAN_AUDIT_PACKET.md`;
  - stable Markdown and JSON exports.
- Existing evaluation machinery:
  - `scripts/run_synthesis_uplift_eval.py`;
  - `scripts/run_proof_by_example.py`;
  - manifest-driven validators and reproducibility gates.

### Dependency order

```text
Frozen task specification and answer keys
        -> frozen input conditions and budgets
        -> raw challenge runs
        -> deterministic and model-assisted scoring
        -> local review/correction exercise
        -> held-out-source update exercise
        -> regenerated reader view
        -> judge evidence packet and write-up claims
```

No downstream stage may silently redefine an answer key, required distinction, affected-object set, or scoring rule after seeing model outputs.

## Fact Ownership

- Source manifests own source identity and corpus membership.
- Worked maps own canonical claim and relation IDs for the demonstration.
- Challenge specifications own task wording, required distinctions, and permitted evidence.
- Answer keys own expected source IDs, relation IDs, scope boundaries, and update effects.
- Raw run artifacts own what each model or condition actually returned.
- Scoring reports may classify results but may not rewrite raw output.
- The final reader view consumes the accepted revised map; it may not recreate evidence relationships from prose.

## Experimental Conditions

Use at least two conditions:

- `flat`: a strong blinded or Deep Research-style synthesis produced from the frozen source packet.
- `map`: a bounded reader packet containing the same case information as explicit claims, relations, cruxes, excerpts, and source IDs.

Use an optional third condition when source text is required to prevent an unfair comparison:

- `map_plus_sources`: the map packet plus the same source excerpts available to the flat condition.

Randomize condition labels in any model-judged comparison. Record input and output token counts. Do not reward length.

## Challenge Tasks

### LHC: hidden dependency

Required questions:

1. Why is Earth survival under cosmic-ray collisions not sufficient by itself?
2. Why do compact astronomical bodies become relevant?
3. Which claims and sources carry the velocity/trapping transition?
4. Which criticism most directly challenges the compact-star safety argument?
5. What would have to change for the bottom-line risk assessment to move materially?

Canonical anchors include `lhc_c004`, `lhc_c012`, `lhc_r003`, and `lhc_r004`.

### Eggs: evidence-role boundaries

Required questions:

1. Why can randomized lipid results and observational cardiovascular outcomes point in different directions without one simply invalidating the other?
2. What explains the apparent BMJ/JAMA tension?
3. What populations, intake ranges, and substitution contexts limit a general recommendation?
4. Which statements are evidence findings, which are guideline interpretations, and which are policy advice?
5. What new result would most change the practical answer?

Canonical anchors include `eggs_c008`, `eggs_c012`, `eggs_c015`, `eggs_c019`, `eggs_r003`, `eggs_r005`, `eggs_r006`, and `eggs_r014`.

### COVID: disagreement and update conditions

Use as a bounded transfer check, not a full adjudication.

Required questions:

1. Does conceding the judged debate imply conceding the substantive conclusion?
2. How do the aggregate forecast and minority distribution differ?
3. Which disagreement concerns process, which concerns evidence, and which concerns Bayesian structure?
4. What evidence would trigger an update?
5. Which later result is only a subargument rather than a whole-case resolution?

Canonical anchors include `covid_c005`, `covid_c006`, `covid_c009`, `covid_c010`, `covid_c011`, `covid_c017`, `covid_c018`, `covid_r002`, `covid_r005`, and `covid_r011`.

## Metrics

### Primary usefulness metrics

- `required_distinction_recall`: required answer-key distinctions clearly present.
- `source_trace_accuracy`: cited source and claim IDs actually support the response.
- `scope_boundary_retention`: populations, endpoints, conditions, and subargument boundaries preserved.
- `unsupported_bridge_count`: inferential links asserted without support in the provided artifact.
- `false_closure_count`: unresolved questions or minority positions incorrectly presented as settled.
- `crux_or_update_trigger_recall`: decision-changing conditions correctly identified.

### Local correction metrics

- error detected;
- correct object localized;
- correct source span recovered;
- source-safe correction produced;
- number of unaffected objects changed;
- residual contradictions after correction.

### Update and compounding metrics

- affected claims and relations correctly identified;
- unaffected IDs preserved;
- new contradictions or caveats surfaced;
- stale statements remaining;
- update edit count and blast radius;
- runtime, model calls, and token use;
- final reader view consistent with the revised map.

Scores are descriptive. The evidence packet must always expose the underlying task-level results.

## Workstreams

### 1. Freeze the challenge specification

Purpose: prevent post-hoc selection of favorable questions or criteria.

Changes:

- Create a versioned challenge manifest with task IDs, case IDs, input conditions, answer-key IDs, token budgets, and scoring fields.
- Create human-readable and JSON answer keys grounded in existing map and source IDs.

Artifacts:

- `experiments/investigator_challenge/challenge_manifest.yaml`
- `experiments/investigator_challenge/answer_keys.json`
- `docs/INVESTIGATOR_CHALLENGE_PROTOCOL.md`

Validation:

- Every required source, claim, and relation ID resolves.
- Every scoring item names an inspectable source or is labeled as a judgment.
- Challenge files are hashed into each run record.

Risks:

- Answer keys may encode the map author's interpretation. Mitigation: mark judgment-dependent items and make source excerpts available.

### 2. Build comparable flat and map input packets

Purpose: avoid comparing unequal corpora or a weak baseline with a curated map.

Changes:

- Freeze the strongest available baseline per case.
- Generate map reader packets under explicit token budgets.
- Record exactly which source spans each condition can access.

Artifacts:

- condition packets and token-accounting reports under `artifacts/investigator_challenge/<run_id>/inputs/`;
- checked-in packet-building specification, not generated model output.

Validation:

- Source-universe parity report.
- Token-budget report.
- No curated answer key is exposed to answer-generation models.

Risks:

- A map necessarily foregrounds distinctions by design. This is the claimed interface benefit, but the report must distinguish interface advantage from discovery ability.

### 3. Run the adversarial follow-up challenge

Purpose: measure whether each condition helps a downstream consumer recover decision-relevant structure.

Changes:

- Add a manifest-driven challenge runner.
- Run at least three available model families when possible.
- Preserve prompts, raw responses, parse failures, token counts, and runtime.

Artifacts:

- `challenge_run.json`;
- raw prompt/output directories;
- `CHALLENGE_RESULTS.md` with task-level results.

Validation:

- Reruns use frozen tasks and input hashes.
- Invalid or unavailable model runs remain visible rather than being silently omitted.

QA:

- Shuffle task order.
- Rename condition labels.
- Include at least one easy control question and one question where a strong flat synthesis should be sufficient.

### 4. Demonstrate local review and correction

Purpose: show the prototype as an epistemic debugger, not just a question-answering context.

Changes:

- Define source-safe semantic mutations for each case and matched clean controls.
- Ask the investigator or downstream model to locate, justify, and repair the mutation.
- Apply accepted repairs to temporary artifact copies only.

Mutation classes:

- invalid source attribution;
- reversed or overstated relation;
- proxy endpoint promoted to final outcome;
- aggregate/minority disagreement collapsed;
- scope caveat removed.

Artifacts:

- mutation manifest;
- clean and corrupted packets;
- detection and repair reports;
- before/after local diffs.

Validation:

- Every mutation is synthetic and labeled.
- Clean controls do not trigger systematic false-positive repair.
- Repairs pass source, endpoint, and relation-reference validation.

### 5. Run a held-out-source update

Purpose: demonstrate compounding and local update behavior.

Changes:

- Select a predeclared held-out source that adds a meaningful caveat, scope boundary, or counterweight.
- Update both the flat and map conditions without exposing future answer keys.
- Generate an impact report before producing revised prose.

Artifacts:

- before and after map snapshots;
- affected-object ledger;
- flat-report diff;
- map diff;
- stale-statement and contradiction reports;
- revised reader view.

Validation:

- Unaffected IDs remain stable.
- Every new or changed claim points to the held-out source.
- The revised reader view is consistent with accepted map changes.

Risk:

- The existing CERN public-page update is structurally useful but may be too weak to change reasoning. Prefer an existing held-out eggs or LHC source with a decision-relevant caveat if source fidelity permits.

### 6. Assemble the judge evidence packet

Purpose: make results independently inspectable in ten to fifteen minutes.

Required sections:

1. capable baseline answer;
2. three adversarial follow-up comparisons;
3. one source-trace walkthrough;
4. one local correction diff;
5. one held-out-source update diff;
6. regenerated reader view;
7. metric table with raw artifact links;
8. what the demonstration establishes and does not establish.

Artifacts:

- `docs/INVESTIGATOR_CHALLENGE.md`;
- `artifacts/investigator_challenge/<run_id>/FINAL_EVIDENCE_PACKET.md`;
- `artifacts/investigator_challenge/<run_id>/completion_audit.json`.

### 7. Revise the competition write-up

Purpose: make the actual demonstrated use the organizing story.

Changes:

- Position the mapper as a complement to Deep Research.
- Embed the strongest task result and update result.
- Replace vague uplift language with task-level observations.
- Answer FLF's reasoning, generalization, scaling, and compounding questions directly.
- Add related-work positioning: provenance, argument maps, and knowledge graphs are prior art; the distinctive contribution is the integrated differential audit and handoff workflow.

## Execution Order

1. Freeze LHC tasks and answer keys because the hidden dependency is the smallest persuasive vertical slice.
2. Build flat and map packets with source-universe and token accounting.
3. Run the LHC follow-up challenge and inspect raw outputs before expanding.
4. Add one LHC correction mutation and clean control.
5. Run one meaningful held-out-source update.
6. Only after the vertical slice works, run the same generic machinery on eggs and the narrow COVID slice.
7. Assemble the judge packet.
8. Rewrite the overview around observed results.
9. Run package, experiment, reference, and reproducibility gates.

## Slice Protocol

Each implementation slice must record:

- owned and forbidden files;
- exact files changed;
- task and artifact IDs introduced;
- focused verification commands;
- raw comparison or mutation artifacts inspected;
- result and residual risk;
- explicit deferred work if the slice cannot be finished.

Do not begin the next case until the LHC vertical slice produces a complete evidence packet or a recorded negative result.

## Verification Tiers

### Focused

- manifest and answer-key reference validation;
- packet source-universe and token-accounting tests;
- mutation clean-control tests;
- held-out-source impact-ledger tests.

### Fast/default

- existing unit tests;
- worked-region and blinded-baseline validators;
- challenge runner in cached or prompt-only mode.

### Corpus/canary

- LHC, eggs, and COVID task runs across available model families;
- task-order and condition-label metamorphic checks.

### Artifact/release

- representative manual inspection of raw outputs and source spans;
- full evidence packet reference validation;
- FLF demo and reproducibility gates.

## Runtime Budgets

- Fast deterministic validation target: under 60 seconds.
- One cached challenge scoring pass: under 60 seconds.
- Live multi-model runs belong in an explicit deep-run tier and may take longer.
- A failed or unavailable backend should not block deterministic packet inspection; record it as unavailable.

## Claim Ladder

Results determine the permitted claim:

- Strong: map condition improves required-distinction recovery across at least two case shapes and multiple consumer models without increasing unsupported bridges.
- Narrow: map condition clearly improves the LHC dependency task and local update/correction surfaces, with mixed results elsewhere.
- Mechanical only: the workflow is inspectable and locally revisable, but downstream question performance is not better.
- Negative: map packets increase overload or error enough that the current interface is not useful; report this and narrow the submission to failure analysis.

Do not promote a claim merely because the implementation is complete.

## Acceptance Criteria

- The LHC vertical slice can be run end to end from a frozen manifest.
- At least three adversarial questions have task-level flat-versus-map outputs and inspectable scoring.
- At least one semantic mutation and one clean control are evaluated.
- At least one held-out source produces an affected-object ledger, stable unaffected IDs, and a revised reader view.
- All prompts, raw outputs, scoring records, token counts, and failures are preserved.
- The judge evidence packet can be followed without reading raw JSON first.
- The write-up reports the claim level actually earned by the results.
- Existing worked-region, reference, test, and reproducibility gates pass.
- Review status remains no stronger than warranted.

## Red-Team Checks

- Tautological task design: include questions a strong flat synthesis should answer and disclose when map tasks are derived from map structure.
- Unequal information: report source-universe and token differences; use `map_plus_sources` where necessary.
- Model-judge bias: retain deterministic rubric fields and raw outputs; do not rely on one model judge.
- Length bias: equalize budgets and instruct evaluators not to reward verbosity.
- Mutation guessing: use matched clean controls.
- Update triviality: select a source with a real caveat or counterweight and disclose if the conclusion does not move.
- Author overfitting: freeze tasks before outputs and reuse generic task/score schemas across cases.
- Aggregate-score concealment: always show per-task outcomes and failed runs.

## Generalizability Checks

- The runner and schemas must discover cases and IDs from manifests rather than domain vocabulary.
- Reordered tasks and renamed condition labels should not change scores materially.
- A paraphrased question should preserve the same required distinctions.
- Duplicate or irrelevant source additions should not alter the affected-object ledger except for explicit warnings.
- Success criteria must include at least two different case shapes before making a cross-domain claim.
- A future unseen case must be runnable without editing generic Python code.

## Stop Conditions

Stop and report rather than expanding scope if:

- a fair flat-versus-map source universe cannot be constructed;
- answer keys require inventing domain claims not grounded in checked-in sources;
- the LHC vertical slice cannot produce interpretable task-level evidence;
- mutation tests create high false-positive rates on clean controls;
- the held-out source is too weak to test update behavior and no suitable existing source is available;
- implementation requires a core schema redesign;
- unrelated user changes would need to be overwritten;
- broad gates fail outside the current slice.

## Final Verification

The intended all-up command is:

```bash
PYTHONPATH=src python3 scripts/run_investigator_challenge.py --all
```

That runner does not exist yet. Implementation is incomplete until it produces the final evidence packet and completion audit, or the plan records a narrower verified command set and explains why.

Existing release checks remain required:

```bash
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 scripts/run_flf_demo.py --skip-build
PYTHONPATH=src python3 scripts/reproducibility_gate.py \
  --include-worked-regions \
  --include-blinded-baselines
git diff --check
```

## Progress Ledger

- [x] Best-use product position recorded.
- [x] End-to-end challenge decomposed.
- [x] Tasks, metrics, safeguards, and claim ladder specified.
- [ ] LHC task manifest and answer keys frozen.
- [ ] Comparable LHC condition packets built.
- [ ] LHC adversarial follow-up challenge run.
- [ ] LHC semantic mutation and clean control run.
- [ ] Held-out-source update run.
- [ ] Eggs and COVID transfer checks run.
- [ ] Judge evidence packet assembled.
- [ ] Competition write-up revised around observed results.
- [ ] Final release checks passed.

## Deferred Work Policy

Every incomplete item must be finished, removed, or recorded with:

- owner;
- reason;
- missing work;
- risk to the competition claim;
- next executable action.

No vague placeholder counts as completion evidence.

