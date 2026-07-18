# Deterministic map Retrieval Proxy

Question: What explains the apparent BMJ/JAMA tension?

The map condition can recover these frozen answer-key objects:

## bmj_jama_tension_scope

BMJ's moderate-consumption null result and JAMA's higher-risk association differ in design, exposure framing, endpoints, and confounding concerns.

Claims:

- `eggs_c008` [bmj_2020_egg_consumption_cvd; observational outcome]: BMJ 2020 reports no overall CVD association for moderate egg consumption up to one egg per day in its cohorts and updated meta-analysis.
- `eggs_c009` [bmj_2020_egg_consumption_cvd; heterogeneity caveat]: BMJ preserves regional heterogeneity and a possible type 2 diabetes caveat rather than giving one global egg effect.
- `eggs_c010` [bmj_2020_egg_consumption_cvd; replacement context]: BMJ replacement models make egg interpretation depend on what replaces eggs, while warning that replacement analyses are statistical modeling rather than observed substitutions.
- `eggs_c011` [bmj_2020_egg_consumption_cvd; baseline-intake caveat]: BMJ's "up to one egg per day" conclusion must be read alongside relatively low typical intake in the included cohorts.
- `eggs_c015` [li_2020_egg_cholesterol_rct_meta; randomized biomarker evidence]: Li 2020 is randomized evidence in healthy participants, but it measures lipid markers rather than long-term CVD events.

Relations:

- `eggs_r003` (in_tension_with): `eggs_c012` -> `eggs_c008`. JAMA's positive dose-response association and BMJ's null moderate-intake conclusion point in different directions and require method/context comparison.
- `eggs_r005` (depends_on): `eggs_c015` -> `eggs_c016`. The biomarker result depends on the RCT endpoint scope: LDL-c and LDL-c/HDL-c, not direct CVD outcomes.

Sources:

- `bmj_2020_egg_consumption_cvd`
- `jama_2019_dietary_cholesterol_eggs`
