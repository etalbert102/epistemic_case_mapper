# FLF Submission Strategy

## Positioning

This repo is the competition-facing prototype for the FLF epistemic case study competition. It should be separated from `decision_space_harness`:

- `decision_space_harness` remains the paper and benchmark repo for measuring decision-space erosion under controlled tasks.
- `epistemic_case_mapper` becomes the runnable workflow, artifact format, and worked-example package for real epistemic case studies.

The submission should present decision-space erosion as the central failure mode: ordinary synthesis can preserve fluency while losing the live structure of the investigation. The proposed remedy is to keep claims, provenance, relations, cruxes, caveats, and missing perspectives as first-class objects.

## High ROI Submission Shape

The strongest near-term submission is not a fully polished product. It is a clear methodology plus a runnable reference implementation that demonstrates:

1. Ingestion: sources are converted into attributed claims and useful metadata.
2. Structure: related claims, support/challenge relations, dependencies, cruxes, and tensions are preserved.
3. Assessment: the workflow surfaces what to inspect next, what is missing, and where confidence should remain conditional.
4. Compounding: outputs are reusable JSON/Markdown artifacts that another investigator can audit, extend, or merge.

## Demonstration Plan

Primary worked examples:

- LHC black holes: a mostly closed technical-risk case that stresses dependency mapping and weakest-link analysis.
- Eggs and health: a messy everyday evidence case that stresses population heterogeneity, study design, and conflicting advice.

Optional stretch example:

- COVID origins slice: use a narrow, well-bounded slice only if there is enough time to avoid superficial handling.

## What To Show Judges

- A compact workflow spec.
- A small schema that is easy to inspect.
- Runnable code that builds a starter map from a case manifest.
- A worked report for at least two cases.
- A before/after example showing how flat synthesis loses options, caveats, or disagreement structure.
- Audit notes that make uncertainty explicit instead of hiding it in prose.

## Near-Term Milestones

1. Populate two case manifests with real source material and source-local excerpts.
2. Replace the deterministic starter mapper with an LLM-assisted extraction pass.
3. Add a relation-building pass for similar, supporting, challenging, dependent, and crux claims.
4. Add a human audit workflow that reviews claims and relations independently.
5. Produce two navigable worked examples and a short submission narrative.

## Paper Connection

The paper can develop the scientific claim later: decision-space erosion is a measurable failure mode of synthesis, and structured preservation interventions reduce it. The FLF prototype should be the practical demonstration that the same idea helps real investigators reason better now.
