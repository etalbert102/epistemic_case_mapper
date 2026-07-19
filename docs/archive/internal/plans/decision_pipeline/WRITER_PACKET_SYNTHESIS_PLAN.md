# Plan: Source-Bound Writer Packet Synthesis

## Objective
Improve final decision memo quality by giving synthesis a compact, source-bound writer packet instead of the full internal memo-ready packet. The final writer should write, not decide which raw quantities and packet internals matter.

## Current Gap
The memo-ready packet now blocks obviously bad quantities, but synthesis still sees too many quantities, source IDs, and internal structures. This creates number-heavy prose, source drift, and overconfident language. The existing model calls are enough; the missing piece is a better deterministic/model-output-derived writing interface.

## Non-Goals
- Do not add another model call.
- Do not hide or delete the full memo-ready packet.
- Do not add egg-specific evidence rules.
- Do not make synthesis responsible for source/evidence selection.

## Design Principles
- Analyst decision and refinement stages decide what matters.
- Quantity binding decides which quantities are source/proposition-compatible.
- Deterministic code assembles a compact writer packet from those accepted artifacts.
- Synthesis receives the writer packet as the evidence interface; the full packet remains audit-only.
- Evaluation must measure packet quality, not just whether a memo was produced.

## Workstreams
1. Writer Packet Builder
   - Build `writer_packet` from answer spine, analyst decision logic, argument plan, evidence items, source trail, and quantity-binding report.
   - Separate evidence units into support, counterweight, crux, scope, and context.
   - Budget quantities per unit and keep source-bound quantity metadata.

2. Writer Packet Quality Report
   - Count total writer quantities, source-bound quantities, source-missing quantities, and budget violations.
   - Flag raw source IDs when display labels are available.
   - Flag rejected quantity values if they reappear in writer evidence.

3. Synthesis Prompt Routing
   - If `writer_packet` exists, the memo synthesis prompt should use it as the writing evidence.
   - The prompt should mention the full packet only as audit context excluded from the writing prompt.

4. Tests And Evaluation
   - Unit test that off-scope quantities are excluded from writer packet.
   - Unit test that writer quantities include source evidence IDs and labels.
   - Rerun the egg synthesis and compare:
     - rejected quantities absent from memo,
     - source-bound quantity count,
     - total memo-facing quantity count,
     - final memo readability.

## Acceptance Criteria
- `analyst_memo_ready_packet` includes `writer_packet` and `writer_packet_quality_report`.
- Synthesis prompt includes `writer_packet` and does not dump the full `evidence_items` list when writer packet exists.
- Writer packet excludes rejected quantity bindings.
- Writer packet keeps exact source metadata for each included quantity.
- Focused and full tests pass.
- Egg rerun shows the toddler-age failure remains fixed and the memo has lower packet-noise risk.

## Red-Team Checks
- If the writer packet is too small, synthesis may omit important caveats. Detect with retained mandatory item checks and writer packet role coverage.
- If quantity budgeting is too strict, useful numerical depth may be lost. Detect by comparing source-bound essential quantities to final memo quantities.
- If display aliases are poor, source readability may not improve. Detect source-label quality warnings separately from binding validity.
- If synthesis still overclaims, the issue is now prompt/calibration, not packet construction.
