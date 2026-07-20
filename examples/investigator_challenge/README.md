# Investigator Challenge Snapshot

This deterministic replay demonstrates artifact addressability and
change locality. It materializes frozen answer-key objects, restores one known
mutation from a clean snapshot, and applies one prewritten source delta. It
does not measure investigator recovery, perform semantic repair, or derive an
update from a newly read source.

Path fields in the curated JSON records are normalized to repository-root-
relative logical paths. Some point to the ignored original run tree; retained
counterparts are grouped under this example's `supporting/` directory.

## Results At A Glance

- **Address:** on `lhc_t003`, flat/map/map-plus-sources scores are
  `0.442`/`0.917`/`0.917`; the map exposes `lhc_c004`, `lhc_c012`, `lhc_r003`,
  and `lhc_r004` because the harness directly renders those frozen objects.
- **Restore:** an injected reversal of `lhc_r004` is identified against the
  frozen original and restored by copying that original; clean-control relation
  `lhc_r003` does not trigger and zero unaffected objects change.
- **Apply delta:** prewritten objects for `cern_lhc_current_page` create
  `lhc_update_c001/c002` and `lhc_update_r001/r002`, touch only
  `lhc_c001/c005`, and preserve all 14 unaffected claim IDs.

These scores describe answer-key-driven coverage and traceability, not human or
model performance, correctness, or a scientific benchmark. The map condition
is advantaged by directly receiving the selected object IDs. A
[matched strong-model run](../../docs/evaluations/MATCHED_STRONG_MODEL_LHC_COMPARISON.md)
recovered much of the same chain. The supported claim is therefore that the map
makes reasoning persistent and inspectable and that known edits can be localized—not
that a strong model cannot reconstruct the chain or that the harness performs
semantic repair.

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

Demonstrated narrowly: direct addressability of selected LHC dependency
objects, one frozen-snapshot restoration, and one stable-ID prewritten-delta
application. Plausible but under-tested: lower-cost handoff and transfer to
fresh cases. Not established: investigator recovery, semantic repair,
autonomous source integration, better final prose, domain correctness, or a
scientific performance benchmark.
