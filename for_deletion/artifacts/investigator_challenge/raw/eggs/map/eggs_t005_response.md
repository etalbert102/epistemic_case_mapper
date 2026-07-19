# Deterministic map Retrieval Proxy

Question: What new result would most change the practical answer?

The map condition can recover these frozen answer-key objects:

## decision_changing_new_result

A decision-changing result would connect egg intake to hard cardiovascular outcomes with clear population, dose, substitution, and confounding controls.

Claims:

- `eggs_c012` [jama_2019_dietary_cholesterol_eggs; observational outcome]: JAMA 2019 reports positive dose-response associations for dietary cholesterol and eggs, with egg associations attenuating after adjustment for dietary cholesterol.
- `eggs_c015` [li_2020_egg_cholesterol_rct_meta; randomized biomarker evidence]: Li 2020 is randomized evidence in healthy participants, but it measures lipid markers rather than long-term CVD events.
- `eggs_c019` [nnr_2023_eggs_scoping_review; evidence-grade caveat]: NNR's egg review is a scoping review built from existing reviews rather than a de novo qualified systematic review, limiting how strongly it can settle the question.

Relations:

- `eggs_r005` (depends_on): `eggs_c015` -> `eggs_c016`. The biomarker result depends on the RCT endpoint scope: LDL-c and LDL-c/HDL-c, not direct CVD outcomes.
- `eggs_r006` (in_tension_with): `eggs_c016` -> `eggs_c008`. Randomized lipid-marker worsening can coexist with observational null CVD outcome findings but should not be collapsed into them.
- `eggs_r014` (refines): `eggs_c019` -> `eggs_c018`. NNR's evidence-grade caveat limits confidence in the scoping-review synthesis.

Sources:

- `li_2020_egg_cholesterol_rct_meta`
- `jama_2019_dietary_cholesterol_eggs`
- `nnr_2023_eggs_scoping_review`
