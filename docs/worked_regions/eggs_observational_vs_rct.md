# Eggs Observational Versus RCT Worked Region

Status: `template`

## Narrow Question

How should an investigator preserve the difference between observational cardiovascular outcome evidence and randomized lipid-marker evidence when reasoning about eggs?

## Fixed Source Subset

Use only these sources unless a blocker is recorded and the user authorizes source acquisition:

- `dga_2020_2025_pmc_summary`
- `aha_2019_dietary_cholesterol_pubmed`
- `aha_2023_dietary_cholesterol_news`
- `bmj_2020_egg_consumption_cvd`
- `jama_2019_dietary_cholesterol_eggs`
- `li_2020_egg_cholesterol_rct_meta`
- `nnr_2023_eggs_scoping_review`

Optional supporting context, not required for the curated map:

- `bmj_2013_egg_consumption_chd_stroke`
- `ma_2021_egg_cvd_dose_response`
- `huang_2020_egg_health_outcomes_evidence_mapping`

## Why This Region Matters

This is the strongest eggs slice because the answer depends on preserving method, endpoint, population, and substitution context. A flat synthesis can produce a plausible "eggs in moderation" answer while losing why different evidence streams point in different directions.

## Expected Cruxes

- Whether clinical outcome evidence or lipid-marker RCT evidence should carry more weight for guidance.
- How substitution context changes the interpretation of egg intake.
- Whether population heterogeneity, especially diabetes or high baseline LDL-C, requires separate guidance.
- Whether guideline communications should be treated as evidence or as decision-context synthesis.

## What Ordinary Synthesis May Flatten

- Clinical outcomes versus biomarkers.
- Cohort/meta-analysis overlap and source dependence.
- Guideline level versus evidence level.
- Population heterogeneity.
- Substitution context.

## Completion Criteria

- [ ] Curated map exists at `examples/eggs/worked_region_observational_vs_rct_map.md`.
- [ ] Flat baseline exists at `examples/eggs/flat_synthesis_baseline.md`.
- [ ] Erosion audit exists at `examples/eggs/decision_space_erosion_audit.md`.
- [ ] Best-region index exists at `examples/eggs/BEST_REGIONS.md`.
- [ ] `PYTHONPATH=src python3 scripts/validate_worked_regions.py` passes.
