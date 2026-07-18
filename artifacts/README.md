# Artifacts

This directory is for generated run outputs.

Checked-in artifacts are intentionally limited to small, reviewable evidence of current prototype behavior. Large exploratory runs, prompt experiments, and local backend scratch outputs should remain untracked.

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

To remove only untracked generated runs:

```bash
git clean -fd artifacts
```

Do not delete tracked artifacts unless the submission package intentionally changes what evidence is checked in.
