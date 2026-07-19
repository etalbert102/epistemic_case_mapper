# Actual Live Comparison: Decision Recovery Path

Date: 2026-07-11

Backend: `ollama:gemma4:12b-mlx`

## Runs

### Eggs: Deep Research Source-Held Comparison

Command shape:

```bash
ECM_OLLAMA_NUM_PREDICT=4096 ECM_OLLAMA_PARALLELISM=4 PYTHONPATH=src python3 scripts/ecm.py synthesize map-briefing \
  --map docs/baselines/deep_research/eggs/prototype_run_gemma4_12b_mlx_fuller_sources/prioritized_map.json \
  --quality-report docs/baselines/deep_research/eggs/prototype_run_gemma4_12b_mlx_fuller_sources/map_quality_report.json \
  --question "For generally healthy adults, should eggs be treated as meaningfully harmful, neutral, or beneficial in dietary advice, especially with respect to cardiovascular risk?" \
  --backend ollama:gemma4:12b-mlx \
  --output-dir artifacts/decision_model_live_quality/eggs_recovery_actual_20260711 \
  --baseline docs/baselines/deep_research/deep_research_eggs_Claude_Opus4.8.md \
  --backend-timeout 240 \
  --backend-retries 1
```

Main artifacts:

- `artifacts/decision_model_live_quality/eggs_recovery_actual_20260711/BRIEFING.md`
- `artifacts/decision_model_live_quality/eggs_recovery_actual_20260711/global_decision_model_report.json`
- `artifacts/decision_model_live_quality/eggs_recovery_actual_20260711/decision_writer_packet_quality_report.json`
- `artifacts/decision_model_live_quality/eggs_recovery_actual_20260711/memo_semantic_acceptance_report.json`
- `artifacts/decision_model_live_quality/eggs_recovery_actual_20260711/telemetry/gap_diagnosis.json`

### COVID: Non-Egg Generalization Check

Command shape:

```bash
ECM_OLLAMA_NUM_PREDICT=4096 ECM_OLLAMA_PARALLELISM=4 PYTHONPATH=src python3 scripts/ecm.py synthesize map-briefing \
  --map artifacts/comparisons/full_pipeline_covid_12b_manifest_question_v4/prioritized_map.json \
  --quality-report artifacts/e2e_realistic/covid/staged_map/map_quality_report.json \
  --question "How should a narrow slice of COVID origins evidence be represented without flattening Bayesian disagreement?" \
  --backend ollama:gemma4:12b-mlx \
  --output-dir artifacts/decision_model_live_quality/covid_recovery_actual_20260711 \
  --region covid_bayesian_disagreement \
  --baseline examples/covid_origins_slice/flat_synthesis_baseline.md \
  --backend-timeout 240 \
  --backend-retries 1
```

Main artifacts:

- `artifacts/decision_model_live_quality/covid_recovery_actual_20260711/BRIEFING.md`
- `artifacts/decision_model_live_quality/covid_recovery_actual_20260711/global_decision_model_report.json`
- `artifacts/decision_model_live_quality/covid_recovery_actual_20260711/decision_writer_packet_quality_report.json`
- `artifacts/decision_model_live_quality/covid_recovery_actual_20260711/memo_semantic_acceptance_report.json`
- `artifacts/decision_model_live_quality/covid_recovery_actual_20260711/telemetry/gap_diagnosis.json`

## Structural Results

The recovery path works as intended structurally.

| Run | Analyst decision model | Global model | Decision writer packet | Retention | Semantic acceptance |
|---|---:|---|---|---|---|
| Eggs | `8/8` parsed, `0` failed | `ready` | `ready`, `23` units | `ready`, `0` missing critical/high/mandatory | `accepted_with_warnings` |
| COVID | `10/10` parsed, `0` failed | `ready` | `ready`, `28` units | `ready`, `0` missing critical/high/mandatory | `accepted_with_warnings` |

This is a meaningful improvement over the earlier failure mode where polished memos could hide decision-readiness failures. The new reports make the semantic acceptance status explicit.

## Memo Metrics

| Output | Words | Digit chars | Notable terms |
|---|---:|---:|---|
| Eggs new memo | `802` | `221` | `LDL` 5, `Drouin` 6, `Zhong` 5, `PURE` 2, `diabetes` 4 |
| Eggs prior live memo | `1454` | `147` | `LDL` 6, `Drouin` 5, `Zhong` 6, `PURE` 1, `diabetes` 13 |
| Eggs Deep Research baseline | `3194` | `923` | `LDL` 53, `ApoB` 22, `PROSPERITY` 5, `hyper` 10, `familial` 2 |
| COVID new memo | `1071` | `276` | `Rootclaim` 24, `Good Judgment` 4, `Levin` 2, `Weissman` 4, `Bayesian` 10 |
| COVID flat baseline | `423` | `9` | `Rootclaim` 5, `Good Judgment` 1, `Levin` 2, `Weissman` 3, `Bayesian` 7 |

## Eggs Comparison

Verdict: the new path is better as a validated decision-support pipeline, but the final memo still does not beat the Deep Research baseline as a standalone answer.

What improved:

- The analyst decision model no longer has partial-shard failure.
- The global decision model is explicit and `ready`.
- The decision writer packet is explicit and `ready`.
- Final retention is clean: no missing critical, high-priority, or mandatory packet evidence.
- The memo includes the decision question and deterministic source list.
- Quantitative density improved versus the prior live memo by digit count, despite being shorter.

What remains weaker than Deep Research:

- The bottom line is less crisp and less calibrated.
- It still underuses central biomarker/subgroup concepts: `ApoB`, hyper-responders, familial hypercholesterolemia, and PROSPERITY are absent.
- It includes some awkward or suspicious quantity prose, especially a long list of percentages in the cholesterol-adjustment paragraph.
- It overleans on broad cohort statements and does not integrate source families as well as the baseline.
- The final readiness report still has warnings: confidence/uncertainty not visible enough, bounded answer not visible enough, and weak/indirect source limits not surfaced clearly enough.

The gap telemetry agrees with this diagnosis. It attributes remaining gaps to missing source/context terms and bad synthesis: baseline concepts are present in the larger source/baseline universe but not sufficiently surfaced in the final briefing.

## COVID Comparison

Verdict: the new memo is stronger than the checked-in flat baseline for decision support.

What improved:

- The memo is more complete and more source-auditable than the flat baseline.
- It preserves the core disagreement structure: expert/adjudicated outcome, Rootclaim postmortem, Good Judgment aggregate/minority distinction, Bayesian decomposition, market/geography interpretation, and bias critiques.
- It includes useful quantitative anchors: `74%`, `25%`, and a lab-leak-favoring odds ratio of `14`.
- It has deterministic source links and a source list.
- Retention is clean and semantic acceptance is `accepted_with_warnings`.

Remaining issues:

- It still reads somewhat mechanical.
- It repeats the “preserve variance rather than collapse to one consensus” point.
- The final readiness report still warns that confidence/uncertainty and boundedness are not visible enough.
- Packet quality has source-grounding warnings and weakly anchored bundles.

Compared with the flat baseline, this is a real decision-support improvement. Compared with the ideal output, it still needs better prose discipline and more explicit bounded-confidence language.

## Overall Assessment

The implemented recovery path improved reliability and auditability more than final prose quality.

Best evidence of improvement:

- Live model parallel decision modeling completed without failed shards in both cases.
- `global_decision_model_report.json` and `decision_writer_packet_quality_report.json` are `ready` in both cases.
- `memo_semantic_acceptance_report.json` now separates decision acceptance from polish.
- COVID shows a clear uplift over a flat baseline.

Main remaining bottleneck:

- Final synthesis still fails to reliably turn a good packet into a first-rate memo. The eggs memo is accepted with warnings, but it remains less decision-grade than Deep Research because it misses or underweights important quantitative/subgroup evidence and does not make confidence boundaries crisp enough.

Highest-ROI next intervention:

- Promote the new `decision_writer_packet` to the active synthesis interface, or add a final synthesis mode that writes directly from the global decision model plus decision writer packet.
- Fix `analyst_packet_refinement_report.json` failures. Both live runs fell back to scaffold there, which means a model stage intended to improve synthesis is not currently contributing.
- Add a first-page obligation ledger for load-bearing quantities, subgroup boundaries, source-family balance, and bounded-confidence language.
