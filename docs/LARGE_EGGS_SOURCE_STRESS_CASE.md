# Large Eggs Source Stress Case

Status: `implemented`

`data/cases/eggs_large_source_stress/` is a deliberately broad, noisy source-grounded eggs case built from live PMC full-text acquisition. It is meant to show that the pipeline can ingest a legitimate source corpus that is too large for a simple direct-synthesis path.

## What It Is For

- Stress-testing source intake, staged extraction, prioritization, and memo construction.
- Demonstrating that the system can preserve provenance across many real sources.
- Evaluating how well the pipeline routes tangential material away from the final decision model.

It is not a manually curated evidence base. Some documents are directly about egg consumption and cardiovascular risk; others are tangentially related through dietary cholesterol, nutrition, choline, lutein, allergy, or diet quality.

## Regenerate The Case

```bash
PYTHONPATH=src python3 scripts/build_eggs_large_source_case.py \
  --target-words 260000 \
  --retmax-per-query 60 \
  --force
```

If local Python certificate validation fails because the environment intercepts HTTPS with a self-signed certificate, rerun with explicit acknowledgement:

```bash
PYTHONPATH=src python3 scripts/build_eggs_large_source_case.py \
  --target-words 260000 \
  --retmax-per-query 60 \
  --force \
  --insecure-tls
```

The script writes:

- `data/cases/eggs_large_source_stress/case.yaml`
- `data/cases/eggs_large_source_stress/sources/raw/*.xml`
- `data/cases/eggs_large_source_stress/sources/text/*.txt`
- `data/cases/eggs_large_source_stress/sources/SOURCE_INVENTORY.md`
- `data/cases/eggs_large_source_stress/CORPUS_REPORT.md`

## Validation

Check that the generated corpus meets the large-source objective:

```bash
PYTHONPATH=src python3 scripts/validate_large_source_case.py
```

Use a live or fake JSON-producing model backend for a staged-processing smoke test:

```bash
PYTHONPATH=src python3 scripts/stress_staged_mapper.py \
  --cases data/cases/eggs_large_source_stress/case.yaml \
  --backends '<model-backend>' \
  --timeouts 20 \
  --retries 0 \
  --relation-pairs 2 \
  --relation-batch-size 2 \
  --max-claims-per-source 1 \
  --output-dir artifacts/stress/eggs_large_source_stress/latest \
  --fail-on-failure
```

The prompt backend is useful for inspecting prompts, but it does not return source-card JSON and therefore is not a valid extraction success check for the current whole-document pipeline.

The generated `CORPUS_REPORT.md` records source count, extracted word count, estimated token count, acquisition queries, skipped records, and retrieval date.
