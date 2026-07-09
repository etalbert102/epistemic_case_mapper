# Semantic Decision Boundary Completion Audit

Date: 2026-07-09

## Objective

Move semantic decisions out of deterministic packet code. Deterministic code should preserve source/model labels, validate explicit metadata contracts, route by explicit fields, and emit warnings. It should not infer that claim text is support, counterweight, scope, crux, or directional quantitative evidence.

## Slice Ledger

- `3df766e Preserve full atomic evidence claims`
  - Preserved full atomic evidence claims instead of reducing claims to the first sentence.
  - Added regression coverage for full-claim preservation in evidence cards.
- `1af1e79 Record semantic decision boundary plan`
  - Recorded the plan and acceptance criteria in `docs/plans/SEMANTIC_DECISION_BOUNDARY_PLAN.md`.
- `7e030f5 Make packet role adjudication report only`
  - Stopped deterministic role adjudication from mutating packet roles.
  - Preserved report artifacts for suspicious-role diagnostics.
- `963b9e0 Use explicit labels for packet roles`
  - Replaced text-keyword role inference in candidate and packet role projection with explicit model/source metadata.
  - Added regressions so text such as "higher risk" does not create a role by itself.
- `2d62c04 Stop deterministic crux construction`
  - Stopped broad relation types from becoming decision cruxes.
  - Made crux reconstruction diagnostic-only rather than synthesizing replacement cruxes.
- `f9804fa Neutralize unpaired quantity interpretation`
  - Removed deterministic directionality from unpaired quantities.
  - Kept local tuple preservation and warnings for unpaired quantities.
- `7d37329 Flag generic answer frames without repair`
  - Added packet QA warnings for generic/artifact-language answer frames.
  - Does not rewrite or invent a substantive answer.
- `d1a99ea Remove text-derived role recommendations`
  - Removed deterministic `recommended_role` suggestions from role adjudication.
  - Role adjudication now only reports explicit metadata contract conflicts.

## Verification

Focused verification completed during implementation:

- `PYTHONPATH=src:scripts python3 -m pytest tests/test_packet_role_adjudication.py tests/test_decision_briefing_packet.py tests/test_packet_qa.py -q`
- `PYTHONPATH=src:scripts python3 -m pytest tests/test_memo_ready_packet.py tests/test_decision_packet_eligibility.py tests/test_decision_packet_source_bottom_lines.py tests/test_packet_critique_parser.py -q`
- `PYTHONPATH=src:scripts python3 -m pytest tests/test_map_briefing_context_schemas.py tests/test_map_briefing_context_reports.py tests/test_decision_packet_source_bottom_lines.py tests/test_decision_briefing_packet.py -q`
- `PYTHONPATH=src:scripts python3 -m pytest tests/test_crux_reconstruction.py tests/test_memo_ready_packet.py tests/test_map_briefing_decision_synthesis.py tests/test_decision_model_vertical_slice.py tests/test_decision_briefing_packet.py -q`
- `PYTHONPATH=src:scripts python3 -m pytest tests/test_memo_ready_packet.py tests/test_quantity_slots.py tests/test_quantity_ledger.py tests/test_decision_briefing_packet.py tests/test_quantitative_retention_packet.py -q`
- `PYTHONPATH=src:scripts python3 -m pytest tests/test_packet_qa.py tests/test_answer_frame_normalization.py tests/test_decision_briefing_packet.py -q`

Full verification:

- `PYTHONPATH=src:scripts python3 -m pytest -q`
- Result: `494 passed`.

Prompt-backend packet run:

```bash
PYTHONPATH=src python3 -m epistemic_case_mapper.cli synthesize map-briefing \
  --map artifacts/semantic/eggs_whole_doc_current_eval_20260709/worked_map.json \
  --quality-report artifacts/semantic/eggs_whole_doc_current_eval_20260709/map_quality_report.json \
  --question "For generally healthy adults, should eggs be treated as meaningfully harmful, neutral, or beneficial in dietary advice, especially with respect to cardiovascular risk?" \
  --backend prompt \
  --output-dir artifacts/packet_assembly_eval/eggs_semantic_boundary_prompt_20260709 \
  --max-claims 0 \
  --backend-timeout 120
```

Result:

- Output brief: `artifacts/packet_assembly_eval/eggs_semantic_boundary_prompt_20260709/BRIEFING.md`
- CLI quality: `usable_with_review`
- Packet QA status: `warning`
- Role adjudication status: `unchanged`
- Crux reconstruction status: `unchanged`

## Before/After Diagnostic Signal

Before this plan, deterministic code could silently repair or relabel semantic content:

- role adjudication could recommend or apply support/counterweight/scope labels from claim text;
- topical relation types could become cruxes;
- unpaired quantities could receive directional interpretations;
- generic answer text could pass as if it answered the decision question.

After this plan:

- `packet_role_adjudication_report.json` reports `method: report_only_explicit_metadata_contract_checks_no_semantic_mutation`;
- `packet_role_adjudication_report.json` has `candidate_count: 0` on the latest eggs prompt run because no explicit metadata contract conflict was present;
- `packet_qa_report.json` flags `answer_frame_generic_or_artifact_language` for `Evidence supports the default answer under stated conditions.`;
- `decision_crux_reconstruction_report.json` states that deterministic code reports weak cruxes but does not synthesize replacement cruxes;
- unpaired quantities carry neutral warnings such as `do not infer direction, pairing, or effect meaning`.

## Residual Risks

- The latest eggs prompt run still has a generic answer frame. This is now exposed as a QA warning rather than hidden by deterministic repair.
- If upstream model/source labels are weak, the packet will preserve that weakness instead of repairing it. The next improvement should strengthen model-owned answer-frame and role labeling, not add keyword fixes.
- Some older modules outside the immediate packet path may still contain semantic-looking helper names or legacy behavior. This audit covers the current packet and memo path touched by the plan, not a full repository-wide formal methods proof.
- Explicit metadata contract checks still encode schema contracts, such as role-to-directionality consistency. This is allowed because it validates internal packet consistency rather than deciding semantic meaning from source text.

## Acceptance Status

- No deterministic function in the current packet path silently changes support/counterweight/scope/crux labels based on claim text: complete for the audited path.
- Existing explicit model/source labels still flow through the packet: complete.
- Suspect labels produce diagnostics instead of semantic mutation: complete.
- Focused and full tests pass: complete.
- Latest eggs prompt run exposes unresolved semantic uncertainty as warnings: complete.

