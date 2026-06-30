# Engine Architecture

Status: `implemented-core`

The reusable engine has three layers:

1. Package config: `submission_manifest.yaml` or another manifest passed with `--manifest` / `--package`.
2. Engine code: `src/epistemic_case_mapper/` plus script entry points under `scripts/`.
3. Package artifacts: case manifests, source files, worked maps, audits, baselines, review docs, exports, and UI data.

The case is the source-corpus unit. The worked region is the operational unit for validation, JSON export, review selection, baseline prompts, and UI anchors.

`ecm` is the package-facing command. `scripts/ecm.py` remains a compatibility wrapper. It can run against an external package root:

```bash
PYTHONPATH=src python3 scripts/ecm.py --repo-root /tmp/package validate package
```

The current FLF submission is one package configured by `submission_manifest.yaml`.
