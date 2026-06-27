# Eggs Decision-Space Erosion Audit

Status: `human-review-needed`
Prompt/procedure: `erosion_audit_prompt_v1`

Baseline comparator: `examples/eggs/flat_synthesis_baseline.md`
Map comparator: `examples/eggs/worked_region_observational_vs_rct_map.md`

## Counted Losses

loss_id: eggs_loss_001

loss_type: `endpoint collapse`

lost_item: The flat baseline says randomized trials "add another layer" but does not preserve the endpoint boundary that Li measures LDL-c and LDL-c/HDL-c rather than CVD events.

source_support: `li_2020_egg_cholesterol_rct_meta` lines 30-36, 188-201, and 292-293.

flat_baseline_omission: The baseline mentions biomarkers but does not make the biomarker-versus-health-outcome boundary a navigable dependency.

case_map_preserves: `eggs_c015`, `eggs_c016`, `eggs_c017`, `eggs_r005`, `eggs_r006`, `eggs_r007`.

adversarial_check: survives, because the source subset and baseline prompt both make endpoint caveats central to the answer.

loss_id: eggs_loss_002

loss_type: `study-design tension flattened`

lost_item: The flat baseline states BMJ and JAMA findings sequentially but does not preserve their tension as a relation requiring method, exposure-unit, and adjustment comparison.

source_support: `bmj_2020_egg_consumption_cvd` lines 40-43 and 537-544; `jama_2019_dietary_cholesterol_eggs` lines 33-52 and 70-73.

flat_baseline_omission: The baseline reports both results but does not keep an explicit conflict edge between null moderate-intake evidence and positive dose-response evidence.

case_map_preserves: `eggs_c008`, `eggs_c012`, `eggs_c013`, `eggs_r003`.

adversarial_check: survives, because the same-source subset contains both findings and the relation changes what a reviewer should inspect next.

loss_id: eggs_loss_003

loss_type: `population caveat weakened`

lost_item: The flat baseline mentions high LDL and diabetes, but does not preserve these as separate subgroup caveats with different source bases and implications.

source_support: `aha_2023_dietary_cholesterol_news` lines 56-62; `bmj_2020_egg_consumption_cvd` lines 524-532.

flat_baseline_omission: High LDL and diabetes appear in a final caveat list rather than as claims that qualify different parts of the recommendation.

case_map_preserves: `eggs_c007`, `eggs_c009`, `eggs_r010`, `eggs_r017`.

adversarial_check: survives, because subgroup caveats are in the fixed sources and materially affect dietary advice.

loss_id: eggs_loss_004

loss_type: `replacement context compressed`

lost_item: The flat baseline says advice depends on foods eggs replace, but does not preserve BMJ's specific replacement-food finding or the warning that replacement analysis is statistical modeling.

source_support: `bmj_2020_egg_consumption_cvd` lines 241 and 531-536.

flat_baseline_omission: The baseline does not name red meat or full-fat milk replacements and does not preserve the modeling caution.

case_map_preserves: `eggs_c010`, `eggs_r011`, `eggs_r016`.

adversarial_check: survives, because replacement context is source-supported and directly affects the practical meaning of "eat fewer eggs" or "eggs are fine."

loss_id: eggs_loss_005

loss_type: `guideline authority blurred`

lost_item: The flat baseline treats federal and AHA guidance as advice but does not preserve that DGA is a preponderance-of-evidence policy process using systematic review, data analysis, and food-pattern modeling.

source_support: `dga_2020_2025_pmc_summary` lines 31-37 and 54-60.

flat_baseline_omission: The baseline cites guideline direction but does not show why guideline documents should be separated from individual evidence studies.

case_map_preserves: `eggs_c001`, `eggs_c002`, `eggs_c003`, `eggs_r013`.

adversarial_check: survives, because the guideline-process distinction is in the source subset and affects how evidence is converted into advice.

loss_id: eggs_loss_006

loss_type: `scoping-review limitation omitted`

lost_item: The flat baseline uses NNR as a total-picture summary but does not preserve that the NNR egg review was a scoping review without de novo or qualified systematic reviews for the egg topic.

source_support: `nnr_2023_eggs_scoping_review` lines 42-52.

flat_baseline_omission: The baseline summarizes NNR's conclusion without the evidence-grade caveat.

case_map_preserves: `eggs_c018`, `eggs_c019`, `eggs_r014`.

adversarial_check: survives, because the limitation affects confidence in the umbrella conclusion and is explicitly in the fixed source subset.

loss_id: eggs_loss_007

loss_type: `similar claims merged`

lost_item: The flat baseline merges "up to one egg per day" across AHA, BMJ, and NNR even though each source uses it differently: public guidance for healthy people, observational cohort conclusion, and scoping-review synthesis.

source_support: `aha_2023_dietary_cholesterol_news` lines 56-62; `bmj_2020_egg_consumption_cvd` lines 40-43 and 537-544; `nnr_2023_eggs_scoping_review` lines 30-41.

flat_baseline_omission: The baseline uses the same phrase across sources without preserving source role and scope distinctions.

case_map_preserves: `eggs_c007`, `eggs_c008`, `eggs_c018`, and the Similar But Not Identical section.

adversarial_check: survives, because same-wording cross-source claims are exactly where ordinary synthesis can hide disagreement and scope differences.

## Borderline Or Rejected Losses

- Not counted: The baseline does not discuss cancer or allergy outcomes, because this worked region is specifically scoped to CVD outcomes, lipid markers, and guidance.
- Not counted: The baseline does not include the optional BMJ 2013, Ma 2021, or Huang 2020 sources, because the fixed subset excludes them.
