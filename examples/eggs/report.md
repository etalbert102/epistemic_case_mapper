# Eggs and Health

Question: What should an investigator believe about the health effects of eating eggs?

Evidence mode: `source_grounded`
Review status: `draft`

## Summary

- Sources: 12
- Candidate claims: 1022
- Seed relations: 25
- Open questions: 3
- Preservation metadata files: 4
- Workflow telemetry stages: 3

## Sources

- `aha_2019_dietary_cholesterol_pubmed`: Dietary Cholesterol and Cardiovascular Risk: A Science Advisory From the American Heart Association
- `aha_2023_dietary_cholesterol_news`: Here's the latest on dietary cholesterol and how it fits in with a healthy diet
- `dga_2020_2025_pmc_summary`: Dietary Guidelines for Americans, 2020-2025
- `bmj_2020_egg_consumption_cvd`: Egg consumption and risk of cardiovascular disease: three large prospective US cohort studies, systematic review, and updated meta-analysis
- `bmj_2013_egg_consumption_chd_stroke`: Egg consumption and risk of coronary heart disease and stroke: dose-response meta-analysis of prospective cohort studies
- `jama_2019_dietary_cholesterol_eggs`: Associations of Dietary Cholesterol or Egg Consumption With Incident Cardiovascular Disease and Mortality
- `li_2020_egg_cholesterol_rct_meta`: Association between Egg Consumption and Cholesterol Concentration: A Systematic Review and Meta-Analysis of Randomized Controlled Trials
- `ma_2021_egg_cvd_dose_response`: Egg consumption and cardiovascular risk: a dose-response meta-analysis of prospective cohort studies
- `huang_2020_egg_health_outcomes_evidence_mapping`: Egg consumption and health outcomes: a global evidence mapping based on an overview of systematic reviews
- `nnr_2023_eggs_scoping_review`: Eggs - a scoping review for Nordic Nutrition Recommendations 2023
- `eggs_dietary_cholesterol_cvd_review`: Eggs, dietary cholesterol, and cardiovascular disease
- `dietary_cholesterol_lack_evidence_cvd_review`: Dietary Cholesterol and the Lack of Evidence in Cardiovascular Disease

## Preservation Metadata

- `data/cases/eggs/metadata/source_method_metadata.md`: Eggs Source Method Metadata
- `data/cases/eggs/metadata/source_independence.md`: Eggs Source Independence Notes
- `data/cases/eggs/metadata/guideline_evolution_timeline.md`: Eggs Guideline And Evidence Evolution Timeline
- `data/cases/eggs/metadata/stakeholder_contexts.md`: Eggs Stakeholder Contexts

### Key Requirements Carried Into This Artifact

- Do not merge clinical-outcome evidence with lipid-biomarker evidence without labeling the evidential step.
- Do not treat meta-analyses as independent if they reuse overlapping cohort studies.
- Preserve population heterogeneity: diabetes, high LDL-C, baseline cardiovascular risk, and dietary pattern.
- Preserve substitution context: eggs replacing processed meat differs from eggs replacing legumes, fish, or whole-food plant proteins.
- Preserve guideline level vs evidence level: guideline communication is not the same as causal evidence.

## Workflow Telemetry

- Candidate sentences inspected: 11614
- Candidate claims created: 1022
- Sentences skipped without claim marker: 2610

## Candidate Claims

- `claim_0001` (risk_claim, aha_2019_dietary_cholesterol_pubmed, normalized_chars:882-1476, local_source_text, source_supported): Dietary Cholesterol and Cardiovascular Risk: A Science Advisory From the American Heart Association Jo Ann S Carson, Alice H Lichtenstein, Cheryl A M Anderson, Lawrence J Appel, Penny M Kris-Etherton, Katie A Meyer, Kristina Petersen, Tamar Polonsky, Linda Van Horn; American Heart Association Nutrition Committee of the Council on Lifestyle and Cardiometabolic Health; Council on Arteriosclerosis, Thrombosis and Vascular Biology; Council on Cardiovascular and Stroke Nursing; Council on Clinical Cardiology; Council on Peripheral Vascular Disease; and Stroke Council • PMID: 31838890 DOI: 10.
- `claim_0002` (risk_claim, aha_2019_dietary_cholesterol_pubmed, normalized_chars:1713-1971, local_source_text, source_supported): This advisory was developed after a review of human studies on the relationship of dietary cholesterol with blood lipids, lipoproteins, and cardiovascular disease risk to address questions about the relevance of dietary cholesterol guidance for heart health.
- `claim_0003` (risk_claim, aha_2019_dietary_cholesterol_pubmed, normalized_chars:1972-2126, local_source_text, source_supported): Evidence from observational studies conducted in several countries generally does not indicate a significant association with cardiovascular disease risk.
- `claim_0004` (counterpoint_or_caveat, aha_2019_dietary_cholesterol_pubmed, normalized_chars:2127-2347, local_source_text, source_supported): Although meta-analyses of intervention studies differ in their findings, most associate intakes of cholesterol that exceed current average levels with elevated total or low-density lipoprotein cholesterol concentrations.
- `claim_0005` (risk_claim, aha_2019_dietary_cholesterol_pubmed, normalized_chars:3041-3116, local_source_text, source_supported): Keywords: AHA Scientific Statements; cholesterol; diet; eggs; risk factors.
- `claim_0006` (inference_claim, aha_2023_dietary_cholesterol_news, normalized_chars:901-1067, local_source_text, source_supported): Because it was often associated with saturated fat, limiting dietary cholesterol – especially by restricting egg consumption – seemed to benefit heart-health efforts.
- `claim_0007` (risk_claim, aha_2023_dietary_cholesterol_news, normalized_chars:2182-2376, local_source_text, source_supported): According to a 2019 AHA science advisory on dietary cholesterol and cardiovascular risk – which Van Horn helped write – high-fat meat, eggs, butter and full-fat dairy products are major sources.
- `claim_0008` (counterpoint_or_caveat, aha_2023_dietary_cholesterol_news, normalized_chars:2486-2571, local_source_text, source_supported): Dietary cholesterol also can be found in baked goods made with eggs, butter or cream.
- `claim_0009` (risk_claim, aha_2023_dietary_cholesterol_news, normalized_chars:2572-2792, local_source_text, source_supported): Although dietary cholesterol was once singled out as a contributor to heart disease, the 2019 science advisory said studies have not generally supported an association between dietary cholesterol and cardiovascular risk.
- `claim_0010` (counterpoint_or_caveat, aha_2023_dietary_cholesterol_news, normalized_chars:2833-3118, local_source_text, source_supported): Although previous federal dietary guidelines recommended limiting consumption of dietary cholesterol to 300 milligrams per day, the current guidelines instead suggest keeping dietary cholesterol consumption "as low as possible without compromising the nutritional adequacy of the diet.
- `claim_0011` (counterpoint_or_caveat, aha_2023_dietary_cholesterol_news, normalized_chars:3172-3242, local_source_text, source_supported): But it is not a free pass to eat all the dietary cholesterol you want.
- `claim_0012` (risk_claim, aha_2023_dietary_cholesterol_news, normalized_chars:3243-3372, local_source_text, source_supported): But focusing on a number, or the lack of evidence linking dietary cholesterol to health risks, could be a misstep, Van Horn said.
- `claim_0013` (inference_claim, aha_2023_dietary_cholesterol_news, normalized_chars:3373-3460, local_source_text, source_supported): That's because foods high in dietary cholesterol also tend to be high in saturated fat.
- `claim_0014` (risk_claim, aha_2023_dietary_cholesterol_news, normalized_chars:3741-3873, local_source_text, source_supported): " And eating too much saturated fat – along with too much sugar and sodium, and too little fiber – raises the risk of heart disease.
- `claim_0015` (risk_claim, aha_2023_dietary_cholesterol_news, normalized_chars:4138-4329, local_source_text, source_supported): Put another way: If you're eating a healthy diet, Van Horn said, a little butter now and then (and its 31 mg of dietary cholesterol per tablespoon) on your toast should not pose a major risk.
- `claim_0016` (inference_claim, aha_2023_dietary_cholesterol_news, normalized_chars:4665-4772, local_source_text, source_supported): Because of that, Van Horn said it once was considered wise to eat no more than two or three yolks per week.
- `claim_0017` (counterpoint_or_caveat, aha_2023_dietary_cholesterol_news, normalized_chars:4821-4972, local_source_text, source_supported): But research regarding the effects of eggs was complicated by the fact that eggs often are eaten with high-fat foods such as bacon, sausage and butter.
- `claim_0018` (inference_claim, aha_2023_dietary_cholesterol_news, normalized_chars:5395-5613, local_source_text, source_supported): Anyone with a high LDL cholesterol level should consider reducing sources of both saturated fat and dietary cholesterol, Van Horn said, because together they are considered more likely to contribute to arterial plaque.
- `claim_0019` (risk_claim, aha_2023_dietary_cholesterol_news, normalized_chars:5614-5703, local_source_text, source_supported): This is especially a concern among people with overweight, obesity or other risk factors.
- `claim_0020` (risk_claim, aha_2023_dietary_cholesterol_news, normalized_chars:5955-6114, local_source_text, source_supported): People with healthy blood cholesterol levels should recognize that as they age, their risk increases and tolerance for less-healthy foods can change, she said.
- `claim_0021` (risk_claim, aha_2023_dietary_cholesterol_news, normalized_chars:6784-6936, local_source_text, source_supported): These include blood cholesterol, blood pressure, blood glucose – all the risk factors that are examined, evaluated and studied to prevent heart disease.
- `claim_0022` (inference_claim, aha_2023_dietary_cholesterol_news, normalized_chars:7039-7228, local_source_text, source_supported): That's because the average American's blood cholesterol level has gone down in recent decades, and some of that is thanks to statin medications and a better understanding of diet, she said.
- `claim_0023` (counterpoint_or_caveat, aha_2023_dietary_cholesterol_news, normalized_chars:8308-8477, local_source_text, source_supported): 31, 2023, to clarify the reference to dietary cholesterol limits, and to include eggs alongside shellfish as a food high in dietary cholesterol but not in saturated fat.
- `claim_0024` (counterpoint_or_caveat, aha_2023_dietary_cholesterol_news, normalized_chars:9163-9485, local_source_text, source_supported): Permission is granted, at no cost and without need for further request, for individuals, media outlets, and non-commercial education and awareness efforts to link to, quote, excerpt from or reprint these stories in any medium as long as no text is altered and proper attribution is made to American Heart Association News.
- `claim_0025` (risk_claim, aha_2023_dietary_cholesterol_news, normalized_chars:10291-10480, local_source_text, source_supported): Eating too many sulfur amino acids may boost cardiovascular disease and death risk Southwestern Quinoa and Egg Breakfast Bowl Donate today to help end heart disease and stroke for everyone.
- `claim_0026` (evidence_claim, dga_2020_2025_pmc_summary, normalized_chars:1148-1310, local_source_text, source_supported): The Dietary Guidelines is grounded in the current body of scientific evidence on diet and health outcomes and aims to promote health and prevent chronic diseases.
- `claim_0027` (evidence_claim, dga_2020_2025_pmc_summary, normalized_chars:1311-1647, local_source_text, source_supported): The process to develop the Dietary Guidelines involved 4 steps: (1) identifying the topics and supporting scientific questions, (2) appointing a Dietary Guidelines Advisory Committee (Committee) to review current scientific evidence, (3) developing the new edition of the Dietary Guidelines, and (4) implementing the Dietary Guidelines.
- `claim_0028` (counterpoint_or_caveat, dga_2020_2025_pmc_summary, normalized_chars:2470-2621, local_source_text, source_supported): Although many recommendations have remained relatively consistent over time, the Dietary Guidelines also has evolved as scientific knowledge has grown.
- `claim_0029` (risk_claim, dga_2020_2025_pmc_summary, normalized_chars:4032-4242, local_source_text, source_supported): PURPOSE OF THE DIETARY GUIDELINES FOR AMERICANS The Dietary Guidelines provides science-based advice on what to eat and drink to promote health, help reduce the risk of chronic disease, and meet nutrient needs.
- `claim_0030` (evidence_claim, dga_2020_2025_pmc_summary, normalized_chars:4243-4449, local_source_text, source_supported): It serves as the cornerstone of federal nutrition programs and policies and is mandated by law to reflect the preponderance of scientific evidence and to be published by USDA and HHS at least every 5 years.
- `claim_0031` (risk_claim, dga_2020_2025_pmc_summary, normalized_chars:4449-4733, local_source_text, source_supported): 2 As an important part of a complex, multifaceted approach to promote health and reduce chronic disease risk, the Dietary Guidelines is written for a professional audience, including policymakers, healthcare professionals, nutrition educators, and federal nutrition program operators.
- `claim_0032` (risk_claim, dga_2020_2025_pmc_summary, normalized_chars:4880-5194, local_source_text, source_supported): Comprehensive, coordinated strategies built on the science-based foundation of the Dietary Guidelines—and a commitment to drive these strategies over time across sectors and settings—can help all Americans consume healthy dietary patterns, achieve and maintain good health, and reduce the risk of chronic diseases.
- `claim_0033` (evidence_claim, dga_2020_2025_pmc_summary, normalized_chars:5890-6322, local_source_text, source_supported): The 2020–2025 process consisted of 4 stages: (1) identifying the topics and supporting scientific questions to be examined, (2) appointing a Dietary Guidelines Advisory Committee (Committee) to review current scientific evidence and develop a scientific report, (3) developing the new edition of the Dietary Guidelines, and (4) implementing the Dietary Guidelines through federal programs and nonfederal program entities (Figure 1).
- `claim_0034` (evidence_claim, dga_2020_2025_pmc_summary, normalized_chars:7202-7618, local_source_text, source_supported): 2020 Dietary Guidelines Advisory Committee Scientific Report Development In the second stage, the Secretaries of USDA and HHS appointed the Committee with the single, time-limited task of reviewing the 2015–2020 Dietary Guidelines, examining the evidence on the selected nutrition and public health topics and scientific questions, and providing independent, science-based advice and recommendations to USDA and HHS.
- `claim_0035` (inference_claim, dga_2020_2025_pmc_summary, normalized_chars:7808-7900, local_source_text, source_supported): The Committee timeline was extended by 1 month because of the impact of COVID-19 (Figure 2).
- `claim_0036` (inference_claim, dga_2020_2025_pmc_summary, normalized_chars:8201-8315, local_source_text, source_supported): This is the largest Committee to date because of the additional emphasis on infants, toddlers, and pregnant women.
- `claim_0037` (counterpoint_or_caveat, dga_2020_2025_pmc_summary, normalized_chars:8563-8838, local_source_text, source_supported): The USDA and HHS not only examined nomination packages individually to ensure each person met the criteria but also considered how a potential candidate's expertise fits with other members of the Committee to ensure a balanced committee with expertise across the topic areas.
- `claim_0038` (evidence_claim, dga_2020_2025_pmc_summary, normalized_chars:8839-9076, local_source_text, source_supported): The Committee's work had 3 defining characteristics: the use of 3 approaches to examine the evidence, the creation of transparent protocols before the evidence review began, and the development of scientific review conclusion statements.
- `claim_0039` (evidence_claim, dga_2020_2025_pmc_summary, normalized_chars:9077-9263, local_source_text, source_supported): The Committee answered each question on diet and health using 1 of 3 approaches: data analysis, food pattern modeling, and Nutrition Evidence Systematic Review (NESR) systematic reviews.
- `claim_0040` (evidence_claim, dga_2020_2025_pmc_summary, normalized_chars:10436-10581, local_source_text, source_supported): The 2020 Committee created a protocol for each question, with support from USDA and HHS staff, before it examined any of the scientific evidence.
- ... 982 more claims in JSON artifact

## Seed Relations

- `rel_0001`: `claim_0001` similar_to `claim_0007` — Tentative seed relation from shared tags: risk
- `rel_0002`: `claim_0001` similar_to `claim_0009` — Tentative seed relation from shared tags: risk
- `rel_0003`: `claim_0001` similar_to `claim_0012` — Tentative seed relation from shared tags: risk
- `rel_0004`: `claim_0001` similar_to `claim_0014` — Tentative seed relation from shared tags: risk
- `rel_0005`: `claim_0001` similar_to `claim_0015` — Tentative seed relation from shared tags: risk
- `rel_0006`: `claim_0001` similar_to `claim_0019` — Tentative seed relation from shared tags: risk
- `rel_0007`: `claim_0001` similar_to `claim_0020` — Tentative seed relation from shared tags: risk
- `rel_0008`: `claim_0001` similar_to `claim_0021` — Tentative seed relation from shared tags: risk
- `rel_0009`: `claim_0001` similar_to `claim_0025` — Tentative seed relation from shared tags: risk
- `rel_0010`: `claim_0001` similar_to `claim_0029` — Tentative seed relation from shared tags: risk
- `rel_0011`: `claim_0001` similar_to `claim_0031` — Tentative seed relation from shared tags: risk
- `rel_0012`: `claim_0001` similar_to `claim_0032` — Tentative seed relation from shared tags: risk
- `rel_0013`: `claim_0001` similar_to `claim_0041` — Tentative seed relation from shared tags: risk
- `rel_0014`: `claim_0001` similar_to `claim_0045` — Tentative seed relation from shared tags: risk
- `rel_0015`: `claim_0001` similar_to `claim_0047` — Tentative seed relation from shared tags: risk
- `rel_0016`: `claim_0001` similar_to `claim_0049` — Tentative seed relation from shared tags: risk
- `rel_0017`: `claim_0001` similar_to `claim_0052` — Tentative seed relation from shared tags: risk
- `rel_0018`: `claim_0001` similar_to `claim_0057` — Tentative seed relation from shared tags: risk
- `rel_0019`: `claim_0001` similar_to `claim_0060` — Tentative seed relation from shared tags: risk
- `rel_0020`: `claim_0001` similar_to `claim_0061` — Tentative seed relation from shared tags: risk
- `rel_0021`: `claim_0001` similar_to `claim_0074` — Tentative seed relation from shared tags: risk
- `rel_0022`: `claim_0001` similar_to `claim_0079` — Tentative seed relation from shared tags: risk
- `rel_0023`: `claim_0001` similar_to `claim_0080` — Tentative seed relation from shared tags: risk
- `rel_0024`: `claim_0001` similar_to `claim_0081` — Tentative seed relation from shared tags: risk
- `rel_0025`: `claim_0001` similar_to `claim_0082` — Tentative seed relation from shared tags: risk

## Open Questions

- `oq_0001` (crux; claim_0001, claim_0002, claim_0005, claim_0006, claim_0007): Which findings depend on substitution context: what foods eggs replace or accompany?
- `oq_0002` (crux; claim_0001, claim_0002, claim_0003, claim_0004, claim_0005): How should observational cardiovascular findings be weighted against randomized lipid-marker findings?
- `oq_0003` (population heterogeneity; claim_0041, claim_0047, claim_0048, claim_0060, claim_0086): Which populations need separate guidance, especially people with diabetes, high LDL cholesterol, or different baseline dietary patterns?

## Audit Notes

- Starter map is deterministic and intentionally conservative.
- Claims are heuristic candidates; human/AI workflow should classify, merge, and audit them.
- Relations are seed links only and should not be treated as settled assessment.
