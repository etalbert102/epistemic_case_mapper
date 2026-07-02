# Fuller-Source Comparison Notes

Question: For generally healthy adults, should eggs be treated as meaningfully harmful, neutral, or beneficial in dietary advice, especially with respect to cardiovascular risk?

## Result

Using fuller source text materially improved the prototype, but did not eliminate the gap with the Deep Research baseline.

The stronger source packet gave the map more decision-relevant detail: Chinese cohort findings, diabetes-specific risk, dietary-cholesterol adjustment, kidney-function concerns, population differences, and short-term trial evidence in people with type 2 diabetes. The output is no longer merely a thin abstract synthesis.

Deep Research still has advantages in narrative flow, contextual judgment, and richer subgroup synthesis. The prototype is better as an inspectable decision packet than as a polished literature review.

## What Source Depth Fixed

- The map became substantially richer: 51 claims and 37 relations versus the earlier abstract-heavy packet's thinner evidence base.
- The final briefing names more load-bearing distinctions: total dietary cholesterol versus eggs, diabetes status, Asian versus US/European cohorts, kidney-function concerns, and short-term cardiometabolic endpoints.
- The bottom line is more decision-relevant: eggs are not classified as simply harmful or beneficial; the brief distinguishes moderate intake in generally healthy adults from higher-risk subgroups and high-intake settings.
- The output has more concrete source anchoring and fewer generic statements.

## What Source Depth Did Not Fix

- The final prose is still less fluent than Deep Research.
- Some evidence-role assignments remain debatable, especially when an extracted claim mixes source context with a directional finding.
- Relation-derived prose can still sound mechanical, even after reader-language repair.
- The map still needs duplicate suppression and better chunk budget coverage for long source packets.
- Deep Research still does a better job integrating external context and explaining why certain sources deserve more weight.

## Updated Diagnosis

The missing-source problem was a large part of the earlier baseline gap, but not the whole problem.

Approximate current read:

- Source depth and source coverage: about 40% of the gap.
- Final synthesis quality and relation-to-prose conversion: about 35% of the gap.
- Evidence weighting, duplicate control, and long-document coverage: about 25% of the gap.

This suggests the prototype should not be judged only on abstract-heavy runs. With better source coverage, its core advantage becomes clearer: it produces an interrogable decision-support packet with visible evidence roles, cruxes, audit trail, quality report, and source-depth manifest. To beat Deep Research as a final answer, it still needs stronger prose planning and evidence-weighting logic.
