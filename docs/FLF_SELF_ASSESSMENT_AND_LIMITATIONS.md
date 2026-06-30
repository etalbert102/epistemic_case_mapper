# FLF Self-Assessment And Limitations

Status: `human-review-needed`

Purpose: give judges one place to inspect how the prototype maps to FLF criteria, where the evidence is strongest, and where the submission should not overclaim.

## Summary

This submission is strongest as a methodology plus runnable reference prototype for preserving and auditing decision-relevant structure during AI-assisted investigation. It is not a finished epistemic stack or a human-validated knowledge base.

The central claim is that flat synthesis can be broadly useful while still eroding the decision space a later reviewer needs: source boundaries, caveats, dependencies, cruxes, similar-but-not-identical claims, and critique/response structure. The prototype does not claim that all summaries fail. It claims that preservation is brittle and hard to audit unless the structure is made explicit.

## Criteria Mapping

| FLF criterion | Evidence in this package | Weakness | Next validation |
| --- | --- | --- | --- |
| Helps someone reason better about a case | `docs/FLF_BEFORE_AFTER_COMPARISON.md`, worked maps, erosion audits, and review packets surface candidate distinctions a reviewer can inspect rather than trust implicitly. | Human reviewers still need to score relation correctness and claim fidelity. | External reviewer records accept/revise/reject decisions on claims, relations, and losses. |
| Generalizes across cases | Demonstrated on LHC black-hole risk, eggs/health, and a narrow COVID origins Bayesian-disagreement slice, which differ by domain, evidentiary closure, controversy profile, and decision context. | The COVID slice is not a full COVID map and needs strict human review before being treated as a worked case. | Add at least one independently reviewed worked region outside the current author-selected set. |
| Scales with better AI or more compute | Stable schema, source IDs, claim IDs, relation IDs, Markdown/JSON exports, validators, and task queues make additional extraction/model passes composable. | Extraction and relation labeling are still curated rather than fully automated. | Run a logged LLM extraction pass and compare it against the curated maps. |
| Compounds across people or teams | Review packets, CSV checklists, stable IDs, source inventories, and task queues let another investigator accept, reject, or extend local pieces. | Multi-reviewer merge and conflict-resolution workflow is only specified, not implemented. | Have a second reviewer edit one map and preserve decision IDs through revision. |
| Stands up to adversarial pressure | Erosion audits include adversarial checks, blinded local-model baselines, failure examples, and explicit limitations. | No completed external audit yet. | Human-score the blinded baselines and map losses for fairness. |
| Produces reusable knowledge artifacts | Full-case scaffolds, worked-region maps, JSON exports, source metadata, and UI dashboard are all checked into the repo. | The static UI is inspection-only and cannot yet persist reviewer decisions. | Add reviewer decision persistence only after provenance handling is explicit. |

## Best Evidence To Inspect

1. `docs/FLF_BEFORE_AFTER_COMPARISON.md`
2. `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`
3. `examples/eggs/worked_region_observational_vs_rct_map.md`
4. `examples/covid_origins_slice/worked_region_bayesian_disagreement_map.md`
5. `docs/review/COVID_HUMAN_AUDIT_PACKET.md`
6. `docs/review/REVIEWER_START_HERE.md`
7. `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv`
8. `docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md`
9. `docs/HUMAN_AUDIT_GUIDE.md`
10. `docs/NEW_SOURCE_UPDATE_DEMO.md`
11. `examples/lhc_black_holes/full_case_flat_synthesis_baseline.md`
12. `examples/eggs/full_case_flat_synthesis_baseline.md`
13. `docs/review/LHC_HUMAN_AUDIT_PACKET.md`
14. `docs/review/EGGS_HUMAN_AUDIT_PACKET.md`
15. `ui/index.html`

## Failure Modes

### The Map Can Preserve Too Much

Decision-space preservation is not maximum-detail retention. A map that preserves every distinction can overwhelm the reviewer. The current mitigation is prioritization through `BEST_REGIONS.md`, review packets, and task queues.

Review question: which preserved distinctions actually change the decision, and which are merely interesting context?

### Relation Labels Can Smuggle Interpretation

The claim text may be source-grounded while the relation type is contestable. A `supports`, `challenges`, `depends_on`, or `crux_for` label can overstate the inferential role of a claim.

Mitigation: every relation has a rationale and remains `human-review-needed`.

### Better Flat Synthesis Can Reduce The Apparent Gap

The prototype should not imply that all summaries fail. Stronger models and better prompts can preserve more detail. The multi-model blinded-baseline audit narrows the claim: the robust problem is not that flat synthesis always loses endpoints, but that preservation is brittle and not easily inspectable.

### Source Selection Can Dominate The Result

If the source subset is biased, a faithful map can still produce a misleading decision surface. Full-case source inventories and source-independence metadata expose what is included and what remains outside each worked region.

### Human Review Can Become A Rubber Stamp

Review packets can look rigorous while reviewers only skim. The method needs explicit accept/reject/revise decisions tied to claims and relations. The current mitigation is item-level CSV checklists, but no completed external review has been recorded yet.

## Risk Register

| Risk | Why it matters | Current mitigation | Remaining work |
| --- | --- | --- | --- |
| No completed human review | Agent-authored maps and audits can be biased or subtly wrong. | Human audit packets and checklists are included. | A named reviewer should record claim, relation, and erosion decisions. |
| Full-case maps are broad scaffolds | Judges may want full source-excerpt-level maps, not just coverage scaffolds. | Every acquired LHC and eggs source is represented in a full-case index and map. | Add source-excerpt-level claims for every full-case cluster. |
| COVID slice is not a full COVID map | A narrow adversarial slice can be mistaken for an origins adjudication or full case study. | COVID artifacts are labeled as a Bayesian-disagreement worked region with a dedicated human audit packet. | Keep it as a worked region unless enough sources and review are added for a full COVID case. |
| Baselines are partly span-limited | A full-document or better-prompted baseline might preserve more structure. | Multi-model blinded baselines and full-case flat baselines make this limitation visible. | Human-score the full-case baselines and add full-document model logs for paper-grade evidence. |
| File-based workflow | Less usable than an interactive knowledge-base tool. | Markdown and JSON exports are inspectable and reusable. | Build reviewer decision persistence only if provenance can be handled safely. |
| Static UI is inspection-only | Judges can browse the artifact more easily, but cannot edit or review inside the UI. | The UI links back to canonical Markdown/CSV review packets. | Add reviewer decision editing only if persistence and provenance can be handled safely. |
| Relation labels need domain review | Incorrect support/challenge/dependency labels can mislead reviewers. | Relation rationales and source excerpts are explicit. | Domain reviewers should score relation correctness. |
| Extraction is not fully automated | Manual curation limits scale. | Deterministic scripts and prompt inventory make the process repeatable. | Add LLM extraction passes with reproducible prompt/model logging. |
| Decision-space erosion is a new framing | Judges may see it as a relabeling of known provenance or argument-mining concerns. | Submission packet distinguishes reviewable decision-relevant structure from generic faithfulness. | Related-work framing should cite provenance, summarization faithfulness, argument mining, and evidence synthesis. |
| Evidence is not quantitative enough for a paper | The contest accepts prototypes, but a paper needs stronger evaluation. | Artifact counts, multi-model baselines, and audit packets provide a measurement scaffold. | Run human-scored evaluations across more tasks and models. |
| Draft extension region is not canonical | The public-risk framing map strengthens realism but is not yet fully wired into the validated worked-region pipeline. | It is explicitly labeled as a draft extension and linked from the judge path. | Promote it into the canonical validator set after human/source review. |

## Submission Boundary

This submission should be judged as a working methodology and reference prototype. It demonstrates how to preserve and audit decision-relevant structure in two full-case scaffolds plus a narrow adversarial COVID worked region. It does not claim to be a complete epistemic stack, a fully automated literature-review system, a full COVID origins adjudication, or a replacement for expert judgment.
