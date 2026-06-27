# Human Review Rubric

Purpose: give the user or an external reviewer a concrete way to audit worked-region artifacts before they are presented as FLF-ready.

Use this rubric for each worked region.

## 1. Source Fidelity

Questions:

- Does each claim include a source ID and local excerpt?
- Is the claim entailed by the excerpt?
- Are interpretation candidates labeled as interpretations rather than direct source claims?
- Are any claims stronger than the source supports?

Scores:

- `0`: repeated unsupported or distorted claims.
- `1`: mostly faithful, with several claims needing revision.
- `2`: claims are source-faithful and uncertainty is labeled.

## 2. Relation Correctness

Questions:

- Are support/challenge/dependency/tension/crux relations justified?
- Are similar-but-not-identical claims kept distinct?
- Are rhetorical relationships separated from evidential relationships?

Scores:

- `0`: relations are mostly decorative.
- `1`: relations are useful but uneven.
- `2`: relations materially improve understanding of the case.

## 3. Crux Usefulness

Questions:

- Would resolving the named crux change the overall assessment?
- Is the crux linked to concrete claims and sources?
- Is the crux too vague to guide further investigation?

Scores:

- `0`: cruxes are generic.
- `1`: cruxes are plausible but need sharpening.
- `2`: cruxes identify high-leverage next investigations.

## 4. Flat-Synthesis Fairness

Questions:

- Was the baseline generated from the same source subset?
- Did the baseline have a fair prompt?
- Are claimed erosion losses actually within scope?
- Does each counted loss survive the adversarial check?

Scores:

- `0`: baseline comparison is unfair or self-serving.
- `1`: baseline comparison is illustrative but not fully controlled.
- `2`: baseline comparison is fair enough to support the prototype claim.

## 5. Reasoning Utility

Questions:

- Does the artifact help a reviewer reason better than a summary alone?
- Does it surface what to inspect next?
- Does it preserve caveats, disagreement, and missing evidence?
- Could another investigator extend it without starting over?

Scores:

- `0`: artifact is mostly a verbose summary.
- `1`: artifact is useful but hard to navigate or extend.
- `2`: artifact is navigable, extensible, and decision-relevant.

## Review Outcome

Use one of:

- `draft`: not ready for review.
- `human-review-needed`: ready for human audit.
- `human-reviewed-revise`: human reviewed; changes required.
- `human-reviewed-showable`: human reviewed; suitable for a demo with stated limits.

Codex must not assign a human-reviewed status without explicit human review notes.
