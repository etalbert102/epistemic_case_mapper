# Decision-Model-First Packet Assembly Vertical Slice Audit

## Scope

This audit records the bounded vertical slice executed from `docs/plans/DECISION_MODEL_FIRST_PACKET_ASSEMBLY_PLAN.md`.

Implemented in this slice:

- faceted decision problem report;
- candidate answer set;
- source evidence graph;
- decision obligation graph;
- evidence-to-answer matrix;
- derived decision slots;
- packet budget allocation report;
- packet compression invariant report;
- protected quantitative-anchor candidate path;
- richness-aware candidate dedupe;
- vertical-slice telemetry report;
- eggs prompt-backend end-to-end run.

Not completed in this slice:

- live model semantic refinement for facets, obligations, or matrix rows;
- direct-source-synthesis baseline comparison in code;
- full packet view split into separate synthesis/audit/source-trace/QA projections;
- calibrated blocking gates for matrix quality or compression invariants.

## Commits

- `84462f2` Record decision-model packet assembly plan
- `45ea711` Add decision problem report artifacts
- `f5719af` Add source evidence graph artifact
- `873752f` Add decision obligation matrix artifacts
- `4ca4a94` Add decision slots and packet budget reports
- `6bd6c33` Protect quantitative anchors in packet assembly
- `7f70ac8` Add decision model vertical slice telemetry
- `59d12e4` Refine vertical slice quantity telemetry

## Verification

Focused gates run during slices:

```bash
PYTHONPATH=src python3 -m pytest tests/test_decision_problem_report.py tests/test_decision_briefing_packet.py tests/test_decision_packet_eligibility.py -q
PYTHONPATH=src python3 -m pytest tests/test_source_evidence_graph.py tests/test_decision_problem_report.py tests/test_decision_briefing_packet.py -q
PYTHONPATH=src python3 -m pytest tests/test_decision_obligation_matrix.py tests/test_source_evidence_graph.py tests/test_decision_problem_report.py tests/test_decision_briefing_packet.py -q
PYTHONPATH=src python3 -m pytest tests/test_decision_slots_and_budget.py tests/test_decision_obligation_matrix.py tests/test_decision_briefing_packet.py -q
PYTHONPATH=src python3 -m pytest tests/test_packet_quantity_candidate_retention.py tests/test_decision_packet_eligibility.py tests/test_decision_briefing_packet.py tests/test_quantity_obligation_ledger.py -q
PYTHONPATH=src python3 -m pytest tests/test_decision_model_vertical_slice_report.py tests/test_packet_quantity_candidate_retention.py tests/test_decision_slots_and_budget.py tests/test_decision_briefing_packet.py -q
```

Final full-suite verification:

```bash
PYTHONPATH=src python3 -m pytest -q
```

Result:

```text
520 passed in 15.35s
```

## End-To-End Run

Command:

```bash
PYTHONPATH=src python3 -m epistemic_case_mapper.cli synthesize map-briefing \
  --map artifacts/semantic/eggs_polarity_v3_eval_20260709/worked_map.json \
  --quality-report artifacts/semantic/eggs_polarity_v3_eval_20260709/map_quality_report.json \
  --question "For generally healthy adults, should eggs be treated as meaningfully harmful, neutral, or beneficial in dietary advice, especially with respect to cardiovascular risk?" \
  --backend prompt \
  --output-dir artifacts/packet_assembly_eval/eggs_decision_model_vertical_slice_20260709 \
  --max-claims 0
```

Primary artifacts:

- `artifacts/packet_assembly_eval/eggs_decision_model_vertical_slice_20260709/decision_model_vertical_slice_report.json`
- `artifacts/packet_assembly_eval/eggs_decision_model_vertical_slice_20260709/decision_briefing_packet.json`
- `artifacts/packet_assembly_eval/eggs_decision_model_vertical_slice_20260709/evidence_answer_matrix.json`
- `artifacts/packet_assembly_eval/eggs_decision_model_vertical_slice_20260709/source_evidence_graph.json`
- `artifacts/packet_assembly_eval/eggs_decision_model_vertical_slice_20260709/packet_budget_allocation_report.json`
- `artifacts/packet_assembly_eval/eggs_decision_model_vertical_slice_20260709/packet_compression_report.json`

## Quality Delta

Original observed failure:

- final decision packet retained zero `quantitative_anchor` bundles even though quantitative evidence existed upstream;
- quantity obligations disagreed across coverage/sufficiency telemetry before the earlier ledger fix;
- quantity evidence was overrepresented as must-retain obligations and underrepresented as first-class evidence bundles.

Current eggs vertical-slice result:

```json
{
  "status": "vertical_slice_operational",
  "candidate_answer_count": 6,
  "source_graph_node_count": 143,
  "source_graph_quantity_node_count": 57,
  "obligation_count": 15,
  "evidence_answer_matrix_row_count": 259,
  "decision_slot_count": 15,
  "quantitative_anchor_bundle_count": 8,
  "top_quantity_represented_bundle_count": 8,
  "quantity_missing_count": 0,
  "quantity_obligation_count": 12
}
```

Bundle role counts:

```json
{
  "context": 7,
  "counterweight": 5,
  "quantitative_anchor": 8,
  "scope_boundary": 4,
  "strongest_support": 4
}
```

This fixes the immediate quantity-retention failure: top quantities are now represented by first-class quantitative-anchor bundles and no top quantity obligations are missing.

## Remaining Risks

- `high_priority_omitted_count` is still high in the eggs packet, so the packet still needs represented-vs-truly-lost omission accounting.
- `low_question_fit_primary_bundle_count` remains nonzero, so report-only relevance warnings need better matrix/slot-level routing before becoming blocking.
- `packet_compression_report` still reports missing invariants on many matrix rows; this is expected while the matrix is broad/report-only, but it must be tightened before relying on it for synthesis.
- Evidence quality is preserved as unknown where not available; the architecture is ready for quality metadata, but extraction quality is still shallow.
- Direct-source-synthesis comparison has not yet been run in code, so decision-usefulness improvement over direct synthesis is not proven by this audit.

## Next Required Slice

Before broadening the architecture, run a live model or direct-source baseline comparison on the same eggs source set and evaluate whether the packet-based memo improves:

- retained quantities;
- counterevidence;
- scope/applicability limits;
- named gaps;
- traceability;
- final readability.

If it does not improve at least one decision-usefulness dimension, stop broad implementation and diagnose whether the bottleneck is the source evidence graph, evidence-to-answer matrix, packet budget allocation, or synthesis.
