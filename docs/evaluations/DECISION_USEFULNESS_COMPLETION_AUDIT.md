# Decision Usefulness Layer Completion Audit

Date: 2026-07-14

## Implementation Commits

- `ef195c5` - recorded the decision-usefulness layer plan.
- `9adeca7` - added `decision_usefulness_packet_v1` schemas, validators, context builder, and compact prompt projection.
- `af42b0a` - added the model-backed decision-usefulness builder and repair loop.
- `04296b3` - integrated the layer into the active memo-ready synthesis path, artifacts, telemetry, and prompt.
- `bc7e234` - added parse/inventory audit reports and artifact coverage.

## What Is Implemented

The active production path now builds a `decision_usefulness_packet_v1` after the canonical writer packet exists and before lightweight writer guidance. The model owns semantic judgments about answer shape, stance, criteria, diagnostic evidence, tradeoffs, crux thresholds, premortems, and monitoring triggers. Deterministic code owns schema normalization, source/evidence ID validation, parse reports, inventory reports, artifact writing, telemetry, and compact prompt projection.

The final synthesis prompt receives only a compact `decision_usefulness` projection, not raw debug surfaces or legacy option/crux artifacts.

## Artifact Path Examples

Eggs saved-artifact live evaluation:

- `artifacts/decision_usefulness_eval/eggs_saved_live_20260714/decision_usefulness_packet.json`
- `artifacts/decision_usefulness_eval/eggs_saved_live_20260714/decision_usefulness_quality_report.json`
- `artifacts/decision_usefulness_eval/eggs_saved_live_20260714/baseline_memo.md`
- `artifacts/decision_usefulness_eval/eggs_saved_live_20260714/with_decision_usefulness_memo.md`
- `artifacts/decision_usefulness_eval/eggs_saved_live_20260714/decision_usefulness_comparison_report.json`
- `artifacts/decision_usefulness_eval/eggs_saved_live_20260714/decision_usefulness_eval.md`

Second-shape check:

- `artifacts/decision_usefulness_eval/covid_saved_live_20260714/decision_usefulness_packet.json`
- `artifacts/decision_usefulness_eval/covid_saved_live_20260714/decision_usefulness_second_shape_check.json`

Sparse upstream-artifact diagnostic:

- `artifacts/decision_usefulness_eval/lhc_saved_live_20260714/decision_usefulness_non_health_check.json`

## Prompt Excerpt

The final prompt now instructs synthesis to use the decision-usefulness projection for options, criteria, tradeoffs, crux thresholds, and update triggers, while avoiding fake alternatives for single-stance, threshold, or classification answers. The reader packet contains a compact `decision_usefulness` field derived from the validated packet.

## Source ID Validation

Eggs evaluation:

- Builder status: `parsed`
- Quality status: `warning`
- Invalid source/evidence references: `0`
- Invalid option/criterion matrix references: `0`
- Warning: `criteria_without_matrix_evidence`

The warning is expected for single-stance answers because the model produced criteria without a multi-option matrix. This should be refined so matrix sparsity is not treated as a warning when `answer_shape` is `single_stance`, `threshold`, or `classification` and diagnostic evidence/cruxes are present.

## Before/After Memo Comparison

On the eggs saved-artifact live evaluation, both baseline synthesis and decision-usefulness synthesis were accepted with retention warnings. The decision-usefulness memo improved source labels and made the scope boundaries clearer. It more directly stated that the neutral recommendation excludes people with type 2 diabetes or borderline high LDL-c.

However, the memo did not fully exploit the new packet. The packet contained a named tradeoff, a crux threshold, and a monitoring trigger, but the synthesized memo mostly absorbed those into ordinary prose rather than making them explicit decision support. This is useful but not yet a decisive uplift over a strong direct synthesis baseline.

## Generalizability Check

The COVID origins representation question produced a valid single-stance decision-usefulness packet with criteria, diagnostic evidence, a tradeoff, a crux threshold, a premortem, and a monitoring trigger. That suggests the layer is not hard-coded to health/nutrition content.

The LHC artifact returned `insufficient_information`, but inspection showed the saved packet lacked canonical priority evidence and an argument spine. That is an upstream artifact sufficiency issue rather than evidence of domain overfit.

## Known Residual Weaknesses

- Synthesis underuses some decision-usefulness rows, especially explicit tradeoff and monitoring-trigger language.
- Quality reporting over-warns on missing option-criteria matrix cells for single-stance answers.
- The layer is only as good as the canonical packet; sparse canonical packets lead to transparent insufficiency.
- The evaluation is saved-artifact based, not a fresh full end-to-end run from documents.
- The comparison is semi-manual and not blind.

## Default Decision

Keep the layer active in the default live path, but non-blocking. It should improve available decision structure when the canonical packet is rich enough and emit transparent warnings when it cannot. It should not become a hard quality gate until the matrix-warning calibration and synthesis-use gap are addressed.
