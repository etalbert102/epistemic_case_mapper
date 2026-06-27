# FLF Winning Submission Worked Regions Plan

This is the living plan for turning the current source-grounded scaffold into a credible FLF contest prototype.

Use with:

```text
/goal Execute docs/plans/flf_winning_submission_worked_regions_plan.md. Keep the plan updated as the living source of truth. Stop only when the LHC and eggs worked regions each have source-grounded maps, before/after flat-synthesis comparisons, audit notes, curated judge pointers, validation passing, and explicit residual risks.
```

## Goal

Turn the current source-grounded scaffold into a credible FLF submission prototype by creating two high-quality worked regions:

- LHC: cosmic-ray / microscopic-black-hole safety argument.
- Eggs: observational CVD evidence vs randomized lipid-marker evidence.

The output should demonstrate that structured case maps preserve decision-relevant structure that ordinary flat synthesis loses.

## Non-Goals

- Do not map the entire source corpus exhaustively.
- Do not add new cases.
- Do not build a UI.
- Do not claim human review unless a human actually reviews it.
- Do not optimize for volume of extracted claims.
- Do not add new source documents unless a blocker is recorded and the user authorizes acquisition.

## Required Reading

Record at least one concrete implication from each input before implementation edits.

- [x] `AGENTS.md`
- [x] `README.md`
- [x] `docs/CODEX_GOAL_FLF_PROTOTYPE_CRITERIA.md`
- [x] `docs/reference/flf_epistemic_case_study_competition_criteria.md`
- [x] `docs/WORKFLOW_SPEC.md`
- [x] `docs/protocols/epistemic_case_map_v0.md`
- [x] `docs/plans/lhc_demo_goal_plan.md`
- [x] `docs/plans/flf_workspace_enhancement_backlog.md`
- [x] `data/cases/lhc_black_holes/case.yaml`
- [x] `data/cases/lhc_black_holes/sources/SOURCE_INVENTORY.md`
- [x] `data/cases/eggs/case.yaml`
- [x] `data/cases/eggs/sources/SOURCE_INVENTORY.md`
- [x] `examples/lhc_black_holes/`
- [x] `examples/eggs/`

## Reading Notes

- `AGENTS.md`: Keep source provenance, disagreement, and review status above fluent summary quality; do not claim human review.
- `README.md`: The prototype's central claim is decision-space erosion, so worked examples must show structure preserved beyond a one-off narrative.
- `docs/CODEX_GOAL_FLF_PROTOTYPE_CRITERIA.md`: The goal must produce checked-in artifacts, pass commands, and record residual risks; transient chat output is not enough.
- `docs/reference/flf_epistemic_case_study_competition_criteria.md`: FLF judges care about reasoning help, generalization, scaling with AI/compute, and compounding across investigators.
- `docs/WORKFLOW_SPEC.md`: The artifact should separate ingestion, structure, and assessment rather than blending them into a summary.
- `docs/protocols/epistemic_case_map_v0.md`: Stable IDs and explicit relation types are part of the reusable protocol.
- `docs/plans/lhc_demo_goal_plan.md`: The LHC case should emphasize dependency structure and public-risk caveats, not just the conclusion that the LHC was safe.
- `docs/plans/flf_workspace_enhancement_backlog.md`: The risk-reduction additions are implemented; the next goal should use templates and validators rather than inventing format.
- `data/cases/lhc_black_holes/case.yaml`: The fixed LHC worked-region source subset is available locally; no web acquisition is needed.
- `data/cases/lhc_black_holes/sources/SOURCE_INVENTORY.md`: LHC sources include formal safety review, independent review, technical analysis, critique, response, public explanation, and later empirical context.
- `data/cases/eggs/case.yaml`: The fixed eggs source subset is available locally; no web acquisition is needed.
- `data/cases/eggs/sources/SOURCE_INVENTORY.md`: Eggs sources include guideline context, cohort/meta-analysis evidence, RCT lipid-marker evidence, and scoping-review context.
- `examples/lhc_black_holes/`: Existing generated artifacts are heuristic drafts; the goal must create curated worked-region files instead of treating the generated report as final.
- `examples/eggs/`: Existing generated artifacts are heuristic drafts; the goal must create curated worked-region files instead of treating the generated report as final.

## Current Inventory

- LHC source subset:
  - Required: `lsag_2008_safety_review`, `spc_2008_lsag_review`, `giddings_mangano_2008_stable_black_holes`, `plaga_2008_metastable_black_holes`, `giddings_mangano_2008_comments_plaga`.
  - Optional context only: `cern_lhc_current_page`, `cern_tiny_black_holes_page`, `johnson_2009_black_hole_case`.
- Eggs source subset:
  - Required: `dga_2020_2025_pmc_summary`, `aha_2019_dietary_cholesterol_pubmed`, `aha_2023_dietary_cholesterol_news`, `bmj_2020_egg_consumption_cvd`, `jama_2019_dietary_cholesterol_eggs`, `li_2020_egg_cholesterol_rct_meta`, `nnr_2023_eggs_scoping_review`.
  - Optional context only: `bmj_2013_egg_consumption_chd_stroke`, `ma_2021_egg_cvd_dose_response`, `huang_2020_egg_health_outcomes_evidence_mapping`.
- Current mapper/report limitations:
  - Generated `case_map.json` files contain heuristic candidate claims and seed similarity relations.
  - Worked-region maps must be curated manually/agentically from source excerpts rather than copied wholesale from generated reports.
  - Human review has not occurred; keep review status no stronger than `human-review-needed`.
- Existing validation support:
  - `scripts/validate_case_artifact.py` validates generated case artifacts.
  - `scripts/reproducibility_gate.py` validates scaffold reproducibility.
  - `scripts/validate_worked_regions.py` validates final worked-region artifacts and intentionally fails until templates are filled.
- Files that will be touched:
  - `docs/worked_regions/*.md`
  - `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`
  - `examples/lhc_black_holes/flat_synthesis_baseline.md`
  - `examples/lhc_black_holes/decision_space_erosion_audit.md`
  - `examples/lhc_black_holes/BEST_REGIONS.md`
  - `examples/eggs/worked_region_observational_vs_rct_map.md`
  - `examples/eggs/flat_synthesis_baseline.md`
  - `examples/eggs/decision_space_erosion_audit.md`
  - `examples/eggs/BEST_REGIONS.md`
  - `docs/FLF_JUDGE_WALKTHROUGH.md`
  - `docs/FLF_SUBMISSION_DRAFT.md`
  - `scripts/validate_worked_regions.py` only if validator bugs are found.
- Files that must not be touched:
  - Do not add new source files.
  - Do not modify raw source corpora unless a source-integrity bug is found.
  - Do not change schema or generated starter mapper unless the validator exposes a blocker.
  - Do not expand to COVID or regulatory tasks in this goal.

## Hard Risk-Reduction Constraints

- Do not add new sources.
- Do not build a UI.
- Do not expand to COVID or regulatory tasks.
- Do not claim human review.
- Do not use the generated heuristic reports as final curated maps.
- Do not count an erosion loss unless the lost item is supported by the same source subset, decision-relevant, preserved by the case map, and omitted or flattened by the baseline.
- Prefer fewer, stronger curated claims over filling the 25-claim upper bound.
- If the baseline was produced without isolation from the curated map, mark the baseline illustrative and disclose the limitation.

## Bounded Slices

### Slice 1: Define Worked Regions

Create:

- `docs/worked_regions/lhc_cosmic_ray_argument.md`
- `docs/worked_regions/eggs_observational_vs_rct.md`

Each worked-region definition must state:

- narrow question,
- source subset,
- why it matters,
- expected cruxes,
- what ordinary synthesis is likely to flatten.

Verification:

- Each region cites at least three relevant source IDs from the local corpus.
- Each cited source ID exists in the corresponding `case.yaml`.

### Slice 2: Build Curated Claim Maps

Create:

- `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`
- `examples/eggs/worked_region_observational_vs_rct_map.md`

Each map must include:

- 12-25 curated claims,
- source ID for every claim,
- source-local excerpt or span marker for every claim,
- a short excerpt for every claim,
- an explicit `entailed_by_excerpt: yes/no/uncertain` check for every claim,
- relation type for each link,
- relation rationale for every link,
- support/challenge/dependency/tension/crux links,
- similar-but-not-identical claim groupings.

Verification:

- No claim lacks a source ID.
- No relation lacks a rationale.
- No claim lacks a source-local excerpt.
- No claim marked `entailed_by_excerpt: no` is used as a supported claim; it must be revised or moved to an audit concern.
- Claims marked `entailed_by_excerpt: uncertain` are labeled as interpretation candidates.
- Each worked region has at least three relation types.
- Each worked region has at least two crux candidates.

### Slice 3: Add Flat-Synthesis Baselines

Create:

- `examples/lhc_black_holes/flat_synthesis_baseline.md`
- `examples/eggs/flat_synthesis_baseline.md`

Each baseline must be generated or written under a controlled baseline protocol:

- Use the same source subset as the worked-region map.
- Use a fixed prompt recorded at the top of the baseline file.
- The baseline prompt must ask for a normal concise synthesis of the source subset.
- The baseline generation/writing pass must not inspect the curated claim map or decision-space erosion audit first.
- If Codex cannot guarantee isolation inside the same run, it must write a `baseline_protocol_limitation` note and treat the baseline as illustrative rather than evaluative.

Baseline prompt:

```text
Using only the listed source excerpts for this worked region, write a concise synthesis that answers the region question for an informed reader. Preserve important caveats where they affect the answer, but do not create a structured claim map.
```

Create:

- `examples/lhc_black_holes/decision_space_erosion_audit.md`
- `examples/eggs/decision_space_erosion_audit.md`

Each erosion audit must identify at least five concrete losses, drawn from:

- omitted caveats,
- collapsed disagreements,
- hidden dependencies,
- missing cruxes,
- evidence treated too uniformly,
- source provenance weakened,
- population or context heterogeneity erased,
- similar-but-not-identical claims merged too aggressively.

Each loss must name what the case map preserves instead.

Each claimed loss must also include an adversarial check:

- Could the flat synthesis reasonably omit this because it was outside the baseline prompt or source subset?
- If yes, do not count it as an erosion loss.
- If uncertain, mark it as `borderline` and exclude it from the five required losses.
- Count only losses that survive the adversarial check.

### Slice 4: Judge-Facing Walkthrough

Create:

- `docs/FLF_JUDGE_WALKTHROUGH.md`
- `docs/FLF_SUBMISSION_DRAFT.md`
- `examples/lhc_black_holes/BEST_REGIONS.md`
- `examples/eggs/BEST_REGIONS.md`

The walkthrough must include:

- a 2-minute path through the LHC worked region,
- a 2-minute path through the eggs worked region,
- why the workflow helps reasoning,
- how artifacts can be extended,
- where the workflow still requires human judgment,
- limits and residual risks.

The submission draft must include:

- problem framing,
- workflow summary,
- artifact format,
- LHC worked-region summary,
- eggs worked-region summary,
- evidence that flat synthesis loses decision-relevant structure,
- limitations,
- install/run instructions,
- remaining human-review needs.

Each `BEST_REGIONS.md` must point to:

- strongest claim cluster,
- strongest relation cluster,
- strongest crux,
- strongest example of preserved caveat or disagreement,
- strongest flat-synthesis loss.

### Slice 5: Human Review Handoff

Create:

- `docs/HUMAN_REVIEW_CHECKLIST.md`

The checklist must let the user audit:

- source-excerpt fidelity,
- whether relation types are justified,
- whether cruxes are real,
- whether flat-synthesis losses are fair,
- whether the artifact is useful to reason with,
- whether any output overclaims review status or evidential certainty.

The goal must stop at `human-review-needed` unless the user explicitly provides review results.

### Slice 6: Validation And Audit

Update or add a mandatory worked-region validator so it checks:

- worked-region definition files exist,
- worked-region map files exist,
- flat-synthesis baseline files exist,
- decision-space erosion audit files exist,
- judge walkthrough exists,
- submission draft exists,
- best-region index files exist,
- human-review checklist exists,
- source IDs referenced in worked-region maps exist in case manifests,
- each worked-region map has 12-25 claims,
- each worked-region map has at least three relation types,
- each worked-region map has at least two crux candidates,
- every curated claim includes a source-local excerpt,
- no unsupported claim is used as a supported claim,
- each flat-synthesis audit has at least five concrete losses,
- each counted erosion loss includes an adversarial check and survives it,
- each worked region scores itself against FLF's four judge questions,
- examples still validate.

Required commands:

```bash
PYTHONPATH=src python3 -m pytest -q
PYTHONPATH=src python3 scripts/build_case_map.py --case data/cases/lhc_black_holes/case.yaml
PYTHONPATH=src python3 scripts/build_case_map.py --case data/cases/eggs/case.yaml
PYTHONPATH=src python3 scripts/validate_case_artifact.py --case data/cases/lhc_black_holes/case.yaml --examples examples/lhc_black_holes
PYTHONPATH=src python3 scripts/validate_case_artifact.py --case data/cases/eggs/case.yaml --examples examples/eggs
PYTHONPATH=src python3 scripts/validate_worked_regions.py
PYTHONPATH=src python3 scripts/reproducibility_gate.py --include-worked-regions
```

The worked-region validator is mandatory. If it cannot be implemented in this goal, stop and report the blocker rather than treating the plan as done.

## Success Threshold

Each worked region must answer FLF's four judge-facing questions:

1. Would this actually help someone reason better about this case?
2. Does it generalize?
3. Does it scale with improvements to AI or more compute?
4. Does it compound, with multiple people or teams building on each other's work?

For each question, record:

- score: `0`, `1`, or `2`,
- evidence from the worked-region artifacts,
- residual risk.

Showable threshold:

- No question may score `0`.
- At least three of the four questions must score `2` for each worked region.
- If a worked region misses threshold, the judge walkthrough must label it as a limitation rather than a successful demo.

## Progress

- [ ] Plan recorded.

## Decisions

- Decision: Focus the next goal on two excellent worked regions rather than broad corpus-wide mapping.
  Rationale: FLF judges need to see that the workflow improves reasoning, not just that it can ingest many documents.
  Date/Author: 2026-06-26 / Codex

## Surprises And Discoveries

Record unexpected source, artifact, or validation issues here.

## Verification Log

Record exact commands, timestamps, and outcomes here.

## Residual Risks

- Current source-grounded examples are still heuristic drafts.
- Human review has not occurred.
- The strongest contest submission likely needs a concise narrative in addition to artifacts.

## Deferred Work

Use this format:

- Owner:
  Reason:
  Risk:
  Next action:

## Done Checklist

- [ ] Required reading is complete and implications are recorded.
- [ ] LHC worked-region definition exists.
- [ ] Eggs worked-region definition exists.
- [ ] LHC curated worked-region map exists.
- [ ] Eggs curated worked-region map exists.
- [ ] LHC flat-synthesis baseline exists.
- [ ] Eggs flat-synthesis baseline exists.
- [ ] LHC decision-space erosion audit exists.
- [ ] Eggs decision-space erosion audit exists.
- [ ] Judge walkthrough exists.
- [ ] Submission draft exists.
- [ ] LHC best-regions index exists.
- [ ] Eggs best-regions index exists.
- [ ] Human review checklist exists.
- [ ] Each worked region has 12-25 curated claims.
- [ ] Each worked region has at least three relation types.
- [ ] Each worked region has at least two crux candidates.
- [ ] Every curated claim includes source-local excerpt and entailment check.
- [ ] Each baseline records the fixed prompt and source subset.
- [ ] Each erosion audit names at least five concrete losses that survive adversarial checks.
- [ ] Each worked region scores itself against FLF's four judge questions.
- [ ] Mandatory worked-region validator passes.
- [ ] LHC example validation passes.
- [ ] Eggs example validation passes.
- [ ] Tests pass.
- [ ] Residual risks are recorded.
- [ ] Review status is no stronger than `human-review-needed`.
