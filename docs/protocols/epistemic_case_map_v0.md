# Epistemic Case Map v0

## Objects

### Source

A source is a document, transcript, dataset, expert statement, or investigator note. Sources should preserve provenance and enough context for an auditor to recover the original basis for a claim.

### Claim

A claim is an atomic or near-atomic proposition that matters to the case. It
should be narrower than a paragraph summary but may remain more
natural-language than a formal logic statement. The current schema preserves a
source ID, source span or offsets when available, excerpt hashes, extraction
method, entailment status, review state, and categorical confidence.

Useful claim types include:

- `evidence_claim`
- `risk_claim`
- `inference_claim`
- `counterpoint_or_caveat`
- `method_claim`
- `substantive_claim`

### Relation

A relation links two claims through `source_claim` and `target_claim`. Direction
is semantic, not merely visual: read a directed edge as "the source claim has
the stated effect on the target claim." The current relation types are:

| Type | Direction and meaning |
| --- | --- |
| `supports` | The source claim supplies evidence or reasoning that strengthens the target claim. |
| `challenges` | The source claim supplies evidence or reasoning that weakens, contradicts, or raises an objection to the target claim. |
| `refines` | The source claim narrows, qualifies, or makes the scope of the target claim more precise. |
| `similar_to` | The claims are relevantly similar but should not be merged automatically. This relation is symmetric; endpoint order has no substantive meaning. |
| `depends_on` | The source claim states a necessary, enabling, or load-bearing condition for the target claim. In other words, the **target depends on the source**. |
| `crux_for` | Resolving or materially changing the source claim would change how the target claim should be assessed. |
| `in_tension_with` | The claims cannot both be accepted without qualification, reconciliation, or a scope distinction. This relation is symmetric; endpoint order has no substantive meaning. |

Every relation must include a rationale explaining why that type and direction
apply. Validators can check allowed types and endpoint existence; they cannot
establish that the inference is substantively correct. Important directed
relations therefore remain human-review obligations. For symmetric relations,
producers should use a stable endpoint ordering so regenerated artifacts do not
churn.

### Open Question

An open question identifies a gap, crux, missing perspective, or next investigation that would improve the map.

## Review Standard

A map is not judged by whether it has a fluent summary. It is judged by whether another investigator can:

- trace claims back to sources,
- see where similar claims differ,
- find disagreements and caveats,
- identify what would change the bottom-line assessment,
- extend the artifact without starting over.

## Known Limits

The current schema is intentionally small. It encodes source spans/offsets and
categorical confidence, while source-independence and method metadata can be
attached through case metadata files and propagated into appraisal. It does
not yet provide formally calibrated probabilities, a first-class author-stance
model, first-class independence edges in the core schema, temporal version
history, multi-reviewer conflict resolution, or user-specific belief updates.
