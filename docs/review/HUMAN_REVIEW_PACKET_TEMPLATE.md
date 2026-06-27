# Human Review Packet Template

Purpose: provide a repeatable packet shape for external review of curated worked-region maps.

## Packet Metadata

```yaml
packet_id: example_packet
case_id: lhc_black_holes
worked_region_id: lhc_cosmic_ray_argument
review_status: human-review-needed
created_by: codex
created_at: 2026-06-26
source_subset:
  - lsag_2008_safety_review
  - spc_2008_lsag_review
prompt_versions:
  source_mapping: source_mapping_prompt_v1
  relation_extraction: relation_extraction_prompt_v1
  erosion_audit: erosion_audit_prompt_v1
```

## Claim Review

For each claim, provide:

```yaml
claim_id: claim_0001
source_id: lsag_2008_safety_review
source_span: normalized_chars:0-120
excerpt: "..."
claim_text: "..."
entailed_by_excerpt: yes
reviewer_decision: pending
reviewer_note: ""
```

Allowed reviewer decisions:

- `accept`
- `revise`
- `reject`
- `needs_discussion`

## Relation Review

For each relation, provide:

```yaml
relation_id: rel_0001
source_claim_id: claim_0001
target_claim_id: claim_0002
relation_type: depends_on
rationale: "..."
reviewer_decision: pending
reviewer_note: ""
```

## Erosion Finding Review

For each baseline comparison finding, provide:

```yaml
loss_id: loss_0001
loss_type: dependency
source_support:
  - claim_0001
  - claim_0002
flat_baseline_excerpt: "..."
case_map_preserves: "..."
adversarial_check: survives
reviewer_decision: pending
reviewer_note: ""
```

## Exported Review Decision

```yaml
reviewer: ""
review_date: ""
overall_decision: human-reviewed-revise
claim_decisions: []
relation_decisions: []
erosion_finding_decisions: []
required_changes: []
showable_with_limits: false
```

Codex must not fill `reviewer`, `review_date`, or mark `showable_with_limits: true` unless the user provides explicit review results.
