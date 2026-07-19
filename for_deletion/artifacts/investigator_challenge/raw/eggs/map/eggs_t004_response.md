# Deterministic map Retrieval Proxy

Question: Which statements are evidence findings, which are guideline interpretations, and which are policy advice?

The map condition can recover these frozen answer-key objects:

## findings_guidelines_policy_roles

The map separates empirical findings, guideline interpretations, and policy-oriented advice.

Claims:

- `eggs_c001` [dga_2020_2025_pmc_summary; guideline context]: The Dietary Guidelines are a policy-oriented synthesis grounded in preponderance of evidence, not a single egg-specific causal study.
- `eggs_c002` [dga_2020_2025_pmc_summary; method context]: DGA advice combines multiple evidence methods, including systematic review, data analysis, and food-pattern modeling.
- `eggs_c003` [dga_2020_2025_pmc_summary; diet-pattern framing]: DGA frames adults' advice around healthy dietary patterns and recommends keeping dietary cholesterol as low as possible within those patterns.
- `eggs_c004` [aha_2019_dietary_cholesterol_pubmed; method split]: The AHA advisory separates observational CVD outcome evidence, which generally lacks significant association, from intervention lipid evidence, which often shows elevated total or LDL cholesterol at higher intakes.
- `eggs_c019` [nnr_2023_eggs_scoping_review; evidence-grade caveat]: NNR's egg review is a scoping review built from existing reviews rather than a de novo qualified systematic review, limiting how strongly it can settle the question.

Relations:

- `eggs_r006` (in_tension_with): `eggs_c016` -> `eggs_c008`. Randomized lipid-marker worsening can coexist with observational null CVD outcome findings but should not be collapsed into them.
- `eggs_r014` (refines): `eggs_c019` -> `eggs_c018`. NNR's evidence-grade caveat limits confidence in the scoping-review synthesis.

Sources:

- `dga_2020_2025_pmc_summary`
- `aha_2019_dietary_cholesterol_pubmed`
- `aha_2023_dietary_cholesterol_news`
- `nnr_2023_eggs_scoping_review`
