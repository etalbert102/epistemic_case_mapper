# Decision-Space Erosion Differentiation

Status: judge-facing framing note

Decision-space erosion is the failure mode where a synthesis remains broadly correct but smooths away the distinctions a later reviewer needs to audit, revise, or extend the reasoning.

## How This Differs From Nearby Work

| Nearby approach | What it usually preserves | What this prototype adds |
| --- | --- | --- |
| Provenance | where a statement came from | source-grounded claims plus relation IDs, caveats, cruxes, review status, and update triggers |
| Faithful summarization | whether prose reflects the sources | an inspectable record of which dependencies and distinctions survived or disappeared |
| Argument mapping | claims, support, objections | source anchoring, erosion audits, mutation repair, held-out update ledgers, and reviewer handoff packets |
| Knowledge graphs | entities and links | decision-relevant assumptions, contested relations, uncertainty, and local review tasks |
| Literature review | synthesized bottom line | stable objects that can be corrected or extended without regenerating the whole synthesis |

The useful comparison is not "map good, summary bad." A strong model can write a good answer from the same source universe. The prototype tries to preserve the structure that makes later investigation compound: source IDs, claim IDs, relation IDs, caveats, cruxes, and localized update records.

## Claim Hierarchy

Demonstrated:

- Worked-region maps expose dependencies that flat syntheses can compress.
- The investigator challenge shows better deterministic recoverability for selected hidden-dependency tasks.
- Local relation repair and held-out source update can preserve unaffected IDs.

Plausible but under-tested:

- The same artifacts will improve handoff between multiple investigators.
- The method will transfer to more mundane contested cases outside the three examples.
- Richer review logs will make expert disagreement easier to resolve.

Not established:

- The prototype consistently beats strong models on final prose.
- The artifacts are domain-correct without human review.
- The current evaluation is a statistically powered benchmark.
- The workflow is ready to replace expert judgment or a finished research system.

## Why This Is FLF-Relevant

The FLF-relevant contribution is a workflow for making epistemic work reusable. A flat synthesis helps immediate understanding; a map helps a future person ask: which distinction mattered, which source carried it, which relation is disputed, what changed when a new source arrived, and what can be revised locally?
