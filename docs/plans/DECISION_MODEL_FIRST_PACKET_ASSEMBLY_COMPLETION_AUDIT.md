# Decision-Model-First Packet Assembly Completion Audit

## Scope

This audit records completion of `docs/plans/DECISION_MODEL_FIRST_PACKET_ASSEMBLY_PLAN.md` as of July 9, 2026.

The implemented architecture is:

```text
decision question
-> decision problem report and candidate answers
-> source evidence graph
-> decision obligation graph
-> evidence-to-answer matrix
-> derived slots and packet budget reports
-> synthesis / audit / source-trace / QA packet views
-> telemetry comparing packet memo retention against a supplied direct-source or deep-research baseline
```

## Completed Slices And Commits

- `84462f2` Record decision-model packet assembly plan
- `45ea711` Add decision problem report artifacts
- `f5719af` Add source evidence graph artifact
- `873752f` Add decision obligation matrix artifacts
- `4ca4a94` Add decision slots and packet budget reports
- `6bd6c33` Protect quantitative anchors in packet assembly
- `7f70ac8` Add decision model vertical slice telemetry
- `59d12e4` Refine vertical slice quantity telemetry
- `4a88bae` Add packet omission and matrix quality telemetry
- `87681ce` Add decision packet view projections
- `bafcb16` Add direct source synthesis comparison telemetry

## Files Changed By The Final Execution Slices

- `src/epistemic_case_mapper/map_briefing_packet_coverage.py`
- `src/epistemic_case_mapper/map_briefing_decision_packet.py`
- `src/epistemic_case_mapper/map_briefing_artifacts.py`
- `src/epistemic_case_mapper/map_briefing_packet_views.py`
- `src/epistemic_case_mapper/map_briefing_direct_synthesis_comparison.py`
- `src/epistemic_case_mapper/map_briefing_telemetry.py`
- `tests/test_packet_omission_accounting.py`
- `tests/test_packet_views.py`
- `tests/test_direct_synthesis_comparison.py`
- `tests/test_decision_obligation_matrix.py`
- `tests/test_map_briefing_decision_contracts.py`

## Verification Commands

Focused checks run during the final slices:

```bash
PYTHONPATH=src python3 -m pytest tests/test_packet_omission_accounting.py tests/test_decision_obligation_matrix.py tests/test_packet_quantity_candidate_retention.py -q
PYTHONPATH=src python3 -m pytest tests/test_packet_views.py tests/test_decision_model_vertical_slice_report.py tests/test_decision_slots_and_budget.py -q
PYTHONPATH=src python3 -m pytest tests/test_direct_synthesis_comparison.py tests/test_map_briefing_decision_contracts.py -q
```

Full-suite checks:

```bash
PYTHONPATH=src python3 -m pytest -q
```

Result after the final code slice:

```text
525 passed in 15.33s
```

## End-To-End Verification Runs

Eggs run:

```bash
PYTHONPATH=src python3 -m epistemic_case_mapper.cli --repo-root . synthesize map-briefing \
  --map artifacts/quality_packet_completion/eggs_prompt/prioritized_map.json \
  --quality-report artifacts/quality_packet_completion/eggs_prompt/evidence_quality_report.json \
  --question "For generally healthy adults, should eggs be treated as meaningfully harmful, neutral, or beneficial in dietary advice, especially with respect to cardiovascular risk?" \
  --backend prompt \
  --output-dir artifacts/decision_model_plan_completion/eggs_prompt \
  --baseline docs/baselines/deep_research/deep_research_eggs_Claude_Opus4.8.md \
  --max-claims 0
```

LHC canary run:

```bash
PYTHONPATH=src python3 -m epistemic_case_mapper.cli --repo-root . synthesize map-briefing \
  --map artifacts/quality_packet_completion/lhc_prompt/prioritized_map.json \
  --quality-report artifacts/quality_packet_completion/lhc_prompt/evidence_quality_report.json \
  --question "Why did investigators conclude that LHC operation would not create a catastrophic black hole risk?" \
  --backend prompt \
  --output-dir artifacts/decision_model_plan_completion/lhc_prompt \
  --baseline examples/lhc_black_holes/flat_synthesis_baseline.md \
  --max-claims 0
```

Both runs completed and emitted:

- `decision_briefing_packet.json`
- `decision_model_vertical_slice_report.json`
- `packet_views.json`
- `evidence_answer_matrix_quality_report.json`
- `telemetry/direct_source_synthesis_comparison.json`

## Eggs Result

Vertical slice status: `vertical_slice_operational`.

Key signals:

```json
{
  "candidate_answer_count": 7,
  "source_graph_node_count": 177,
  "source_graph_quantity_node_count": 72,
  "obligation_count": 17,
  "evidence_answer_matrix_row_count": 307,
  "decision_slot_count": 17,
  "quantitative_anchor_bundle_count": 8,
  "top_quantity_represented_bundle_count": 8,
  "compression_missing_invariant_count": 176
}
```

Coverage:

```json
{
  "candidate_pool_count": 68,
  "evidence_bundle_count": 29,
  "high_priority_omitted_count": 31,
  "high_priority_represented_elsewhere_count": 28,
  "high_priority_truly_lost_count": 3,
  "quantity_missing_count": 0,
  "low_question_fit_primary_bundle_count": 6
}
```

Direct-source/deep-research comparison telemetry:

```json
{
  "status": "baseline_retains_more_traceable_anchors",
  "retention_delta_vs_baseline": {
    "source_label_mentions": 12,
    "quantity_mentions": 8,
    "bundle_anchor_mentions": -1
  }
}
```

Read: the packet architecture now preserves quantities and source labels better than the saved baseline on this deterministic anchor metric, but the baseline still retains one more bundle-level semantic anchor. The packet still reports three truly lost high-priority items after trimming.

## Non-Eggs Canary Result

Vertical slice status: `vertical_slice_operational`.

Key signals:

```json
{
  "candidate_answer_count": 3,
  "source_graph_node_count": 39,
  "source_graph_quantity_node_count": 1,
  "obligation_count": 9,
  "evidence_answer_matrix_row_count": 21,
  "decision_slot_count": 9,
  "quantitative_anchor_bundle_count": 3,
  "top_quantity_represented_bundle_count": 3,
  "compression_missing_invariant_count": 1
}
```

Coverage:

```json
{
  "candidate_pool_count": 26,
  "evidence_bundle_count": 11,
  "high_priority_omitted_count": 0,
  "high_priority_represented_elsewhere_count": 0,
  "high_priority_truly_lost_count": 0,
  "quantity_missing_count": 0,
  "low_question_fit_primary_bundle_count": 1
}
```

Direct-source baseline comparison telemetry:

```json
{
  "status": "packet_memo_retains_at_least_as_many_traceable_anchors",
  "retention_delta_vs_baseline": {
    "source_label_mentions": 4,
    "quantity_mentions": 1,
    "bundle_anchor_mentions": 0
  }
}
```

Read: the same packet architecture transfers to an unrelated catastrophic-risk case and satisfies the decision-model-first invariants without truly lost high-priority evidence.

## Acceptance Criteria Status

- Explicit faceted decision problem report: complete.
- Explicit candidate answer set: complete.
- Source evidence graph with source/claim/quantity lineage: complete.
- Decision obligation graph: complete.
- Evidence-to-answer matrix: complete.
- Derived decision slots: complete.
- Quantitative anchors represented as bundles: complete.
- Richness-aware dedupe: complete.
- Deterministic semantic blockers converted to warnings where relevant to packet retention: complete for this plan scope.
- Coverage distinguishes represented evidence from truly lost evidence: complete.
- Non-eggs canary satisfies decision-model-first invariants: complete.
- Compression invariant reports are emitted: complete.
- Obligation-aware packet budget reports are emitted: complete.
- Packet views split synthesis, audit, source-trace, and QA projections: complete.
- Packet-based synthesis is compared against supplied direct-source/deep-research baselines: complete.
- Full test suite passes: complete.

## Known Limitations And Deferred Work

- The eggs packet still has three truly lost high-priority items after trimming; packet assembly is no longer silently losing them, but retention is not yet perfect.
- The evidence-to-answer matrix is broad and report-oriented. It is useful for coverage and slot construction, but `compression_missing_invariant_count` remains high on eggs.
- Prompt-backend end-to-end runs verify deterministic artifact construction and pipeline wiring. They do not prove live-model memo quality.
- The direct-source comparison uses traceable anchors. It does not score prose coherence, argument sophistication, or whether the baseline's additional bundle anchor is decision-critical.
- Some generated memo prose remains awkward because this plan was packet-architecture work, not a final prose-polish plan.

## Final Judgment

The recorded plan is fully executed by its own criteria. The architecture now produces the planned owner artifacts, projection views, omission accounting, comparison telemetry, and cross-case verification. The remaining problems are visible quality issues in packet selection and final prose, not incomplete execution of the decision-model-first packet assembly plan.
