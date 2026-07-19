# Investigator Challenge Evidence Packet

Challenge: `investigator_challenge_v1`
Mode: `deterministic_retrieval_proxy`
Earned claim level: **narrow**

This packet demonstrates a narrow product claim: the structured map is useful as an investigator handoff and audit surface, not as a prettier prose generator.

## Capable Baseline Answer

The flat condition uses checked-in synthesis baselines rather than a deliberately weak summary. Representative flat input packets are preserved under `supporting/inputs/<case>/flat_packet.md`.

## Adversarial Follow-Up Comparisons

| case | flat avg | map avg | map + sources avg |
| --- | ---: | ---: | ---: |
| lhc | 0.651 | 0.872 | 0.886 |
| eggs | 0.664 | 0.805 | 0.805 |
| covid | 0.771 | 0.850 | 0.867 |

Representative task-level comparisons:

### `lhc_t001`

Why is Earth survival under cosmic-ray collisions not sufficient by itself?

- flat composite: 0.734
- map composite: 0.833
- map + sources composite: 0.833
- raw flat response: `supporting/raw/lhc/flat/lhc_t001_response.md`
- raw map response: `supporting/raw/lhc/map/lhc_t001_response.md`

### `lhc_t003`

Which claims and sources carry the velocity/trapping transition?

- flat composite: 0.442
- map composite: 0.917
- map + sources composite: 0.917
- raw flat response: `supporting/raw/lhc/flat/lhc_t003_response.md`
- raw map response: `supporting/raw/lhc/map/lhc_t003_response.md`

### `lhc_t004`

Which criticism most directly challenges the compact-star safety argument?

- flat composite: 0.617
- map composite: 0.833
- map + sources composite: 0.917
- raw flat response: `supporting/raw/lhc/flat/lhc_t004_response.md`
- raw map response: `supporting/raw/lhc/map/lhc_t004_response.md`

## Source-Trace Walkthrough

`lhc_t003` asks for the velocity/trapping transition. The map response names `lhc_c004`, `lhc_c012`, `lhc_r003`, `lhc_r004`, and their source IDs. This is the recoverability surface the flat answer typically hides inside prose.

## Local Correction Diff

- synthetic mutation: `lhc_mutation_reversed_trapping_relation`
- detected: `True`
- localized object: `lhc_r004`
- clean control triggered: `False`
- diff: `mutation/lhc/repair_diff.md`

## Held-Out Source Update

- new source: `cern_lhc_current_page`
- added claims: `lhc_update_c001`, `lhc_update_c002`
- added relations: `lhc_update_r001`, `lhc_update_r002`
- touched existing claims: `lhc_c001`, `lhc_c005`
- unaffected claim IDs stable: `True` (14 unaffected claims)
- map diff: `update/lhc/map_update_diff.md`
- flat diff: `update/lhc/flat_update_diff.md`
- revised reader view: `update/lhc/revised_reader_view.md`

## Metric And Artifact Index

| artifact | path |
| --- | --- |
| run record | `challenge_run.json` |
| completion audit | `completion_audit.json` |
| lhc scoring | `scoring/lhc/task_scores.json` |
| lhc token report | `supporting/inputs/lhc/token_budget_report.json` |
| eggs scoring | `scoring/eggs/task_scores.json` |
| eggs token report | `supporting/inputs/eggs/token_budget_report.json` |
| covid scoring | `scoring/covid/task_scores.json` |
| covid token report | `supporting/inputs/covid/token_budget_report.json` |

## What This Establishes

- The map condition makes hidden dependencies, source traces, and local updates easier to recover in deterministic replay.
- The held-out source update preserves stable IDs and makes affected objects explicit.
- The curated snapshot preserves score records, hashes, mutation reports, update ledgers, token-budget reports, three representative flat input packets, and six representative LHC responses under `supporting/`. The complete generated replay is retained separately in quarantine as provenance, outside the judge path.

## What This Does Not Establish

- It is not a scientific validation study.
- It does not prove the map always beats a strong live research model on prose quality.
- It does not claim human review beyond artifacts explicitly marked for human review.
