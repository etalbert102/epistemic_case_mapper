# Generalizability Red Team

Status: `human-review-needed`

Purpose: make the generalizability claim easier to evaluate and harder to overread. This document states where the method appears portable, where that portability is still under-proven, and what evidence would move the submission from plausible generality to demonstrated generality.

## Bottom Line

The workflow is plausibly general across cases where the hard part is preserving decision-relevant structure: caveats, evidence-grade boundaries, dependencies, cruxes, live disagreements, and same-label-but-different-object distinctions.

The current package does not yet prove that a second operator can apply the workflow to an arbitrary new case with low variance. The strongest artifacts are curated worked regions, not randomly sampled case slices.

## Red-Team Objection

A skeptical reviewer can reasonably say:

> The method generalizes as a schema, but the repository mainly shows that a skilled curator can pick cases where mapping is useful and fill the map well.

That critique is fair. The submission has three differently shaped cases, but all three reward structure preservation:

- LHC black holes has explicit safety-argument dependencies.
- Eggs and health has study-design, endpoint, guideline, and subgroup distinctions.
- The COVID origins slice has explicit Bayesian disagreement and subargument boundaries.

Those are good stress tests for the proposed mechanism, but they are not enough to show that the method travels under ordinary operating conditions.

## Where The Method Should Travel

| Case shape | Why the mapper should help | Current evidence | Generalizability status |
| --- | --- | --- | --- |
| Closed technical risk argument | Safety depends on assumptions, caveats, and critique/response structure. | LHC cosmic-ray worked region preserves low-velocity trapping, compact-star scope, and Plaga/GM dispute structure. | Strongest demonstrated fit. |
| Messy health or policy evidence | Conclusions depend on endpoint fit, study design, population caveats, and evidence grade. | Eggs worked region separates CVD outcomes, lipid markers, guideline framing, and NNR limits. | Plausible demonstrated fit. |
| Adversarial live disagreement | Reviewers need to distinguish debate result, process critique, priors, subarguments, and updates. | COVID slice preserves Bayesian decomposition and minority disagreement without claiming full adjudication. | Useful stress test, but deliberately narrow. |
| Mundane contested decision | The method should show value without dramatic cruxes or unusually explicit arguments. | Not yet demonstrated. | Main missing transfer test. |
| Sparse or low-quality source environment | The method may expose source weakness, but cannot manufacture reliable structure. | Not yet demonstrated. | Likely limited fit. |
| Fast-moving current question | Stable IDs and update triggers should help, but source churn may dominate. | `docs/evaluations/investigator_challenge/NEW_SOURCE_UPDATE.md` shows one source-update pattern, not a live case. | Partial fit. |

## Failure Boundaries

The mapper is likely worth using when at least one of these is true:

- A conclusion depends on a caveat or scope limit that summaries often compress.
- Multiple sources use similar language for non-identical claims.
- Evidence types need to stay separate, such as outcomes, mechanisms, markers, forecasts, or guidelines.
- A critique/response pair changes whether a claim is merely asserted or technically answered.
- A future investigator needs to revise part of the reasoning without restarting from raw sources.

The mapper is likely not worth the overhead when:

- The question is a direct factual lookup with a stable answer.
- The source set is too thin to support relation labeling.
- The main bottleneck is source discovery, data access, or domain measurement, not synthesis.
- Relation labels would be mostly speculative.
- The reviewer only needs a quick orientation and will not reuse the artifact.

The method is actively risky if consumers treat `supports`, `challenges`, `depends_on`, or `crux_for` labels as reviewed conclusions when the artifact is still `human-review-needed`.

## Minimal Portable Workflow

This is the case-independent recipe the current artifacts instantiate:

1. Define the decision question and the intended review boundary.
2. Freeze a source subset for the worked region.
3. Extract source-grounded claims with source IDs, spans, excerpts, and review state.
4. Label relations only when the rationale can be stated and later checked.
5. Identify caveats, cruxes, missing perspectives, and update triggers.
6. Produce a flat synthesis from the same source subset.
7. Audit which decision-relevant distinctions survived, flattened, disappeared, or distorted.
8. Hand off a review packet where another investigator can accept, revise, reject, or flag claims and relations.

This workflow is intentionally narrower than "summarize the literature." It is a structure-preservation and review-handoff workflow.

## Fresh-Case Transfer Test

The best next generalizability test is one independently chosen mundane-but-contested case. The test should use a fixed time budget and report failures instead of selecting only successful regions.

Good candidate questions:

- Do classroom air purifiers reduce respiratory illness enough to justify school purchase?
- Do phone bans improve school learning outcomes?
- Does creatine meaningfully help older adults preserve muscle or cognition?
- Are gas stoves a meaningful childhood-asthma risk in ordinary households?
- Does remote work reduce productivity in knowledge-work teams?

Protocol:

1. Pick the question before inspecting which sources map cleanly.
2. Select a small source subset using ordinary search and record inclusion criteria.
3. Spend 60-90 minutes producing a first-pass map and flat baseline.
4. Record every relation that felt hard to label or not worth preserving.
5. Count at least three outcomes: useful preserved distinctions, mapping overhead, and reviewer confusion points.
6. Decide whether the method was better than a careful flat synthesis for that case.

Passing result: the map exposes at least one review-relevant distinction that the flat synthesis makes harder to inspect, and the overhead is acceptable for a future reviewer.

Failing result: the map adds bookkeeping without improving local revisability, or relation labels become too speculative to trust.

## Second-Operator Test

The strongest compact test of portability is not another polished example. It is a second operator using the method.

Recommended exercise:

1. Give a reviewer one source packet, one map, and the minimal workflow above.
2. Ask them to revise 10 claims and 10 relations without consulting the original curator.
3. Record accept, revise, reject, and needs-discussion decisions.
4. Compare where the reviewer disagrees with the original relation labels.
5. Record whether stable IDs made the review faster than prose-only notes.

Passing result: the reviewer can localize disagreements and improve the artifact without remapping the whole case.

Failing result: the reviewer cannot tell what each relation means, cannot locate the source support, or has to reconstruct the argument from scratch.

## What Would Strengthen The Transfer Claim

Current evidence makes transfer plausible, but it should be treated as demonstrated only after one of these additions:

- a completed fresh-case transfer test outside LHC, eggs, and COVID;
- a second-operator review log with actual accept/revise/reject decisions;
- a logged LLM extraction pass showing which parts of the workflow can be repeated without bespoke hand curation;
- a failed-case analysis showing where the method should not be used.

The last item matters because a method that names its failure boundary is more portable than one that claims universal applicability.

## Submission Implication

The generalizability claim should be phrased conservatively:

> The package demonstrates a portable artifact shape and a plausible workflow across three differently shaped cases. It does not yet prove low-variance application by other operators on arbitrary new cases.

That boundary strengthens the submission by making the remaining evidence gap visible rather than hidden.
