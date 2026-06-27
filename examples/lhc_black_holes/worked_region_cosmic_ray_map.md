# LHC Worked Region: Cosmic-Ray Argument Map

Status: `template`
Prompt/procedure: `source_mapping_prompt_v1`, `relation_extraction_prompt_v1`

## Source Subset

- `lsag_2008_safety_review`
- `spc_2008_lsag_review`
- `giddings_mangano_2008_stable_black_holes`
- `plaga_2008_metastable_black_holes`
- `giddings_mangano_2008_comments_plaga`

## Curated Claims

TODO: Add 12-25 curated claims. Use this format for each claim:

```yaml
- claim_id: lhc_c001
  source_id: lsag_2008_safety_review
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
- relation_id: lhc_r001
  source_claim_id: lhc_c001
  target_claim_id: lhc_c002
  relation_type: depends_on
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
