# Staged Mapper Stress Testing

Status: `implemented`

Use the stress harness to measure whether staged semantic mapping validates, how often it falls back to deterministic claims or relations, and how runtime changes across cases and model backends.

## Quick COVID Matrix

```bash
PYTHONPATH=src python3 scripts/stress_staged_mapper.py \
  --cases data/cases/covid_origins_slice/case.yaml \
  --models gemma4:26b qwen3:8b \
  --timeouts 5 20 \
  --retries 0 \
  --relation-pairs 4 \
  --relation-batch-size 4 \
  --runs-per-config 1 \
  --chunk-lines 80 \
  --chunk-overlap-lines 5 \
  --max-claims-per-chunk 3 \
  --output-dir artifacts/stress/staged_mapper/latest_covid_smoke
```

This tests model and timeout sensitivity on the full seven-source COVID packet.

## Cross-Case Smoke

```bash
PYTHONPATH=src python3 scripts/stress_staged_mapper.py \
  --models qwen3:8b \
  --timeouts 10 \
  --retries 0 \
  --relation-pairs 2 \
  --relation-batch-size 2 \
  --runs-per-config 1 \
  --chunk-lines 40 \
  --chunk-overlap-lines 5 \
  --max-chunks-per-source 12 \
  --max-claims-per-chunk 3 \
  --max-sources 2 \
  --output-dir artifacts/stress/staged_mapper/latest_cross_case_smoke
```

This touches COVID, eggs, and LHC while limiting each case to its first two sources.

## Outputs

Each run writes:

- `runs.jsonl`: one machine-readable row per config.
- `runs.csv`: spreadsheet-friendly row output.
- `summary.json`: aggregate validation, fallback, backend-error, and runtime counts.
- `workspaces/`: disposable package workspaces with prompts, raw outputs, canonical JSON, run summaries, and generated maps.

Important fields:

- `validated`: whether semantic validation passed.
- `fallback_claim_count`: accepted claims created by deterministic fallback after model under-extraction or backend failure.
- `fallback_relation_count`: accepted relations created by deterministic fallback when no model edge validated.
- `backend_error_count`: timed-out or failed backend calls.
- `runtime_seconds`: end-to-end runtime for the config.
- `all_chunk_count`, `selected_chunk_count`, `skipped_chunk_count`: whether the run was exhaustive or budgeted.
- `relation_batch_count`: how many relation-classification backend calls were made.

High validation with high fallback counts means the pipeline is structurally robust but semantic extraction quality is still backend-limited for that setting. Good stress results should have both high validation and low fallback rates.

High `skipped_chunk_count` means the run was intentionally budgeted. This is acceptable for smoke and triage runs, but not for a final exhaustive map unless the skipped chunk list has been reviewed.
