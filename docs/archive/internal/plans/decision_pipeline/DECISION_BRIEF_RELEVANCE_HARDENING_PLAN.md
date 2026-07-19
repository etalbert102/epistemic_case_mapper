# Plan: Harden Decision-Relevance Mapping And Briefing

## Objective
Make the source-to-map-to-brief pipeline produce decision-support memos whose main answer is driven by source-grounded, question-relevant evidence. The target is not smoother prose alone: the map must exclude boilerplate, distinguish out-of-scope evidence, expose enough relations to support synthesis, and make validation failures visible before a polished memo is produced.

## Current Gap
The latest full eggs run exposed six general failure classes:

- deterministic concept-gap backfill can admit navigation, footer, policy, or metadata text as evidence;
- weak lexical question-fit lets wrong-population evidence enter the main answer;
- evidence slots can be filled by structurally invalid values, such as person-time standing in for population;
- relation construction can leave a large prioritized map with only a few accepted edges;
- validators can score a memo as clean while the memo relies on wrong-scope evidence;
- final prose can repeat inventory-like evidence because the upstream map lacks a compact argument board.

## Non-Goals
- Do not add domain-specific egg, cholesterol, or HEPA hacks.
- Do not expand source collection. The prototype assumes the user provides documents.
- Do not replace source-grounding checks with prose rewrite prompts.
- Do not make model calls responsible for schema validity or obvious non-evidence filtering.

## Design Principles
- Deterministic code should own source hygiene, schema validity, impossible slot rejection, graph sufficiency thresholds, and telemetry.
- LLMs should own bounded semantic judgment, relation classification, section synthesis, and awkward-language edits.
- Classical/statistical methods should help with ranking, diversity, relation-candidate selection, and duplicate suppression.
- Every filter must emit inspectable reasons so future runs can diagnose lost coverage versus improved precision.
- Report-only warnings are acceptable for calibrated quality signals; invalid claims and boilerplate evidence should be blocking.
- Generalize by detecting evidence structure and question fit, not by naming the current case.

## Workstreams

1. Source Hygiene And Backfill Admission
   - Add a shared non-evidence classifier for boilerplate, navigation/footer rows, metadata rows, MeSH/list-only rows, and low-predicate fragments.
   - Use it in fallback extraction, concept-gap backfill, and relation-pair selection.
   - Emit rejected backfill candidates with source/span/reason.

2. Question-Fit Evidence Cards
   - Add deterministic population, endpoint, and overall question-fit fields to evidence cards.
   - Penalize wrong-population evidence and route it away from top-line/practical sections.
   - Preserve out-of-scope evidence only as caveat or appendix material.

3. Slot Admission Hardening
   - Reject structurally invalid slot fills: person-time as population, source titles as outcome, policy/footer rows as recommendations, and method-only rows as decision advice.
   - Surface rejected slot candidates in telemetry where practical.

4. Relation Graph Sufficiency
   - Add deterministic relation backfill when model-classified relations are too sparse for the number of usable claims.
   - Keep fallback edges low-confidence and review-marked.
   - Warn when relation-to-claim coverage is too low.

5. Validation And Quality Telemetry
   - Add briefing validators for wrong-scope evidence, sparse relations, appendix-only top-line evidence, and map-quality caps.
   - Ensure memo quality scores cannot look perfect when upstream map artifacts are structurally weak.

## Execution Order
1. Implement source hygiene and regression tests for the observed boilerplate failures.
2. Add question-fit metadata and slot gates, then test the adult-versus-child and person-time cases.
3. Add relation densification and graph-sufficiency warnings.
4. Upgrade memo validation and quality scoring.
5. Run unit tests, maintainability gate, and at least one full eggs rerun.

## Acceptance Criteria
- `Privacy Policy`, `Nutrition Policy*`, official-site security text, DOI/PMID rows, and MeSH-only/list-only rows cannot become backfilled evidence claims.
- Adult decision questions do not treat infant/toddler/child-only evidence as top-line support.
- Person-years and sample-size-only descriptions cannot fill default-population slots.
- Maps with many claims and very few relations receive an explicit graph-sufficiency warning.
- Briefing validation surfaces scope/relevance problems instead of scoring them as clean.
- The full test suite and maintainability gate pass.

## Red-Team Checks
- A new non-health case with policy documents should not reject substantive policy recommendations just because they contain the word `policy`.
- A pediatric decision question should not reject child evidence merely because child terms are present.
- Deterministic fallback relations should improve graph inspectability without pretending to be high-confidence model judgments.
- Validators should not require every case to have the same evidence families; they should warn about structural weakness, not enforce one domain template.

## Completion Audit
Record implementation commits, verification commands, and a before/after note for the full-run artifact that motivated this plan.
