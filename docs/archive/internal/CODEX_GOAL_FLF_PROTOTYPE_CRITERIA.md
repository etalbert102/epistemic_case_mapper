# Codex Goal Criteria For The FLF Prototype

## Purpose

This document defines the verifiable criteria a Codex `/goal` run must satisfy when building the FLF epistemic case-map prototype.

The goal is not "make the repo better." The goal is to produce a judge-facing prototype that demonstrates a repeatable workflow for preserving provenance, claims, relationships, cruxes, caveats, uncertainty, and missing perspectives in real epistemic case studies.

This criteria document combines:

- FLF competition requirements from `docs/reference/flf_epistemic_case_study_competition_criteria.md`.
- Codex goal-mode research from `docs/reference/codex_goal_ability_research.md`.
- Agent planning standards from `/Users/eli/Documents/Experiments/docx-review-engine/docs/agent_plan_quality_guide.md`.

## Goal Contract

A Codex goal for this repo is valid only if it states:

1. A single durable objective.
2. The case or cases in scope.
3. Files and docs Codex must read before editing.
4. What Codex must not change.
5. The artifacts that must exist at completion.
6. The commands that must pass.
7. The review rubric that must be satisfied.
8. The stopping condition.
9. The progress log or plan file Codex must keep updated.

If any of these are missing, use `/plan` first and refine the goal before running it.

## Minimum Viable Prototype Goal

The first strong goal should target one complete worked example, not the entire submission.

The `/goal` command itself should be short. The detailed contract should live in a checked-in plan file so Codex can reread and update it across a long run.

Recommended initial goal:

```text
/goal Execute docs/plans/lhc_demo_goal_plan.md. Keep that plan updated as the living source of truth. Stop only when its done checklist and docs/CODEX_GOAL_FLF_PROTOTYPE_CRITERIA.md both pass, or when a stop rule requires reporting a blocker.
```

## Non-Goals For The First Goal Run

- Do not attempt a full COVID origins analysis.
- Do not build a broad product UI before the workflow and artifact shape are credible.
- Do not optimize for polished prose at the expense of traceable claims.
- Do not add dependencies unless they directly support ingestion, mapping, validation, or report generation.
- Do not hide uncertainty by collapsing caveats, disagreements, or missing evidence into a single fluent summary.
- Do not treat seed notes as if they are final source evidence.

## Source Acquisition Policy

The prototype has two evidence modes.

### Seed Mode

Seed mode uses existing `case.yaml` notes. It is acceptable for scaffolding the workflow, but it is not a final FLF demo.

Pass conditions:

- Every seed source uses `source_type: seed_notes`.
- Every claim derived from seed material has `confidence: low`.
- `source_span` is `heuristic_sentence`, `seed_note`, or another explicit non-final marker.
- `audit.md` states that the artifact is seed-derived and names the source types still needed.

Fail conditions:

- Seed notes are described as final source evidence.
- A seed-derived claim is presented as settled.

### Source-Grounded Mode

Source-grounded mode uses real source material with URLs, downloaded excerpts, or local source files.

Pass conditions:

- Each source includes title, source type, URL or local path.
- Web-acquired sources include retrieval date.
- Publication date is recorded when available.
- Source-local excerpts are stored in the manifest or a local source file.
- Claims cite `source_id` and a source-local span or excerpt marker.
- `audit.md` distinguishes direct source claims from inferred relations and missing evidence.

Fail conditions:

- Claims are generated from memory or web snippets without being recorded as source material.
- A source is cited in prose but absent from `case.yaml`.

### Web Use

Codex may use web search only when the goal or plan explicitly allows source acquisition.

When web use is allowed:

- Prefer primary or authoritative sources.
- Record source URL, access date, source type, and the reason the source is relevant.
- Do not rely on search snippets as evidence.
- Save enough local excerpt or notes for a reviewer to audit the claim without repeating the search.

When web use is not allowed:

- Codex must work only from checked-in manifests, docs, and local files.
- Missing external evidence must be recorded as a gap.

## Required Inputs

Before implementation, Codex must inspect:

- `README.md`
- `docs/WORKFLOW_SPEC.md`
- `docs/protocols/epistemic_case_map_v0.md`
- `docs/reference/flf_epistemic_case_study_competition_criteria.md`
- `docs/reference/codex_goal_ability_research.md`
- `data/cases/<case_id>/case.yaml`
- Current schema and mapper code under `src/epistemic_case_mapper/`
- Current CLI under `scripts/`
- Current tests under `tests/`

Pass condition:

- The progress log or plan file names each inspected input and records at least one concrete implication from it.

Fail condition:

- Codex begins broad edits before recording what it learned from the required inputs.

## Required Artifacts

A goal run is complete only when generated artifacts exist for the target case:

- `artifacts/<case_id>/case_map.json`
- `artifacts/<case_id>/report.md`
- `artifacts/<case_id>/audit.md`

Generated artifacts under `artifacts/` remain gitignored. Curated judge-facing snapshots must be checked in under:

- `examples/<case_id>/case_map.json`
- `examples/<case_id>/report.md`
- `examples/<case_id>/audit.md`
- `examples/<case_id>/README.md`

Pass condition:

- `artifacts/<case_id>/...` can be regenerated locally.
- `examples/<case_id>/...` contains a checked-in snapshot of the demo output.
- `examples/<case_id>/README.md` states the exact command that generated the snapshot and whether it is seed mode or source-grounded mode.
- A fresh clone can regenerate the artifacts using documented commands.
- A validation command confirms regenerated artifacts match the checked-in example snapshot, or records the exact expected differences.

Fail condition:

- The only evidence of success is transient chat text or untracked local output.
- The checked-in example is stale relative to the documented generation command.

## Prototype Capability Criteria

### 1. Ingestion

The prototype must represent source provenance explicitly.

Pass conditions:

- Every extracted claim has a `source_id`.
- Every source has a title and source type.
- Claims derived from seed notes are marked through `source_type: seed_notes`, `confidence: low`, and an explicit seed/non-final `source_span`.
- Missing source material is recorded as an evidence gap, not silently ignored.

Fail conditions:

- Claims appear without source attribution.
- The report makes claims stronger than the source material supports.
- Seed notes are presented as equivalent to final primary sources.

### 2. Structure

The prototype must preserve the shape of the argument.

Pass conditions:

- Seed mode includes candidate relations only when the relation rationale states the textual basis or why the relation is tentative.
- Source-grounded mode includes multiple relation types where supported by source material.
- Similar-but-not-identical claims are preserved as separate claims or explicitly grouped with distinctions.
- Support, challenge, dependency, refinement, tension, and crux candidates are represented when present.
- The report exposes relations in a navigable way, not only a prose summary.

Fail conditions:

- The map collapses disagreement into a single consensus statement.
- It omits caveats that matter to the investigation.
- It treats all related claims as identical.

### 3. Assessment

The prototype must help a reviewer decide what to inspect next.

Pass conditions:

- The output includes at least three case-specific open questions.
- Each open question links to at least one claim ID or source ID unless the gap is explicitly "missing source needed."
- The output identifies likely cruxes or explains why cruxes remain unknown.
- The audit names missing source types or perspectives.
- The report distinguishes settled claims from unresolved or weakly supported claims.

Fail conditions:

- The output performs false closure.
- The report says the case is resolved without showing dependencies or remaining uncertainties.
- Missing evidence is absent from the artifact.

### 4. Compounding

The artifact must be reusable by another investigator.

Pass conditions:

- JSON output validates against the schema.
- Markdown output is readable without running code.
- IDs are stable enough for review comments and follow-up edits.
- The artifact can be extended without recomputing the whole case from scratch.
- Two consecutive deterministic builds produce the same source IDs, claim IDs, relation IDs, and open-question IDs.

Fail conditions:

- The only useful output is a one-off narrative.
- Claim IDs or source IDs are unstable across deterministic reruns.
- There is no documented way to add a source and regenerate the map.

### 5. Judge-Facing Usability

The prototype must be easy for a competition judge to inspect quickly.

Pass conditions:

- `report.md` has a concise top-level summary.
- The report lists sources, claims, relations, open questions, and audit notes.
- The report points to the highest-value regions of the artifact.
- `audit.md` maps the artifact to FLF criteria.

Fail conditions:

- A reviewer must read raw JSON first to understand the artifact.
- The report lacks a clear explanation of how the prototype improves reasoning.
- The artifact is technically valid but not navigable.

## Engineering Criteria

### 1. Scope Control

Pass conditions:

- The goal modifies only files relevant to the target prototype slice.
- Any deferred work is recorded with owner, reason, risk, and next action.
- No unrelated cleanup or broad refactor is mixed into the run.

Fail conditions:

- The run touches unrelated projects or archived harness material.
- The run changes behavior outside the target case-map workflow without explanation.

### 2. Verification

At minimum, the goal must verify setup and run:

```bash
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
PYTHONPATH=src ./.venv/bin/python -m pytest -q
PYTHONPATH=src ./.venv/bin/python scripts/build_case_map.py --case data/cases/<case_id>/case.yaml
```

If a local virtual environment already exists, the goal may reuse it and record that choice. The fast verification equivalent is:

```bash
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 scripts/build_case_map.py --case data/cases/<case_id>/case.yaml
```

If new validation scripts are added, the goal must document and run them.

Pass conditions:

- Tests pass.
- Case-map generation succeeds.
- Generated JSON can be loaded and validated by the Pydantic schema.
- Curated snapshots under `examples/<case_id>/` are created or refreshed when the goal claims a judge-facing demo.
- The validation command checks artifact completeness, deterministic ID stability, and snapshot parity.
- The final response records exact commands run and outcomes.

Fail conditions:

- Verification is skipped.
- Failures are ignored or only described vaguely.
- The final report cannot be regenerated.
- Checked-in examples are not compared against regenerated artifacts.

### 2a. Artifact Completeness

The validation command must check these minimum fields and counts for a demo artifact:

- case ID is present,
- evidence mode is present in metadata or audit output,
- review status is present in metadata or audit output,
- at least one source exists,
- at least one claim exists,
- at least three case-specific open questions exist,
- each claim has `claim_id`, `text`, `source_id`, `confidence`, and `source_span`,
- each relation has `relation_id`, source and target claim IDs, relation type, and rationale,
- audit output includes a scoring table or equivalent structured criteria assessment,
- generated report and audit files exist.

For source-grounded mode, validation must additionally check:

- each web-acquired source has a retrieval date,
- each source-grounded claim has a source-local span or excerpt marker,
- audit output distinguishes direct source claims from inferred relations.

### 3. Diagnostics

Pass conditions:

- Validation failures include the case ID, source ID or claim ID when applicable, artifact path, failure category, and suggested next action.
- Warnings are distinguished from blocking failures.

Fail conditions:

- Errors are opaque, such as "invalid output" without a path or object ID.

### 4. Runtime Budget

Pass conditions:

- The fast verification path should complete in under 60 seconds on the local repo for the starter prototype.
- Longer source-ingestion or LLM-assisted runs must be separated from the fast validation path.

Fail conditions:

- Routine verification depends on slow, network-bound, or nondeterministic calls without a cached artifact or explicit deep-run mode.

## Plan Quality Criteria

For substantial changes, Codex must maintain a checked-in plan or progress log.

Required sections:

- Goal.
- Non-goals.
- Current inventory.
- Bounded slices.
- Progress.
- Decisions.
- Surprises and discoveries.
- Verification.
- Residual risks.
- Deferred work.

Pass conditions:

- Every slice has a verification command.
- Every stopping point updates progress.
- Every incomplete subsystem is finished, removed, or recorded in deferred work.
- The plan names the final command or artifact proving completion.

Fail conditions:

- The plan is only a strategy note.
- The plan lacks stopping conditions.
- The plan lets Codex stop halfway while appearing done.

## Launch Checklist

Do not start a Codex `/goal` run until each item passes.

- [ ] Target case is named.
- [ ] Required docs to read are named.
- [ ] Desired artifacts are named.
- [ ] Non-goals are named.
- [ ] Verification commands are named.
- [ ] Stopping condition is explicit.
- [ ] Progress log or plan file path is specified.
- [ ] Source provenance rules are explicit.
- [ ] Generated artifact policy is explicit.
- [ ] Deferred-work policy is explicit.
- [ ] Evidence mode is explicit: seed mode or source-grounded mode.
- [ ] Web-use policy is explicit.
- [ ] Review status target is explicit: `draft`, `agent-reviewed`, `human-review-needed`, or `human-reviewed`.

## Done Checklist

A Codex `/goal` run can stop only when each item passes.

- [ ] Required inputs were inspected and summarized in the plan/progress log.
- [ ] Target artifacts were generated.
- [ ] Curated example snapshots exist under `examples/<case_id>/` if the goal claims a judge-facing demo.
- [ ] JSON artifact validates against the schema.
- [ ] Markdown report is navigable and judge-facing.
- [ ] Audit file maps output to FLF ingestion, structure, assessment, and compounding criteria.
- [ ] Claims preserve source IDs.
- [ ] Caveats, tensions, open questions, and missing evidence are visible.
- [ ] At least three open questions are case-specific and linked to claim/source IDs or explicit missing-source gaps.
- [ ] Seed-derived material is visibly labeled, or source-grounded material has recorded URLs/paths and source-local excerpts.
- [ ] Verification commands pass.
- [ ] Residual risks are recorded.
- [ ] Deferred work is specific and actionable.
- [ ] Artifact review status is no stronger than the actual review performed.
- [ ] Final response reports changed files, commands run, outcomes, and remaining risks.

## Review Status Policy

Use these statuses consistently in plans, reports, and audit files:

- `draft`: scaffolded output; not yet audited.
- `agent-reviewed`: reviewed by Codex against this criteria document.
- `human-review-needed`: ready for human review but not externally validated.
- `human-reviewed`: reviewed by the user or another human reviewer.

Codex may not mark an artifact `human-reviewed`. It must stop at `agent-reviewed` or `human-review-needed` unless a human explicitly provides review results in the repo or thread.

## Scoring Rubric

Use this rubric to decide whether the prototype is ready to show or needs another goal loop.

| Area | 0 | 1 | 2 |
| --- | --- | --- | --- |
| Ingestion | Claims lack provenance. | Claims have source IDs but weak span/source detail. | Claims, sources, and gaps are clearly attributed and auditable. |
| Structure | Mostly prose summary. | Some relations exist but are incomplete or hard to inspect. | Relations preserve support, challenge, dependency, similarity, tension, and crux structure where relevant. |
| Assessment | No clear next investigation. | Open questions exist but are generic. | Cruxes, missing evidence, uncertainty, and next inspections are concrete. |
| Compounding | One-off artifact. | Reusable JSON exists but extension path is unclear. | Stable schema, IDs, regeneration commands, and extension workflow are clear. |
| Judge usability | Hard to inspect. | Understandable with effort. | Quickly navigable with clear pointers and audit mapping. |
| Verification | Not run or not reproducible. | Basic tests run. | Tests, build, validation, and artifact audit are documented and repeatable. |
| Plan discipline | No living plan. | Plan exists but weak progress/decision logging. | Plan records progress, decisions, surprises, verification, residual risks, and deferred work. |

Operational scoring rule:

- Score 0 if any fail condition in that area is present.
- Score 1 if pass conditions are partially met but at least one required subcheck is missing.
- Score 2 only if every pass condition in that area is satisfied and evidence is cited in `audit.md`.
- If the score depends on human judgment, `audit.md` must name the judgment and the evidence used.

Minimum showable score:

- No area may score 0.
- At least four areas should score 2.
- Ingestion, structure, and verification must each score 2 before treating the artifact as a serious FLF demo.
- A seed-mode artifact may be shown as a workflow scaffold, but not as a source-grounded FLF demo.

## Recommended Goal Sequence

Use multiple bounded goals rather than one broad goal.

1. Goal 1: Make the LHC worked example credible and auditable.
2. Goal 2: Add validation and audit tooling so artifacts can be scored repeatedly.
3. Goal 3: Apply the workflow to eggs and compare where the structure differs.
4. Goal 4: Prepare the judge-facing submission package with curated pointers.
5. Goal 5: Optionally add a narrow COVID origins slice only if the first two cases are solid.

## Stop Rules

Codex must stop and report rather than continue if:

- source evidence is insufficient to make a claim without invention,
- tests fail and the failure cannot be resolved within the current slice,
- the goal requires new external data not available in the repo and web use is not explicitly authorized,
- artifact generation becomes nondeterministic without an explicit reason,
- implementation requires a major schema redesign not covered by the goal,
- the work would spill into a second case before the first case passes the done checklist.

## Practical Next Step

Before launching the first `/goal`, finish the remaining goal infrastructure:

- `AGENTS.md` with repo-specific Codex instructions,
- `.agent/PLANS.md` or `docs/PLANS.md` for execution-plan discipline,
- a validation command or script that checks artifact completeness.

`docs/plans/lhc_demo_goal_plan.md` is the living plan for the first goal run. The remaining files will make the goal self-contained enough for Codex to execute without relying on chat history.
