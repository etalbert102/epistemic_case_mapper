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
- `ollama:<model>`: run `ollama run <model>` with the prompt on stdin.

The backend can be overridden per run:

```bash
ecm --repo-root /path/to/package --package package.yaml semantic run map \
  --region my_case_initial_region \
  --backend command:'my-json-model --temperature 0'
```

For non-prompt backends, `semantic run map` writes to the region `map_path` by default and then runs semantic JSON validation. `semantic run critique` writes to `artifacts/semantic/<region>_critique.json` by default and validates the critique JSON. Use `--output` to redirect either file and `--no-validate` only when intentionally capturing raw model output for debugging.

The deterministic code owns package layout, source copying, prompt construction, path selection, and JSON validation. The model backend owns only semantic extraction or critique text generation.
