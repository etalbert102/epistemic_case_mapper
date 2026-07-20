# Eggs Worked Region: Observational Outcomes Versus RCT Lipid Markers

Status: `human-review-needed`
Prompt/procedure: `source_mapping_prompt_v1`, `relation_extraction_prompt_v1`
Evidence mode: `source_grounded`
Review note: agent-curated from local source excerpts; human review has not occurred.

## Source Subset

- `dga_2020_2025_pmc_summary`
- `aha_2019_dietary_cholesterol_pubmed`
- `aha_2023_dietary_cholesterol_news`
- `bmj_2020_egg_consumption_cvd`
- `jama_2019_dietary_cholesterol_eggs`
- `li_2020_egg_cholesterol_rct_meta`
- `nnr_2023_eggs_scoping_review`

## What To Notice

This map is not trying to give dietary advice. It makes the evidence structure reviewable by separating:

- observational CVD outcomes from randomized lipid-marker trials,
- BMJ/JAMA tension from guideline language,
- general healthy-pattern advice from population-specific caveats,
- "up to one egg per day" statements that do different work in different sources.

## Curated Claims

claim_id: eggs_c001

source_id: dga_2020_2025_pmc_summary

source_span: `lines 31-37`

excerpt: "The Dietary Guidelines... is grounded in the current body of scientific evidence... aims to promote health and prevent chronic diseases... provides science-based advice... mandated by law to reflect the preponderance of scientific evidence."

entailed_by_excerpt: yes

role: `guideline context`

claim: The Dietary Guidelines are a policy-oriented synthesis grounded in preponderance of evidence, not a single egg-specific causal study.

claim_id: eggs_c002

source_id: dga_2020_2025_pmc_summary

source_span: `lines 54-60`

excerpt: "The Committee answered each question... using... data analysis, food pattern modeling, and... systematic reviews... looked across all of the conclusion statements... to develop overarching advice."

entailed_by_excerpt: yes

role: `method context`

claim: DGA advice combines multiple evidence methods, including systematic review, data analysis, and food-pattern modeling.

claim_id: eggs_c003

source_id: dga_2020_2025_pmc_summary

source_span: `lines 73-80`

excerpt: "Healthy dietary patterns... low in red and processed meats... advised limiting intake of saturated fats... and keeping dietary cholesterol intake as low as possible."

entailed_by_excerpt: yes

role: `diet-pattern framing`

claim: DGA frames adults' advice around healthy dietary patterns and recommends keeping dietary cholesterol as low as possible within those patterns.

claim_id: eggs_c004

source_id: aha_2019_dietary_cholesterol_pubmed

source_span: `lines 122-124`

excerpt: "Observational studies... generally does not indicate a significant association with cardiovascular disease risk... intervention studies... associate intakes... with elevated total or low-density lipoprotein cholesterol."

entailed_by_excerpt: yes

role: `method split`

claim: The AHA advisory separates observational CVD outcome evidence, which generally lacks significant association, from intervention lipid evidence, which often shows elevated total or LDL cholesterol at higher intakes.

claim_id: eggs_c005

source_id: aha_2019_dietary_cholesterol_pubmed

source_span: `line 123`

excerpt: "Dietary guidance should focus on healthy dietary patterns... relatively low in cholesterol... guidance focused on dietary patterns is more likely to improve diet quality."

entailed_by_excerpt: yes

role: `guideline framing`

claim: AHA guidance favors dietary-pattern advice over a standalone numeric cholesterol target.

claim_id: eggs_c006

source_id: aha_2023_dietary_cholesterol_news

source_span: `lines 49-52`

excerpt: "Keeping dietary cholesterol consumption 'as low as possible without compromising the nutritional adequacy of the diet'... not a free pass... cannot isolate dietary cholesterol from that total fat intake."

entailed_by_excerpt: yes

role: `public guidance caveat`

claim: AHA's public explanation warns that removing a numeric cholesterol target is not permission to ignore cholesterol, saturated fat, and total diet.

claim_id: eggs_c007

source_id: aha_2023_dietary_cholesterol_news

source_span: `lines 56-62`

excerpt: "Healthy people can include up to a whole egg... each day... Anyone with a high LDL cholesterol level should consider reducing sources of both saturated fat and dietary cholesterol."

entailed_by_excerpt: yes

role: `population caveat`

claim: AHA public guidance allows up to one egg per day for healthy people but separates high-LDL groups for stricter saturated-fat and cholesterol reduction.

claim_id: eggs_c008

source_id: bmj_2020_egg_consumption_cvd

source_span: `lines 40-43`

excerpt: "Consumption of at least one egg per day was not associated with incident cardiovascular disease risk... moderate egg consumption (up to one egg per day) is not associated with cardiovascular disease risk overall."

entailed_by_excerpt: yes

role: `observational outcome`

claim: BMJ 2020 reports no overall CVD association for moderate egg consumption up to one egg per day in its cohorts and updated meta-analysis.

claim_id: eggs_c009

source_id: bmj_2020_egg_consumption_cvd

source_span: `lines 524-532`

excerpt: "Considerable heterogeneity existed... US, Europe, and Asia... high egg consumption could be associated with a higher risk... among people with type 2 diabetes... further studies are warranted."

entailed_by_excerpt: yes

role: `heterogeneity caveat`

claim: BMJ preserves regional heterogeneity and a possible type 2 diabetes caveat rather than giving one global egg effect.

claim_id: eggs_c010

source_id: bmj_2020_egg_consumption_cvd

source_span: `lines 241 and 531-536`

excerpt: "Higher risk... when eggs were replaced with processed red meat... unprocessed red meat... full fat milk... replacement analysis is a statistical modeling strategy... interpreted with caution."

entailed_by_excerpt: yes

role: `replacement context`

claim: BMJ replacement models make egg interpretation depend on what replaces eggs, while warning that replacement analyses are statistical modeling rather than observed substitutions.

claim_id: eggs_c011

source_id: bmj_2020_egg_consumption_cvd

source_span: `lines 537-544`

excerpt: "Moderate egg consumption (up to one egg per day) is not associated... mean egg consumption... was relatively low... most participants consumed one to less than five eggs per week."

entailed_by_excerpt: yes

role: `baseline-intake caveat`

claim: BMJ's "up to one egg per day" conclusion must be read alongside relatively low typical intake in the included cohorts.

claim_id: eggs_c012

source_id: jama_2019_dietary_cholesterol_eggs

source_span: `lines 33-52`

excerpt: "Each additional 300 mg... dietary cholesterol... higher risk of incident CVD... each additional half an egg... higher risk... associations between egg consumption... were no longer significant after adjusting for dietary cholesterol consumption."

entailed_by_excerpt: yes

role: `observational outcome`

claim: JAMA 2019 reports positive dose-response associations for dietary cholesterol and eggs, with egg associations attenuating after adjustment for dietary cholesterol.

claim_id: eggs_c013

source_id: jama_2019_dietary_cholesterol_eggs

source_span: `lines 70-73`

excerpt: "Cohort-stratified... models... nutrients correlated with dietary cholesterol... adjusted... dietary patterns... subgroup analyses... diabetes... hyperlipidemia... low lipids."

entailed_by_excerpt: yes

role: `method detail`

claim: JAMA explicitly models dietary cholesterol, egg consumption, correlated nutrients, food groups, dietary patterns, and subgroups, which affects interpretation of the positive associations.

claim_id: eggs_c014

source_id: jama_2019_dietary_cholesterol_eggs

source_span: `lines 477-484`

excerpt: "Residual confounding was a potential reason for inconsistent results... observational and cannot establish causality... findings should be considered in the development of dietary guidelines."

entailed_by_excerpt: yes

role: `causal caveat`

claim: JAMA treats its findings as guideline-relevant but acknowledges residual confounding and that observational data cannot establish causality.

claim_id: eggs_c015

source_id: li_2020_egg_cholesterol_rct_meta

source_span: `lines 30-36`

excerpt: "Only included randomized controlled trials... healthy populations... pooled results showed... higher LDL-c/HDL-c ratio... higher LDL-c... RCTs with long term follow-up are needed."

entailed_by_excerpt: yes

role: `randomized biomarker evidence`

claim: Li 2020 is randomized evidence in healthy participants, but it measures lipid markers rather than long-term CVD events.

claim_id: eggs_c016

source_id: li_2020_egg_cholesterol_rct_meta

source_span: `lines 188-201`

excerpt: "More egg consumption... significant elevation... LDL-c/HDL-c ratio... significantly higher concentration of LDL-c... did not show significant difference... HDL-c."

entailed_by_excerpt: yes

role: `randomized biomarker evidence`

claim: Li reports higher LDL-c/HDL-c ratio and LDL-c with more egg consumption, while HDL-c does not significantly change in the pooled analysis.

claim_id: eggs_c017

source_id: li_2020_egg_cholesterol_rct_meta

source_span: `lines 207 and 279-293`

excerpt: "Results did not show a clear trend... longer-term high egg-consumption may lead to higher LDL-c/HDL-c ratio and LDL-c... RCTs with long term follow-up are needed."

entailed_by_excerpt: yes

role: `duration and dose caveat`

claim: Li's RCT synthesis suggests longer duration may matter but does not establish a clean dose trend or long-term health-outcome effect.

claim_id: eggs_c018

source_id: nnr_2023_eggs_scoping_review

source_span: `lines 30-41`

excerpt: "Systematic reviews of randomized clinical trials indicates that higher egg intake may increase serum total cholesterol concentration and the ratio of low-density lipoprotein to high-density lipoprotein cholesterol, but with substantial heterogeneity in the response... observational studies does not provide strong support for a detrimental role of moderate egg consumption... up to one egg/day... one egg/day is unlikely to adversely affect overall disease risk."

entailed_by_excerpt: yes

role: `umbrella synthesis`

claim: NNR synthesizes the tension by treating RCT lipid changes as heterogeneous warning signals while observational evidence gives little support for harm from up to one egg per day, especially in European studies.

claim_id: eggs_c019

source_id: nnr_2023_eggs_scoping_review

source_span: `lines 42-52`

excerpt: "No de novo systematic reviews or qualified systematic reviews available... literature search... 38 articles... systematic review or meta-analysis... most recent and comprehensive meta-analyses were chosen."

entailed_by_excerpt: yes

role: `evidence-grade caveat`

claim: NNR's egg review is a scoping review built from existing reviews rather than a de novo qualified systematic review, limiting how strongly it can settle the question.

## Relations

relation_id: eggs_r001

source_claim: `eggs_c004`

target_claim: `eggs_c018`

relation_type: supports

rationale: AHA's observational-versus-intervention split is echoed by NNR's summary of observational outcomes and RCT lipid changes.

relation_id: eggs_r002

source_claim: `eggs_c008`

target_claim: `eggs_c018`

relation_type: supports

rationale: BMJ's moderate-consumption null finding supports NNR's "up to one egg/day" no-harm summary.

relation_id: eggs_r003

source_claim: `eggs_c012`

target_claim: `eggs_c008`

relation_type: in_tension_with

rationale: JAMA's positive dose-response association and BMJ's null moderate-intake conclusion point in different directions and require method/context comparison.

relation_id: eggs_r004

source_claim: `eggs_c014`

target_claim: `eggs_c012`

relation_type: refines

rationale: JAMA's causal caveat limits how directly its positive association should be converted into advice.

relation_id: eggs_r005

source_claim: `eggs_c015`

target_claim: `eggs_c016`

relation_type: depends_on

rationale: The biomarker result depends on the RCT endpoint scope: LDL-c and LDL-c/HDL-c, not direct CVD outcomes.

relation_id: eggs_r006

source_claim: `eggs_c016`

target_claim: `eggs_c008`

relation_type: in_tension_with

rationale: Randomized lipid-marker worsening can coexist with observational null CVD outcome findings but should not be collapsed into them.

relation_id: eggs_r007

source_claim: `eggs_c017`

target_claim: `eggs_c016`

relation_type: refines

rationale: Duration and dose caveats qualify the interpretation of the LDL-c and LDL-c/HDL-c findings.

relation_id: eggs_r008

source_claim: `eggs_c003`

target_claim: `eggs_c005`

relation_type: similar_to

rationale: DGA and AHA both frame dietary cholesterol through overall dietary patterns rather than isolated egg counts.

relation_id: eggs_r009

source_claim: `eggs_c006`

target_claim: `eggs_c007`

relation_type: refines

rationale: The public AHA "not a free pass" caveat explains why the one-egg/day statement is conditional on diet and LDL status.

relation_id: eggs_r010

source_claim: `eggs_c009`

target_claim: `eggs_c008`

relation_type: refines

rationale: Regional and diabetes heterogeneity qualifies BMJ's overall null finding.

relation_id: eggs_r011

source_claim: `eggs_c010`

target_claim: `eggs_c008`

relation_type: refines

rationale: Replacement context affects what "egg risk" means in actual dietary choices.

relation_id: eggs_r012

source_claim: `eggs_c011`

target_claim: `eggs_c008`

relation_type: refines

rationale: Low typical cohort intake constrains how broadly the "up to one egg/day" conclusion should be read.

relation_id: eggs_r013

source_claim: `eggs_c001`

target_claim: `eggs_c003`

relation_type: depends_on

rationale: The guideline cholesterol recommendation depends on a policy process using preponderance of evidence, not on one study alone.

relation_id: eggs_r014

source_claim: `eggs_c019`

target_claim: `eggs_c018`

relation_type: refines

rationale: NNR's evidence-grade caveat limits confidence in the scoping-review synthesis.

relation_id: eggs_r015

source_claim: `eggs_c004`

target_claim: `eggs_c018`

relation_type: crux_for

rationale: How to weigh observational outcomes against intervention lipid markers is a crux for the overall egg recommendation.

relation_id: eggs_r016

source_claim: `eggs_c010`

target_claim: `eggs_c005`

relation_type: crux_for

rationale: Replacement foods and dietary-pattern framing are a crux for converting evidence into advice.

relation_id: eggs_r017

source_claim: `eggs_c007`

target_claim: `eggs_c018`

relation_type: refines

rationale: High-LDL subgroup guidance prevents the NNR one-egg/day summary from becoming a universal free pass.

## Crux Candidates

- crux: Should direct observational CVD outcome evidence outweigh randomized lipid-marker evidence when giving dietary advice? Linked claims: `eggs_c004`, `eggs_c008`, `eggs_c015`, `eggs_c016`, `eggs_c018`.
- crux: Is "moderate intake" adequately represented as up to one egg/day, or should low typical cohort intake and high-LDL/diabetes caveats narrow the advice? Linked claims: `eggs_c007`, `eggs_c009`, `eggs_c011`.
- crux: Should eggs be evaluated as an isolated food, as a dietary cholesterol source, or as a replacement within a dietary pattern? Linked claims: `eggs_c003`, `eggs_c005`, `eggs_c010`, `eggs_c012`.

## Similar But Not Identical

- `eggs_c008` and `eggs_c018` both support moderate egg intake, but BMJ is a cohort/meta-analysis finding and NNR is a scoping synthesis.
- `eggs_c012` and `eggs_c016` both push toward caution, but JAMA is observational CVD/mortality association while Li is randomized lipid-marker evidence.
- `eggs_c003`, `eggs_c005`, and `eggs_c006` all concern guidance, but DGA gives federal guideline process, AHA 2019 gives advisory framing, and AHA 2023 gives public interpretation.
- `eggs_c009`, `eggs_c011`, and `eggs_c017` are different caveats: population heterogeneity, baseline intake, and trial duration/dose.

## Audit Notes

- No claim in this map is marked human-reviewed.
- The baseline comparison is illustrative because this same Codex run had access to the curated-map task and source-packet orientation.
- This map intentionally keeps "eggs", "dietary cholesterol", "LDL-c", and "CVD outcomes" separate because merging them is the main erosion risk.

## Evidence Check

| Probe | Evidence | Boundary |
| --- | --- | --- |
| Local reasoning value | Separates methods, endpoints, populations, replacement foods, and guideline framing. | Nutrition specialists should review whether the selected caveats are weighted fairly. |
| Transfer beyond this case | The method/endpoints/guideline distinction applies to many everyday evidence questions. | Some domains need stronger evidence-independence metadata. |
| Ability to absorb more work | More compute can expand source coverage while preserving the same claim and relation protocol. | Automated extraction may overproduce weak claims without review. |
| Reuse by later reviewers | Stable IDs and cruxes let future reviewers add studies or dispute relation labels locally. | Actual multi-reviewer workflow remains untested. |
