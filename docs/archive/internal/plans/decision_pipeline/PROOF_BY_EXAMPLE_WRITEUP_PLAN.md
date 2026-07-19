# Proof-By-Example Write-Up Plan

Status: superseded by `docs/plans/INVESTIGATOR_CHALLENGE_DEMONSTRATION_PLAN.md`, which treats the end-to-end investigator task as the primary demonstration and this proof packet as one downstream artifact.

## Goal

Turn `docs/EPISTEMIC_CASE_MAPPER_WRITEUP.md` into a judge-facing argument whose major claims are backed by examples a judge can inspect or commands a judge can run.

The submission will not claim formal scientific validation. It will show a narrower form of evidence: source-grounded worked examples, blinded synthesis comparators, a local-update demonstration, explicit failure detection, and reproducibility checks.

## Non-Goals

- Do not claim independent scientific, domain-expert, or human validation.
- Do not acquire new sources or change the case conclusions.
- Do not change schemas, mapping behavior, or the decision-memo pipeline.
- Do not touch unrelated modified files in the working tree.
- Do not treat artifact counts or passing tests as evidence of epistemic correctness.

## Design Principles

- Every central claim must point to an inspectable artifact or runnable demonstration.
- Lead with the smallest example that makes the reasoning benefit visible.
- Distinguish pipeline validity from reasoning usefulness.
- Report what a demonstration establishes and what it does not establish together.
- Prefer the existing generic validators and manifest-driven case discovery over case-specific machinery.

## Required-Reading Implications

- `README.md`: keep decision-space erosion as the central contribution and make the runnable judge path short.
- `docs/archive/internal/WORKFLOW_SPEC.md`: preserve ingestion, structure, assessment, and synthesis as separate responsibilities.
- `docs/protocols/epistemic_case_map_v0.md`: stable IDs, traceable claims, typed relations, and extension without restart are the review standard.
- `docs/archive/internal/CODEX_GOAL_FLF_PROTOTYPE_CRITERIA.md`: checked-in evidence and exact verification commands are required; transient chat results are insufficient.
- `docs/reference/flf_epistemic_case_study_competition_criteria.md`: directly answer whether the approach helps reasoning, generalizes, scales, and compounds.
- `docs/reference/flf_judging_rubric.md`: compare against capable baselines and keep adversarial and methodological limits visible.
- `docs/archive/internal/plans/flf_winning_submission_worked_regions_plan.md`: reuse the curated LHC and eggs regions and blinded baselines; do not inflate their review status.
- `docs/archive/internal/plans/lhc_demo_goal_plan.md`: the LHC demonstration must expose the velocity/trapping dependency, not merely restate the safety conclusion.
- The three `data/cases/*/case.yaml` files: use the existing source-grounded corpora and keep COVID explicitly bounded as a narrow slice.

## Workstreams

1. Proof packet
   - Add `docs/PROOF_BY_EXAMPLE.md` with embedded LHC, eggs, and COVID examples.
   - Include multi-model comparison, local update, integrity-failure, and reproducibility demonstrations.

2. Runnable experiment
   - Add `scripts/run_proof_by_example.py`.
   - Run existing worked-region, blinded-baseline, update-demo, export, and judge-path validators.
   - Inject an invalid source reference into a temporary artifact and require the validator to reject it with an object-level diagnostic.
   - Write a timestamped JSON and Markdown run record under `artifacts/proof_by_example/`.

3. Write-up revision
   - Embed the strongest before/after example near the front.
   - Replace vague uplift language with demonstrated, bounded findings.
   - Add an evidence ledger, operational demo command, and direct answers to FLF's four judge questions.
   - Preserve limitations next to the corresponding evidence.

4. Package integration
   - Add the proof packet to the submission manifest's judge, required-document, and reference-scan lists.
   - Link it from the main orientation documents.

## Verification

- `PYTHONPATH=src python3 scripts/run_proof_by_example.py`
- `PYTHONPATH=src python3 scripts/run_flf_demo.py --skip-build`
- `PYTHONPATH=src python3 scripts/reproducibility_gate.py --include-worked-regions --include-blinded-baselines`
- `PYTHONPATH=src python3 -m pytest -q`
- `git diff --check`

## Acceptance Criteria

- A judge can see the core LHC reasoning gain without opening another document.
- Each case example names stable claim/relation IDs and links to its source-grounded map.
- The proof runner passes all clean controls and detects the injected invalid source reference.
- The write-up distinguishes demonstrated artifact behavior from untested human usefulness and domain correctness.
- No claim of formal, independent, or human review is introduced.
- Unrelated working-tree changes remain untouched.

## Progress

- [x] Required repository and competition context read.
- [x] Existing demonstrations and validators inventoried.
- [ ] Proof packet and runner implemented.
- [ ] Demonstrations executed and results recorded.
- [ ] Write-up revised.
- [ ] Final gates passed.

## Residual Risks

- The erosion audits remain agent-authored and need judge scrutiny.
- Blinded baselines are span-limited, not full-corpus deep-research runs.
- Validator mutation experiments demonstrate inspectable failure, not semantic correctness.
- No second operator or external domain reviewer has evaluated the workflow.

## Deferred Work

- Owner: future investigator
  Reason: a second-operator fresh-case run is not available before this submission revision.
  Risk: transfer and review-cost claims remain plausible rather than demonstrated.
  Next action: run a predeclared unseen case and record operator time, revisions, and disagreements.
