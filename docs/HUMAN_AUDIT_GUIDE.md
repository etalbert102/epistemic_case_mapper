# Human Audit Guide

Status: `human-review-needed`

Purpose: consolidate the worked judge example, auditor walkthrough, checklist, and rubric into one reviewer handoff guide.

## Compact Worked Example

Task: judge whether a short synthesis should say that moderate egg intake is generally acceptable because recent observational evidence does not show overall CVD harm.

Source subset:

- `aha_2019_dietary_cholesterol_pubmed`
- `bmj_2020_egg_consumption_cvd`
- `jama_2019_dietary_cholesterol_eggs`
- `li_2020_egg_cholesterol_rct_meta`
- `nnr_2023_eggs_scoping_review`

Flat output:

```text
Moderate egg intake, up to about one egg per day, is not consistently associated with higher cardiovascular disease risk in recent observational evidence. Some studies report positive associations for eggs or dietary cholesterol, and randomized trials show that higher egg intake can worsen LDL-related lipid markers. Overall, eggs can fit in a healthy diet for many people, but advice should consider total diet quality and individual risk.
```

This is not a bad answer. It is broadly plausible and useful as prose. The map adds a review surface:

| Decision-relevant item | Map location | Why it matters |
| --- | --- | --- |
| Observational CVD outcomes and RCT lipid markers answer different questions. | `eggs_c004`, `eggs_c015`, `eggs_c016`, `eggs_r005`, `eggs_r006`, `eggs_r015` | A reviewer should not treat LDL marker movement as the same endpoint as incident CVD. |
| BMJ and JAMA point in different observational directions. | `eggs_c008`, `eggs_c012`, `eggs_c013`, `eggs_r003` | The next audit question is method, exposure unit, adjustment, and cohort context, not which paper to quote. |
| "Up to one egg/day" means different things across sources. | `eggs_c007`, `eggs_c008`, `eggs_c018`, Similar But Not Identical section | The phrase can mean public guidance, cohort exposure category, or scoping-review synthesis. |
| NNR is a scoping review, not a de novo systematic review. | `eggs_c018`, `eggs_c019`, `eggs_r014` | The umbrella conclusion needs evidence-grade limits attached. |

## Auditor Workflow

Use this sequence before trusting a worked-region artifact.

0. Start with the reviewer entry point and self-contained Tier 1 checklist.
   - `docs/review/REVIEWER_START_HERE.md`
   - `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv`
1. Audit the source subset before model outputs.
   - Do all source IDs exist in the case manifest?
   - Does each source have local text and provenance?
   - Are critique and response sources both present when disagreement matters?
   - Is public reassurance separated from technical evidence?
2. Freeze the curated map before comparing outputs.
   - Do not revise the map after seeing the flat baseline unless the map is moved back to draft status and the comparison is rerun.
3. Generate or inspect the flat baseline.
   - The baseline should use the same source subset and a recorded prompt.
   - Count an omission as decision-space erosion only if it reduces recoverability of a decision-relevant option, frame, conflict, dependency, caveat, or source boundary.
4. Audit erosion findings.
   - Check source support, decision relevance, fairness, and case-map contrast.
5. Record item-level decisions.

Example decision records:

```yaml
claim_id: eggs_c015
reviewer_decision: accept | revise | reject | needs_discussion
reviewer_note: Does the Li 2020 excerpt support the claim that the RCT evidence measures lipid markers rather than CVD outcomes?

relation_id: eggs_r006
reviewer_decision: accept | revise | reject | needs_discussion
reviewer_note: Is it fair to call randomized lipid-marker worsening in tension with BMJ's observational null CVD finding, or should this relation be narrowed?

loss_id: eggs_loss_001
reviewer_decision: accept | revise | reject | needs_discussion
reviewer_note: Does the flat synthesis preserve the endpoint boundary well enough, or does the map add decision-relevant auditability?
```

## Checklist

### Source Fidelity

- [ ] Every claim has a source ID.
- [ ] Every claim has a local excerpt or span.
- [ ] The excerpt entails the claim, or the claim is labeled as an interpretation candidate.
- [ ] No claim is stronger than the source supports.
- [ ] Provenance tags describe what was actually retrieved or supplied, not confidence.

### Relation Correctness

- [ ] Every relation has a type and rationale.
- [ ] Support, challenge, dependency, tension, crux, and similarity links are not used interchangeably.
- [ ] Similar-but-not-identical claims remain distinct.
- [ ] Critiques and responses are preserved rather than collapsed into a single settled conclusion.

### Crux And Open Question Usefulness

- [ ] Each crux would change the assessment if resolved differently.
- [ ] Each open question links to relevant claims or sources.
- [ ] Missing evidence is surfaced rather than hidden.

### Flat Baseline Fairness

- [ ] The baseline uses the same source subset as the map.
- [ ] The baseline prompt is recorded.
- [ ] The baseline did not inspect the curated map first, or the limitation is disclosed.
- [ ] Each counted erosion loss survives an adversarial fairness check.

### Reasoning Utility

- [ ] The artifact helps recover options, frames, caveats, dependencies, and conflicts more easily than a flat summary.
- [ ] The artifact is navigable enough for another investigator to extend.
- [ ] Residual uncertainty and review limits are visible.

## Scoring Rubric

Use scores from 0 to 2 for each category:

| Category | 0 | 1 | 2 |
| --- | --- | --- | --- |
| Source fidelity | Repeated unsupported or distorted claims. | Mostly faithful, with several claims needing revision. | Claims are source-faithful and uncertainty is labeled. |
| Relation correctness | Relations are mostly decorative. | Relations are useful but uneven. | Relations materially improve understanding of the case. |
| Crux usefulness | Cruxes are generic. | Cruxes are plausible but need sharpening. | Cruxes identify high-leverage next investigations. |
| Flat-synthesis fairness | Baseline comparison is unfair or self-serving. | Baseline comparison is illustrative but not fully controlled. | Baseline comparison is fair enough to support the prototype claim. |
| Reasoning utility | Artifact is mostly a verbose summary. | Artifact is useful but hard to navigate or extend. | Artifact is navigable, extensible, and decision-relevant. |

## Review Outcome

Use one of:

- `draft`: not ready for review.
- `human-review-needed`: ready for human audit but not approved.
- `human-reviewed-revise`: human reviewed; changes required.
- `human-reviewed-showable`: human reviewed; suitable for a demo with stated limits.

Codex or another model must not assign a human-reviewed status without explicit human review notes.

Case-specific packets:

- `docs/review/REVIEWER_START_HERE.md`
- `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv`
- `docs/review/LHC_HUMAN_AUDIT_PACKET.md`
- `docs/review/EGGS_HUMAN_AUDIT_PACKET.md`
- `docs/review/COVID_HUMAN_AUDIT_PACKET.md`
- `docs/review/LHC_HUMAN_AUDIT_CHECKLIST.csv`
- `docs/review/EGGS_HUMAN_AUDIT_CHECKLIST.csv`
- `docs/review/COVID_HUMAN_AUDIT_CHECKLIST.csv`
