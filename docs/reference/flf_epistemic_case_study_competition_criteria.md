# FLF Epistemic Case Study Competition Criteria

Source: user-provided copy of the FLF competition page, dated June 4, 2026.

This document records the competition requirements and evaluation criteria that should guide the `epistemic_case_mapper` prototype.

For the newer detailed seven-dimension judging rubric and prize-tier guidance, see `docs/reference/flf_judging_rubric.md`.

## Competition Summary

FLF is running a competition for workflows and methodologies that use AI to produce reliable, trustworthy knowledge bases grounded in real-world cases. The competition emphasizes reusable, refinable, structured analyses that can survive scrutiny and support future investigations.

Prize range:

- Approximately $200k total prize pool.
- $5k to $50k for winning submissions.
- Multiple $50k prizes are possible.
- Strong winners may be offered further funded work.

Submission deadline:

- Entries are due July 19, 2026.
- Optional early feedback deadline was June 21, 2026.

## Core Problem Framing

FLF is interested in the gap between impressive human epistemic investigations and current AI-assisted knowledge-base workflows.

Current AI-assisted knowledge-base tools show useful pieces, such as agent memory, personal wikis, and deep research tools. The competition identifies a limitation: these often produce single-user artifacts tuned to one investigator's context rather than artifacts that travel, combine, and survive scrutiny.

The central opportunity is compounding epistemic work:

- Preserve relations between sources, claims, authors, evidence, reasons, doubts, and counterarguments.
- Keep structure alive so less is lost by compression.
- Preserve space for nuance even when it is not immediately consumed.
- Produce reusable artifacts that future investigators can refine and extend.

## Required Case Studies

The competition provides three challenge cases:

1. COVID-19 origins.
   - Debated, adversarial, high-stakes, and still evolving.
   - Rich starting material includes a judged debate, judge decisions, Bayesian analyses, Rootclaim response, videos, and comment threads.
   - Useful stress test for transparent, traversable, updateable, and trustworthy reasoning.

2. LHC black hole risk.
   - Mostly closed and uncontested technical-risk case.
   - Useful for probing dependencies, key considerations, and weakest or most speculative points.
   - Should make complex accumulated knowledge accessible.

3. Eggs and health.
   - Vague, open-ended, everyday evidence case.
   - Useful for surfacing methods of knowing, population heterogeneity, and what questions matter.

The tooling should generalize beyond these cases, because judges may assess against other difficult case studies.

## Stack Layers

FLF frames epistemic investigations as three interacting layers: ingestion, structure, and assessment.

### Ingestion

Question: How do you take a messy, multi-source evidence base and turn it into something structured enough to reason over?

Desired capabilities:

- Extract and attribute claims to specific sources.
- Preserve provenance metadata: who said what, when, and in what context.
- Identify when the same claim appears across multiple sources in different forms.
- Search for resources bearing on topics and subtopics.
- Capture useful metadata tags, including:
  - topics,
  - source relationships,
  - methodologies,
  - deference,
  - assumptions.

### Structure

Question: How do you document relationships between claims so the full shape of the argument becomes navigable?

Desired capabilities:

- Resolve inference structure: which claims and evidence support which other claims.
- Represent discourse structure: sub-questions, implicit and explicit differences of emphasis, and how parts of the debate relate to the overall inquiry.
- Capture similar-but-not-identical claims, including differences in framing, caveats, conditions, estimates, and uncertainty.
- Track how structure evolves over time.

### Assessment

Question: How do you evaluate what to believe or what to inspect next given the structured evidence base?

Desired capabilities:

- Identify rhetorical moves that carry more persuasive weight than evidential weight.
- Flag correlated evidence being treated as independent.
- Identify cruxes: factual or inferential disagreements that would most change the overall picture if resolved.
- Surface missing sources, perspectives, or primary information.
- Provide confidence-calibration frameworks that account for:
  - out-of-model error,
  - adversarial information environments,
  - limits of any single analyst's expertise.
- Distinguish what a debate settled from what it merely performed settling.

## Good Entry Shapes

FLF is open to multiple submission shapes. Strong entries may combine them.

### Workflow Spec

A step-by-step human-AI workflow for producing structured epistemic analysis of a complex dispute.

Requirements:

- Demonstrate on multiple parts of at least two cases.
- Allow human steering and subjective judgments where appropriate.
- Let others with different beliefs or preferences usefully pick up where another investigator left off.
- Scale gracefully toward mostly or entirely hands-free operation.
- Make design uncertainty and tradeoffs transparent.

### Prototype Tool

A runnable pipeline, likely involving LLMs, that implements one or more layers of the stack.

Requirements:

- Demonstrate repeatably on each case study or a defensible subset.
- Substantially accelerate investigation.
- Ideally produce reusable, shareable knowledge artifacts.
- Ideally stand up to adversarial pressure.

### Protocol

An artifact format or protocol enabling interoperability and compounding without flattening underlying material.

Requirements:

- Demonstrate with reference to the competition cases.
- Navigate the tension between interoperability and nuance.
- Link diverse subtopics and complex, multi-perspective investigations.
- Preserve important detail.
- Be maintainable over time as sources, users, and AI capabilities change.

### Stepping-Stone Alternatives

Potentially valuable but less likely to win top prizes without follow-up:

- A repeatable comparative analysis applying two or more AI assessment methodologies to the same questions.
- A critique with counterexamples showing weaknesses in a promising approach.

## Judge-Facing Questions

FLF highlights four core judging questions:

1. Would this actually help someone reason better about this case?
2. Does it generalize?
3. Does it scale with improvements to AI or more compute?
4. Does it compound, with multiple people or teams building on each other's work?

## Prize Criteria

### $50k Level

An entry may be prizeworthy at the highest level if it:

- Is truly inspiring to FLF.
- Changes how the judges think about the problem.
- Could become a new reference point for AI-assisted epistemic work.
- Produces artifacts or methods judges would want others to use.

### $5k to $50k Level

An entry may receive a smaller prize if it:

- Meaningfully advances the state of the art.
- Advances the full stack or a well-defined layer such as ingestion, structure, or assessment.
- Demonstrates faithful, scalable AI-assisted investigation.

### Continuation Funding

Strong entries may lead to further funded work, especially if they show promise for forecasting, prediction, or broader epistemic infrastructure.

## Submission Constraints And Preferences

- Written discussion should aim to stay under 10 pages, excluding appendix-like material and worked examples.
- Worked examples and knowledge bases can be larger if they remain navigable.
- Code should be brief, legible, well documented, and close to one-click install/run.
- Curated pointers to especially effective worked-example regions are encouraged.

## Implications For This Repo

The `epistemic_case_mapper` repo should optimize for:

1. A crisp protocol and workflow rather than a broad product.
2. Two strong worked examples first: LHC black holes and eggs.
3. A narrow COVID origins slice only if it can be handled with enough rigor.
4. Artifacts that preserve source provenance, claims, similar-but-not-identical variants, support/challenge relations, cruxes, caveats, missing perspectives, and audit notes.
5. A repeatable pipeline that shows how AI helps without hiding where human judgment enters.
6. A judge-facing report that makes the artifact navigable quickly.

## Alignment With Decision-Space Erosion

The competition's concern with structure loss maps directly onto decision-space erosion.

Relevant erosion risks:

- Synthesis compresses away live alternatives.
- Similar but non-identical claims are merged too aggressively.
- Discourse structure is flattened into a single narrative.
- Correlated evidence is counted as independent.
- Cruxes and caveats are omitted.
- Missing perspectives are hidden by confident prose.

The prototype should show that structured epistemic maps reduce these risks by keeping the investigator's live decision space explicit, inspectable, and reusable.
