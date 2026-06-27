# Eggs Source Method Metadata

Purpose: give future worked-region agents the method, endpoint, and decision-context metadata needed to preserve rather than flatten the eggs evidence base.

## Source Method Table

| Source ID | Evidence Type | Population / Scope | Endpoint | Exposure | Main Validity Risks | Directness |
| --- | --- | --- | --- | --- | --- | --- |
| `dga_2020_2025_pmc_summary` | federal guideline summary | U.S. population dietary patterns | dietary-pattern guidance | protein foods including eggs | high-level summary, not egg-specific causal evidence | indirect guideline context |
| `aha_2019_dietary_cholesterol_pubmed` | science advisory record | cardiovascular-risk guidance | blood lipids, lipoproteins, CVD risk | dietary cholesterol, eggs | abstract-level record; full advisory not locally captured | guideline context |
| `aha_2023_dietary_cholesterol_news` | public guidance explainer | general public | practical dietary cholesterol advice | dietary cholesterol, eggs | public-facing simplification | guideline communication |
| `bmj_2020_egg_consumption_cvd` | cohorts + updated meta-analysis | large U.S. cohorts plus meta-analysis | incident CVD | egg consumption | residual confounding, substitution context, cohort overlap | direct clinical outcomes |
| `bmj_2013_egg_consumption_chd_stroke` | prospective cohort meta-analysis | cohort-study populations | CHD, stroke | egg consumption dose | residual confounding, diabetes subgroup interpretation | direct clinical outcomes |
| `jama_2019_dietary_cholesterol_eggs` | pooled cohort study | U.S. cohorts | incident CVD, mortality | dietary cholesterol, eggs | observational confounding, measurement error | direct clinical outcomes |
| `li_2020_egg_cholesterol_rct_meta` | RCT meta-analysis | trial participants | LDL-C, HDL-C, lipid ratios | egg consumption | surrogate endpoints, short duration, diet control variation | mechanistic/biomarker |
| `ma_2021_egg_cvd_dose_response` | dose-response cohort meta-analysis | prospective cohorts | CVD, CHD, stroke, heart failure, mortality | egg consumption dose | between-study heterogeneity, cohort overlap | direct clinical outcomes |
| `huang_2020_egg_health_outcomes_evidence_mapping` | overview/evidence map | systematic reviews | multiple health outcomes | egg consumption | umbrella-level dependence on included reviews | evidence map |
| `nnr_2023_eggs_scoping_review` | guideline scoping review | Nordic/Baltic guideline context | CVD, T2D, cancer, nutrient context | egg intake | scoping review not de novo causal adjudication | guideline evidence synthesis |
| `eggs_dietary_cholesterol_cvd_review` | narrative review | general nutrition literature | CVD and risk factors | eggs, dietary cholesterol | narrative selection, interpretive synthesis | interpretive context |
| `dietary_cholesterol_lack_evidence_cvd_review` | narrative review | general nutrition literature | CVD | dietary cholesterol | narrative selection, advocacy risk | interpretive counterpoint |

## Key Preservation Requirements

- Do not merge clinical-outcome evidence with lipid-biomarker evidence without labeling the evidential step.
- Do not treat meta-analyses as independent if they reuse overlapping cohort studies.
- Preserve population heterogeneity: diabetes, high LDL-C, baseline cardiovascular risk, and dietary pattern.
- Preserve substitution context: eggs replacing processed meat differs from eggs replacing legumes, fish, or whole-food plant proteins.
- Preserve guideline level vs evidence level: guideline communication is not the same as causal evidence.
