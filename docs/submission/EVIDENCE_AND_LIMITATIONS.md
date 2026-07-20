# Evidence And Limitations

Status: `human-review-needed`

Purpose: show where the evidence is strongest, where the prototype is still thin, and which conclusions remain unsupported.

## Summary

The project is strongest as a methodology plus runnable reference prototype for preserving operational judgment during AI-assisted investigation. It is not a finished epistemic stack or a human-validated knowledge base.

The central claim is that AI-assisted workflows can lose reasoning structure during retrieval, claim normalization, mapping, and synthesis even when the final answer is broadly useful. That becomes decision-space erosion when a decision-relevant option, interpretation, evidence path, caveat, or review boundary becomes materially less visible or recoverable before accountable review. The prototype does not claim that all summaries fail. It claims that preservation is brittle and hard to audit unless the structure is made explicit.

## Evidence Boundary

Demonstrated:

- The source-grounded LHC and seven-source eggs worked-region maps preserve dependencies, caveats, and review handles that flat syntheses can compress; the COVID region is a separate `seed`-mode format stress test.
- A 50-source eggs run preserves the exact generated map and fail-closed memo evidence, demonstrating scale handling while exposing a sparse active relation graph and unresolved generation defects.
- The investigator challenge shows that frozen answer-key objects are directly addressable in map artifacts.
- Frozen-snapshot restoration and a prewritten source-delta replay preserve stable IDs for unaffected map objects.
- The package demonstrates artifact fidelity across Markdown, JSON, review packets, snapshot restoration, and update ledgers.

Plausible but under-tested:

- The same artifacts will improve multi-investigator handoff.
- The same method will transfer to fresh cases without author selection.
- More complete review logs will make expert disagreement easier to adjudicate.

Not established:

- The current prototype consistently beats strong models on final prose quality.
- The artifacts are domain-correct without human review.
- The challenge is a statistically powered benchmark.
- The challenge measures investigator discovery, semantic repair, or autonomous source integration.

## Evidence Ledger

This table connects each proposed conclusion to its evidence, remaining gap, and next useful test.

| Evidence area | What the package shows | Boundary | Stronger next check |
| --- | --- | --- | --- |
| Concrete reasoning gain | `docs/submission/PROOF_BY_EXAMPLE.md`, worked maps, scripted blinded baselines, and the multi-model audit show distinctions that model prose can preserve unevenly: LHC velocity/trapping dependencies, eggs evidence-role boundaries, and COVID disagreement structure. | The comparison against off-the-shelf deep research and top-range coding agents is still mostly qualitative. | Compare the map workflow against a fresh deep-research baseline on the same sub-question. |
| Transfer across case shapes | LHC black-hole risk, eggs/health, and a narrow COVID origins slice differ by closure, controversy, evidence type, and adversarial pressure. `docs/submission/GENERALIZABILITY_RED_TEAM.md` now names failure boundaries and transfer-test criteria. | The strongest maps are still author-selected worked regions rather than randomly sampled case slices, and no second operator has applied the method independently. | Run one fresh-case transfer test outside the current set, or have a second reviewer revise 10 claims and 10 relations while recording accept/revise/reject decisions. |
| Reusable artifacts | Stable source IDs, claim IDs, relation IDs, Markdown/JSON exports, review packets, and task queues let another investigator inspect or extend local pieces. | Multi-reviewer merge and conflict-resolution workflow is specified but not implemented. | Have a second reviewer revise one map while preserving IDs and recording accept/revise/reject decisions. |
| Framework integration | `docs/methodology/DECISION_SPACE_FRAMEWORK.md` maps retrieval-gated reasoning, claim normalization, decision-space construction, judgment anchors, artifact fidelity, and auditable authority onto concrete project artifacts. | The current integration is strongest as an artifact audit; the UI does not yet persist reviewer interventions. | Run a reviewer session and verify that accept/revise/reject decisions propagate through regenerated artifacts. |
| Ability to absorb more work | Validators, schema, prompt inventory, source manifests, and JSON exports can accept more sources, claims, relations, and model passes. | Extraction and relation labeling are still curated; the current strongest artifact depends on careful human/agent curation. | Run a logged LLM extraction pass and compare it against the curated maps for recall, precision, and review cost. |
| Live model behavior | `examples/live_model_runs/` preserves a valid-with-review eggs map and a rejected LHC map from `ollama:gemma4:12b-mlx`, including prompt/raw transcripts, repair records, and quality diagnostics. | One run succeeded with review risks and one failed; this is operational evidence, not a reliability estimate or human quality score. | Repeat on unseen regions and measure candidate acceptance, repair cost, and claim/relation precision against independent review. |
| Inspectable method | Workflow docs, prompt inventory, validators, source manifests, audit notes, and `human-review-needed` status make design choices and uncertainty visible. | Some source-fidelity and relation-correctness judgments are still embedded in curated Markdown rather than independently reviewed. | Add a completed review log that shows which claims, relations, and losses were accepted, revised, or rejected. |
| Stress under disagreement | Erosion audits, blinded local-model baselines, multi-model baseline audit, failure-mode discussion, and narrow COVID stress test expose where flat synthesis is brittle. | No external adversarial review has tried to break the maps or source selections. | Ask a motivated reviewer to challenge one worked region and record whether the map helps localize disagreement. |
| Framing contribution | Broad correctness is not enough: a synthesis can be right while losing the reviewable structure needed for compounding epistemic work. `docs/submission/REFERENCE_LINEAGE.md` ties this to examples involving measurement, construct validity, systems safety, and structured analysis. `docs/methodology/DECISION_SPACE_FRAMEWORK.md` maps the broader decision-space framework onto project artifacts. | The framing may still look like provenance or argument mapping unless the mechanism chain and LHC one-minute example are persuasive. | Ask an external reviewer whether the framework clarifies the project or merely adds terminology to argument mapping. |
| Matched strong-model boundary | `docs/evaluations/MATCHED_STRONG_MODEL_LHC_COMPARISON.md` records a response that recovers much of the LHC dependency chain when instructed to use the same source universe. | The invocation transcript was not retained, so this is a reported claim-boundary illustration rather than auditable performance evidence. | Repeat on fresh cases with retained invocation records and have humans judge recovery, repairability, and update cost. |

## Best Evidence To Inspect

1. [LHC worked map](../../examples/lhc_black_holes/worked_region_cosmic_ray_map.md)
2. [Substantive eggs map](../../examples/eggs/worked_region_observational_vs_rct_map.md)
3. [Fifty-source eggs stress run](../../examples/eggs_large_source_stress/README.md)
4. [Proof by example](PROOF_BY_EXAMPLE.md)
5. [Investigator challenge](../../examples/investigator_challenge/README.md)

For the full artifact inventory, use `docs/submission/ARTIFACT_INDEX.md`. For item-level review, use `docs/review/REVIEWER_START_HERE.md` and `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv`.

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
| Full-case maps are broad scaffolds | Coverage indexes may be mistaken for source-excerpt-level maps. | Every acquired LHC and eggs source is represented in a full-case index and map. | Add source-excerpt-level claims for every full-case cluster. |
| COVID slice is not a full COVID map | A narrow adversarial slice can be mistaken for an origins adjudication or full case study. | COVID artifacts are labeled as a Bayesian-disagreement worked region with a dedicated human audit packet. | Keep it as a worked region unless enough sources and review are added for a full COVID case. |
| Baselines are partly span-limited | A full-document or better-prompted baseline might preserve more structure. | Multi-model blinded baselines and full-case flat baselines make this limitation visible. | Have humans review the full-case baselines and add full-document model logs for paper-grade evidence. |
| File-based workflow | Less usable than an interactive knowledge-base tool. | Markdown and JSON exports are inspectable and reusable. | Build reviewer decision persistence only if provenance can be handled safely. |
| Static UI is inspection-only | Readers can browse the artifact more easily, but cannot edit or review inside the UI. | The UI links back to canonical Markdown/CSV review packets. | Add reviewer decision editing only if persistence and provenance can be handled safely. |
| Relation labels need domain review | Incorrect support/challenge/dependency labels can mislead reviewers. | Relation rationales and source excerpts are explicit. | Domain reviewers should assess relation correctness. |
| Extraction is not fully automated | Manual curation limits scale. | Deterministic scripts and prompt inventory make the process repeatable. | Add LLM extraction passes with reproducible prompt/model logging. |
| Decision-space framework may look like relabeling | The project may appear to be ordinary provenance, argument mapping, or summarization faithfulness under new vocabulary. | `docs/submission/REFERENCE_LINEAGE.md` and `docs/methodology/DECISION_SPACE_FRAMEWORK.md` connect the terms to concrete artifacts and intervention points. | Test whether a reviewer can explain the mechanism chain after the five-minute path without coaching. |
| Evidence is not quantitative enough for a paper | A paper would require stronger evaluation than the current prototype evidence. | Artifact counts, multi-model baselines, and audit packets provide a measurement scaffold. | Run human-reviewed evaluations across more tasks and models. |
| Draft extension region is not canonical | The public-risk framing map strengthens realism but is not yet fully wired into the validated worked-region pipeline. | It is explicitly labeled as a draft extension and linked from the review path. | Promote it into the canonical validator set after human/source review. |

## Current Boundary

This is a working methodology and reference prototype. It demonstrates how to preserve and audit decision-relevant structure in two full-case scaffolds plus a narrow adversarial COVID worked region. It is not a complete epistemic stack, a fully automated literature-review system, a full COVID origins adjudication, or a replacement for expert judgment.
