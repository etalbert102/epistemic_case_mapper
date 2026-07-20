# Reference Lineage

Status: `human-review-needed`

Purpose: connect the prototype to competition-provided examples of strong epistemic work. These references are not evidence for the LHC, eggs, or COVID claims; they clarify the kind of scrutiny this workflow is meant to make easier.

## Core Pattern

The reference examples share a pattern: strong epistemic work often finds hidden mismatches between what a claim appears to say and what the underlying evidence, measurement, dataset, intervention, or system model actually supports.

This prototype turns that pattern into a reusable artifact format. It gives reviewers stable handles for:

- source boundaries,
- measurement or endpoint differences,
- same-label-but-not-same-object distinctions,
- relation dependencies,
- caveats and scope limits,
- cruxes and update triggers,
- loss audits when flat synthesis hides any of the above.

## Design Implications From The References

| Reference family | Useful idea | How the mapper incorporates it |
| --- | --- | --- |
| Transparent Replications / importance hacking | A result can be real but framed as more important, novel, or decision-relevant than the measurement warrants. | Erosion audits ask whether flat synthesis overstates decisiveness or hides what the result actually supports. |
| Flake and Fried / questionable measurement practices | Conclusions depend on whether the measure fits the construct. | Eggs maps separate CVD outcomes, LDL markers, guideline synthesis, population caveats, and replacement-food modeling. |
| Nadel and Pritchett / construct validity in development RCTs | The same label can refer to meaningfully different interventions across sites. | The maps preserve same-label differences, such as "up to one egg/day" across guidance, cohort exposure, and scoping-review contexts. |
| Leveson / systems-theoretic safety | Safety arguments need dependency structure, control assumptions, and changing-context awareness, not just summary conclusions. | The LHC map separates natural exposure, velocity/trapping caveats, compact-star arguments, critique, and response. |
| Society Library / Diablo Canyon | Complex policy questions benefit from searchable, multi-perspective claim and evidence structures. | The package uses Markdown/JSON maps, stable IDs, UI inspection, and task queues rather than a single report. |
| Heuer / structured analytic techniques | Competing hypotheses and disconfirming evidence should remain explicit under uncertainty. | Relation types, cruxes, challenges, and open questions keep live disagreement visible. |
| Data Colada and Elisabeth Bik-style forensic scrutiny | Research integrity work often turns on inspecting the artifact behind the claim, not only the claim's verbal summary. | Claims carry excerpts, source IDs, entailment checks, and review status so later reviewers can inspect the underlying artifact. |
| Examine.com-style evidence grading | Useful synthesis distinguishes study quality, effect size, and claim scope at the claim level. | Worked maps keep claim-level evidence boundaries instead of flattening a field into one bottom-line recommendation. |
| Gelman-style statistical criticism | Overconfident conclusions often rest on shaky modeling, extrapolation, or reporting choices. | Erosion losses flag hidden dependencies, unsupported scope expansion, and over-smoothed conclusions. |

## Method Implications

The method is not intended merely to make a better AI summary. It is designed to make scrutiny easier to repeat:

1. Fix a source subset.
2. Extract claim-level units with source support.
3. Preserve relations and caveats.
4. Compare against ordinary synthesis.
5. Record which distinctions survived or disappeared.
6. Hand the result to a reviewer without asking them to restart from raw sources.

That is why the primary artifact is not the final prose answer. It is the review surface.
