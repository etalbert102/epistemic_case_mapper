# Packet Construction Repair Completion Audit

Date: 2026-07-09

## Goal

Execute the packet assembly improvement plan in bounded, verified slices so the decision packet can more reliably transform a claim map into a memo-ready evidence package without over-compressing, role-skewing, or losing decision-critical context.

## Completed Slices

1. Decision synthesis contract
   - Commit: `1b18797 Add decision synthesis contract to packets`
   - Added explicit answer-frame, decision-question, required-context, and source-lineage contract fields to reader-facing and memo-ready packets.
   - Verification: targeted contract tests.

2. Packet QA report harness
   - Commit: `de82194 Add packet QA report harness`
   - Added packet-level QA telemetry for answer-frame cleanliness, source lineage, quantity blobs, role dominance, truncated claims, and weak cruxes.
   - Verification: `42 passed`.

3. Answer-frame normalization
   - Commit: `24404fd Normalize packet answer frames`
   - Added deterministic normalization and arbitration for malformed or embedded answer-frame text.
   - Verification: `50 passed`.

4. Role adjudication and memo-ready selection
   - Commit: `7aaf1dd Adjudicate packet roles and cap memo selection`
   - Added role adjudication after packet critique/refinement and a capped, role-balanced memo-ready selection step.
   - Verification: `46 passed`.

5. Quantity slots and crux reconstruction
   - Commit: `27248ae Normalize quantities and reconstruct cruxes`
   - Added quantity-slot normalization and reconstructed decision cruxes from support/counterweight tensions.
   - Verification: `47 passed`.

6. Final hardening and live verification
   - Pending commit in this slice.
   - Hardened critique parsing for string-valued `missing_decision_functions`.
   - Prevented role adjudication from flipping negated support claims containing risk terms.
   - Changed reconstructed crux lineage to use an individual source label so retention checks can match later citations.
   - Added regression coverage for role adjudication and critique schema flexibility.

## Final Verification

Focused packet suite:

```text
PYTHONPATH=src:scripts python3 -m pytest \
  tests/test_packet_role_adjudication.py \
  tests/test_crux_reconstruction.py \
  tests/test_packet_qa.py \
  tests/test_memo_ready_packet.py \
  tests/test_quantity_slots.py \
  tests/test_answer_frame_normalization.py \
  tests/test_decision_briefing_packet.py \
  tests/test_packet_critique_schema_flexibility.py -q

52 passed in 1.00s
```

Full suite:

```text
PYTHONPATH=src:scripts python3 -m pytest -q

487 passed in 15.08s
```

Prompt-backend packet run:

```text
artifacts/packet_assembly_eval/eggs_packet_repair_prompt_v4_20260709
```

Key results:

- `memo_packet_retention_report.status`: `ready`
- `memo_packet_retention_report.missing_mandatory_count`: `0`
- `final_decision_readiness_report.status`: `decision_ready_with_warnings`
- Remaining warning: prompt backend skipped live packet critique.
- `packet_qa_report.status`: `warning`
- Packet QA summary: answer frame clean, source lineage present, no quantity-blob warning, no role-dominance warning, one truncated claim warning, one weak-crux warning.

Live Gemma packet run:

```text
artifacts/packet_assembly_eval/eggs_packet_repair_live_gemma4_12b_mlx_v3_20260709
```

Key results:

- `final_decision_readiness_report.status`: `decision_ready`
- `memo_packet_retention_report.status`: `ready`
- `memo_packet_retention_report.missing_mandatory_count`: `0`
- `packet_critique_adjudication_report.status`: `accepted`
- `memo_ready_synthesis_report.status`: `accepted`
- `memo_ready_repair_report.status`: `accepted`
- `memo_ready_final_polish_report.status`: `accepted`
- `packet_qa_report.status`: `warning`
- Packet QA summary: answer frame clean, source lineage present, no quantity-blob warning, no role-dominance warning, one truncated claim warning, one weak-crux warning.

The previous live blocker was:

```text
packet_critique_parse_failed: missing_decision_functions.0 should be an object
```

The final live run parsed this shape successfully and retained the critique as structured data.

## Observed Product Quality

The final live memo is substantially cleaner than the earlier packet outputs. It answers the decision question directly, states a neutral/tolerable default for generally healthy adults, names scope boundaries, includes the JAMA counterweight, and lists sources.

The memo is still not at the level of a strong deep-research baseline. The main remaining weaknesses are:

- It overstates the certainty of some quantitative anchors, especially when confidence intervals are present but the model describes them as a high-certainty baseline.
- It still compresses important subgroup distinctions into a short scope section.
- The packet still contains one truncated claim inherited from upstream extraction.
- The packet QA still flags a weak upstream crux, even though the memo-ready crux reconstruction improves the crux used for synthesis.
- The source list is present, but source-to-sentence citation density remains lighter than the deep-research baseline.

## Completion Assessment

The packet assembly repair plan is implemented for the intended vertical slice:

- deterministic QA now exposes packet problems instead of hiding them;
- answer-frame normalization keeps malformed fields from contaminating the memo;
- role adjudication reduces obvious semantic role mistakes;
- memo-ready selection avoids role dominance;
- quantitative anchors are separated from prose blobs;
- crux reconstruction creates a decision-relevant tension for synthesis;
- live critique parsing no longer blocks on common model-shape variation;
- retention and final readiness gates pass on the live eggs run.

Residual quality issues are now concentrated upstream in claim extraction/truncation and downstream in final prose/source citation density, not in the packet assembly mechanics addressed by this plan.
