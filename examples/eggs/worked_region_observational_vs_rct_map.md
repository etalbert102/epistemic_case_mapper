# Eggs Worked Region: Observational Outcomes Versus RCT Lipid Markers

Status: `template`
Prompt/procedure: `source_mapping_prompt_v1`, `relation_extraction_prompt_v1`

## Source Subset

- `dga_2020_2025_pmc_summary`
- `aha_2019_dietary_cholesterol_pubmed`
- `aha_2023_dietary_cholesterol_news`
- `bmj_2020_egg_consumption_cvd`
- `jama_2019_dietary_cholesterol_eggs`
- `li_2020_egg_cholesterol_rct_meta`
- `nnr_2023_eggs_scoping_review`

## Curated Claims

TODO: Add 12-25 curated claims. Use this format for each claim:

```yaml
- claim_id: eggs_c001
  source_id: bmj_2020_egg_consumption_cvd
  source_span: normalized_chars:TBD
  excerpt: "TBD"
  claim_text: "TBD"
  claim_type: evidence
  entailed_by_excerpt: yes
  review_state: source_supported
```

## Relations

TODO: Add relations using at least three relation types.

```yaml
- relation_id: eggs_r001
  source_claim_id: eggs_c001
  target_claim_id: eggs_c002
  relation_type: in_tension_with
  rationale: "TBD"
```

## Crux Candidates

TODO: Add at least two crux candidates.

## Similar But Not Identical

TODO: Add grouped distinctions that should not be flattened.

## FLF Judge Questions

| Question | Score | Evidence | Residual risk |
| --- | ---: | --- | --- |
| Would this help someone reason better about this case? | 0 | TODO | TODO |
| Does it generalize? | 0 | TODO | TODO |
| Does it scale with improvements to AI or more compute? | 0 | TODO | TODO |
| Does it compound with multiple people or teams? | 0 | TODO | TODO |
