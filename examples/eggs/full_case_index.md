# Eggs And Health Full-Case Index

Status: `broad-source-scaffold`

Purpose: provide a full-case navigation layer over all currently acquired eggs sources. The worked region `eggs_observational_vs_rct` remains the deeper curated anchor.

## Case Question

What should an investigator believe about the health effects of eating eggs?

## Source Coverage

| Source ID | Role In Full Case | Current Use |
| --- | --- | --- |
| `aha_2019_dietary_cholesterol_pubmed` | AHA science advisory record | dietary cholesterol, blood lipid, and CVD framing |
| `aha_2023_dietary_cholesterol_news` | AHA public guidance explainer | healthy-person and high-LDL communication |
| `dga_2020_2025_pmc_summary` | federal dietary guideline summary | policy/guideline process and dietary pattern framing |
| `bmj_2020_egg_consumption_cvd` | cohorts plus updated meta-analysis | moderate egg intake, CVD outcomes, replacement context |
| `bmj_2013_egg_consumption_chd_stroke` | dose-response cohort meta-analysis | earlier CHD/stroke meta-analytic context |
| `jama_2019_dietary_cholesterol_eggs` | pooled cohort study | cautionary dietary cholesterol and egg associations |
| `li_2020_egg_cholesterol_rct_meta` | RCT lipid meta-analysis | randomized biomarker evidence |
| `ma_2021_egg_cvd_dose_response` | later dose-response meta-analysis | CVD, CHD, stroke, heart failure, mortality dose-response |
| `huang_2020_egg_health_outcomes_evidence_mapping` | overview/evidence map | multiple health outcomes beyond CVD |
| `nnr_2023_eggs_scoping_review` | guideline scoping review | guideline synthesis and evidence-grade caveats |
| `eggs_dietary_cholesterol_cvd_review` | narrative review | interpretive CVD/cholesterol context |
| `dietary_cholesterol_lack_evidence_cvd_review` | narrative review | counterpoint on weak dietary cholesterol evidence |

## Full-Case Cluster Index

| Cluster ID | Topic | Primary Sources | Review Priority |
| --- | --- | --- | --- |
| `eggs_full_cluster_001` | Guideline and dietary-pattern framing | `dga_2020_2025_pmc_summary`, `aha_2019_dietary_cholesterol_pubmed`, `aha_2023_dietary_cholesterol_news`, `nnr_2023_eggs_scoping_review` | worked-region anchor |
| `eggs_full_cluster_002` | Observational CVD outcome evidence | `bmj_2020_egg_consumption_cvd`, `bmj_2013_egg_consumption_chd_stroke`, `jama_2019_dietary_cholesterol_eggs`, `ma_2021_egg_cvd_dose_response` | worked-region anchor |
| `eggs_full_cluster_003` | Randomized lipid-marker evidence | `li_2020_egg_cholesterol_rct_meta`, `aha_2019_dietary_cholesterol_pubmed`, `nnr_2023_eggs_scoping_review` | worked-region anchor |
| `eggs_full_cluster_004` | Replacement-food and dietary-context interpretation | `bmj_2020_egg_consumption_cvd`, `dga_2020_2025_pmc_summary`, `aha_2023_dietary_cholesterol_news` | high |
| `eggs_full_cluster_005` | Population heterogeneity | `bmj_2020_egg_consumption_cvd`, `aha_2023_dietary_cholesterol_news`, `bmj_2013_egg_consumption_chd_stroke`, `nnr_2023_eggs_scoping_review` | high |
| `eggs_full_cluster_006` | Evidence synthesis and scoping limits | `huang_2020_egg_health_outcomes_evidence_mapping`, `nnr_2023_eggs_scoping_review`, `ma_2021_egg_cvd_dose_response` | medium |
| `eggs_full_cluster_007` | Narrative review and counterpoint context | `eggs_dietary_cholesterol_cvd_review`, `dietary_cholesterol_lack_evidence_cvd_review` | medium |
| `eggs_full_cluster_008` | Broader health outcomes beyond CVD | `huang_2020_egg_health_outcomes_evidence_mapping`, `nnr_2023_eggs_scoping_review` | medium |

## Best Current Anchor

- Deep worked map: `examples/eggs/worked_region_observational_vs_rct_map.md`
- Full broad map: `examples/eggs/full_case_map.md`
- Erosion audit anchor: `examples/eggs/decision_space_erosion_audit.md`

## Immediate Human Review Path

1. Confirm each source appears in the correct cluster.
2. Review the worked-region anchor before broader clusters.
3. Check that cohort and meta-analysis sources are not counted as fully independent.
4. Check whether narrative reviews are used as interpretive context rather than primary evidence.
5. Add a broader-outcomes worked region if FLF judges want more than CVD and lipid-marker coverage.
