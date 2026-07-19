# Eggs and health Map Packet

This packet exposes the reviewable case structure: sources, claims, relations, and crux candidates.

## Sources

- `dga_2020_2025_pmc_summary`
- `aha_2019_dietary_cholesterol_pubmed`
- `aha_2023_dietary_cholesterol_news`
- `bmj_2020_egg_consumption_cvd`
- `jama_2019_dietary_cholesterol_eggs`
- `li_2020_egg_cholesterol_rct_meta`
- `nnr_2023_eggs_scoping_review`

## Claims

- `eggs_c001` [dga_2020_2025_pmc_summary; guideline context]: The Dietary Guidelines are a policy-oriented synthesis grounded in preponderance of evidence, not a single egg-specific causal study.
  - excerpt: "The Dietary Guidelines... is grounded in the current body of scientific evidence... aims to promote health and prevent chronic diseases... provides science-based advice... mandated by law to reflect the preponderance of scientific evidence."
- `eggs_c002` [dga_2020_2025_pmc_summary; method context]: DGA advice combines multiple evidence methods, including systematic review, data analysis, and food-pattern modeling.
  - excerpt: "The Committee answered each question... using... data analysis, food pattern modeling, and... systematic reviews... looked across all of the conclusion statements... to develop overarching advice."
- `eggs_c003` [dga_2020_2025_pmc_summary; diet-pattern framing]: DGA frames adults' advice around healthy dietary patterns and recommends keeping dietary cholesterol as low as possible within those patterns.
  - excerpt: "Healthy dietary patterns... low in red and processed meats... advised limiting intake of saturated fats... and keeping dietary cholesterol intake as low as possible."
- `eggs_c004` [aha_2019_dietary_cholesterol_pubmed; method split]: The AHA advisory separates observational CVD outcome evidence, which generally lacks significant association, from intervention lipid evidence, which often shows elevated total or LDL cholesterol at higher intakes.
  - excerpt: "Observational studies... generally does not indicate a significant association with cardiovascular disease risk... intervention studies... associate intakes... with elevated total or low-density lipoprotein cholesterol."
- `eggs_c005` [aha_2019_dietary_cholesterol_pubmed; guideline framing]: AHA guidance favors dietary-pattern advice over a standalone numeric cholesterol target.
  - excerpt: "Dietary guidance should focus on healthy dietary patterns... relatively low in cholesterol... guidance focused on dietary patterns is more likely to improve diet quality."
- `eggs_c006` [aha_2023_dietary_cholesterol_news; public guidance caveat]: AHA's public explanation warns that removing a numeric cholesterol target is not permission to ignore cholesterol, saturated fat, and total diet.
  - excerpt: "Keeping dietary cholesterol consumption 'as low as possible without compromising the nutritional adequacy of the diet'... not a free pass... cannot isolate dietary cholesterol from that total fat intake."
- `eggs_c007` [aha_2023_dietary_cholesterol_news; population caveat]: AHA public guidance allows up to one egg per day for healthy people but separates high-LDL groups for stricter saturated-fat and cholesterol reduction.
  - excerpt: "Healthy people can include up to a whole egg... each day... Anyone with a high LDL cholesterol level should consider reducing sources of both saturated fat and dietary cholesterol."
- `eggs_c008` [bmj_2020_egg_consumption_cvd; observational outcome]: BMJ 2020 reports no overall CVD association for moderate egg consumption up to one egg per day in its cohorts and updated meta-analysis.
  - excerpt: "Consumption of at least one egg per day was not associated with incident cardiovascular disease risk... moderate egg consumption (up to one egg per day) is not associated with cardiovascular disease risk overall."
- `eggs_c009` [bmj_2020_egg_consumption_cvd; heterogeneity caveat]: BMJ preserves regional heterogeneity and a possible type 2 diabetes caveat rather than giving one global egg effect.
  - excerpt: "Considerable heterogeneity existed... US, Europe, and Asia... high egg consumption could be associated with a higher risk... among people with type 2 diabetes... further studies are warranted."
- `eggs_c010` [bmj_2020_egg_consumption_cvd; replacement context]: BMJ replacement models make egg interpretation depend on what replaces eggs, while warning that replacement analyses are statistical modeling rather than observed substitutions.
  - excerpt: "Higher risk... when eggs were replaced with processed red meat... unprocessed red meat... full fat milk... replacement analysis is a statistical modeling strategy... interpreted with caution."
- `eggs_c011` [bmj_2020_egg_consumption_cvd; baseline-intake caveat]: BMJ's "up to one egg per day" conclusion must be read alongside relatively low typical intake in the included cohorts.
  - excerpt: "Moderate egg consumption (up to one egg per day) is not associated... mean egg consumption... was relatively low... most participants consumed one to less than five eggs per week."
- `eggs_c012` [jama_2019_dietary_cholesterol_eggs; observational outcome]: JAMA 2019 reports positive dose-response associations for dietary cholesterol and eggs, with egg associations attenuating after adjustment for dietary cholesterol.
  - excerpt: "Each additional 300 mg... dietary cholesterol... higher risk of incident CVD... each additional half an egg... higher risk... associations between egg consumption... were no longer significant after adjusting for dietary cholesterol consumption."
- `eggs_c013` [jama_2019_dietary_cholesterol_eggs; method detail]: JAMA explicitly models dietary cholesterol, egg consumption, correlated nutrients, food groups, dietary patterns, and subgroups, which affects interpretation of the positive associations.
  - excerpt: "Cohort-stratified... models... nutrients correlated with dietary cholesterol... adjusted... dietary patterns... subgroup analyses... diabetes... hyperlipidemia... low lipids."
- `eggs_c014` [jama_2019_dietary_cholesterol_eggs; causal caveat]: JAMA treats its findings as guideline-relevant but acknowledges residual confounding and that observational data cannot establish causality.
  - excerpt: "Residual confounding was a potential reason for inconsistent results... observational and cannot establish causality... findings should be considered in the development of dietary guidelines."
- `eggs_c015` [li_2020_egg_cholesterol_rct_meta; randomized biomarker evidence]: Li 2020 is randomized evidence in healthy participants, but it measures lipid markers rather than long-term CVD events.
  - excerpt: "Only included randomized controlled trials... healthy populations... pooled results showed... higher LDL-c/HDL-c ratio... higher LDL-c... RCTs with long term follow-up are needed."
- `eggs_c016` [li_2020_egg_cholesterol_rct_meta; randomized biomarker evidence]: Li reports higher LDL-c/HDL-c ratio and LDL-c with more egg consumption, while HDL-c does not significantly change in the pooled analysis.
  - excerpt: "More egg consumption... significant elevation... LDL-c/HDL-c ratio... significantly higher concentration of LDL-c... did not show significant difference... HDL-c."
- `eggs_c017` [li_2020_egg_cholesterol_rct_meta; duration and dose caveat]: Li's RCT synthesis suggests longer duration may matter but does not establish a clean dose trend or long-term health-outcome effect.
  - excerpt: "Results did not show a clear trend... longer-term high egg-consumption may lead to higher LDL-c/HDL-c ratio and LDL-c... RCTs with long term follow-up are needed."
- `eggs_c018` [nnr_2023_eggs_scoping_review; umbrella synthesis]: NNR synthesizes the tension by treating RCT lipid changes as heterogeneous warning signals while observational evidence gives little support for harm from up to one egg per day, especially in European studies.
  - excerpt: "RCTs suggest lipid changes with substantial heterogeneity... observational studies does not provide strong support for a detrimental role of moderate egg consumption... up to one egg/day... one egg/day is unlikely to adversely affect overall disease risk."
- `eggs_c019` [nnr_2023_eggs_scoping_review; evidence-grade caveat]: NNR's egg review is a scoping review built from existing reviews rather than a de novo qualified systematic review, limiting how strongly it can settle the question.
  - excerpt: "No de novo systematic reviews or qualified systematic reviews available... literature search... 38 articles... systematic review or meta-analysis... most recent and comprehensive meta-analyses were chosen."

## Relations

- `eggs_r001` (supports): `eggs_c004` -> `eggs_c018`. AHA's observational-versus-intervention split is echoed by NNR's summary of observational outcomes and RCT lipid changes.
- `eggs_r002` (supports): `eggs_c008` -> `eggs_c018`. BMJ's moderate-consumption null finding supports NNR's "up to one egg/day" no-harm summary.
- `eggs_r003` (in_tension_with): `eggs_c012` -> `eggs_c008`. JAMA's positive dose-response association and BMJ's null moderate-intake conclusion point in different directions and require method/context comparison.
- `eggs_r004` (refines): `eggs_c014` -> `eggs_c012`. JAMA's causal caveat limits how directly its positive association should be converted into advice.
- `eggs_r005` (depends_on): `eggs_c015` -> `eggs_c016`. The biomarker result depends on the RCT endpoint scope: LDL-c and LDL-c/HDL-c, not direct CVD outcomes.
- `eggs_r006` (in_tension_with): `eggs_c016` -> `eggs_c008`. Randomized lipid-marker worsening can coexist with observational null CVD outcome findings but should not be collapsed into them.
- `eggs_r007` (refines): `eggs_c017` -> `eggs_c016`. Duration and dose caveats qualify the interpretation of the LDL-c and LDL-c/HDL-c findings.
- `eggs_r008` (similar_to): `eggs_c003` -> `eggs_c005`. DGA and AHA both frame dietary cholesterol through overall dietary patterns rather than isolated egg counts.
- `eggs_r009` (refines): `eggs_c006` -> `eggs_c007`. The public AHA "not a free pass" caveat explains why the one-egg/day statement is conditional on diet and LDL status.
- `eggs_r010` (refines): `eggs_c009` -> `eggs_c008`. Regional and diabetes heterogeneity qualifies BMJ's overall null finding.
- `eggs_r011` (refines): `eggs_c010` -> `eggs_c008`. Replacement context affects what "egg risk" means in actual dietary choices.
- `eggs_r012` (refines): `eggs_c011` -> `eggs_c008`. Low typical cohort intake constrains how broadly the "up to one egg/day" conclusion should be read.
- `eggs_r013` (depends_on): `eggs_c001` -> `eggs_c003`. The guideline cholesterol recommendation depends on a policy process using preponderance of evidence, not on one study alone.
- `eggs_r014` (refines): `eggs_c019` -> `eggs_c018`. NNR's evidence-grade caveat limits confidence in the scoping-review synthesis.
- `eggs_r015` (crux_for): `eggs_c004` -> `eggs_c018`. How to weigh observational outcomes against intervention lipid markers is a crux for the overall egg recommendation.
- `eggs_r016` (crux_for): `eggs_c010` -> `eggs_c005`. Replacement foods and dietary-pattern framing are a crux for converting evidence into advice.
- `eggs_r017` (refines): `eggs_c007` -> `eggs_c018`. High-LDL subgroup guidance prevents the NNR one-egg/day summary from becoming a universal free pass.

## Crux Candidates

- crux: Should direct observational CVD outcome evidence outweigh randomized lipid-marker evidence when giving dietary advice? Linked claims: `eggs_c004`, `eggs_c008`, `eggs_c015`, `eggs_c016`, `eggs_c018`.
- crux: Is "moderate intake" adequately represented as up to one egg/day, or should low typical cohort intake and high-LDL/diabetes caveats narrow the advice? Linked claims: `eggs_c007`, `eggs_c009`, `eggs_c011`.
- crux: Should eggs be evaluated as an isolated food, as a dietary cholesterol source, or as a replacement within a dietary pattern? Linked claims: `eggs_c003`, `eggs_c005`, `eggs_c010`, `eggs_c012`.

## Similar But Not Identical

- `eggs_c008` and `eggs_c018` both support moderate egg intake, but BMJ is a cohort/meta-analysis finding and NNR is a scoping synthesis.
- `eggs_c012` and `eggs_c016` both push toward caution, but JAMA is observational CVD/mortality association while Li is randomized lipid-marker evidence.
- `eggs_c003`, `eggs_c005`, and `eggs_c006` all concern guidance, but DGA gives federal guideline process, AHA 2019 gives advisory framing, and AHA 2023 gives public interpretation.
- `eggs_c009`, `eggs_c011`, and `eggs_c017` are different caveats: population heterogeneity, baseline intake, and trial duration/dose.
