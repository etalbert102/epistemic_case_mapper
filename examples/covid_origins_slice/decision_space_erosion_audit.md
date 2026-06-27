# COVID Origins Slice Decision-Space Erosion Audit

Status: `human-review-needed`
Prompt/procedure: `decision_space_erosion_audit_v1`
Baseline comparator: `examples/covid_origins_slice/flat_synthesis_baseline.md`
Map comparator: `examples/covid_origins_slice/worked_region_bayesian_disagreement_map.md`

## Counted Losses

loss_id: covid_loss_001
loss_type: `adjudication/process distinction`
lost_item: The flat baseline mentions Rootclaim's concession and process critique but does not make the distinction between debate outcome, process critique, and substantive posterior disagreement directly auditable.
source_support:
  - `rootclaim_debate_results`
case_map_preserves: `covid_c005`, `covid_c006`, `covid_c007`, `covid_r002`, `covid_r003`
flat_baseline_omission: The prose compresses these into a post-debate disagreement paragraph.
adversarial_check: survives; a paragraph can fairly mention all three, but the reviewer cannot inspect which relation is concession, tension, or process refinement.

loss_id: covid_loss_002
loss_type: `aggregate/minority distribution`
lost_item: The flat baseline says Good Judgment was not unanimous but does not preserve the aggregate forecast and persistent minority as separate reviewable claims.
source_support:
  - `good_judgment_superforecasting`
case_map_preserves: `covid_c009`, `covid_c010`, `covid_r005`
flat_baseline_omission: The prose does not make the minority-disagreement qualification an explicit relation.
adversarial_check: survives; the distinction matters because aggregate and distribution answer different review questions.

loss_id: covid_loss_003
loss_type: `market-geography role ambiguity`
lost_item: The flat baseline lists origin site, superspreading location, and ascertainment assumptions but does not turn them into a navigable crux.
source_support:
  - `acx_rootclaim_review`
  - `debarre_worobey_reply`
case_map_preserves: `covid_c004`, `covid_c012`, `covid_c013`, `covid_r008`, `covid_r012`, `covid_r014`
flat_baseline_omission: The prose leaves the market-geography roles in one sentence.
adversarial_check: survives; the role of geography is a high-leverage disagreement, not just context.

loss_id: covid_loss_004
loss_type: `Bayesian decomposition authority`
lost_item: The flat baseline reports Levin's large odds ratio but does not preserve the decomposition and working-paper status as separate audit targets.
source_support:
  - `levin_2025_bayesian_assessment`
case_map_preserves: `covid_c014`, `covid_c015`, `covid_c016`, `covid_r009`, `covid_r010`, `covid_r013`
flat_baseline_omission: The prose gives the odds ratio and decomposition at high level but not the relation between decomposition, result, and source-status caveat.
adversarial_check: survives; this is exactly where a reviewer needs to inspect assumptions before trusting the number.

loss_id: covid_loss_005
loss_type: `subargument/whole-case boundary`
lost_item: The flat baseline says Weissman's critique does not resolve the whole case, but it does not preserve the subargument boundary as an explicit relation.
source_support:
  - `weissman_2026_phylogeny_comment`
case_map_preserves: `covid_c017`, `covid_c018`, `covid_r011`
flat_baseline_omission: The prose includes the caution but not as an auditable claim-relation pair.
adversarial_check: survives; this boundary prevents a later user from over-updating on a narrow methodological critique.

loss_id: covid_loss_006
loss_type: `update-trigger flattening`
lost_item: The flat baseline says future evidence would move the assessment but does not preserve Good Judgment's update triggers as a separate conditional belief state.
source_support:
  - `good_judgment_superforecasting`
case_map_preserves: `covid_c011`, `covid_r006`, `covid_r015`
flat_baseline_omission: The prose converts specific update triggers into a generic future-evidence sentence.
adversarial_check: survives; concrete update triggers are part of what makes the artifact reusable.

## Borderline Or Rejected Losses

- The flat baseline does preserve the high-level warning that COVID should be represented as structured disagreement, so this audit should not claim that the prose is misleading overall.
- The flat baseline explicitly names multiple evidence families; the remaining losses are about auditability and relation structure, not total omission.

