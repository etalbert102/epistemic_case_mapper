# Plan: Model Context And Legacy Cleanup

## Objective
Make every live model prompt receive only the context needed for its task, while moving audit-only data to artifacts and deleting or quarantining legacy code that no longer belongs on the active memo path.

## Current Gap
The active memo path uses `memo_ready_packet -> writer_decision_interface -> memo synthesis`. The remaining risk was compatibility drift: old packet-first, section-rewrite, reader-contract rewrite, and editorial repair modules could still be invoked by fallback callers even though they were no longer the intended memo path.

## Non-Goals
- Do not remove human-facing artifacts that are useful for debugging.
- Do not weaken retention checks or source traceability.
- Do not tune behavior to the egg case.

## Design Principles
- Separate model-facing context from audit artifacts.
- Preserve fact ownership: the writer consumes the writer model context, not raw packets.
- Prefer one supported path over compatibility fallbacks once callers have migrated.
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

4. Legacy Final-Output Removal
   - Purpose: Make memo creation single-path: final synthesis requires `memo_ready_packet.evidence_items`.
   - Changes: Remove packet-first/section-rewrite fallback branch; migrate `decision_model_slice` to assemble a memo-ready packet before synthesis.
   - Validation: Active memo-ready tests pass; missing-packet callers fail clearly with a progress status.

5. Obsolete Module Deletion
   - Purpose: Remove dead code and tests that only exercised unsupported paths.
   - Changes: Delete section rewrite, packet-first memo generation, reader-packet repair, packet-retention repair, old editorial pass, warning repair, and final memo editor modules.
   - Validation: Repository scan finds no imports of deleted modules or exported legacy APIs.

## Execution Order
1. Add writer model context and switch synthesis prompts.
2. Update tests to enforce non-pollution.
3. Remove stale writer-packet prompt fallback.
4. Remove final-output legacy fallback and migrate the vertical slice caller.
5. Delete obsolete modules/tests and trim facade exports.
6. Run focused prompt/final-output tests, symbol scans, compileall, and full suite.

## Acceptance Criteria
- Live synthesis prompts do not include `excluded_evidence_log`, `lineage_report`, raw `writer_packet`, or filtered evidence text.
- Required obligations still appear in the prompt as a compact ledger.
- Full audit interface remains available as an artifact.
- No stale writer-packet-only synthesis fallback remains in active code.
- `write_final_reader_outputs` requires `scaffold.memo_ready_packet.evidence_items` and records `failed_missing_memo_ready_packet` for invalid callers.
- No imports remain for deleted legacy modules or legacy rewrite APIs.
- Final verification: `PYTHONPATH=src python3 -m pytest -q`.

## Red-Team Checks
- If filtered evidence text appears anywhere in a synthesis prompt, the model can use off-question evidence.
- If the retention ledger is removed entirely, the writer may drop mandatory evidence.
- If fallback code is deleted before callers are migrated, tests should fail with `missing_memo_ready_packet`; migrate callers rather than restoring fallback behavior.

## Generalizability Checks
- Tests use generic flood/option fixtures and synthetic off-question evidence, not only eggs.
- Context compiler strips by semantic field ownership, not domain vocabulary.
- Audit artifacts remain complete for any case shape.
- Missing-packet behavior is structural, not case-specific: any caller must assemble a memo-ready packet before synthesis.

## Completion Audit

Completed slices:
- Added `writer_model_context_v1` so synthesis prompts receive only writer-facing facts, quantities, sources, and decision structure. Full `writer_decision_interface_v1` remains available as an audit artifact.
- Removed audit-only `excluded_evidence_log`, `lineage_report`, and filtered evidence IDs from memo synthesis prompts.
- Removed the bare decision-writer-packet synthesis fallback; prompts now require a memo-ready packet with `evidence_items`.
- Replaced the no-evidence memo-ready prompt fallback with an explicit unavailable note instead of dumping raw packet JSON.
- Compacted packet critique/refinement model context by replacing raw `section_views` and broad `coverage_report` payloads with `section_summary` and `coverage_summary`.
- Removed the legacy final-output branch from `write_final_reader_outputs`; missing memo-ready packets now fail explicitly instead of silently routing to packet-first or section rewrite.
- Migrated `decision_model_slice` synthesis to call the active decision-packet assembly stage before final memo synthesis.
- Deleted obsolete packet-first, section-rewrite, reader-packet repair, packet-retention repair, old editorial pass, warning repair, and final memo editor modules, along with tests that only covered those unsupported paths.
- Trimmed facade exports and prompt-contract helpers so deleted APIs are no longer advertised as supported.

Verification:
- Focused prompt/context tests were added or updated for each changed boundary.
- Added regression coverage that missing memo-ready packets raise clearly and that `decision_model_slice` uses the memo-ready synthesis path.
- Legacy-symbol scan passes: no imports remain for deleted modules or removed rewrite APIs.
- Final all-up verification passed: `PYTHONPATH=src python3 -m pytest -q` -> 557 passed.

Deferred work:
- None for the removed legacy output paths. Remaining cleanup should be based on new dependency scans, not compatibility with packet-first or section-rewrite synthesis.
