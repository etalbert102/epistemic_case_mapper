# Decision Model Completion Audit

Status: `implemented-and-smoke-verified`
Date: 2026-07-04

## Scope

This audit records execution of `docs/DECISION_MODEL_PIPELINE_PLAN.md`.

The completed implementation makes the full briefing path emit an explicit argument model and section synthesis packets alongside the existing map, quantity, memo, appendix, and telemetry artifacts. The smoke checks below verify artifact integration on an eggs comparison case and a non-eggs COVID origins slice. They do not by themselves prove that a live model-backed memo now beats the Deep Research baseline on prose quality.

## Implementation Commits

- `7f62db5` Add quantitative anchors and execution plan
- `4b6bf99` Add argument model artifact
- `4c3d558` Persist section synthesis packets
- `e53626e` Add final briefing review packet
- `3654895` Emit section packets for prompt briefings

## Implemented Artifact Path

Every map-briefing run now has a discoverable path for:

- `argument_model.json`
- `decision_synthesis_model.json`
- `graph_synthesis_packet.json`
- `quantity_ledger.json`
- `section_synthesis_packets.json`
- `BRIEFING.md`
- `EVIDENCE_APPENDIX.md`
- `briefing_summary.json`
- `telemetry/gap_diagnosis.json`
- `FINAL_REVIEW_PACKET.md`

The final review packet is generated from run artifacts and is intentionally not a separate quality judgment.

## Verification

Focused tests:

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_section_rewrite.py tests/test_map_briefing.py tests/test_quantity_ledger.py
```

Result: `42 passed in 2.50s`

Full tests:

```bash
PYTHONPATH=src python3 -m pytest -q
```

Result: `170 passed in 11.63s`

Maintainability gate:

```bash
PYTHONPATH=src python3 scripts/maintainability_gate.py
```

Result: pass, including embedded `170 passed in 11.62s`.

## Smoke Runs

Eggs source-held comparison smoke:

```bash
PYTHONPATH=src python3 scripts/ecm.py synthesize map-briefing \
  --map docs/baselines/deep_research/eggs/prototype_run_gemma4_12b_mlx_contract/prioritized_map.json \
  --quality-report artifacts/real_briefs/eggs_moderate_consumption/staged_map/map_quality_report.json \
  --question "For generally healthy adults, should eggs be treated as meaningfully harmful, neutral, or beneficial in dietary advice, especially with respect to cardiovascular risk?" \
  --backend prompt \
  --output-dir artifacts/decision_model_completion_smoke/eggs_prompt \
  --baseline docs/baselines/deep_research/eggs/deep_research_baseline.md \
  --backend-timeout 30
```

Result:

- briefing: `artifacts/decision_model_completion_smoke/eggs_prompt/BRIEFING.md`
- section packets: `artifacts/decision_model_completion_smoke/eggs_prompt/section_synthesis_packets.json`
- final review packet: `artifacts/decision_model_completion_smoke/eggs_prompt/FINAL_REVIEW_PACKET.md`
- argument model counts: support `5`, counterarguments `5`, quantitative anchors `8`, scope boundaries `8`, cruxes `8`
- quantity ledger counts: quantities `96`, quantitative cards `13`

Non-eggs structural smoke:

```bash
PYTHONPATH=src python3 scripts/ecm.py synthesize map-briefing \
  --map artifacts/comparisons/full_pipeline_covid_12b_frame_aware_v3/prioritized_map.json \
  --quality-report artifacts/comparisons/full_pipeline_covid_12b_frame_aware_v3/memo_quality_report.json \
  --question "Given this evidence slice, what should a careful investigator conclude about the competing COVID origins arguments represented here?" \
  --backend prompt \
  --output-dir artifacts/decision_model_completion_smoke/covid_prompt \
  --backend-timeout 30
```

Result:

- briefing: `artifacts/decision_model_completion_smoke/covid_prompt/BRIEFING.md`
- section packets: `artifacts/decision_model_completion_smoke/covid_prompt/section_synthesis_packets.json`
- final review packet: `artifacts/decision_model_completion_smoke/covid_prompt/FINAL_REVIEW_PACKET.md`
- argument model counts: support `5`, counterarguments `0`, quantitative anchors `3`, scope boundaries `8`, cruxes `3`

## Acceptance Criteria Status

| Criterion | Status | Evidence |
|---|---|---|
| Full pipeline emits argument model, section packets, quantity anchors, memo, appendix, telemetry, and final review packet | Pass | Both smoke runs emitted the artifact family. |
| Decision question and sources are deterministic | Pass | Existing metadata/appendix tests pass; smoke final review packets show exact supplied questions. |
| Main memo path can consume promoted quantitative anchors | Pass for integration | Argument model and section packets carry quantitative anchors; live prose quality still depends on backend capability. |
| Scope boundaries and counterarguments are explicit and evidence-owned | Pass for integration | `argument_model.json` and section packets expose these slots with source/claim IDs where available. |
| Before/after eval proves prose improvement over current map briefing | Not re-proven in this audit | Requires a live model-backed benchmark, not a prompt-backend smoke. |
| Eggs comparison against Deep Research has a narrowed gap | Existing prior evidence, not newly re-run | See `docs/baselines/deep_research/eggs/prototype_run_gemma4_12b_mlx_contract/COMPARISON_NOTES.md`. |
| At least one non-eggs case demonstrates structural transfer | Pass for structural smoke | COVID prompt-backend smoke emitted the same artifact family. |
| Full tests pass | Pass | `170 passed`. |
| Maintainability gate remains calibrated | Pass | Gate passed, including domain vocabulary isolation and design debt checks. |

## Residual Risk

- The implementation is structurally complete, but a live model-backed eggs rerun is still needed before claiming the final memo beats the checked-in Deep Research baseline on readability or synthesis sophistication.
- Prompt-backend smoke verifies packet assembly and deterministic scaffolding. It does not measure how well a stronger model uses those packets.
- The COVID smoke produced no counterargument slots. That can be valid for a given map, but a model-backed adversarial case should be used to verify counterargument richness.
- Quantitative anchors are now promoted into artifacts and prompts; the next quality check should inspect whether final prose uses them naturally rather than only listing them.

## Next Quality Gate

Run one live backend comparison after this structural completion:

```bash
PYTHONPATH=src python3 scripts/ecm.py synthesize map-briefing \
  --map docs/baselines/deep_research/eggs/prototype_run_gemma4_12b_mlx_fuller_sources/prioritized_map.json \
  --quality-report docs/baselines/deep_research/eggs/prototype_run_gemma4_12b_mlx_fuller_sources/map_quality_report.json \
  --question "For generally healthy adults, should eggs be treated as meaningfully harmful, neutral, or beneficial in dietary advice, especially with respect to cardiovascular risk?" \
  --backend ollama:gemma4:12b-mlx \
  --output-dir artifacts/decision_model_live_quality/eggs_gemma4_12b_mlx \
  --baseline docs/baselines/deep_research/deep_research_eggs_Claude_Opus4.8.md \
  --backend-timeout 120 \
  --backend-retries 1
```

Judge the result against the Deep Research baseline on first-page readability, quantitative depth, crux clarity, scope binding, and unsupported-claim rate.
