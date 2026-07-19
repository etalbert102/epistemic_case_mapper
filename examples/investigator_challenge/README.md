# Investigator Challenge Snapshot

This checked-in deterministic replay tests whether a structured map gives a
later investigator better handles for recovery, local repair, and held-out
source update than a capable flat synthesis alone. It is evidence of artifact
usefulness, not human-reviewed domain correctness or general model superiority.

## Results At A Glance

- **Recover:** on `lhc_t003`, flat/map/map-plus-sources scores are
  `0.442`/`0.917`/`0.917`; the map exposes `lhc_c004`, `lhc_c012`, `lhc_r003`,
  and `lhc_r004` as the velocity/trapping chain.
- **Repair:** a synthetic reversal of `lhc_r004` is detected and a source-safe
  repair is produced; clean-control relation `lhc_r003` does not trigger and
  zero unaffected objects change.
- **Update:** adding `cern_lhc_current_page` creates `lhc_update_c001/c002` and
  `lhc_update_r001/r002`, touches only `lhc_c001/c005`, and preserves all 14
  unaffected claims and their stable IDs.

These scores are deterministic coverage-and-traceability proxies, not human
judgments of correctness or a scientific benchmark. A
[matched strong-model run](../../docs/evaluations/MATCHED_STRONG_MODEL_LHC_COMPARISON.md)
recovered much of the same chain. The claim is therefore that the map makes
reasoning persistent, inspectable, locally revisable, and updateable—not that a
strong model can never reconstruct it.

## Inspect The Evidence

1. [CHALLENGE_RESULTS.md](CHALLENGE_RESULTS.md) gives the compact cross-case table.
2. [FINAL_EVIDENCE_PACKET.md](FINAL_EVIDENCE_PACKET.md) gives task-level results.
3. [mutation/lhc/repair_diff.md](mutation/lhc/repair_diff.md) shows the relation repair.
4. [update/lhc/affected_object_ledger.json](update/lhc/affected_object_ledger.json)
   and [update/lhc/map_update_diff.md](update/lhc/map_update_diff.md) show update locality.
5. [`supporting/`](supporting/) retains representative input, response, and
   token-budget evidence for auditing the snapshot.

The protocol is documented in
[`docs/evaluations/investigator_challenge/PROTOCOL.md`](../../docs/evaluations/investigator_challenge/PROTOCOL.md).
Regenerate a complete local replay with:

```bash
PYTHONPATH=src python scripts/run_investigator_challenge.py --all
```

Demonstrated narrowly: LHC dependency recovery, one localized semantic repair,
and one stable-ID source update. Plausible but under-tested: lower-cost handoff
and transfer to fresh cases. Not established: better final prose, a substitute
for domain review, or a scientific performance benchmark.
