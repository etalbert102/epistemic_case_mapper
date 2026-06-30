# FLF Judging Rubric

Source: user-provided contest judging criteria, recorded 2026-06-30.

This document records the scoring dimensions and prize-tier guidance that should guide the `epistemic_case_mapper` submission. It complements `docs/reference/flf_epistemic_case_study_competition_criteria.md`, which records the broader contest framing and case-study setup.

## Scoring Dimensions

Strong submissions do not need to land well on every dimension. A deep contribution on a few can still win the top tier, but submissions should plausibly engage most dimensions.

### 1. Epistemic Uplift

Does this actually help a thoughtful person reason better about the case?

- Meaningfully better than off-the-shelf deep research or a top-of-range Claude Code investigation on the same sub-questions.
- Faithful to evidence; does not sand off uncertainty or smuggle in unsupported confidence.
- Makes load-bearing evidence visible: which pieces are driving the conclusion, and which claims or evidence are getting unearned or insufficient weight?
- Surfaces what matters: cruxes, missing perspectives, and rhetorical-vs-evidential moves.

### 2. Generalizability

Will the workflow travel?

- Works across cases of different shape, such as curated debate, confident answer with complex evidence, and mundane-but-contested questions.
- Plausibly applies to cases beyond the three provided case studies.
- Is not narrowly overfit to the provided case studies.

### 3. Compounding And Shareability

Do the artifacts produced help future investigators build on this work?

- Outputs are structured and interrogable, not just narrative summaries.
- Another team could pick up the artifact and extend it.
- Pieces could plausibly interoperate with other submissions' pieces.

### 4. Scalability

Does the approach get better with more compute, better models, or more contributors?

- Not bottlenecked on any single hand-designed human step.
- Benefits as base-model capability rises.
- Benefits from increased resources: more adversarial scrutiny, incremental sources, and more effort or compute spent on checks.

### 5. Methodological Transparency

Is the submission well-specified enough to evaluate, replicate, and critique?

- The spec or workflow is written down, with key decisions and tradeoffs called out.
- Where the creator is uncertain, that uncertainty is named rather than papered over.
- A judge can tell why the methodology is shaped this way, not just what it does.

### 6. Adversarial Robustness

How well do the artifacts and methodology hold up when participants and consumers have differing views and priorities?

- Outputs withstand motivated reading and downstream-model interrogation.
- The methodology resists being gamed by sources optimizing to mislead.
- Failure modes and uncertainties are named and bounded, not hidden.

### 7. Insight Contribution

Does the submission shift how judges think about the problem itself?

- Surfaces sub-problems, framings, or considerations judges had missed.
- Offers critiques that force re-evaluation of promising approaches, especially with potent counterexamples.
- Provides comparative analyses that surface non-obvious tradeoffs or difficult choices across methodologies.

## Prize Tiers

Prize tiers are guidance, not a formula; final decisions remain at judges' discretion.

| Tier | Range | Looks like |
| --- | --- | --- |
| Transformative | $35k-$50k | Substantial advance on the state of the art. Reshapes how the next generation of this tooling should be built. Could be a single deep contribution or a broader push across several dimensions. |
| Strong | $15k-$35k | Notable improvement on the state of the art. Either a meaningful gain across several dimensions or a clearly impressive gain on one. |
| Promising | $5k-$15k | A real but mild improvement on the state of the art, or a partial/exploratory contribution containing insight or working components judges would want to build on. |

Multiple prizes may be awarded per tier. The pool can expand for a wave of strong work, and strong submissions may lead to offers of further funded work.

## Notes For Judges

- Anchor against good baselines. Before scoring, check what off-the-shelf deep research or a careful Claude Code investigation produces on the same sub-question. The bar is "meaningfully better than that."
- Read for the spec, not the polish. A clear workflow with a rough prototype usually beats a polished prototype with opaque methodology.
- Run it, don't just read it. For tool and workflow submissions, exercise the methodology on a sub-question you are personally curious about; usefulness shows up in use, not only in the writeup.

## Implications For This Repo

The submission should make the seven dimensions easy to inspect:

1. Epistemic uplift: lead with the LHC dependency example and the erosion audit.
2. Generalizability: show LHC, eggs, and the narrow COVID slice as differently shaped cases.
3. Compounding and shareability: emphasize stable IDs, Markdown/JSON maps, review packets, and task queues.
4. Scalability: distinguish current curated maps from future LLM extraction and multi-reviewer expansion.
5. Methodological transparency: keep workflow, prompts, validators, limitations, and uncertainty visible.
6. Adversarial robustness: foreground blinded baselines, failure modes, and human-review-needed status.
7. Insight contribution: frame decision-space erosion as the contribution, especially the claim that broad correctness can still erase reviewable structure.
