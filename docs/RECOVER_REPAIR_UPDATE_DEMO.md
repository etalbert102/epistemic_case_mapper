# Recover, Repair, Update Demo

Status: deterministic replay artifact

This is the fastest way to judge whether the map adds value beyond a competent flat synthesis. The point is not prettier prose. The point is whether a later investigator can recover a hidden dependency, repair a local semantic error, and add a new source without rewriting the whole case.

## 1. Recover

Frozen task `lhc_t003` asks:

> Which claims and sources carry the velocity/trapping transition?

The deterministic retrieval proxy scores the checked-in flat LHC baseline at `0.442`, the map condition at `0.917`, and the map-plus-sources condition at `0.917`.

What the map exposes:

- `lhc_c004`: cosmic-ray products and LHC products differ in velocity and trapping relevance.
- `lhc_c012`: Giddings/Mangano's trapping analysis supplies the technical bridge.
- `lhc_r003` and `lhc_r004`: the relation handles showing why compact-star evidence becomes relevant.

Metric boundary: this score is a deterministic coverage and traceability proxy. It is evidence that stable IDs and relation handles improve recoverability, not a human judgment that the map is universally better.

## 2. Repair

The replay injects one synthetic semantic mutation: `lhc_r004` is reversed.

Result:

- mutation detected: `True`
- localized object: `lhc_r004`
- source-safe repair produced: `True`
- clean control relation `lhc_r003` triggered: `False`
- unaffected objects changed: `0`

The repair diff is preserved at `artifacts/investigator_challenge/latest/mutation/lhc/repair_diff.md`.

Why this matters: the map makes correction local. A reviewer can change one relation while preserving unaffected claims and relation IDs.

## 3. Update

The held-out source update adds `cern_lhc_current_page` after the map exists.

Result:

- added claims: `lhc_update_c001`, `lhc_update_c002`
- added relations: `lhc_update_r001`, `lhc_update_r002`
- touched existing claims: `lhc_c001`, `lhc_c005`
- unaffected claim IDs stable: `True`
- unaffected claims preserved: `14`

The update ledger is preserved at `artifacts/investigator_challenge/latest/update/lhc/affected_object_ledger.json`; the map diff is preserved at `artifacts/investigator_challenge/latest/update/lhc/map_update_diff.md`.

Why this matters: a new source can be attached to the existing reasoning surface. The artifact records what changed and what did not, which a flat rewrite does not make easy to inspect.

## What This Shows

Demonstrated:

- the map improves recoverability on the LHC velocity/trapping dependency in deterministic replay,
- semantic repair can be localized to one relation,
- a held-out source update can preserve stable IDs for unaffected objects.

Plausible but under-tested:

- the same review surface will improve multi-investigator handoff,
- the same update workflow will transfer cleanly across fresh cases.

Not established:

- the map always produces better final prose,
- the map is a substitute for domain review,
- the current deterministic proxy is a scientific benchmark.
