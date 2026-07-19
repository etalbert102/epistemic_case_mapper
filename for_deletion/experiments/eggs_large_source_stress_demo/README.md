# Eggs Large Source Stress Demo

This demo package runs the staged decision-memo pipeline on the 50-source egg and
cardiovascular-health corpus in
`data/cases/eggs_large_source_stress/case.yaml`.

The purpose is to demonstrate the pipeline's inspectable path on a corpus that is
larger than a direct single-prompt synthesis path can comfortably handle. The
manifest keeps all 50 source IDs in scope and leaves generated maps, quality
reports, decision packets, warnings, and memos under `artifacts/`.

## Status

The files in this directory are demo wiring, not curated final worked-region
artifacts. Run outputs are intentionally written outside the tracked package so
the demo can be rerun without changing source-controlled files.

## Run

```sh
PYTHONPATH=src python3 scripts/ecm.py \
  --package experiments/eggs_large_source_stress_demo/manifest.yaml \
  semantic staged status \
  --region eggs_large_source_stress_demo \
  --run-dir artifacts/semantic/eggs_large_source_stress_demo/staged_brief \
  --verbose
```

```sh
OLLAMA_NUM_PARALLEL=8 PYTHONPATH=src python3 scripts/ecm.py \
  --package experiments/eggs_large_source_stress_demo/manifest.yaml \
  semantic staged brief \
  --region eggs_large_source_stress_demo \
  --backend ollama:gemma4:12b-mlx \
  --output artifacts/semantic/eggs_large_source_stress_demo/staged_brief/generated_map.json \
  --artifact-dir artifacts/semantic/eggs_large_source_stress_demo/staged_brief/map \
  --briefing-dir artifacts/semantic/eggs_large_source_stress_demo/staged_brief/briefing \
  --max-claims-per-source 8 \
  --claim-consolidation deterministic \
  --max-relation-pairs 120 \
  --relation-batch-size 8 \
  --briefing-max-claims 0 \
  --backend-timeout 300 \
  --backend-retries 2
```

## Resume

After map construction succeeds, rebuild only the decision memo:

```sh
PYTHONPATH=src python3 scripts/ecm.py \
  --package experiments/eggs_large_source_stress_demo/manifest.yaml \
  semantic staged resume \
  --region eggs_large_source_stress_demo \
  --from-stage map \
  --backend ollama:gemma4:12b-mlx \
  --run-dir artifacts/semantic/eggs_large_source_stress_demo/staged_brief \
  --briefing-max-claims 0 \
  --backend-timeout 300 \
  --backend-retries 2
```

Primary outputs:

- `artifacts/semantic/eggs_large_source_stress_demo/staged_brief/generated_map.json`
- `artifacts/semantic/eggs_large_source_stress_demo/staged_brief/map/map_quality_report.json`
- `artifacts/semantic/eggs_large_source_stress_demo/staged_brief/map/pipeline_progress.json`
- `artifacts/semantic/eggs_large_source_stress_demo/staged_brief/briefing/BRIEFING.md`
- `artifacts/semantic/eggs_large_source_stress_demo/staged_brief/briefing/FINAL_REVIEW_PACKET.md`
- `artifacts/semantic/eggs_large_source_stress_demo/staged_brief/briefing/memo_progress.json`
