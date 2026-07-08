# Plan: Evidence Role Matrix For Maximal Context Use

## Objective
Make the briefing pipeline use source evidence maximally well without overwhelming the model. The end state is a reusable evidence role matrix that preserves every candidate card in an audit layer, exposes section-specific working sets to synthesis, allows the same evidence to serve different analytic roles across sections, and reports coverage gaps after synthesis.

## Current Gap
The current pipeline builds rich source cards, candidate evidence cards, canonical spine fields, and section packets, but section synthesis receives an aggressively compressed `owned_evidence` / `reference_only_evidence` view. This helps control prompt size, but it can drop useful source material, make evidence ownership too exclusive, and hide whether important cards were omitted because they were irrelevant, over budget, or assigned elsewhere.

## Non-Goals
- Do not increase model context by dumping the full map or full source corpus into every section prompt.
- Do not make final prose generation depend on manual review.
- Do not remove existing `owned_evidence` and `reference_only_evidence` fields in this slice; preserve compatibility while adding role-aware fields.
- Do not add domain-specific vocabulary or case-specific routing rules.
- Do not promote new coverage checks to hard blocking until they have report-only telemetry.

## Design Principles
- Deterministic code owns breadth, stable IDs, budgets, matrix construction, coverage accounting, and audit artifacts.
- The model owns section-local judgment and prose synthesis from a bounded packet.
- Evidence can be reused across sections when it serves a different analytic purpose.
- Every card that is not shown to a model should have an inspectable reason.
- Prompt inputs and validators should derive from the same section working set.
- New gates start report-only unless they protect an already-calibrated invariant.

## Fact Ownership
- `candidate_evidence_cards` owns the full source-grounded evidence inventory.
- `evidence_role_matrix` owns allowed section uses for each candidate card.
- `section_evidence_working_sets` owns the exact cards shown to each section model call.
- `section_context_acceptance_report` owns whether the section packet is suitable for synthesis.
- `evidence_role_coverage_report` owns post-packet coverage gaps and omitted-card reasons.

Downstream synthesis must consume `section_evidence_working_sets`; it should not rederive evidence eligibility from prose or map ordering.

## Workstreams
1. Record and wire matrix artifact
   - Purpose: make the role matrix a first-class structured artifact.
   - Changes: add a reusable builder that consumes candidate cards and section context packets, emits section uses (`load_bearing`, `contextual`, `contrast`, `boundary`, `do_not_use`) and compact section working sets.
   - Artifacts: `evidence_role_matrix.json`, `section_evidence_working_sets.json`.
   - Validation: focused unit tests for role assignment, reuse, omission reasons, and budgets.

2. Feed section synthesis from working sets
   - Purpose: let each model call see the right evidence without requiring global ownership exclusivity.
   - Changes: update `compile_model_section_packet` to prefer the section working set; preserve compatibility fields while adding `primary_evidence`, `contextual_evidence`, `contrast_evidence`, `boundary_evidence`, and `do_not_use_evidence`.
   - Artifacts: updated `section_synthesis_packets.json`.
   - Validation: prompt-contract tests prove model packet contains role-aware evidence and existing owned/reference fields remain stable.

3. Add report-only coverage telemetry
   - Purpose: make dropped high-value evidence visible after packet construction.
   - Changes: add `evidence_role_coverage_report` summarizing shown cards, omitted high-priority cards, per-section budget pressure, and cards reused for distinct section roles.
   - Artifacts: `evidence_role_coverage_report.json` and summary links.
   - Validation: unit tests for high-priority omitted-card warnings and non-fatal status.

4. Improve section prompt guidance
   - Purpose: make the model use the role matrix as an analytic planner rather than a list to restate.
   - Changes: update section rewrite prompt to reference role-aware evidence groups and section-specific value.
   - Artifacts: section debug prompts.
   - Validation: tests that generated prompts include the role matrix fields and no legacy-only instructions conflict.

5. All-up verification
   - Purpose: prove the change is integrated rather than just artifact-writing.
   - Commands: `python3 -m compileall -q src/epistemic_case_mapper tests`; `PYTHONPATH=src python3 -m pytest -q`.
   - Completion audit: update this plan with commits, tests, residual risks, and final status.

## Execution Protocol
- Execute in bounded slices.
- Commit after each verified slice.
- Stop if focused tests or full tests fail.
- Do not leave partial artifacts unreferenced by the run summary.
- Do not make report-only warnings blocking in this plan.

## Acceptance Criteria
- The scaffold contains `evidence_role_matrix`, `section_evidence_working_sets`, and `evidence_role_coverage_report`.
- Final review artifacts link the new structured reports.
- Section model packets consume the working sets and still expose compatibility fields.
- Important cards can appear in multiple sections with different roles.
- High-priority cards omitted from all section working sets are reported with reasons.
- Full test suite passes.

## Red-Team Checks
- If the matrix is only written but not used by synthesis, the plan fails.
- If evidence reuse causes repetitive prose without distinct section use, coverage telemetry should show repeated same-role reuse.
- If budgets hide important evidence, omitted-card telemetry should identify the card and reason.
- If validation and prompt context diverge, tests should fail because both read the same working set.

## Generalizability Checks
- Role assignment must use generic evidence metadata, not health, nutrition, policy, or contest-specific words.
- The matrix must work with arbitrary section names by falling back to generic roles.
- Tests should use synthetic non-domain examples.
- New artifacts should degrade gracefully when candidate cards or section packets are missing.

## Commit Ledger
- Pending: record plan.
- Pending: matrix artifact.
- Pending: model-packet integration.
- Pending: coverage telemetry and artifact links.
- Pending: all-up verification.
