# Reviewer Start Here

Status: `human-review-needed`

Purpose: let a human reviewer audit the evidence without first learning the whole repository.

## Recommended Review Passes

| Pass | Time | What to open | Output |
| --- | ---: | --- | --- |
| Quick pass | 30 minutes | `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv` | Accept/revise/reject the highest-risk rows. |
| Serious pass | 2 hours | Tier 1 checklist plus the three case packets below. | Fill confidence, required revision, and notes for each priority row. |
| Full pass | 4+ hours | All worked maps, baselines, audits, source files, and multi-model baselines. | Promote, revise, or reject worked-region claims. |

## One File To Fill First

Start with:

- `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv`

This CSV inlines the item text, source excerpt or support, map context, review question, and falsification prompt. It is designed so the first pass can happen from one spreadsheet-like file.

Allowed decisions:

- `accept`: source support, relation label, or erosion finding is fair enough to show with stated limits.
- `revise`: the item is directionally useful but needs narrower wording, different relation type, or clearer caveat.
- `reject`: the item is unsupported, misleading, or not decision-relevant.
- `needs_discussion`: the item requires domain expertise, source checking, or adjudication before it can be used.

Confidence values:

- `low`: reviewer is uncertain or did not inspect the original source.
- `medium`: reviewer inspected the local excerpt or source note and the row looks plausible.
- `high`: reviewer inspected the original source or enough surrounding context to stand behind the decision.

## Case Packets

Use these after or alongside the Tier 1 CSV:

- `docs/review/LHC_HUMAN_AUDIT_PACKET.md`
- `docs/review/EGGS_HUMAN_AUDIT_PACKET.md`
- `docs/review/COVID_HUMAN_AUDIT_PACKET.md`

## Review Questions

For claims:

- Does the source excerpt support the exact claim?
- Is the claim too broad, too certain, or missing a caveat?
- Is the claim useful for reasoning, or merely decorative?

For relations:

- Is the relation type fair: support, challenge, dependency, tension, crux, refinement, or similarity?
- Would this edge make a future reader overstate the inference?
- Should the edge be weakened, split, retagged, or removed?

For erosion findings:

- Did the flat synthesis actually preserve this distinction well enough?
- Is the mapped distinction decision-relevant?
- Is the audit overstating the loss?

## Completed Row Examples

Accepted row:

```csv
item_type,item_id,reviewer_decision,confidence,required_revision,reviewer_notes
claim,eggs_c015,accept,medium,,Local excerpt supports that the RCT evidence concerns lipid markers rather than CVD outcomes.
```

Revised row:

```csv
item_type,item_id,reviewer_decision,confidence,required_revision,reviewer_notes
relation,lhc_r004,revise,medium,"Change relation from supports to refines.",The edge is useful but currently sounds stronger than the compact-star evidence alone warrants.
```

Rejected row:

```csv
item_type,item_id,reviewer_decision,confidence,required_revision,reviewer_notes
loss,covid_loss_005,reject,low,,The flat synthesis already states this is not a whole-case resolution; the map may improve auditability but the loss should not be counted as omission.
```

## Handoff Rule

Do not change any artifact from `human-review-needed` to `human-reviewed-showable` unless a human reviewer has filled reviewer name or identifier, review date, item decisions, and required revisions.
