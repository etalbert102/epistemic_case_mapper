# Investigator Challenge Protocol

Status: deterministic replay protocol

Purpose: demonstrate artifact addressability and change locality in a frozen
investigator handoff package. This is a deterministic artifact harness, not a
test of investigator performance, semantic repair, or autonomous source
integration.

## Reproducible Command

```bash
PYTHONPATH=src python3 scripts/run_investigator_challenge.py --all
```

Default outputs are written to:

```text
artifacts/investigator_challenge/latest/
```

The compact checked-in review snapshot is under
`examples/investigator_challenge/`; representative raw evidence is retained in
its `supporting/` directory, while bulk replay output remains local.

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

The scoring pass materializes frozen answer-key objects from each condition; it
is not a live model benchmark and does not measure unaided discovery. It checks
whether preselected objects and distinctions are explicitly addressable in each
representation:

- required distinction recall;
- source trace accuracy;
- scope boundary retention;
- unsupported bridge count;
- false closure count;
- crux or update trigger recall.

Scores are descriptive properties of this answer-key-driven materialization.
The map condition has a structural advantage because it renders the selected
IDs directly, so score differences must not be presented as measured user or
model performance. The checked-in packet links to representative inputs,
responses, token reports, and score records for inspection.

## Frozen-Snapshot Restoration Exercise

The LHC slice includes a synthetic reversed-relation mutation on `lhc_r004`,
plus a clean control on `lhc_r003`. The runner detects the exact injected
reversal by comparing it with the frozen clean object, then copies the clean
relation back. This shows object localization and restoration mechanics; it is
not a semantic diagnosis or repair method.

## Prewritten Held-Out-Source Delta

The LHC slice applies already-written claim and relation objects for the
previously acquired `cern_lhc_current_page` source from
`docs/evaluations/investigator_challenge/NEW_SOURCE_UPDATE.md`. The runner does
not read the source and derive those objects. It writes:

- before and after map snapshots;
- affected-object ledger;
- map update diff;
- flat update diff;
- revised reader view.

## Claim Boundaries

This protocol can show that named map objects are directly addressable and that
a known correction or prewritten delta can be applied without changing
unaffected IDs. It does not measure investigator success, perform semantic
repair, derive updates from sources, prove better prose than a strong research
model, or supply external human validation.
