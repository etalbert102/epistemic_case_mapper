# Artifacts

This directory is for generated run outputs.

No generated run is part of the active checked-in `artifacts/` surface. Local
runs, prompt experiments, and backend scratch outputs remain ignored here.
Curated competition evidence belongs under `examples/`; historical tracked
runs awaiting deletion review are quarantined under `for_deletion/`.

## Current Reader Path

For a staged briefing run, start with the paths printed by:

```bash
ecm semantic staged brief --region <region_id> --backend prompt
```

Read outputs in this order:

1. `BRIEFING.md`
2. `briefing_summary.json`
3. `FINAL_REVIEW_PACKET.md`
4. `map/run_summary.json`
5. `map/pipeline_progress.json`

## Cleanup Policy

Before deleting local generated artifacts, check what is tracked:

```bash
git ls-files artifacts
```

To preview and then remove only ignored generated runs:

```bash
git clean -ndX artifacts
git clean -fdX artifacts
```

The only tracked file expected under `artifacts/` is this policy README.
