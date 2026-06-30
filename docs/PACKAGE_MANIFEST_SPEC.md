# Package Manifest Spec

Status: `implemented-core`

The package manifest is parsed by `src/epistemic_case_mapper/submission_manifest.py`.

Core package fields:

- `schema_version`
- `package_id`
- `package_label`
- `id_patterns`
- `ui_hero`
- `judge_paths`
- `required_docs`
- `reference_scan_paths`
- `extension_artifacts`
- `update_demos`
- `cases`

Each case declares its case manifest path, optional starter output path, optional full-case scaffold, optional task queue, UI settings, and one or more worked regions.

Each worked region declares:

- `region_id`
- `case_key`
- `id_prefix`
- `definition_path`
- `map_path`
- `audit_path`
- `baseline_path`
- `best_path`
- `output_json_path`
- `required_sources`
- `thresholds`
- optional `review`
- optional `blinded_baseline`

`id_patterns` defines how backticked IDs are recognized in docs:

```yaml
id_patterns:
  claim: "claim:demo:[0-9]+"
  relation: "rel:demo:[0-9]+"
  loss: "loss:demo:[0-9]+"
```

Defaults support the current FLF style: `lhc_c001`, `lhc_r001`, and `lhc_loss_001`.
