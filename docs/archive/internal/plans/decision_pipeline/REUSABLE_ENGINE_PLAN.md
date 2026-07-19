# Reusable Engine Plan

Status: `implemented`

Purpose: turn `epistemic_case_mapper` from a strong FLF submission package into a reusable engine for arbitrary epistemic-map packages.

## Target State

A new package should need only:

- a package manifest,
- case manifests and source files,
- worked-region artifacts,
- optional UI, review, and baseline config,
- commands such as `ecm validate --package path/to/package.yaml`.

It should not require Python edits, submission-specific path constants, hard-coded LHC/Eggs/COVID examples, or implicit one-worked-region-per-case assumptions.

## Phase 1: Define The Package Boundary

Separate:

- `src/epistemic_case_mapper/`: reusable engine,
- current repo root or a future `packages/flf_submission/`: one configured package,
- `scripts/`: compatibility wrappers and command-line entry points,
- `ui/`: reusable shell driven by package data.

Acceptance test: a temporary package outside the FLF content tree can pass a package manifest to engine validators.

## Phase 2: Promote Manifest To Engine Contract

Extend the manifest from submission-specific config into a package contract:

- `package_id`,
- `package_label`,
- `schema_version`,
- `judge_paths`,
- `required_docs`,
- `reference_scan_paths`,
- `cases`,
- `worked_regions`,
- `ui`,
- `review`,
- `baselines`,
- `validation_profiles`.

The current nested case shape can remain supported, but engine helpers should expose region- and baseline-keyed views.

Acceptance test: two worked regions under one case are both discoverable and neither overwrites the other.

## Phase 3: Make Region IDs The Operational Unit

Cases own source corpora. Regions own maps, audits, baselines, review priorities, and exports.

Commands should support:

```bash
ecm validate region --package package.yaml --region demo.region_a
ecm baseline run --package package.yaml --region demo.region_a
ecm export region --package package.yaml --region demo.region_a
```

Compatibility flags such as `--case` may remain, but should expand to all regions for that case.

## Phase 4: Make ID Grammar Configurable

The current default recognizes:

- `{prefix}_c001`,
- `{prefix}_r001`,
- `{prefix}_loss_001`.

Engine packages should be able to define alternate ID regexes without Python edits.

Acceptance test: a fixture using IDs like `claim:demo:001` validates.

## Phase 5: Generalize Artifact Parsers

Keep markdown key-value blocks as `markdown_kv_v1`, but define parser adapters:

- `markdown_kv_v1`,
- `json_case_map_v1`,
- future YAML or database-backed formats.

Acceptance test: two fixture regions use different artifact formats and share the same validator interface.

## Phase 6: Separate Engine Validators From Package Profiles

Reusable validators:

- schema validity,
- path existence,
- source membership,
- ID reference integrity,
- claim/source grounding fields,
- relation endpoint validity,
- audit loss fields,
- baseline isolation,
- UI data consistency.

Package profiles configure:

- minimum claim counts,
- required sections,
- required audit fields,
- baseline requirements,
- review packet requirements.

Acceptance test: a non-FLF package can disable `BEST_REGIONS.md` and pass under its own profile.

## Phase 7: Make UI Fully Data-Driven

Remove hard-coded UI hero references to the current LHC example.

Manifest/UI data should provide:

- hero title,
- flat example,
- mapped example,
- links,
- case tabs,
- one or more worked regions per case.

Acceptance test: a synthetic package produces UI data and static UI without LHC strings.

## Phase 8: Add Complete Multi-Region Support

Update model and scripts so:

- a case can contain many regions,
- a region can contain many baselines,
- baselines are keyed by `baseline_id`,
- UI can show multiple anchors for a case,
- review checklist generation can include multiple regions per case.

Acceptance test: one case with two worked regions generates two JSON exports, two baseline configs, and two review sections.

## Phase 9: Build A Baseline Engine

Baseline config should be explicit:

```yaml
blinded_baseline:
  baseline_id: demo.region_a.gemma
  question: ...
  output_path: ...
  spans: ...
```

Support:

- region selection,
- case selection as a grouping convenience,
- dry-run prompt rendering,
- span validation,
- deterministic output labels.

## Phase 10: Add An Engine CLI

Add `ecm` commands:

```bash
ecm validate package --package package.yaml
ecm validate region --package package.yaml --region demo.region_a
ecm export json --package package.yaml
ecm ui build --package package.yaml
ecm baseline prompt --package package.yaml --baseline demo.region_a.gemma
ecm review checklist --package package.yaml
```

Old scripts can remain wrappers while tests move to the CLI.

Implementation: `ecm` and `scripts/ecm.py` expose `package prepare`, `validate package`, `validate region`, `export json`, `export region`, `ui build`, `baseline prompt`, `baseline run`, `review checklist`, and `quality init/check/gate` as package-manifest-oriented commands.

## Phase 11: Add Package Fixtures

Fixture packages should cover:

1. single markdown region,
2. multiple regions under one case,
3. custom ID grammar,
4. UI enabled with no full-case scaffold,
5. full-case plus task queue,
6. two blinded baselines,
7. JSON artifact format,
8. invalid reference negative case.

Coverage lives in `tests/test_submission_manifest_generalization.py`. The fixture builds a temporary package with multiple regions under one case, custom ID grammar, UI enabled without FLF strings, full-case scaffold, task queue, two markdown regions, one JSON region, multiple blinded baselines, review checklist generation, region export, baseline dry-run, and an invalid-reference negative check.

## Phase 12: Documentation

Implemented docs:

- `docs/ENGINE_ARCHITECTURE.md`
- `docs/PACKAGE_MANIFEST_SPEC.md`
- `docs/ARTIFACT_FORMATS.md`
- `docs/VALIDATION_PROFILES.md`
- `docs/MIGRATING_FLF_SUBMISSION.md`

Keep FLF submission docs separate from reusable engine docs.

## Done Definition

The engine is reusable when this works:

```bash
ecm validate package --package /tmp/arbitrary_epistemic_package/package.yaml
ecm export json --package /tmp/arbitrary_epistemic_package/package.yaml
ecm ui build --package /tmp/arbitrary_epistemic_package/package.yaml
```

And the package:

- has no LHC/Eggs/COVID content,
- has two regions under one case,
- uses a non-default ID grammar,
- enables UI,
- has at least one blinded baseline,
- passes without Python edits.

This done definition is covered by the synthetic transfer fixture and the `ecm` command tests.
