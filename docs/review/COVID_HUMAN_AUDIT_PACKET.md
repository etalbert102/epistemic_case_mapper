# COVID Human Audit Packet

Status: `human-review-needed`

Purpose: provide a narrow human-review path for the COVID Bayesian-disagreement worked region. This packet is for source fidelity and relation fairness, not for deciding COVID origins.

## Scope

Worked region: `covid_bayesian_disagreement`

Core files:

- `docs/review/REVIEWER_START_HERE.md`
- `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv`
- `examples/covid_origins_slice/worked_region_bayesian_disagreement_map.md`
- `examples/covid_origins_slice/flat_synthesis_baseline.md`
- `examples/covid_origins_slice/decision_space_erosion_audit.md`
- `examples/covid_origins_slice/BEST_REGIONS.md`

## Priority Claims

Complete the COVID rows in `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv` first. It inlines the row text, source support, review question, and falsification prompt.

Start with:

- `covid_c005`: Rootclaim concession that Peter Miller won the debate.
- `covid_c006`: Rootclaim's maintained lab-leak conclusion.
- `covid_c009` and `covid_c010`: Good Judgment aggregate forecast versus persistent minority disagreement.
- `covid_c012` and `covid_c013`: Debarre/Worobey geography-bias rebuttal and its infection-location caveat.
- `covid_c014`, `covid_c015`, and `covid_c016`: Levin's decomposition, reported odds ratio, and working-paper status caveat.
- `covid_c017` and `covid_c018`: Weissman phylogeny critique and subargument-scope caveat.

For each priority claim, record:

```yaml
claim_id:
reviewer_decision: pending
reviewer_note:
```

Allowed decisions: `accept`, `revise`, `reject`, `needs_discussion`.

## Priority Relations

Start with:

- `covid_r002`: debate concession versus continued substantive disagreement.
- `covid_r005`: Good Judgment aggregate forecast qualified by minority distribution.
- `covid_r007`: Debarre/Worobey reply as a challenge to geography-based lab-leak-favoring inference.
- `covid_r010`: source-status caveat qualifying Levin's reported odds ratio.
- `covid_r011`: Weissman critique versus whole-case scope boundary.
- `covid_r014`: early-case geography as a crux for the dispute.

For each priority relation, record:

```yaml
relation_id:
reviewer_decision: pending
reviewer_note:
```

## Priority Erosion Findings

Start with:

- `covid_loss_003`: market-geography role ambiguity.
- `covid_loss_004`: Bayesian decomposition authority.
- `covid_loss_005`: subargument/whole-case boundary.

For each priority loss, record:

```yaml
loss_id:
reviewer_decision: pending
reviewer_note:
```

## Reviewer Warnings

- Do not infer that this map adjudicates COVID origins.
- Check original sources before marking claims human-reviewed; current source files are source-local notes.
- Be stricter than in LHC or eggs because COVID is adversarial, politically charged, and methodologically contested.
