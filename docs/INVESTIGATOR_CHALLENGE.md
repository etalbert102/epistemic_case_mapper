# Investigator Challenge Demonstration

Status: runnable deterministic demonstration

Run:

```bash
PYTHONPATH=src python3 scripts/run_investigator_challenge.py --all
```

Latest generated packet:

```text
artifacts/investigator_challenge/latest/FINAL_EVIDENCE_PACKET.md
```

Compact judge packet:

```text
docs/RECOVER_REPAIR_UPDATE_DEMO.md
```

## What To Look At

The challenge starts from capable flat baselines and asks follow-up questions that matter to an investigator:

- Can the answer recover hidden dependencies?
- Can it trace the source and relation carrying a distinction?
- Can a local semantic error be detected and repaired without rewriting the case?
- Can a held-out source be added while preserving unaffected work?

The runner produces raw condition packets, raw task responses, task scores, a synthetic mutation report, an update ledger, and a final judge packet.

## Current Demonstrated Result

The deterministic replay shows the map condition recovering more of the frozen dependency structure than the flat condition on the LHC hidden-dependency slice, with transfer checks on eggs and the COVID origins slice. The strongest demonstration is not prose quality; it is reviewability:

- `lhc_t003` recovers the velocity/trapping transition through `lhc_c004`, `lhc_c012`, `lhc_r003`, and `lhc_r004`.
- The synthetic reversed relation on `lhc_r004` is localized and repaired while the clean control remains clean.
- The held-out CERN public FAQ update adds `lhc_update_c001`, `lhc_update_c002`, `lhc_update_r001`, and `lhc_update_r002`, touches only `lhc_c001` and `lhc_c005`, and preserves stable IDs for unaffected claims.

## Why This Demonstrates Prototype Value

A flat research answer can be good and still make it hard to inspect what the conclusion depends on. This challenge makes that difference concrete: the map gives a downstream investigator stable objects to query, audit, correct, and update.

## Matched Strong-Model Check

`docs/evaluations/MATCHED_STRONG_MODEL_LHC_COMPARISON.md` records a single `gpt-5.6-sol` run on the same five LHC sources, with the worked map and answer keys withheld by instruction. The strong model recovered much of the dependency chain. That is useful boundary evidence: the prototype should be judged on recoverability, local revisability, and update surfaces, not on a claim that a strong model cannot ever reconstruct the argument.

## Limits

This is a deterministic replay harness, not a live multi-model benchmark. It should be read as evidence that the prototype exposes useful investigation handles, not as proof that it always beats Deep Research-style synthesis on final writing quality.
