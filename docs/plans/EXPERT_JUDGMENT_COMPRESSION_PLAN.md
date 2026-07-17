# Plan: Expert Judgment Compression Layer

## Objective

Improve decision memo quality by adding a model-authored expert judgment compression layer before synthesis. The layer should let model judgment decide salience, source hierarchy, counterweight disposition, and memo voice while deterministic code preserves traceability, source IDs, quantity coverage, and validation.

## Current Gap

The pipeline retains evidence effectively, but section prompts are compliance-heavy. That makes generated memos decision-useful but often less expert-like: prose becomes modular, repetitive, citation-driven, and cautious rather than governed by a crisp analytical read.

## Design Split

- Deterministic code:
  - build the compression input;
  - preserve stable evidence IDs, source IDs, and quantities;
  - validate unknown IDs and missing mandatory evidence;
  - attach section-specific expert briefs to section packets;
  - report whether final prose surfaced the compressed judgment.
- Model judgment:
  - decide the governing judgment;
  - decide which evidence carries, bounds, calibrates, or should be subordinated;
  - produce section-specific analytical briefs;
  - provide memo voice guidance.

## Implemented Slices

1. Expert compression artifact and QA
   - Added `map_briefing_expert_judgment_compression.py`.
   - Added `expert_judgment_compression_input_v1`, `expert_judgment_compression_v1`, `expert_judgment_compression_report_v1`, and `expert_judgment_utilization_report_v1`.
   - Uses Pydantic to validate model output shape.

2. Prompt and section integration
   - `map_briefing_memo_ready_prompt.py` now carries `expert_judgment_compression` into reader packets and section writer packets.
   - `map_briefing_memo_ready_section_notes.py` renders `### Expert judgment brief` before compliance-style notes.
   - When an expert brief is present, redundant guidance/audit sections are suppressed from section notes so the model receives a smaller, cleaner handoff.

3. Synthesis integration and transparency
   - `map_briefing_memo_ready_finalization.py` can run the expert compression call before section synthesis.
   - Compression failures are visible and do not silently fall back when the feature is enabled.
   - Final synthesis reports include compression and utilization reports.
   - Feature is currently opt-in via `ECM_EXPERT_JUDGMENT_COMPRESSION=1`.

4. Tests and replay audit
   - Added `tests/test_expert_judgment_compression.py`.
   - Focused regression:
     - `PYTHONPATH=src:tests python3 -m pytest -q tests/test_expert_judgment_compression.py tests/test_canonical_decision_writer_packet.py tests/test_parallel_section_synthesis.py tests/test_analyst_decision_spine.py tests/test_decision_usefulness_synthesis.py tests/test_live_enrichment_contract.py`
     - Result: `47 passed`.

## Replay Artifacts

- `artifacts/replay/eggs_expert_judgment_compression_audit_20260717/`
  - Synthetic compression QA on the real eggs packet.
  - Compression input report:
    - input chars: `17,584`
    - evidence items: `11`
    - mandatory evidence items: `4`
    - quantity count: `4`
    - source count: `14`
  - QA status: `ready`.
  - Section prompt size reduction when expert brief is present:
    - source weighting: `16,247 -> 8,813`
    - answer evidence: `18,382 -> 9,620`
    - counterweights: `15,505 -> 9,621`
    - practical implication: `14,037 -> 7,706`

- `artifacts/replay/eggs_expert_judgment_live_20260717/`
  - Live expert compression with `ollama:gemma4:12b-mlx`.
  - Compression status: `accepted`.
  - QA status: `ready`.
  - Missing mandatory evidence: `0`.
  - Unknown evidence/source/quantity values: `0`.

- `artifacts/replay/eggs_expert_judgment_full_live_20260717/`
  - Full opt-in live memo path.
  - Synthesis status: `accepted_with_evidence_tag_warnings`.
  - Compression status: `accepted`.
  - Required evidence retention: `ready`.
  - Missing mandatory evidence: `0`.
  - Decision surface: `ready`.
  - Analyst utilization: `ready`.
  - Expert utilization after telemetry fix: `ready`.
  - Presented source-binding warnings: `6`.

## Promotion Decision

Do not make this the default production path yet.

Reason:

- The architecture works and prompt context is cleaner.
- Live compression itself passes QA.
- Final memo retains evidence and surfaces expert judgment.
- But the full live memo did not clearly beat the previous best presented memo on prose quality, and citation/source-binding warnings increased relative to the prior deterministic presented memo (`4 -> 6` after presentation).

The feature is therefore implemented fully as an opt-in experimental production path, not silently promoted as default.

## Acceptance Criteria Status

- [x] Compression artifact exists and is inspectable.
- [x] Model output is schema-validated.
- [x] Mandatory evidence and quantity coverage are checked.
- [x] Unknown evidence/source/quantity IDs are rejected by QA.
- [x] Section prompts consume section-specific expert briefs.
- [x] Section prompt sizes decrease materially when expert compression is present.
- [x] Final reports include expert-compression and utilization telemetry.
- [x] Live compression succeeds on the eggs packet.
- [x] Full opt-in live synthesis runs end to end.
- [x] Feature remains opt-in until the memo-quality promotion gate is met.

## Remaining Work

- Improve citation/source-binding behavior under the expert-compression path before default promotion.
- Compare expert-compression output against the `gpt-5.6-sol` polished target and the prior best deterministic presented memo.
- Add an unrelated-case live replay before any default promotion.
- Consider using the compression brief to drive a single global memo synthesis or smaller section-local writing calls, depending on which produces better prose with lower source-binding warnings.
