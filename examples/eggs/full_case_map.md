# Eggs And Health Full-Case Knowledge Map

Status: `broad-source-scaffold`
Evidence mode: `source_grounded_manifest_and_metadata`
Review note: broad full-case scaffold from all acquired sources; worked-region anchors are more deeply curated and should be trusted more than broad clusters until human review occurs.

## Source Set

- `aha_2019_dietary_cholesterol_pubmed`
- `aha_2023_dietary_cholesterol_news`
- `dga_2020_2025_pmc_summary`
- `bmj_2020_egg_consumption_cvd`
- `bmj_2013_egg_consumption_chd_stroke`
- `jama_2019_dietary_cholesterol_eggs`
- `li_2020_egg_cholesterol_rct_meta`
- `ma_2021_egg_cvd_dose_response`
- `huang_2020_egg_health_outcomes_evidence_mapping`
- `nnr_2023_eggs_scoping_review`
- `eggs_dietary_cholesterol_cvd_review`
- `dietary_cholesterol_lack_evidence_cvd_review`

## Full-Case Thesis

The eggs case is not a binary "good" or "bad" question. It is a structured evidence problem about intake level, replacement food, population risk, endpoint, study design, guideline context, and evidence independence.

## Knowledge Clusters

cluster_id: eggs_full_cluster_001

topic: Guideline and dietary-pattern framing

sources: `dga_2020_2025_pmc_summary`, `aha_2019_dietary_cholesterol_pubmed`, `aha_2023_dietary_cholesterol_news`, `nnr_2023_eggs_scoping_review`

decision_space_preserved: guideline statements should be distinguished from primary causal evidence and from public-facing simplifications.

map_status: worked-region anchor

cluster_claim: Major guidance sources frame eggs through dietary patterns, cholesterol exposure, nutritional adequacy, and population risk rather than treating eggs as an isolated universally good or bad food.

anchor_claims: `eggs_c001`, `eggs_c002`, `eggs_c003`, `eggs_c005`, `eggs_c006`, `eggs_c007`, `eggs_c018`, `eggs_c019`

cluster_id: eggs_full_cluster_002

topic: Observational CVD outcome evidence

sources: `bmj_2020_egg_consumption_cvd`, `bmj_2013_egg_consumption_chd_stroke`, `jama_2019_dietary_cholesterol_eggs`, `ma_2021_egg_cvd_dose_response`

decision_space_preserved: observational cohorts and meta-analyses should be compared by outcome, exposure unit, adjustment, cohort overlap, and population heterogeneity.

map_status: worked-region anchor

cluster_claim: Observational outcome evidence is mixed: some syntheses support no clear harm for moderate intake, while other pooled or dose-response analyses support more caution, especially around dietary cholesterol and subgroups.

anchor_claims: `eggs_c008`, `eggs_c009`, `eggs_c010`, `eggs_c011`, `eggs_c012`, `eggs_c013`, `eggs_c014`

cluster_id: eggs_full_cluster_003

topic: Randomized lipid-marker evidence

sources: `li_2020_egg_cholesterol_rct_meta`, `aha_2019_dietary_cholesterol_pubmed`, `nnr_2023_eggs_scoping_review`

decision_space_preserved: randomized lipid-marker evidence is more controlled but less direct than long-term clinical outcome evidence.

map_status: worked-region anchor

cluster_claim: Randomized trials show lipid-marker concerns, especially LDL-C and LDL-C/HDL-C ratio, but do not by themselves settle long-term CVD event risk.

anchor_claims: `eggs_c004`, `eggs_c015`, `eggs_c016`, `eggs_c017`, `eggs_c018`

cluster_id: eggs_full_cluster_004

topic: Replacement-food and dietary-context interpretation

sources: `bmj_2020_egg_consumption_cvd`, `dga_2020_2025_pmc_summary`, `aha_2023_dietary_cholesterol_news`

decision_space_preserved: advice about eggs depends on what they replace and what dietary pattern they sit within.

map_status: broad scaffold

cluster_claim: Eggs cannot be evaluated only as a cholesterol unit; replacement foods and overall dietary pattern change the interpretation of risk.

anchor_claims: `eggs_c003`, `eggs_c006`, `eggs_c010`

cluster_id: eggs_full_cluster_005

topic: Population heterogeneity

sources: `bmj_2020_egg_consumption_cvd`, `aha_2023_dietary_cholesterol_news`, `bmj_2013_egg_consumption_chd_stroke`, `nnr_2023_eggs_scoping_review`

decision_space_preserved: healthy adults, high-LDL individuals, people with diabetes, and regional populations should not be merged.

map_status: broad scaffold

cluster_claim: The practical recommendation changes across healthy adults, high-LDL groups, diabetes or prediabetes contexts, and populations with different baseline diets.

anchor_claims: `eggs_c007`, `eggs_c009`, `eggs_c011`

cluster_id: eggs_full_cluster_006

topic: Evidence synthesis and scoping limits

sources: `huang_2020_egg_health_outcomes_evidence_mapping`, `nnr_2023_eggs_scoping_review`, `ma_2021_egg_cvd_dose_response`

decision_space_preserved: umbrella maps, scoping reviews, and dose-response meta-analyses differ in what they can settle.

map_status: broad scaffold

cluster_claim: Evidence synthesis sources help map the landscape, but their conclusions depend on included reviews, overlapping primary studies, scope, and review method.

anchor_claims: `eggs_c018`, `eggs_c019`

cluster_id: eggs_full_cluster_007

topic: Narrative review and counterpoint context

sources: `eggs_dietary_cholesterol_cvd_review`, `dietary_cholesterol_lack_evidence_cvd_review`

decision_space_preserved: narrative reviews are useful for interpretive framing and counterpoints, but they should not be counted as independent primary evidence.

map_status: broad scaffold

cluster_claim: Narrative reviews supply context for how dietary cholesterol evidence is interpreted, including arguments that the dietary cholesterol-CVD link is weaker than older guidance assumed.

cluster_id: eggs_full_cluster_008

topic: Broader health outcomes beyond CVD

sources: `huang_2020_egg_health_outcomes_evidence_mapping`, `nnr_2023_eggs_scoping_review`

decision_space_preserved: CVD, T2D, cancer, nutrient adequacy, and other outcomes should not be collapsed into one health judgment.

map_status: broad scaffold

cluster_claim: The broader eggs question includes multiple outcomes beyond CVD, but the current deep anchor is focused on CVD outcomes, lipid markers, guideline framing, and population caveats.

## Cross-Cluster Relations

relation_id: eggs_full_rel_001

source_cluster: `eggs_full_cluster_003`

target_cluster: `eggs_full_cluster_002`

relation_type: in_tension_with

rationale: RCT lipid-marker evidence can support caution even when observational CVD outcome evidence is null or mixed.

relation_id: eggs_full_rel_002

source_cluster: `eggs_full_cluster_004`

target_cluster: `eggs_full_cluster_001`

relation_type: depends_on

rationale: Guideline advice depends on dietary-pattern and replacement-food reasoning, not just isolated egg exposure.

relation_id: eggs_full_rel_003

source_cluster: `eggs_full_cluster_005`

target_cluster: `eggs_full_cluster_001`

relation_type: refines

rationale: Population heterogeneity prevents healthy-person advice from applying automatically to high-risk groups.

relation_id: eggs_full_rel_004

source_cluster: `eggs_full_cluster_006`

target_cluster: `eggs_full_cluster_002`

relation_type: refines

rationale: Evidence-synthesis method and overlap determine how much weight to give repeated cohort/meta-analysis conclusions.

relation_id: eggs_full_rel_005

source_cluster: `eggs_full_cluster_008`

target_cluster: `eggs_full_cluster_002`

relation_type: expands_scope

rationale: A full health judgment must eventually go beyond CVD outcomes, even though the current deep anchor is CVD-focused.

## Full-Case Cruxes

- Should direct observational CVD outcome evidence outweigh randomized lipid-marker evidence for public dietary advice?
- Which cohort/meta-analysis results are independent rather than repeated views of overlapping evidence?
- How should guidance differ for healthy adults, high-LDL individuals, and people with diabetes or prediabetes?
- Should eggs be evaluated as isolated cholesterol exposure, nutrient-dense protein food, or replacement within a dietary pattern?
- How much should scoping reviews and evidence maps influence confidence when de novo systematic review evidence is limited?

## Worked-Region Anchor

The best current deep anchor is `examples/eggs/worked_region_observational_vs_rct_map.md`. It gives source-level claims and relation rationales for `eggs_full_cluster_001`, `eggs_full_cluster_002`, `eggs_full_cluster_003`, `eggs_full_cluster_004`, and `eggs_full_cluster_005`.

## Remaining Expansion Work

- Add source-excerpt-level claims for BMJ 2013, Ma 2021, Huang 2020, and the narrative reviews.
- Add a worked region on broader health outcomes beyond CVD.
- Add a worked region on diabetes/high-LDL subgroup treatment.
- Add a full-case flat baseline and compare it to this scaffold.
