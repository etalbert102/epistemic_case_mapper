# Code Generalizability Plan

Status: `implemented`

Purpose: record the implementation path that made adding a fourth case or worked region a data/config operation, not a Python-code-edit operation.

## Goal

The code should be considered generalizable when adding a new worked region requires:

- adding source/docs artifacts,
- adding one manifest entry,
- running generators and validators,

and does not require modifying Python constants, regexes, UI case lists, review checklist priorities, or baseline config dictionaries.

## Phase 1: Define One Canonical Manifest

Create `submission_manifest.yaml` as the single source of truth for:

- cases,
- worked regions,
- full-case scaffolds,
- baselines,
- UI inclusion,
- review packet paths,
- source subsets,
- ID prefixes,
- validation thresholds,
- priority review items.

Example shape:

```yaml
cases:
  - case_key: lhc
    case_id: lhc_black_holes
    case_path: data/cases/lhc_black_holes/case.yaml
    label: LHC Black Hole Risk
    ui:
      include: true
      theme: risk
    worked_regions:
      - region_id: lhc_cosmic_ray_argument
        id_prefix: lhc
        map_path: examples/lhc_black_holes/worked_region_cosmic_ray_map.md
        audit_path: examples/lhc_black_holes/decision_space_erosion_audit.md
        baseline_path: examples/lhc_black_holes/flat_synthesis_baseline.md
        required_sources:
          - lsag_2008_safety_review
        thresholds:
          min_claims: 8
          max_claims: 35
          min_losses: 3
```

Acceptance test: no validator has hard-coded `lhc`, `eggs`, or `covid` region lists outside the manifest loader.

## Phase 2: Centralize Manifest Loading

Add `src/epistemic_case_mapper/submission_manifest.py`.

Responsibilities:

- parse `submission_manifest.yaml`,
- validate config schema with Pydantic or dataclasses,
- expose helpers:
  - `iter_cases()`,
  - `iter_worked_regions()`,
  - `iter_ui_cases()`,
  - `iter_full_case_scaffolds()`,
  - `iter_review_priorities()`,
  - `collect_known_ids()`.

Acceptance test: `artifact_utils.REGION_FILES`, `validate_worked_regions.REGIONS`, `build_ui_data.CASES`, and similar constants are removed or replaced by manifest-derived objects.

## Phase 3: Generalize ID Validation

Replace hard-coded regexes in `scripts/validate_submission_references.py`.

Current issue: the validator only recognizes `lhc_*`, `eggs_*`, and `covid_*` IDs.

New behavior:

- collect all claim, relation, and loss IDs from manifest-declared worked maps and audits,
- scan docs for backticked IDs matching configurable ID forms,
- validate any ID with a known prefix from the manifest,
- optionally warn on unknown-but-ID-shaped references.

Acceptance test: add a synthetic region with prefix `demo`; reference `demo_c999` in a doc; the validator must fail.

## Phase 4: Generalize Worked-Region Validation

Move all thresholds into the manifest:

- min/max claim count,
- min relation types,
- min crux mentions or crux section rows,
- min erosion losses,
- required source IDs,
- required sections,
- whether baseline is required,
- whether audit is required.

Avoid global assumptions like "every worked region needs 12-25 claims" or "every audit needs five losses."

Acceptance tests:

- a small worked region with 6 claims can pass if the manifest says `min_claims: 5`,
- a large worked region with 40 claims can pass if the manifest says `max_claims: 50`.

## Phase 5: Make UI Case Selection Configurable

Change `scripts/build_ui_data.py` to read manifest UI settings:

- include/exclude cases by config,
- support full-case and worked-region-only cases,
- support cases without task queues,
- support optional spotlights.

Change `scripts/validate_ui.py`:

- expected case count comes from the manifest,
- required fields depend on included case capabilities,
- no hard-coded `len(cases) == 2`.

Acceptance test: mark COVID `ui.include: true`, regenerate `ui/data.json`, and have the UI validator expect three cases.

## Phase 6: Generalize Baseline Generation

Move `scripts/run_blinded_baselines.py` config into the manifest or a dedicated `baselines.yaml`.

Each baseline config should include:

- case key,
- region ID,
- question,
- output path template,
- model label,
- source spans,
- required source IDs.

Add validation:

- every span path exists,
- every line range is in bounds,
- every required source has at least one span or explicit reason,
- output path is derived deterministically.

Acceptance tests:

- adding a baseline for a synthetic case requires no Python code edit,
- invalid line span fails before model invocation.

## Phase 7: Generalize Human Review Checklist

Move `PRIORITIES` out of `scripts/build_tier1_review_checklist.py`.

Manifest options:

```yaml
review:
  priority_claim_ids:
    - lhc_c004
  priority_relation_ids:
    - lhc_r003
  priority_loss_ids:
    - lhc_loss_001
  selection_strategy: explicit
```

Later support automatic selection:

- first N claims by role,
- all crux relations,
- all losses marked highest severity,
- random sample with seed.

Acceptance tests:

- a new case with explicit priority IDs appears in the generated CSV,
- missing priority ID fails clearly.

## Phase 8: Separate Submission Package From Reusable Engine

Keep contest-specific docs and paths, but isolate them.

Suggested structure:

- `src/epistemic_case_mapper/`: reusable schema, manifest loader, parsers, validators,
- `scripts/`: thin CLI wrappers,
- `submission_manifest.yaml`: current FLF package config,
- `docs/`: current submission docs.

This makes clear:

- the engine is general,
- the current submission is one configured package.

Acceptance test: reusable tests create a temp manifest and temp worked region without touching FLF docs.

## Phase 9: Improve Starter Mapper Generality

Keep current deterministic extraction, but stop treating it as a strong mapper for arbitrary cases.

Improvements:

- support configurable claim markers per case,
- support configurable open-question templates,
- derive open questions from `case_type`, source metadata, and missing relation classes,
- allow manifest-defined crux prompts,
- expose starter quality warnings.

Acceptance test: a new `case_type: mundane_policy` gets open questions about intervention, outcomes, confounding, implementation context, and missing stakeholders without code edits.

## Phase 10: Add A Synthetic Transfer Test

Create a synthetic transfer fixture in `tests/test_submission_manifest_generalization.py` with:

- tiny `case.yaml`,
- 2-3 source files,
- one worked map,
- one baseline,
- one erosion audit,
- custom ID prefix such as `demo_c001`.

Test that:

- the manifest loader sees it,
- validators pass,
- JSON export includes it,
- ID references are validated,
- UI includes or excludes it according to config,
- checklist generation handles it.

This is the critical proof that the system is not fitted only to LHC, eggs, and COVID.

## Phase 11: Update Documentation

Add `docs/ADDING_A_CASE.md`.

It should explain:

1. add source corpus,
2. write `case.yaml`,
3. add manifest entry,
4. add worked-region files,
5. configure thresholds,
6. configure baseline spans,
7. run validators,
8. optionally include in UI,
9. optionally add review priorities.

Acceptance test: a new contributor can add a fixture case by following only this doc.

## Phase 12: Final Validation Commands

Target final command set:

```bash
PYTHONPATH=src python3 scripts/validate_submission_manifest.py
PYTHONPATH=src python3 scripts/validate_worked_regions.py
PYTHONPATH=src python3 scripts/validate_submission_references.py
PYTHONPATH=src python3 scripts/export_worked_region_json.py --check
PYTHONPATH=src python3 scripts/build_ui_data.py --check
PYTHONPATH=src python3 scripts/build_tier1_review_checklist.py --check
PYTHONPATH=src python3 scripts/reproducibility_gate.py --include-worked-regions
PYTHONPATH=src python3 -m pytest -q
```

## Implemented Order

1. Added manifest schema and loader.
2. Migrated `scripts/artifact_utils.py` and JSON export.
3. Migrated `scripts/validate_worked_regions.py`.
4. Migrated `scripts/validate_submission_references.py`.
5. Migrated UI, summaries, full-case checks, realism checks, review checklist, blinded baseline config, and the reproducibility gate.
6. Added `scripts/validate_submission_manifest.py`.
7. Added a synthetic fourth-case transfer test.
8. Added `docs/ADDING_A_CASE.md`.

## Done Definition

The code is fully generalizable when adding a new worked region requires one manifest entry plus artifacts, and the existing validation/export/review/UI scripts discover and check that region without Python changes.
