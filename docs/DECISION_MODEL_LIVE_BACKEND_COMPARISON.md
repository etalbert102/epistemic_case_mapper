# Decision Model Live Backend Comparison

Date: 2026-07-04
Backend: `ollama:gemma4:12b-mlx`

## Run

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

Output:

- briefing: `artifacts/decision_model_live_quality/eggs_gemma4_12b_mlx/BRIEFING.md`
- evidence appendix: `artifacts/decision_model_live_quality/eggs_gemma4_12b_mlx/EVIDENCE_APPENDIX.md`
- final review packet: `artifacts/decision_model_live_quality/eggs_gemma4_12b_mlx/FINAL_REVIEW_PACKET.md`
- gap diagnosis: `artifacts/decision_model_live_quality/eggs_gemma4_12b_mlx/telemetry/GAP_DIAGNOSIS.md`

Internal validation:

- briefing validation: `passes_contract`, score `100`
- memo quality report: `polished`, score `100`
- section rewrite: `accepted_partial`, `7` accepted sections of `9`
- reader memo rewrite: `accepted_after_repair`

## Verdict

The live backend output is a real improvement over earlier rough prototype memos, but it still does not beat the Deep Research baseline as a standalone decision-support synthesis.

It is stronger on inspectability: the run emits an argument model, quantity ledger, section packets, validation reports, per-section prompts/raw outputs, and a gap diagnosis. A judge can audit how the memo was assembled and where the evidence map constrained it.

It is weaker on synthesis: the memo is shorter, less quantitatively dense, and less clinically discriminating. It reaches the same broad answer as the baseline, but it does not yet explain the answer with the same richness.

## Where The Prototype Wins

- More auditable artifact trail than the baseline.
- Clear decision question and deterministic source list in the memo.
- Explicit crux section that names biomarker-vs-hard-outcome, subgroup, and dose-boundary cruxes.
- Internal validation caught and repaired several section/rewrite issues.
- The gap diagnosis correctly identifies source coverage and decision synthesis as the largest remaining drivers.

## Where Deep Research Still Wins

- First-page answer quality: the baseline states the practical answer, confidence, intake threshold, and caution subgroups in one precise bottom line.
- Quantitative depth: the baseline includes more effect sizes, sample sizes, confidence intervals, and biomarker changes in main prose.
- Biomarker synthesis: the baseline integrates LDL-C, ApoB, LDL:HDL ratio, saturated fat, and responder heterogeneity; the prototype mentions LDL but omits ApoB entirely from the final memo.
- Subgroup handling: the baseline covers type 2 diabetes, high LDL/ApoB, familial hypercholesterolemia, hyper-responders, high baseline risk, and very high intake. The prototype mainly covers diabetes and a weak kidney-function exception.
- Source use: the prototype underuses PROSPERITY, Carter 2025, PURE, AHA guidance, and hyper-responder evidence in the final prose.
- Narrative synthesis: the baseline explains why RCTs, cohorts, biomarkers, and substitution evidence point in different directions. The prototype is more section-correct than deeply explanatory.

## Concrete Quality Signals

Word and term scan:

| Metric | Prototype | Deep Research baseline |
|---|---:|---:|
| Words | `1424` | `2813` |
| Digit characters | `147` | `923` |
| `LDL` mentions | `6` | `53` |
| `ApoB` mentions | `0` | `22` |
| `PROSPERITY` mentions | `0` | `5` |
| `PURE` mentions | `1` | `3` |
| `hyper` mentions | `0` | `10` |
| `familial` mentions | `0` | `2` |

Telemetry gap drivers:

- source coverage: baseline uses source/context not present in the briefing packet;
- decision synthesis: baseline concepts are present as context but not synthesized into the memo.

## Main Failure Mode Exposed

The pipeline now has the right intermediate artifacts, but the synthesis layer still does not reliably promote the most decision-relevant quantitative and subgroup evidence into the main memo. The problem is not only prose polish. It is prioritization and synthesis: high-value evidence exists in the packet but is not consistently made load-bearing in the final answer.

Examples:

- `argument_model.json` includes quantitative anchors from Drouin-Chartier and Zhong, but the memo does not put the central `RR 0.98, 95% CI 0.93 to 1.03, 1,720,108 participants` result in the bottom line.
- The final memo names LDL but omits ApoB and hyper-responder handling, even though those are central to the baseline's decision logic.
- The memo overweights Qin 2018 as key supporting evidence, although the baseline treats it as one regional cohort among a broader triangulation.
- The memo includes an impaired-kidney-function exception that is not as decision-central as the baseline's high LDL/ApoB, familial hypercholesterolemia, and hyper-responder boundaries.

## Next Intervention

Add a deterministic "main-memo obligation ledger" after the argument model and before section synthesis. It should require each final memo to either include, explicitly reject, or mark out of scope:

- top effect estimates and confidence intervals;
- largest study-scale anchors;
- strongest opposing quantitative result;
- key subgroup boundaries;
- mechanistic/biomarker cruxes that change the decision;
- guideline/practical threshold statements;
- source-family balance across RCTs, cohorts, guidelines, mechanisms, and substitution/comparator evidence.

The model should still write the prose, but deterministic code should decide which obligations must appear in the first page and which can remain in the appendix.
