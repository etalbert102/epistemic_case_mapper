# Evidence And Limitations

Status: `human-review-needed`

Purpose: give reviewers one place to inspect where the evidence is strongest, where the prototype is still thin, and where the submission should not overclaim.

## Summary

This submission is strongest as a methodology plus runnable reference prototype for preserving operational judgment during AI-assisted investigation. It is not a finished epistemic stack or a human-validated knowledge base.

The central claim is that AI-assisted workflows can lose reasoning structure during retrieval, claim normalization, mapping, and synthesis even when the final answer is broadly useful. That becomes decision-space erosion when a decision-relevant option, interpretation, evidence path, caveat, or review boundary becomes materially less visible or recoverable before accountable review. The prototype does not claim that all summaries fail. It claims that preservation is brittle and hard to audit unless the structure is made explicit.

## Claim Boundary

Demonstrated:

- Source-grounded worked-region maps preserve dependencies, caveats, critique/response structure, and review handles that flat syntheses can compress.
- The investigator challenge shows better deterministic recoverability for selected hidden-dependency tasks.
- Local repair and held-out-source update can preserve stable IDs for unaffected map objects.
- The package demonstrates artifact fidelity across Markdown, JSON, review packets, mutation repair, and update ledgers.

Plausible but under-tested:

- The same artifacts will improve multi-investigator handoff.
- The same method will transfer to fresh cases without author selection.
- More complete review logs will make expert disagreement easier to adjudicate.

Not established:

- The current prototype consistently beats strong models on final prose quality.
- The artifacts are domain-correct without human review.
- The challenge is a statistically powered benchmark.

## Evidence Ledger

This table is organized around the submission's own evidence, not as a scoring guide.

| Evidence area | What the package shows | Boundary | Stronger next check |
| --- | --- | --- | --- |
| Concrete reasoning gain | `docs/submission/PROOF_BY_EXAMPLE.md`, worked maps, and erosion audits show distinctions that ordinary synthesis can flatten: LHC velocity/trapping dependencies, eggs endpoint boundaries, and COVID disagreement structure. | The comparison against off-the-shelf deep research and top-range coding agents is still mostly qualitative, despite multi-model baseline audits. | Compare the map workflow against a fresh deep-research baseline on the same sub-question. |
| Transfer across case shapes | LHC black-hole risk, eggs/health, and a narrow COVID origins slice differ by closure, controversy, evidence type, and adversarial pressure. `docs/submission/GENERALIZABILITY_RED_TEAM.md` now names failure boundaries and transfer-test criteria. | The strongest maps are still author-selected worked regions rather than randomly sampled case slices, and no second operator has applied the method independently. | Run one fresh-case transfer test outside the current set, or have a second reviewer revise 10 claims and 10 relations while recording accept/revise/reject decisions. |
| Reusable artifacts | Stable source IDs, claim IDs, relation IDs, Markdown/JSON exports, review packets, and task queues let another investigator inspect or extend local pieces. | Multi-reviewer merge and conflict-resolution workflow is specified but not implemented. | Have a second reviewer revise one map while preserving IDs and recording accept/revise/reject decisions. |
| Framework integration | `docs/methodology/DECISION_SPACE_FRAMEWORK.md` maps retrieval-gated reasoning, claim normalization, decision-space construction, judgment anchors, artifact fidelity, and auditable authority onto concrete repo artifacts. | The current integration is strongest as a submission framing and artifact audit; the UI does not yet persist reviewer interventions. | Run a reviewer session and verify that accept/revise/reject decisions propagate through regenerated artifacts. |
| Ability to absorb more work | Validators, schema, prompt inventory, source manifests, and JSON exports can accept more sources, claims, relations, and model passes. | Extraction and relation labeling are still curated; the current strongest artifact depends on careful human/agent curation. | Run a logged LLM extraction pass and compare it against the curated maps for recall, precision, and review cost. |
| Inspectable method | Workflow docs, prompt inventory, validators, source manifests, audit notes, and `human-review-needed` status make design choices and uncertainty visible. | Some source-fidelity and relation-correctness judgments are still embedded in curated Markdown rather than independently reviewed. | Add a completed review log that shows which claims, relations, and losses were accepted, revised, or rejected. |
| Stress under disagreement | Erosion audits, blinded local-model baselines, multi-model baseline audit, failure-mode discussion, and narrow COVID stress test expose where flat synthesis is brittle. | No external adversarial review has tried to break the maps or source selections. | Ask a motivated reviewer to challenge one worked region and record whether the map helps localize disagreement. |
| Framing contribution | The submission argues that broad correctness is not enough: a synthesis can be right while losing the reviewable structure needed for compounding epistemic work. `docs/submission/REFERENCE_LINEAGE.md` ties this to contest examples around measurement, construct validity, systems safety, and structured analysis. `docs/methodology/DECISION_SPACE_FRAMEWORK.md` maps the broader decision-space framework onto repo artifacts. | The framing may still look like provenance or argument mapping unless the mechanism chain and LHC one-minute example land. | Have an external reviewer judge whether the framework mapping clarifies the project or feels like terminology layered on top of argument mapping. |
| Matched strong-model check | `docs/evaluations/MATCHED_STRONG_MODEL_LHC_COMPARISON.md` shows that a strong model can recover much of the LHC dependency chain from the same source universe when directly asked. | This is a single run, not a benchmark. It narrows rather than expands the claim: the map is a review surface, not proof of prose superiority. | Repeat on fresh cases and have humans judge recovery, repairability, and update cost. |

## Best Evidence To Inspect

1. `examples/investigator_challenge/README.md`
2. `docs/submission/PROOF_BY_EXAMPLE.md`
3. `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`
4. `docs/evaluations/MATCHED_STRONG_MODEL_LHC_COMPARISON.md`
5. `docs/methodology/DECISION_SPACE_FRAMEWORK.md`

For the full artifact inventory, use `docs/submission/ARTIFACT_INDEX.md`. For review rather than judge orientation, use `docs/review/REVIEWER_START_HERE.md` and `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv`.

## Failure Modes

### The Map Can Preserve Too Much

Decision-space preservation is not maximum-detail retention. A map that preserves every distinction can overwhelm the reviewer. The current mitigation is prioritization through each case README, review packets, and task queues.

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
| Transfer is plausible but under-tested | Reviewers may accept that the artifact shape travels while still doubting that another operator can apply it well to a fresh case. | `docs/submission/GENERALIZABILITY_RED_TEAM.md` names suitable and unsuitable case shapes, gives a minimal portable workflow, and defines fresh-case and second-operator tests. | Complete one transfer test on a mundane contested case or record an independent second-operator review. |
| Full-case maps are broad scaffolds | Judges may want full source-excerpt-level maps, not just coverage scaffolds. | Every acquired LHC and eggs source is represented in a full-case index and map. | Add source-excerpt-level claims for every full-case cluster. |
| COVID slice is not a full COVID map | A narrow adversarial slice can be mistaken for an origins adjudication or full case study. | COVID artifacts are labeled as a Bayesian-disagreement worked region with a dedicated human audit packet. | Keep it as a worked region unless enough sources and review are added for a full COVID case. |
| Baselines are partly span-limited | A full-document or better-prompted baseline might preserve more structure. | Multi-model blinded baselines and full-case flat baselines make this limitation visible. | Have humans review the full-case baselines and add full-document model logs for paper-grade evidence. |
| File-based workflow | Less usable than an interactive knowledge-base tool. | Markdown and JSON exports are inspectable and reusable. | Build reviewer decision persistence only if provenance can be handled safely. |
| Static UI is inspection-only | Judges can browse the artifact more easily, but cannot edit or review inside the UI. | The UI links back to canonical Markdown/CSV review packets. | Add reviewer decision editing only if persistence and provenance can be handled safely. |
| Relation labels need domain review | Incorrect support/challenge/dependency labels can mislead reviewers. | Relation rationales and source excerpts are explicit. | Domain reviewers should assess relation correctness. |
| Extraction is not fully automated | Manual curation limits scale. | Deterministic scripts and prompt inventory make the process repeatable. | Add LLM extraction passes with reproducible prompt/model logging. |
| Decision-space framework may look like relabeling | Judges may see the project as ordinary provenance, argument mapping, or summarization faithfulness under new vocabulary. | `docs/submission/REFERENCE_LINEAGE.md` and `docs/methodology/DECISION_SPACE_FRAMEWORK.md` connect the terms to concrete artifacts and intervention points. | Test whether a reviewer can explain the mechanism chain after the five-minute path without coaching. |
| Evidence is not quantitative enough for a paper | The contest accepts prototypes, but a paper needs stronger evaluation. | Artifact counts, multi-model baselines, and audit packets provide a measurement scaffold. | Run human-reviewed evaluations across more tasks and models. |
| Draft extension region is not canonical | The public-risk framing map strengthens realism but is not yet fully wired into the validated worked-region pipeline. | It is explicitly labeled as a draft extension and linked from the judge path. | Promote it into the canonical validator set after human/source review. |

## Submission Boundary

This submission is best read as a working methodology and reference prototype. It demonstrates how to preserve and audit decision-relevant structure in two full-case scaffolds plus a narrow adversarial COVID worked region. It does not claim to be a complete epistemic stack, a fully automated literature-review system, a full COVID origins adjudication, or a replacement for expert judgment.
