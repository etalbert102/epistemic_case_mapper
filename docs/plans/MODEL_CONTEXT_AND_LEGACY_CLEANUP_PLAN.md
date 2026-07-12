# Plan: Model Context And Legacy Cleanup

## Objective
Make every live model prompt receive only the context needed for its task, while moving audit-only data to artifacts and deleting or quarantining legacy code that no longer belongs on the active memo path.

## Current Gap
The active memo path now uses `memo_ready_packet -> writer_decision_interface -> memo synthesis`, but the writer prompt still includes audit fields such as excluded evidence and lineage. Legacy packet-first and section-rewrite branches remain interleaved with active final-output code, making it hard to tell which model calls matter.

## Non-Goals
- Do not remove human-facing artifacts that are useful for debugging.
- Do not weaken retention checks or source traceability.
- Do not remove fallback behavior until tests prove the active path covers the caller.
- Do not tune behavior to the egg case.

## Design Principles
- Separate model-facing context from audit artifacts.
- Preserve fact ownership: the writer consumes the writer model context, not raw packets.
- Keep fallback paths explicit, narrow, and named as fallback.
- Verify each slice with focused tests before committing.

## Workstreams
1. Writer Model Context Compiler
   - Purpose: Strip audit-only fields before synthesis.
   - Changes: Add `build_writer_model_context`; update synthesis prompt to use it.
   - Artifacts: Continue writing full `writer_decision_interface.json` and quality report.
   - Validation: Prompt tests assert excluded evidence text, excluded evidence log, lineage, and raw writer packet are not in model prompts.

2. Prompt Surface Cleanup
   - Purpose: Avoid duplicate evidence channels.
   - Changes: Keep retention checklist as the separate required ledger; remove it from the serialized writer context.
   - Validation: Prompt still contains required ledger content and load-bearing quantities.

3. Legacy Prompt Deletion
   - Purpose: Remove stale writer-packet-only prompt fallback.
   - Changes: Artifact prompt generation uses the active memo-ready prompt when available; writer-packet-only prompts become an explicit unavailable note.
   - Validation: No active prompt path calls `_legacy_writer_decision_interface`.

4. Legacy Final-Output Quarantine
   - Purpose: Make old packet-first/section-rewrite branch visibly fallback-only.
   - Changes: Rename/report fallback boundary and leave deletion criteria for remaining old modules.
   - Validation: Active memo-ready tests continue passing; fallback tests still pass or are explicitly migrated.

## Execution Order
1. Add writer model context and switch synthesis prompts.
2. Update tests to enforce non-pollution.
3. Remove stale writer-packet prompt fallback.
4. Run focused prompt and final-output tests.
5. Run maintainability and full suite.

## Acceptance Criteria
- Live synthesis prompts do not include `excluded_evidence_log`, `lineage_report`, raw `writer_packet`, or filtered evidence text.
- Required obligations still appear in the prompt as a compact ledger.
- Full audit interface remains available as an artifact.
- No stale writer-packet-only synthesis fallback remains in active code.
- Final verification: `PYTHONPATH=src python3 -m pytest -q`.

## Red-Team Checks
- If filtered evidence text appears anywhere in a synthesis prompt, the model can use off-question evidence.
- If the retention ledger is removed entirely, the writer may drop mandatory evidence.
- If fallback code is deleted before callers are migrated, prompt-only and legacy tests will fail.

## Generalizability Checks
- Tests use generic flood/option fixtures and synthetic off-question evidence, not only eggs.
- Context compiler strips by semantic field ownership, not domain vocabulary.
- Audit artifacts remain complete for any case shape.

## Completion Audit

Completed slices:
- Added `writer_model_context_v1` so synthesis prompts receive only writer-facing facts, quantities, sources, and decision structure. Full `writer_decision_interface_v1` remains available as an audit artifact.
- Removed audit-only `excluded_evidence_log`, `lineage_report`, and filtered evidence IDs from memo synthesis prompts.
- Removed the bare decision-writer-packet synthesis fallback; prompts now require a memo-ready packet with `evidence_items`.
- Replaced the no-evidence memo-ready prompt fallback with an explicit unavailable note instead of dumping raw packet JSON.
- Compacted packet critique/refinement model context by replacing raw `section_views` and broad `coverage_report` payloads with `section_summary` and `coverage_summary`.

Verification:
- Focused prompt/context tests were added or updated for each changed boundary.
- Final all-up verification passed: `PYTHONPATH=src python3 -m pytest -q` -> 667 passed.

Deferred legacy code:
- Packet-first, section-rewrite, reader-contract rewrite, and older editorial repair modules remain because direct tests still cover them and fallback callers still exist.
- These modules should be deleted only after a separate migration proves no supported command or test uses the fallback final-output path.
- Until then, active-path cleanup should focus on preventing those modules from receiving live traffic when `memo_ready_packet.evidence_items` is available.
