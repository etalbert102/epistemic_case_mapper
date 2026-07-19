# Package Manifest Spec

Status: `implemented-core`

The package manifest is parsed by `src/epistemic_case_mapper/submission_manifest.py`.

Core package fields:

- `schema_version`
- `package_id`
- `package_label`
- `default_model_backend`
- `id_patterns`
- `relation_ontology`
- `ui_hero`
- `judge_paths`
- `required_docs`
- `reference_scan_paths`
- `extension_artifacts`
- `update_demos`
- `cases`

`default_model_backend` controls `ecm semantic run ...` when `--backend` is omitted. Supported values are documented in `docs/guides/RUNNING_THE_PIPELINE.md`; the default is `prompt`, which writes prompts without calling a model.

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
- `map_format`
- `audit_format`
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

`relation_ontology` defines which relation labels are accepted in worked maps. The defaults are:

- `supports`
- `challenges`
- `refines`
- `similar_to`
- `depends_on`
- `crux_for`
- `in_tension_with`

Packages can add custom relation labels only by defining them:

```yaml
relation_ontology:
  custom_definitions:
    implementation_risk_for: A source claim names an implementation condition that can prevent the target claim from holding in practice.
```

Supported artifact formats:

- `markdown_kv_v1`
- `json_case_map_v1`

`best_path` may be omitted when `thresholds.require_best_sections: false`.

Case source entries support quality-risk metadata:

```yaml
sources:
  - source_id: example_source
    title: Example Source
    source_type: local_note
    path: data/cases/example/sources/text/example.txt
    provenance_level: local_note
    evidence_role: implementation
    needs_upgrade: true
    limitations:
      - Local note, not a primary source.
```

Explicit weak provenance levels are surfaced in reviewer/UI warnings: `secondary_summary`, `local_note`, and `synthetic_note`.
