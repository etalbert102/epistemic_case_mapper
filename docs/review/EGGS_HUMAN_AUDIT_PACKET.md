# Eggs Human Audit Packet

Status: `human-review-needed`

Purpose: give an external reviewer a case-specific packet for auditing the eggs worked region without first reading the whole repo.

## Packet Metadata

```yaml
packet_id: eggs_observational_vs_rct_audit_packet
case_id: eggs
worked_region_id: eggs_observational_vs_rct
review_status: human-review-needed
created_by: codex
created_at: 2026-06-27
source_subset:
  - dga_2020_2025_pmc_summary
  - aha_2019_dietary_cholesterol_pubmed
  - aha_2023_dietary_cholesterol_news
  - bmj_2020_egg_consumption_cvd
  - jama_2019_dietary_cholesterol_eggs
  - li_2020_egg_cholesterol_rct_meta
  - nnr_2023_eggs_scoping_review
prompt_versions:
  source_mapping: source_mapping_prompt_v1
  relation_extraction: relation_extraction_prompt_v1
  flat_baseline: flat_baseline_prompt_v1
  blinded_baseline: flat_baseline_prompt_v1_blinded_ollama
  erosion_audit: erosion_audit_prompt_v1
```

## Review Files

- Reviewer start page: `docs/review/REVIEWER_START_HERE.md`
- Self-contained Tier 1 checklist: `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv`
- Worked map: `examples/eggs/worked_region_observational_vs_rct_map.md`
- Region definition: `docs/worked_regions/eggs_observational_vs_rct.md`
- Best-region pointer: `examples/eggs/README.md`
- Illustrative baseline: `examples/eggs/flat_synthesis_baseline.md`
- Blinded local-model baselines: `examples/eggs/blinded_flat_synthesis_baseline_*.md`
- Erosion audit: `examples/eggs/decision_space_erosion_audit.md`
- Blinded comparator audit: `docs/review/BLINDED_BASELINE_AUDIT.md`
- Multi-model comparator audit: `docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md`
- Full fillable checklist: `docs/review/EGGS_HUMAN_AUDIT_CHECKLIST.csv`

## Reviewer Tasks

1. Complete the eggs rows in `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv` before opening the full map.
2. Check source fidelity for every claim in the worked map.
3. Check that observational CVD outcome claims are kept separate from randomized lipid-marker claims.
4. Check that guideline-process claims are not treated as direct outcome evidence.
5. Check whether subgroup caveats, replacement-food logic, and NNR scoping-review limits are preserved fairly.
6. Check whether each counted erosion loss is fair against the stronger blinded model baselines.

## Priority Claims

Start with these claims before auditing the rest of the map:

- `eggs_c004`: AHA observational-outcome versus intervention-lipid evidence split.
- `eggs_c008`: BMJ moderate-intake outcome framing.
- `eggs_c012`: JAMA dietary cholesterol and egg association framing.
- `eggs_c015` and `eggs_c016`: randomized lipid-marker evidence from Li 2020.
- `eggs_c018`: NNR synthesis of heterogeneous RCT lipid signals and observational moderate-intake evidence.

For each priority claim, record:

```yaml
claim_id:
reviewer_decision: pending
reviewer_note:
```

Allowed decisions: `accept`, `revise`, `reject`, `needs_discussion`.

## Priority Relations

Start with these relations:

- `eggs_r003`: BMJ/JAMA observational-result tension.
- `eggs_r005`: biomarker result depends on the RCT endpoint scope.
- `eggs_r006`: randomized lipid-marker worsening should not be collapsed into observational CVD outcome evidence.
- `eggs_r007`: duration and dose caveats qualify the Li lipid-marker findings.
- `eggs_r015`: observational outcomes versus intervention lipid markers as a crux for the overall recommendation.

For each priority relation, record:

```yaml
relation_id:
reviewer_decision: pending
reviewer_note:
```

## Priority Erosion Findings

Start with these losses:

- `eggs_loss_003`: subgroup caveat specificity.
- `eggs_loss_005`: DGA process provenance.
- `eggs_loss_006`: NNR scoping-review limitation.
- `eggs_loss_007`: different meanings of `up to one egg/day`.

Do not count `eggs_loss_001` or `eggs_loss_002` against the Gemma4 blinded comparator unless the reviewer explicitly disagrees with `docs/review/BLINDED_BASELINE_AUDIT.md`.

For each priority loss, record:

```yaml
loss_id:
reviewer_decision: pending
reviewer_note:
```

## Final Review Decision

```yaml
reviewer:
review_date:
overall_decision: human-review-needed
source_fidelity_score:
relation_correctness_score:
crux_usefulness_score:
flat_synthesis_fairness_score:
reasoning_utility_score:
required_changes: []
showable_with_limits: false
```

Codex must not fill reviewer identity, review date, or `showable_with_limits: true` without explicit human review results.
