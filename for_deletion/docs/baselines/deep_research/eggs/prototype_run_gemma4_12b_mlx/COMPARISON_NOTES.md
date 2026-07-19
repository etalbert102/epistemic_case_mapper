# Comparison Notes

Question: For generally healthy adults, should eggs be treated as meaningfully harmful, neutral, or beneficial in dietary advice, especially with respect to cardiovascular risk?

## Bottom Line

On this first source-held comparison, Deep Research is still stronger as a polished final report. The prototype adds useful inspectable structure, especially claim roles, relation types, and explicit quality metadata, but the generated briefing is less coherent and less careful about subgroup caveats.

The prototype is useful as decision-support scaffolding, not yet as a superior reader-facing synthesis.

## Where The Prototype Helped

- It produced reusable artifacts: a generated map, source-grounded claims, relation edges, a quality report, and a briefing summary.
- It selected the correct broad config family: `empirical_policy_decision`.
- It surfaced the central tension between positive US observational associations and neutral adjusted/meta-analytic evidence.
- It created a relation-rich map: `27` relations with `crux_for`, `in_tension_with`, `challenges`, `depends_on`, and `refines` edges.
- It made source limitations visible, including that many reconstructed documents were abstract-level rather than full text.

## Where Deep Research Was Stronger

- The Deep Research report is much more readable and better organized.
- It preserves the main practical answer more precisely: moderate intake is approximately neutral for generally healthy adults, with caution at high intake and in diabetes/high LDL/FH subgroups.
- It handles RCT-vs-observational evidence more cleanly.
- It includes more quantitative detail and richer subgroup discussion.
- It does not mix evidence direction as awkwardly as the prototype briefing does.

## Prototype Weaknesses Exposed

- The briefing overstates the diabetes implication: it says patients with type 2 diabetes may safely include high-egg diets, while Deep Research gives a more cautious synthesis because cohort subgroup signals remain concerning despite neutral DIABEGG biomarkers.
- The `Main Support` section includes concern evidence from Li, Spence, and Zhong without clearly labeling those as counterevidence.
- The `Conflicting Evidence` section has awkward generated language such as "Claim A" and "Claim B"; deterministic repair did not fully translate relation records into reader-friendly prose.
- The briefing leans toward "neutral to potentially beneficial," which is stronger than the safer "approximately neutral at moderate intake" framing.
- The run used a bounded chunk budget and mostly abstract-level source records, so it lacks the source depth Deep Research had.

## Fairness Caveat

This was not a perfect apples-to-apples comparison. Deep Research had access to retrieval and likely fuller source context. The prototype run used the cited sources reconstructed from the final report, mostly as abstracts. This is enough to test whether our scaffolding can add structure over a competent source list, but not enough to claim a full-document superiority test.

## Product Implication

The mapper is producing valuable intermediate evidence structure, but the reader-facing synthesis layer needs another pass. The next target should be section-aware briefing generation that keeps concern evidence out of support sections unless it is explicitly framed as a tension, and that preserves subgroup caution separately from the general healthy-adult answer.

