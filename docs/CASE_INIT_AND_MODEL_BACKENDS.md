# Case Init And Model Backends

Status: `implemented`

The reusable path for a new package is:

```bash
ecm --repo-root /path/to/package --package package.yaml case init \
  --case-id my_case \
  --title "My Case" \
  --question "What should a careful reader conclude?" \
  --docs doc_a.txt doc_b.md
```

This creates a manifest, case manifest, copied source files, a starter worked region, a starter map, a placeholder erosion audit, a baseline comparator, and UI/review scaffold files. The starter map is explicitly only a source inventory; it is meant to make the package runnable before a substantive model or human mapping pass replaces it.

## Optional Source Intake Filter

Before initialization, run the optional first-phase intake filter when a document packet may contain off-question, unreadable, or low-trust sources:

```bash
ecm --repo-root /path/to/package case filter-sources \
  --question "What should a careful reader conclude?" \
  --docs doc_a.txt doc_b.md \
  --backend prompt
```

The filter writes `source_intake_filter.json` and `SOURCE_INTAKE_FILTER.md`. With `--backend prompt`, it records the model prompt without calling a model. With `command:<cmd>` or `ollama:<model>`, it adds model judgments about likely relevance and trust concerns.

The filter is an intake screen, not the final evidence-quality assessment. `case init --filter-sources` records the same report before copying sources but keeps all readable sources by default. Add `--exclude-filtered-sources` only when you want the filter to route final `exclude` decisions away before the full mapping pipeline runs:

```bash
ecm --repo-root /path/to/package --package package.yaml case init \
  --case-id my_case \
  --title "My Case" \
  --question "What should a careful reader conclude?" \
  --docs doc_a.txt doc_b.md \
  --filter-sources \
  --exclude-filtered-sources
```

## End-To-End Briefing

After `case init`, the shortest path from sources to a reader-facing memo is:

```bash
ecm --repo-root /path/to/package --package package.yaml semantic staged brief \
  --region my_case_initial_region \
  --backend prompt
```

The `prompt` backend is the safe first run: it writes prompts, scaffolds, deterministic review artifacts, and a memo shell without requiring a model. For a live model, replace it with `command:<cmd>` or `ollama:<model>`.

The command prints the briefing memo, summary JSON, map run summary, and `FINAL_REVIEW_PACKET.md`. Read them in that order:

1. Briefing memo: the reader-facing output.
2. Summary JSON: paths and high-level quality signals.
3. Final review packet: traceability, warning, and quality review surface.
4. Map run summary: extraction and relation-building diagnostics.

## Pipeline And Resume Points

The staged CLI has three high-level handoffs:

1. `documents`: the case manifest and source files are available.
2. `map`: `generated_map.json` and `map/map_quality_report.json` are available.
3. `briefing`: `briefing/BRIEFING.md`, `briefing/briefing_summary.json`, and `briefing/FINAL_REVIEW_PACKET.md` are available.

Check what can be resumed:

```bash
ecm --repo-root /path/to/package --package package.yaml semantic staged status \
  --region my_case_initial_region
```

The status view shows a compact stage table and a suggested next command. Add `--verbose` when you need the full checked-artifact inventory.

Resume from the original documents and rebuild the full default staged run:

```bash
ecm --repo-root /path/to/package --package package.yaml semantic staged resume \
  --region my_case_initial_region \
  --from-stage documents \
  --backend ollama:gemma4:26b
```

Resume from an existing map artifact bundle and rebuild only the briefing:

```bash
ecm --repo-root /path/to/package --package package.yaml semantic staged resume \
  --region my_case_initial_region \
  --from-stage map \
  --backend ollama:gemma4:26b
```

Report the existing final briefing paths without rerunning model calls:

```bash
ecm --repo-root /path/to/package --package package.yaml semantic staged resume \
  --region my_case_initial_region \
  --from-stage briefing
```

By default these commands use `artifacts/semantic/<region>/staged_brief/`:

- map: `generated_map.json`
- map diagnostics: `map/`
- briefing: `briefing/`

Use `--run-dir`, `--map`, `--quality-report`, or `--briefing-dir` when resuming from copied or renamed artifacts.

## Backend Selection

The package manifest can set:

```yaml
default_model_backend: prompt
```

Supported backend specs:

- `prompt`: write the source-bounded prompt to `prompts/<region>/...` without calling a model.
- `command:<command>`: run a local command that reads the prompt from stdin and writes the response to stdout.
- `ollama:<model>`: call Ollama's local HTTP chat API in JSON mode by default. Set `ECM_OLLAMA_BACKEND=cli` to use the older `ollama run <model> --format json --hidethinking --nowordwrap` subprocess path.

The backend can be overridden per run:

```bash
ecm --repo-root /path/to/package --package package.yaml semantic run map \
  --region my_case_initial_region \
  --backend command:'my-json-model --temperature 0'
```

For non-prompt backends, `semantic run map` writes to the region `map_path` by default and then runs semantic JSON validation. `semantic run critique` writes to `artifacts/semantic/<region>_critique.json` by default and validates the critique JSON. The runner canonicalizes JSON returned inside a fenced block or after prefatory text before validation. Use `--output` to redirect either file and `--no-validate` only when intentionally capturing model output for debugging.

The deterministic code owns package layout, source copying, prompt construction, path selection, and JSON validation. The model backend owns only semantic extraction or critique text generation.

## Staged Mapping

For realistic multi-source packets, prefer the staged mapper over one-shot `semantic run map`:

```bash
ecm --repo-root /path/to/package --package package.yaml semantic staged map \
  --region my_case_initial_region \
  --backend ollama:gemma4:26b \
  --backend-timeout 90 \
  --backend-retries 1 \
  --chunk-lines 40 \
  --chunk-overlap-lines 5 \
  --relation-batch-size 4
```

The staged mapper:

- splits each required source into source-local line chunks,
- supports overlapping chunks so important context is less likely to be split across chunk boundaries,
- can optionally cap chunks per source or total chunks for long-document budgeted runs,
- creates a deterministic source-span catalog with stable `span_id`s,
- asks the backend to select `span_id`s and classify claims, not copy excerpts,
- derives `source_id`, `source_span`, and exact `excerpt` deterministically from the selected span,
- retries transient backend failures,
- records backend failures and uses one deterministic source-span fallback claim when a claim chunk fails,
- rejects malformed claims and unknown span IDs before assembly,
- assigns claim IDs deterministically,
- builds high-priority claim-pair packets deterministically,
- asks the backend to classify bounded batches of relation pairs as relations or `none`,
- rejects relation endpoints and relation types that do not validate,
- records a single deterministic fallback relation for review if no model-produced relation validates,
- assembles the final map and runs the same semantic map validator,
- writes invalid assembled maps to `failed_candidate.json` instead of overwriting the configured region map path.

Intermediate prompts, raw model output, accepted objects, rejected objects, and `run_summary.json` are written under `artifacts/semantic/<region>/staged` unless `--artifact-dir` is supplied. The summary records `all_chunk_count`, `selected_chunk_count`, `skipped_chunk_count`, and `skipped_chunks` so budgeted runs are auditable.

`--backend-timeout` bounds each claim-chunk call and each relation-batch call. `--backend-retries` retries transient backend failures before fallback logic runs. `--max-relation-pairs` caps the deterministic relation opportunities sent to the backend. `--relation-batch-size` controls how many candidate pairs are classified per backend call.

For short packets, prefer exhaustive smaller chunks:

```bash
ecm --repo-root /path/to/package --package package.yaml semantic staged map \
  --region my_case_initial_region \
  --chunk-lines 25 \
  --chunk-overlap-lines 5
```

For long documents, use smaller chunks plus an explicit budget. `0` means unlimited for both budget flags:

```bash
ecm --repo-root /path/to/package --package package.yaml semantic staged map \
  --region my_case_initial_region \
  --chunk-lines 25 \
  --chunk-overlap-lines 5 \
  --max-chunks-per-source 12 \
  --max-total-chunks 80
```

Budgets preserve at least one selected chunk per source when the total budget allows it, then fill remaining slots by deterministic chunk score. This score only schedules model calls; it does not create final claims.

Useful Ollama environment variables:

- `OLLAMA_HOST`: local Ollama host, default `http://127.0.0.1:11434`.
- `ECM_OLLAMA_NUM_PREDICT`: max generated tokens for Ollama JSON calls, default `768`.
- `ECM_OLLAMA_TEMPERATURE`: Ollama temperature, default `0`.
- `ECM_OLLAMA_BACKEND=cli`: opt back into the older `ollama run` subprocess backend.
