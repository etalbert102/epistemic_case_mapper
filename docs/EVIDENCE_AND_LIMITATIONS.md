# Evidence And Limitations

Status: `human-review-needed`

Purpose: give reviewers one place to inspect where the evidence is strongest, where the prototype is still thin, and where the submission should not overclaim.

## Summary

This submission is strongest as a methodology plus runnable reference prototype for preserving and auditing decision-relevant structure during AI-assisted investigation. It is not a finished epistemic stack or a human-validated knowledge base.

The central claim is that flat synthesis can be broadly useful while still eroding the decision space a later reviewer needs: source boundaries, caveats, dependencies, cruxes, similar-but-not-identical claims, and critique/response structure. The prototype does not claim that all summaries fail. It claims that preservation is brittle and hard to audit unless the structure is made explicit.

## Evidence Ledger

This table is organized around the submission's own evidence, not as a scoring guide.

| Evidence area | What the package shows | Boundary | Stronger next check |
| --- | --- | --- | --- |
| Concrete reasoning gain | `docs/FLF_BEFORE_AFTER_COMPARISON.md`, worked maps, and erosion audits show distinctions that ordinary synthesis can flatten: LHC velocity/trapping dependencies, eggs endpoint boundaries, and COVID disagreement structure. | The comparison against off-the-shelf deep research and top-range Claude Code is still mostly qualitative, despite multi-model baseline audits. | Compare the map workflow against a fresh deep-research baseline on the same sub-question. |
| Transfer across case shapes | LHC black-hole risk, eggs/health, and a narrow COVID origins slice differ by closure, controversy, evidence type, and adversarial pressure. `docs/GENERALIZABILITY_RED_TEAM.md` now names failure boundaries and transfer-test criteria. | The strongest maps are still author-selected worked regions rather than randomly sampled case slices, and no second operator has applied the method independently. | Run one fresh-case transfer test outside the current set, or have a second reviewer revise 10 claims and 10 relations while recording accept/revise/reject decisions. |
| Reusable artifacts | Stable source IDs, claim IDs, relation IDs, Markdown/JSON exports, review packets, and task queues let another investigator inspect or extend local pieces. | Multi-reviewer merge and conflict-resolution workflow is specified but not implemented. | Have a second reviewer revise one map while preserving IDs and recording accept/revise/reject decisions. |
| Ability to absorb more work | Validators, schema, prompt inventory, source manifests, and JSON exports can accept more sources, claims, relations, and model passes. | Extraction and relation labeling are still curated; the current strongest artifact depends on careful human/agent curation. | Run a logged LLM extraction pass and compare it against the curated maps for recall, precision, and review cost. |
| Inspectable method | Workflow docs, prompt inventory, validators, source manifests, audit notes, and `human-review-needed` status make design choices and uncertainty visible. | Some source-fidelity and relation-correctness judgments are still embedded in curated Markdown rather than independently reviewed. | Add a completed review log that shows which claims, relations, and losses were accepted, revised, or rejected. |
| Stress under disagreement | Erosion audits, blinded local-model baselines, multi-model baseline audit, failure-mode discussion, and narrow COVID stress test expose where flat synthesis is brittle. | No external adversarial review has tried to break the maps or source selections. | Ask a motivated reviewer to challenge one worked region and record whether the map helps localize disagreement. |
| Framing contribution | The submission argues that broad correctness is not enough: a synthesis can be right while erasing the reviewable structure needed for compounding epistemic work. `docs/REFERENCE_LINEAGE.md` ties this to contest examples around measurement, construct validity, systems safety, and structured analysis. | The framing may still look like provenance or argument mapping unless the LHC one-minute example lands. | Add a short comparison showing how decision-space erosion differs from ordinary provenance, summarization faithfulness, and argument mining. |
| Matched strong-model check | `docs/evaluations/MATCHED_STRONG_MODEL_LHC_COMPARISON.md` shows that a strong model can recover much of the LHC dependency chain from the same source universe when directly asked. | This is a single run, not a benchmark. It narrows rather than expands the claim: the map is a review surface, not proof of prose superiority. | Repeat on fresh cases and have humans judge recovery, repairability, and update cost. |

## Best Evidence To Inspect

1. `docs/FLF_BEFORE_AFTER_COMPARISON.md`
2. `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`
3. `examples/eggs/worked_region_observational_vs_rct_map.md`
4. `examples/covid_origins_slice/worked_region_bayesian_disagreement_map.md`
5. `docs/review/COVID_HUMAN_AUDIT_PACKET.md`
6. `docs/GENERALIZABILITY_RED_TEAM.md`
7. `docs/review/REVIEWER_START_HERE.md`
8. `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv`
9. `docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md`
10. `docs/HUMAN_AUDIT_GUIDE.md`
11. `docs/NEW_SOURCE_UPDATE_DEMO.md`
12. `docs/RECOVER_REPAIR_UPDATE_DEMO.md`
13. `docs/DECISION_SPACE_EROSION_DIFFERENTIATION.md`
14. `docs/evaluations/MATCHED_STRONG_MODEL_LHC_COMPARISON.md`
15. `examples/lhc_black_holes/full_case_flat_synthesis_baseline.md`
16. `examples/eggs/full_case_flat_synthesis_baseline.md`
17. `docs/review/LHC_HUMAN_AUDIT_PACKET.md`
18. `docs/review/EGGS_HUMAN_AUDIT_PACKET.md`
19. `ui/index.html`

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
| Transfer is plausible but under-tested | Reviewers may accept that the artifact shape travels while still doubting that another operator can apply it well to a fresh case. | `docs/GENERALIZABILITY_RED_TEAM.md` names suitable and unsuitable case shapes, gives a minimal portable workflow, and defines fresh-case and second-operator tests. | Complete one transfer test on a mundane contested case or record an independent second-operator review. |
| Full-case maps are broad scaffolds | Judges may want full source-excerpt-level maps, not just coverage scaffolds. | Every acquired LHC and eggs source is represented in a full-case index and map. | Add source-excerpt-level claims for every full-case cluster. |
| COVID slice is not a full COVID map | A narrow adversarial slice can be mistaken for an origins adjudication or full case study. | COVID artifacts are labeled as a Bayesian-disagreement worked region with a dedicated human audit packet. | Keep it as a worked region unless enough sources and review are added for a full COVID case. |
| Baselines are partly span-limited | A full-document or better-prompted baseline might preserve more structure. | Multi-model blinded baselines and full-case flat baselines make this limitation visible. | Have humans review the full-case baselines and add full-document model logs for paper-grade evidence. |
| File-based workflow | Less usable than an interactive knowledge-base tool. | Markdown and JSON exports are inspectable and reusable. | Build reviewer decision persistence only if provenance can be handled safely. |
| Static UI is inspection-only | Judges can browse the artifact more easily, but cannot edit or review inside the UI. | The UI links back to canonical Markdown/CSV review packets. | Add reviewer decision editing only if persistence and provenance can be handled safely. |
| Relation labels need domain review | Incorrect support/challenge/dependency labels can mislead reviewers. | Relation rationales and source excerpts are explicit. | Domain reviewers should assess relation correctness. |
| Extraction is not fully automated | Manual curation limits scale. | Deterministic scripts and prompt inventory make the process repeatable. | Add LLM extraction passes with reproducible prompt/model logging. |
| Decision-space erosion is a new framing | Judges may see it as a relabeling of known provenance or argument-mining concerns. | `docs/REFERENCE_LINEAGE.md` now connects the framing to contest-provided examples of construct-validity, measurement, safety, evidence-grading, and structured-analysis work. | Add a short judge-facing comparison showing how this differs from ordinary provenance, summarization faithfulness, and argument mining. |
| Evidence is not quantitative enough for a paper | The contest accepts prototypes, but a paper needs stronger evaluation. | Artifact counts, multi-model baselines, and audit packets provide a measurement scaffold. | Run human-reviewed evaluations across more tasks and models. |
| Draft extension region is not canonical | The public-risk framing map strengthens realism but is not yet fully wired into the validated worked-region pipeline. | It is explicitly labeled as a draft extension and linked from the judge path. | Promote it into the canonical validator set after human/source review. |

## Submission Boundary

This submission is best read as a working methodology and reference prototype. It demonstrates how to preserve and audit decision-relevant structure in two full-case scaffolds plus a narrow adversarial COVID worked region. It does not claim to be a complete epistemic stack, a fully automated literature-review system, a full COVID origins adjudication, or a replacement for expert judgment.
