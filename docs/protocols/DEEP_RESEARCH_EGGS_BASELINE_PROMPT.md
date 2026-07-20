# Deep Research Eggs Baseline Prompt

Purpose: record the external Deep Research baseline prompt for the eggs and dietary-cholesterol case. Use this to generate a retrieval-plus-synthesis baseline, then run the epistemic mapper on the same retrieved source set for a controlled source-held comparison.

Procedure tag: `deep_research_eggs_retrieval_baseline_v1`

## Prompt

```text
I want a careful Deep Research report on a decision-relevant nutrition evidence question.

Question:
For generally healthy adults, should eggs be treated as meaningfully harmful, neutral, or beneficial in dietary advice, especially with respect to cardiovascular risk?

Please conduct a source-grounded synthesis using high-quality sources. Prioritize:
- randomized controlled trials and meta-analyses
- large prospective cohort studies
- dietary guideline documents
- evidence reviews from credible public-health or medical bodies
- sources that directly address eggs, dietary cholesterol, LDL, ApoB if available, cardiovascular events, and relevant subgroup differences

Please do not optimize for a simple yes/no answer. Optimize for decision support.

Your report should include:

1. Bottom line
Give the most defensible practical answer, with calibrated confidence.

2. Source list
List the most important sources you used, with links, publication year, source type, and why each source matters.

3. Load-bearing evidence
Identify which findings most affect the answer. Separate:
- direct egg-consumption evidence
- dietary cholesterol evidence
- biomarker evidence such as LDL/ApoB
- hard outcome evidence such as cardiovascular events

4. RCT vs observational evidence
Explain what each evidence type can and cannot establish here. Note confounding, dietary substitution issues, trial duration, endpoints, and external validity.

5. Key cruxes
Identify the uncertainties that would most change the recommendation. For each, say what evidence would resolve it.

6. Tensions and counterarguments
Present the strongest reasons for concern about eggs and the strongest reasons for neutrality/low concern. Do not flatten disagreements.

7. Subgroups and scope limits
Discuss whether the answer changes for people with diabetes, high LDL/ApoB, familial hypercholesterolemia, high baseline cardiovascular risk, or very high egg intake.

8. Practical recommendation
Give a practical dietary-advice conclusion. Be explicit about what follows from the evidence and what remains judgment.

Rules:
- Cite sources for important claims.
- Distinguish direct evidence from inference.
- Do not overstate certainty.
- Avoid generic nutrition advice unless it changes the answer to the egg-specific question.
- At the end, provide a compact bibliography/source table with URLs.
```

## Evaluation Use

Run this prompt blind, without giving the model the curated map, quality report, stress output, or config profile. Save the final report and retrieved source list.

For controlled comparison, feed only the retrieved source documents into the epistemic mapper with the same question. Compare the outputs on crux visibility, load-bearing evidence visibility, uncertainty calibration, source-role handling, tension preservation, artifact reusability, and reader coherence.
