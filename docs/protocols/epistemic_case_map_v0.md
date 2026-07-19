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

A relation links two claims. Current relation types:

- `supports`
- `challenges`
- `refines`
- `similar_to`
- `depends_on`
- `crux_for`
- `in_tension_with`

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
