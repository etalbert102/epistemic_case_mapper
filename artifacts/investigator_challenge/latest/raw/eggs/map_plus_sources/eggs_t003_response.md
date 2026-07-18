# Deterministic map_plus_sources Retrieval Proxy

Question: What populations, intake ranges, and substitution contexts limit a general recommendation?

The map condition can recover these frozen answer-key objects:

## population_intake_substitution_limits

Population risk, intake range, replacement foods, and diabetes or high-risk subgroups limit a general recommendation.

Claims:

- `eggs_c007` [aha_2023_dietary_cholesterol_news; population caveat]: AHA public guidance allows up to one egg per day for healthy people but separates high-LDL groups for stricter saturated-fat and cholesterol reduction.
  - excerpt: "Healthy people can include up to a whole egg... each day... Anyone with a high LDL cholesterol level should consider reducing sources of both saturated fat and dietary cholesterol."
- `eggs_c008` [bmj_2020_egg_consumption_cvd; observational outcome]: BMJ 2020 reports no overall CVD association for moderate egg consumption up to one egg per day in its cohorts and updated meta-analysis.
  - excerpt: "Consumption of at least one egg per day was not associated with incident cardiovascular disease risk... moderate egg consumption (up to one egg per day) is not associated with cardiovascular disease risk overall."
- `eggs_c015` [li_2020_egg_cholesterol_rct_meta; randomized biomarker evidence]: Li 2020 is randomized evidence in healthy participants, but it measures lipid markers rather than long-term CVD events.
  - excerpt: "Only included randomized controlled trials... healthy populations... pooled results showed... higher LDL-c/HDL-c ratio... higher LDL-c... RCTs with long term follow-up are needed."
- `eggs_c019` [nnr_2023_eggs_scoping_review; evidence-grade caveat]: NNR's egg review is a scoping review built from existing reviews rather than a de novo qualified systematic review, limiting how strongly it can settle the question.
  - excerpt: "No de novo systematic reviews or qualified systematic reviews available... literature search... 38 articles... systematic review or meta-analysis... most recent and comprehensive meta-analyses were chosen."

Relations:

- `eggs_r002` (supports): `eggs_c008` -> `eggs_c018`. BMJ's moderate-consumption null finding supports NNR's "up to one egg/day" no-harm summary.
- `eggs_r014` (refines): `eggs_c019` -> `eggs_c018`. NNR's evidence-grade caveat limits confidence in the scoping-review synthesis.

Sources:

- `aha_2019_dietary_cholesterol_pubmed`
- `bmj_2020_egg_consumption_cvd`
- `jama_2019_dietary_cholesterol_eggs`
- `nnr_2023_eggs_scoping_review`
