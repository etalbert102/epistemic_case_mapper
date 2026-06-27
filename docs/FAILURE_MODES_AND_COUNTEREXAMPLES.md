# Failure Modes And Counterexamples

Status: `human-review-needed`

Purpose: make the prototype more credible by identifying places where the method can fail or where the current evidence is weaker than the headline claim.

## Failure Mode 1: The Map Can Preserve Too Much

Decision-space preservation is not the same as maximum-detail retention. A map that preserves every distinction can overwhelm the reviewer and make the decision surface harder to inspect.

Current example: the LHC worked region preserves Earth exposure, solar exposure, white-dwarf scope, neutron-star scope, trapping, Plaga's critique, and GM's response. That is useful, but a reviewer still needs prioritization. The task queue and best-region files are the current mitigation.

Review question: which preserved distinctions actually change the decision, and which are merely interesting context?

## Failure Mode 2: Relation Labels Can Smuggle Interpretation

The claim text may be source-grounded while the relation type is contestable. A `supports`, `challenges`, `depends_on`, or `crux_for` label can overstate the inferential role of a claim.

Current example: LHC relations around Plaga and GM are useful, but a domain reviewer should decide whether the GM response fully answers Plaga's strongest stopping/cross-section challenge or only narrows it.

Mitigation: every relation has a rationale and remains `human-review-needed`.

## Failure Mode 3: Better Flat Synthesis Can Reduce The Apparent Gap

The prototype should not imply that all summaries fail. Stronger models and better prompts can preserve more detail.

Current example: `docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md` notes that some local baselines preserve more of the eggs study-design split than the initial illustrative baseline. That narrows the eggs claim: the robust problem is not that flat synthesis always loses endpoints, but that preservation is brittle and not easily inspectable.

Mitigation: the before/after comparison states that the contribution is an audit surface, not a blanket indictment of summarization.

## Failure Mode 4: Source Selection Can Dominate The Result

If the source subset is biased, a highly faithful map can still produce a misleading decision surface.

Current example: LHC worked-region evidence is strongest around the cosmic-ray and compact-star argument. It does not fully represent legal, public legitimacy, or operational governance questions until the draft public-risk region is reviewed.

Mitigation: full-case source inventories and source-independence metadata expose what is included and what remains outside each worked region.

## Failure Mode 5: Human Review Can Become A Rubber Stamp

Review packets can look rigorous while reviewers only skim. The method needs explicit accept/reject/revise decisions tied to claims and relations.

Current mitigation: CSV checklists require item-level decisions, but no completed external review has been recorded yet.

## Counterexample The Submission Should Survive

A judge might produce a careful full-case synthesis that explicitly names the main caveats, tensions, and cruxes. That would weaken the claim that flat prose necessarily erodes decision space.

The prototype should answer: even in that case, the structured map still helps because later investigators can inspect, update, and dispute individual claims and relations without reverse-engineering a paragraph.

## Submission Boundary

The submission should claim that structured preservation makes decision-space loss visible and auditable. It should not claim that the current maps are final truth, that summaries are useless, or that the prototype replaces expert judgment.
