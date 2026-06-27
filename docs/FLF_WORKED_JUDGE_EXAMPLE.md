# FLF Worked Judge Example

Status: `human-review-needed`

Purpose: show, in one compact example, how the prototype changes what a judge or auditor can inspect.

## Task

Question: should a short synthesis say that moderate egg intake is generally acceptable because recent observational evidence does not show overall CVD harm?

Source subset:

- `aha_2019_dietary_cholesterol_pubmed`
- `bmj_2020_egg_consumption_cvd`
- `jama_2019_dietary_cholesterol_eggs`
- `li_2020_egg_cholesterol_rct_meta`
- `nnr_2023_eggs_scoping_review`

## Flat Output

A normal concise synthesis can reasonably say:

```text
Moderate egg intake, up to about one egg per day, is not consistently associated with higher cardiovascular disease risk in recent observational evidence. Some studies report positive associations for eggs or dietary cholesterol, and randomized trials show that higher egg intake can worsen LDL-related lipid markers. Overall, eggs can fit in a healthy diet for many people, but advice should consider total diet quality and individual risk.
```

This is not a bad answer. It is broadly plausible and useful as prose.

## What The Map Adds

The map makes the review surface explicit:

| Decision-relevant item | Map location | Why it matters |
| --- | --- | --- |
| Observational CVD outcomes and RCT lipid markers answer different questions. | `eggs_c004`, `eggs_c015`, `eggs_c016`, `eggs_r005`, `eggs_r006`, `eggs_r015` | A reviewer should not treat LDL marker movement as the same endpoint as incident CVD. |
| BMJ and JAMA point in different observational directions. | `eggs_c008`, `eggs_c012`, `eggs_c013`, `eggs_r003` | The next audit question is method, exposure unit, adjustment, and cohort context, not which paper to quote. |
| "Up to one egg/day" means different things across sources. | `eggs_c007`, `eggs_c008`, `eggs_c018`, Similar But Not Identical section | The phrase can mean public guidance, cohort exposure category, or scoping-review synthesis. |
| NNR is a scoping review, not a de novo systematic review. | `eggs_c018`, `eggs_c019`, `eggs_r014` | The umbrella conclusion needs evidence-grade limits attached. |

## What The Auditor Should Do

The auditor should not simply decide whether the flat paragraph is true. Instead, they should record item-level decisions:

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

## Judge Takeaway

The prototype is useful if the judge can move from "this paragraph sounds reasonable" to "these are the exact claims and relations I need to verify before trusting the paragraph." The map is not a longer summary; it is a checklist of decision-relevant structure that can be accepted, revised, rejected, or extended.
