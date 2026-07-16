# Plan: Relation Source-Faithfulness Repair

## Objective
Prevent composite relation rows from being used as primary support for a decision answer when their endpoint source bottom lines conflict with that use. The end state is a general repair path for any case where relation semantics and answer polarity diverge.

## Current Gap
The pipeline correctly carries source bottom lines into analyst adjudication, but it only reports source-faithfulness conflicts after adjudication. If a relation row is labeled as supporting an answer even though one endpoint source bottom line signals the opposite, the row can still enter the primary reasoning chain and influence the final memo.

## Non-Goals
- Do not add domain-specific vocabularies for eggs, cholesterol, JAMA, health, or nutrition.
- Do not make deterministic code decide the correct substantive answer.
- Do not rerun source extraction or relation building as part of this repair.

## Design Principles
- Treat relation labels as claim-to-claim semantics, not answer polarity.
- Use deterministic code to detect contradictions and route unresolved contradictions away from primary support.
- Use model judgment, when available, to revise only flagged rows.
- Preserve every warning and revision as an auditable artifact.

## Workstreams
1. Relation Endpoint Matrix
   - Purpose: Make relation rows inspectable as composite evidence units.
   - Changes: Add a compact endpoint polarity matrix to each relation ledger row using endpoint claim IDs, source IDs, bottom lines, and polarity signals.
   - Artifacts: `analyst_evidence_ledger.json` rows include `relation_endpoint_answer_matrix`.
   - Validation: Unit tests verify mixed endpoint polarity is preserved.

2. Targeted Source-Faithfulness Repair
   - Purpose: Correct model misclassification without broad semantic hard-coding.
   - Changes: After live adjudication, detect source-faithfulness warnings and repair only flagged rows. The repair prompt receives the decision question, flagged row, ledger row, endpoint matrix, and warning reason.
   - Artifacts: `analyst_source_faithfulness_repair_report` is embedded in the adjudication output.
   - Validation: Unit tests verify warning detection and deterministic safe routing when repair is unavailable or invalid.

3. Unresolved Warning Quarantine
   - Purpose: Prevent known contradictory rows from becoming primary support.
   - Changes: Packet construction applies a general policy: unresolved source-faithfulness warnings cannot enter `load_bearing_primary_support`; they become counterweight/scope/crux/context depending on their existing answer relation, or `needs_human_or_model_review`.
   - Artifacts: Packet quality report lists original warnings and unresolved quarantines.
   - Validation: Regression test where increased-risk source bottom line plus neutral support role is routed out of the primary reasoning chain.

4. Retest On Existing Source Map
   - Purpose: Confirm the actual failure mode improves.
   - Changes: Rebuild memo from the existing eggs source claim map with the live backend.
   - Artifacts: New `artifacts/semantic/.../BRIEFING.md`, `analyst_packet_quality_report.json`, and progress logs.
   - Validation: `relation:eggs_r003` and `relation:eggs_r008` no longer appear as primary neutral support; source-faithfulness warning count is zero or unresolved rows are quarantined away from primary support.

## Acceptance Criteria
- Existing tests pass.
- New tests cover a non-egg synthetic relation conflict.
- The packet builder no longer places source-faithfulness-conflicted rows in `primary_reasoning_chain`.
- Live eggs rebuild shows the JAMA relation rows are either repaired or visibly quarantined away from primary support.

## Red-Team Checks
- False positive: a relation may connect a risk source to a neutral answer as a legitimate counterweight. This should be allowed if it is labeled counterweight, scope, crux, or context, not primary support.
- False certainty: deterministic code must not assert that the answer is harmful or neutral; it only blocks contradictory primary-support use.
- Model overcorrection: targeted repair may over-demote useful relation context. The original row, repaired row, and warning reason must stay visible.

## Generalizability Checks
- Synthetic fixtures should use generic “exposure” and “option” examples, not eggs vocabulary.
- The trigger depends on source-bottom-line signals and answer-role conflict, not source IDs or domain terms.
- Relation rows remain usable as context when source polarity is mixed.
