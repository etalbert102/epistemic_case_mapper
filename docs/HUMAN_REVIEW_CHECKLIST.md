# Human Review Checklist

Purpose: give a human reviewer a compact checklist for deciding whether a worked-region artifact can move beyond `human-review-needed`.

## Source Fidelity

- [ ] Every claim has a source ID.
- [ ] Every claim has a local excerpt or span.
- [ ] The excerpt entails the claim, or the claim is labeled as an interpretation candidate.
- [ ] No claim is stronger than the source supports.
- [ ] Provenance tags describe what was actually retrieved or supplied, not confidence.

## Relation Correctness

- [ ] Every relation has a type and rationale.
- [ ] Support, challenge, dependency, tension, crux, and similarity links are not used interchangeably.
- [ ] Similar-but-not-identical claims remain distinct.
- [ ] Critiques and responses are preserved rather than collapsed into a single settled conclusion.

## Crux And Open Question Usefulness

- [ ] Each crux would change the assessment if resolved differently.
- [ ] Each open question links to relevant claims or sources.
- [ ] Missing evidence is surfaced rather than hidden.

## Flat Baseline Fairness

- [ ] The baseline uses the same source subset as the map.
- [ ] The baseline prompt is recorded.
- [ ] The baseline did not inspect the curated map first, or the limitation is disclosed.
- [ ] Each counted erosion loss survives an adversarial fairness check.

## Reasoning Utility

- [ ] The artifact helps recover options, frames, caveats, dependencies, and conflicts more easily than a flat summary.
- [ ] The artifact is navigable enough for another investigator to extend.
- [ ] Residual uncertainty and review limits are visible.

## Review Outcome

Choose one:

- [ ] `human-reviewed-revise`: reviewed, but changes are required.
- [ ] `human-reviewed-showable`: suitable for a demo with stated limits.

Reviewer:

Date:

Required changes:
