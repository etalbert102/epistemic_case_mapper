# Adding A Case

Status: `implemented-guide`

This repository is configured through `submission_manifest.yaml`. A new case or worked region should require new artifacts plus one manifest entry, not Python edits.

## 1. Add The Source Corpus

Create a case directory under `data/cases/<case_id>/`.

For source-grounded work, put local source text under:

```text
data/cases/<case_id>/sources/text/
```

Use stable source IDs. They are the handles that claims, baselines, audits, and review packets will cite.

## 2. Write `case.yaml`

Create `data/cases/<case_id>/case.yaml` with:

- `case_id`
- `title`
- `question`
- `case_type`
- `evidence_mode`
- `review_status`
- `sources`

Optional `open_question_templates` let a case define starter-map questions without changing `starter_mapper.py`.

## 3. Add The Manifest Entry

Add a case entry to `submission_manifest.yaml`.

At minimum:

```yaml
cases:
  - case_key: demo
    case_id: demo
    label: Demo Case
    case_path: data/cases/demo/case.yaml
    ui:
      include: false
    worked_regions:
      - case_key: demo
        case_label: Demo Case
        region_id: demo_region
        id_prefix: demo
        definition_path: docs/worked_regions/demo_region.md
        map_path: examples/demo/worked_region_map.md
        audit_path: examples/demo/decision_space_erosion_audit.md
        baseline_path: examples/demo/flat_synthesis_baseline.md
        best_path: examples/demo/README.md
        output_json_path: examples/demo/worked_region_map.json
        required_sources:
          - demo_source_1
```

The `id_prefix` drives reference validation for IDs such as `demo_c001`, `demo_r001`, and `demo_loss_001`.

## 4. Add Worked-Region Artifacts

Add:

- a worked-region definition in `docs/worked_regions/`
- a worked map under `examples/<case_id>/`
- a flat baseline
- an erosion audit
- best-region sections in the case `README.md`

Claims must include source IDs, excerpts, and entailment checks. Relations and losses should use the same ID prefix declared in the manifest.

## 5. Configure Thresholds

Use manifest `thresholds` when the new region is smaller or larger than the current examples:

```yaml
thresholds:
  min_claims: 5
  max_claims: 50
  min_relation_types: 2
  min_losses: 2
```

This keeps validators case-appropriate without editing `scripts/validate_worked_regions.py`.

## 6. Configure Review Priorities

If the region should appear in generated review checklists, add explicit review IDs:

```yaml
review:
  worked_region_id: demo_region
  claim_ids: [demo_c001]
  relation_ids: [demo_r001]
  loss_ids: [demo_loss_001]
```

`scripts/validate_submission_manifest.py` fails if these IDs do not exist in the declared map or audit.

## 7. Configure Blinded Baseline Spans

If generating a blinded flat baseline, add `blinded_baseline` with source spans. The validator checks that every required source has spans and every line range is in bounds before model invocation.

## 8. Optional UI And Full-Case Settings

Set `ui.include: true` only when the case has enough artifacts to be useful in `ui/data.json`.

Optional case sections:

- `full_case`
- `task_queue`
- `ui.spotlights`

The UI builder and validator adjust expectations from the manifest.

## 9. Run Validators

```bash
PYTHONPATH=src python3 scripts/validate_submission_manifest.py
PYTHONPATH=src python3 scripts/validate_worked_regions.py
PYTHONPATH=src python3 scripts/validate_submission_references.py
PYTHONPATH=src python3 scripts/export_worked_region_json.py --check
PYTHONPATH=src python3 scripts/build_tier1_review_checklist.py --check
PYTHONPATH=src python3 scripts/build_ui_data.py --check
PYTHONPATH=src python3 scripts/reproducibility_gate.py --include-worked-regions
PYTHONPATH=src python3 -m pytest -q
```

For a narrow change, validate one region:

```bash
PYTHONPATH=src python3 scripts/validate_worked_regions.py --region demo_region
```

## 10. Transfer Test

`tests/test_submission_manifest_generalization.py` builds a temporary synthetic case with a custom `demo` ID prefix and runs the manifest, worked-region, and reference validators against it. Treat that test as the guardrail against accidentally reintroducing case-specific Python constants.
