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
  --backend-retries 1
```

The staged mapper:

- splits each required source into source-local line chunks,
- creates a deterministic source-span catalog with stable `span_id`s,
- asks the backend to select `span_id`s and classify claims, not copy excerpts,
- derives `source_id`, `source_span`, and exact `excerpt` deterministically from the selected span,
- retries transient backend failures,
- records backend failures and uses one deterministic source-span fallback claim when a claim chunk fails,
- rejects malformed claims and unknown span IDs before assembly,
- assigns claim IDs deterministically,
- builds high-priority claim-pair packets deterministically,
- asks the backend to classify one bounded pair at a time as a relation or `none`,
- rejects relation endpoints and relation types that do not validate,
- records a single deterministic fallback relation for review if no model-produced relation validates,
- assembles the final map and runs the same semantic map validator,
- writes invalid assembled maps to `failed_candidate.json` instead of overwriting the configured region map path.

Intermediate prompts, raw model output, accepted objects, rejected objects, and `run_summary.json` are written under `artifacts/semantic/<region>/staged` unless `--artifact-dir` is supplied.

`--backend-timeout` bounds each claim-chunk call and each relation-pair call. `--backend-retries` retries transient backend failures before fallback logic runs. `--max-relation-pairs` caps the deterministic relation opportunities sent to the backend.

Useful Ollama environment variables:

- `OLLAMA_HOST`: local Ollama host, default `http://127.0.0.1:11434`.
- `ECM_OLLAMA_NUM_PREDICT`: max generated tokens for Ollama JSON calls, default `768`.
- `ECM_OLLAMA_TEMPERATURE`: Ollama temperature, default `0`.
- `ECM_OLLAMA_BACKEND=cli`: opt back into the older `ollama run` subprocess backend.
