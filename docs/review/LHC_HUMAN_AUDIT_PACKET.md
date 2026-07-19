# LHC Human Audit Packet

Status: `human-review-needed`

Purpose: give an external reviewer a case-specific packet for auditing the LHC worked region without first reading the whole repo.

## Packet Metadata

```yaml
packet_id: lhc_cosmic_ray_argument_audit_packet
case_id: lhc_black_holes
worked_region_id: lhc_cosmic_ray_argument
review_status: human-review-needed
created_by: codex
created_at: 2026-06-27
source_subset:
  - lsag_2008_safety_review
  - spc_2008_lsag_review
  - giddings_mangano_2008_stable_black_holes
  - plaga_2008_metastable_black_holes
  - giddings_mangano_2008_comments_plaga
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
- Worked map: `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`
- Region definition: `docs/worked_regions/lhc_cosmic_ray_argument.md`
- Best-region pointer: `examples/lhc_black_holes/README.md`
- Illustrative baseline: `examples/lhc_black_holes/flat_synthesis_baseline.md`
- Blinded local-model baselines: `examples/lhc_black_holes/blinded_flat_synthesis_baseline_*.md`
- Erosion audit: `examples/lhc_black_holes/decision_space_erosion_audit.md`
- Blinded comparator audit: `docs/review/BLINDED_BASELINE_AUDIT.md`
- Multi-model comparator audit: `docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md`
- Full fillable checklist: `docs/review/LHC_HUMAN_AUDIT_CHECKLIST.csv`

## Reviewer Tasks

1. Complete the LHC rows in `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv` before opening the full map.
2. Check source fidelity for every claim in the worked map.
3. Check that velocity/trapping, compact-star scope, Plaga critique, and GM response claims are not stronger than their excerpts.
4. Check whether relation labels distinguish support, challenge, dependency, tension, and crux correctly.
5. Check whether each counted erosion loss is fair to a normal concise synthesis.
6. Check whether any blinded model baseline already preserves a claimed loss well enough that the loss should be narrowed or rejected.

## Priority Claims

Start with these claims before auditing the rest of the map:

- `lhc_c001` through `lhc_c004`: natural exposure and velocity/trapping context.
- `lhc_c005` through `lhc_c009`: compact-star argument and white-dwarf/neutron-star scope.
- `lhc_c010` through `lhc_c014`: Plaga critique and GM response.

For each priority claim, record:

```yaml
claim_id:
reviewer_decision: pending
reviewer_note:
```

Allowed decisions: `accept`, `revise`, `reject`, `needs_discussion`.

## Priority Relations

Start with these relations:

- `lhc_r003`: velocity/trapping dependency.
- `lhc_r004`: why compact-star evidence becomes relevant.
- `lhc_r016`: how the map keeps the natural-exposure proof from being overcompressed.

For each priority relation, record:

```yaml
relation_id:
reviewer_decision: pending
reviewer_note:
```

## Priority Erosion Findings

Start with these losses:

- `lhc_loss_001`: low-velocity trapping dependency.
- `lhc_loss_002`: white-dwarf versus neutron-star scope split.
- `lhc_loss_005`: GM response threads.
- `lhc_loss_006`: separate Earth/Sun/stars/universe exposure roles.

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
