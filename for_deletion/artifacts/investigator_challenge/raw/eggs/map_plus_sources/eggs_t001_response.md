# Deterministic map_plus_sources Retrieval Proxy

Question: Why can randomized lipid results and observational cardiovascular outcomes point in different directions without one simply invalidating the other?

The map condition can recover these frozen answer-key objects:

## rct_lipids_vs_observational_events

RCT lipid changes and observational cardiovascular outcomes answer different endpoint questions and can point in different directions.

Claims:

- `eggs_c004` [aha_2019_dietary_cholesterol_pubmed; method split]: The AHA advisory separates observational CVD outcome evidence, which generally lacks significant association, from intervention lipid evidence, which often shows elevated total or LDL cholesterol at higher intakes.
  - excerpt: "Observational studies... generally does not indicate a significant association with cardiovascular disease risk... intervention studies... associate intakes... with elevated total or low-density lipoprotein cholesterol."
- `eggs_c012` [jama_2019_dietary_cholesterol_eggs; observational outcome]: JAMA 2019 reports positive dose-response associations for dietary cholesterol and eggs, with egg associations attenuating after adjustment for dietary cholesterol.
  - excerpt: "Each additional 300 mg... dietary cholesterol... higher risk of incident CVD... each additional half an egg... higher risk... associations between egg consumption... were no longer significant after adjusting for dietary cholesterol consumption."
- `eggs_c018` [nnr_2023_eggs_scoping_review; umbrella synthesis]: NNR synthesizes the tension by treating RCT lipid changes as heterogeneous warning signals while observational evidence gives little support for harm from up to one egg per day, especially in European studies.
  - excerpt: "RCTs suggest lipid changes with substantial heterogeneity... observational studies does not provide strong support for a detrimental role of moderate egg consumption... up to one egg/day... one egg/day is unlikely to adversely affect overall disease risk."

Relations:

- `eggs_r001` (supports): `eggs_c004` -> `eggs_c018`. AHA's observational-versus-intervention split is echoed by NNR's summary of observational outcomes and RCT lipid changes.
- `eggs_r006` (in_tension_with): `eggs_c016` -> `eggs_c008`. Randomized lipid-marker worsening can coexist with observational null CVD outcome findings but should not be collapsed into them.

Sources:

- `aha_2019_dietary_cholesterol_pubmed`
- `li_2020_egg_cholesterol_rct_meta`
- `nnr_2023_eggs_scoping_review`
