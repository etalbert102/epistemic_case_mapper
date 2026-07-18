# Decision-Space Erosion Differentiation

Status: judge-facing framing note

Decision-space erosion is a downstream failure mode, not a label for every omission. It occurs when a synthesis or workflow makes a decision-relevant option, interpretation, evidence path, caveat, or review boundary materially less visible or recoverable before accountable review.

The broader decision-space writing frame is:

```text
retrieval gate -> claim normalization -> decision-space construction -> judgment anchors -> artifact fidelity -> auditable authority
```

This prototype is strongest when read as a concrete implementation of that chain. It is not only preserving more text. It is preserving the objects a later reviewer needs in order to exercise judgment.

## How This Differs From Nearby Work

| Nearby approach | What it usually preserves | What this prototype adds |
| --- | --- | --- |
| Provenance | where a statement came from | source-grounded claims plus relation IDs, caveats, cruxes, review status, and update triggers |
| Faithful summarization | whether prose reflects the sources | an inspectable record of which dependencies and distinctions survived or disappeared |
| Argument mapping | claims, support, objections | source anchoring, erosion audits, mutation repair, held-out update ledgers, and reviewer handoff packets |
| Knowledge graphs | entities and links | decision-relevant assumptions, contested relations, uncertainty, and local review tasks |
| Literature review | synthesized bottom line | stable objects that can be corrected or extended without regenerating the whole synthesis |

The useful comparison is not "map good, summary bad." A strong model can write a good answer from the same source universe. The prototype tries to preserve the structure that makes later investigation compound: source IDs, claim IDs, relation IDs, caveats, cruxes, and localized update records.

## Framework Mapping

| Decision-space concept | Current artifact surface | What the reviewer can do |
| --- | --- | --- |
| Retrieval-gated reasoning | case manifests, source packets, optional intake filter, source-universe parity reports | inspect which evidence entered the reasoning space |
| Claim normalization | source-grounded claims, excerpts, span IDs, source IDs | compare normalized claims against source text and flag lost scope |
| Decision-space construction | maps, relation graphs, cruxes, caveats, similar-but-not-identical sections | see which options, dependencies, and tensions remain available |
| Judgment anchors | claim IDs, relation IDs, crux IDs, review checklists, task queues | accept, revise, reject, or escalate local judgments |
| Artifact fidelity | Markdown, JSON exports, validation gates, mutation diffs, update ledgers | verify that reviewable structure survives transformation |
| Auditable authority | human-review packets and localized repair/update workflows | intervene without regenerating the whole case |

This mapping also narrows the claims. The prototype does not solve source discovery or domain truth by itself. It preserves and audits the bounded decision space created from the declared source packet.

## Claim Hierarchy

Demonstrated:

- Worked-region maps expose dependencies that flat syntheses can compress.
- The investigator challenge shows better deterministic recoverability for selected hidden-dependency tasks.
- Local relation repair and held-out source update can preserve unaffected IDs.
- The artifacts give reviewers local intervention points rather than forcing review through final prose alone.

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
