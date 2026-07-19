# Investigator Challenge Protocol

Status: deterministic replay protocol

Purpose: demonstrate the prototype as an investigator handoff layer. The challenge asks whether a structured map makes hidden dependencies, source traces, local corrections, and source updates easier to inspect than a flat synthesis.

## Reproducible Command

```bash
PYTHONPATH=src python3 scripts/run_investigator_challenge.py --all
```

Default outputs are written to:

```text
artifacts/investigator_challenge/latest/
```

The compact checked-in review snapshot is under
`examples/investigator_challenge/`; bulk raw replay output remains local or is
quarantined under `for_deletion/`.

## Frozen Inputs

- Challenge manifest: `experiments/investigator_challenge/challenge_manifest.yaml`
- Answer keys: `experiments/investigator_challenge/answer_keys.json`
- Worked maps:
  - `examples/lhc_black_holes/worked_region_cosmic_ray_map.json`
  - `examples/eggs/worked_region_observational_vs_rct_map.json`
  - `examples/covid_origins_slice/worked_region_bayesian_disagreement_map.json`
- Flat baselines:
  - `examples/lhc_black_holes/flat_synthesis_baseline.md`
  - `examples/eggs/flat_synthesis_baseline.md`
  - `examples/covid_origins_slice/flat_synthesis_baseline.md`

## Conditions

- `flat`: checked-in flat synthesis plus source-universe declaration.
- `map`: source IDs, claim IDs, relation IDs, relation rationales, and crux candidates.
- `map_plus_sources`: the map condition plus claim excerpts.

The runner records source-universe parity and packet word counts for each condition.

## Metrics

The scoring pass is a deterministic retrieval proxy, not a live model benchmark. It measures whether the relevant objects and distinctions are recoverable from each condition:

- required distinction recall;
- source trace accuracy;
- scope boundary retention;
- unsupported bridge count;
- false closure count;
- crux or update trigger recall.

Scores are descriptive. The checked-in judge packet links to representative
inputs, retrieved responses, token reports, and score records so the aggregate
numbers do not need to be trusted on their own. A complete prompt/response
replay is regenerated locally by the challenge runner rather than included in
the active review surface.

## Local Correction Exercise

The LHC slice includes a synthetic reversed-relation mutation on `lhc_r004`, plus a clean control on `lhc_r003`. The runner writes clean, corrupted, and repaired map snapshots and a local diff.

## Held-Out Source Update

The LHC slice adds the already acquired but held-out source
`cern_lhc_current_page` from
`docs/evaluations/investigator_challenge/NEW_SOURCE_UPDATE.md`. The runner writes:

- before and after map snapshots;
- affected-object ledger;
- map update diff;
- flat update diff;
- revised reader view.

## Claim Boundaries

This protocol can show that the map is a more inspectable investigation surface. It does not prove that the prototype writes better prose than a strong research model, and it does not claim external human validation unless a separate review artifact says so.
