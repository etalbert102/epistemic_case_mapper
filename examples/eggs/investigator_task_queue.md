# Eggs Investigator Task Queue

Status: `human-review-needed`

Purpose: show realistic next tasks for turning the eggs scaffold into a fuller reusable knowledge base.

## Task Queue

task_id: eggs_task_001

task_type: source_overlap_audit

priority: high

cluster: `eggs_full_cluster_002`

sources: `bmj_2020_egg_consumption_cvd`, `bmj_2013_egg_consumption_chd_stroke`, `jama_2019_dietary_cholesterol_eggs`, `ma_2021_egg_cvd_dose_response`

task: Identify cohort overlap and endpoint differences across the observational/meta-analysis sources.

realism_value: Prevents correlated evidence from being counted as independent support.

done_when: The full-case map records which observational sources are independent, overlapping, or methodologically distinct.

task_id: eggs_task_002

task_type: worked_region_candidate

priority: high

cluster: `eggs_full_cluster_008`

sources: `huang_2020_egg_health_outcomes_evidence_mapping`, `nnr_2023_eggs_scoping_review`

task: Create a worked region on broader health outcomes beyond CVD.

realism_value: Tests whether the method can handle vague everyday questions where outcome scope is part of the decision.

done_when: Claims separate CVD, T2D, cancer, nutrient adequacy, and review-method limits.

task_id: eggs_task_003

task_type: subgroup_review

priority: high

cluster: `eggs_full_cluster_005`

sources: `aha_2023_dietary_cholesterol_news`, `bmj_2020_egg_consumption_cvd`, `bmj_2013_egg_consumption_chd_stroke`, `nnr_2023_eggs_scoping_review`

task: Expand high-LDL, diabetes, and healthy-adult subgroup caveats into source-grounded claims.

realism_value: Makes the artifact useful for different real users instead of an average-person summary.

done_when: The map distinguishes healthy-adult guidance, high-LDL caution, and diabetes/prediabetes uncertainty.

task_id: eggs_task_004

task_type: full_case_baseline

priority: medium

cluster: `all`

sources: `aha_2019_dietary_cholesterol_pubmed`, `aha_2023_dietary_cholesterol_news`, `dga_2020_2025_pmc_summary`, `bmj_2020_egg_consumption_cvd`, `bmj_2013_egg_consumption_chd_stroke`, `jama_2019_dietary_cholesterol_eggs`, `li_2020_egg_cholesterol_rct_meta`, `ma_2021_egg_cvd_dose_response`, `huang_2020_egg_health_outcomes_evidence_mapping`, `nnr_2023_eggs_scoping_review`, `eggs_dietary_cholesterol_cvd_review`, `dietary_cholesterol_lack_evidence_cvd_review`

task: Generate a whole-case flat synthesis from source abstracts/excerpts, then audit whether it preserves endpoint, population, replacement, and evidence-grade structure.

realism_value: Tests whether the technique helps on the full everyday-evidence question, not only the CVD/lipid worked region.

done_when: A full-case baseline and full-case erosion audit exist and are marked `human-review-needed`.

task_id: eggs_task_005

task_type: source_acquisition

priority: medium

cluster: `eggs_full_cluster_001`

sources: `dga_2020_2025_pmc_summary`

task: Add the full USDA/HHS Dietary Guidelines PDF if retrieval succeeds, then compare it to the current PMC summary.

realism_value: Demonstrates source updating and improves guideline-process fidelity.

done_when: The manifest, source inventory, source method metadata, and relevant claims distinguish full guideline text from summary text.
