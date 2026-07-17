# Plan: Citation Carefulness

## Objective
Make memo citations more careful by binding each inline citation to the specific sentence-level claim it supports, while preserving the existing deterministic source normalization and source-list rendering.

## Current Gap
The pipeline already carries stable source IDs and builds a useful `CITATION_TRACE.md`, but the final memo can over-bundle citations. A source can be cited on a broad support sentence even when its actual role is boundary, counterweight, calibration, or context. Current validators catch unknown sources and quantity/source adjacency, but not whether a cited source supports the exact sentence in the right role.

## Non-Goals
- Do not add a new whole-memo model call.
- Do not replace deterministic source-list rendering.
- Do not introduce domain-specific egg/nutrition rules.
- Do not make the new gate blocking until it has enough calibration signal.

## Design Principles
- Use deterministic code for stable IDs, extraction of cited sentences, source lookup, and report generation.
- Use existing model judgment already present in source weighting, section packets, and evidence rows rather than adding a new citation model pass.
- Keep semantic decisions visible as warnings and trace rows instead of silently rewriting.
- Prefer role-aware guidance before synthesis and role-aware audit after synthesis.
- Generalize around citation roles and claim support, not around this case's sources.

## Workstreams
1. Citation-role atoms
   - Purpose: create citeable atoms that encode what a source may be used for.
   - Changes: extend source-bound atoms with `citation_role`, `use_for`, and `do_not_use_for` derived from existing evidence/source-weight fields.
   - Artifacts: atoms inside section packets and memo-ready reports.
   - Validation: unit tests for support/boundary/calibration/context role derivation.

2. Writer-facing section notes
   - Purpose: make the model cite with role discipline before prose generation.
   - Changes: render required evidence notes with role/use-limit language and a positive citation policy.
   - Artifacts: section markdown prompt notes.
   - Validation: prompt-rendering tests assert role-specific citation guidance appears.

3. Sentence-level citation audit
   - Purpose: detect over-bundling, role mismatch, unsupported citation, and quantity misbinding.
   - Changes: add a report under source binding that extracts cited sentences and compares citations to packet atoms and source judgments.
   - Artifacts: `citation_care_report` nested in `source_binding_report`.
   - Validation: tests for role mismatch and over-bundled citation warnings.

4. Citation trace upgrade
   - Purpose: let a reader understand why a cited source appears in a sentence.
   - Changes: include role-aware source use and matching packet evidence next to citation contexts in `CITATION_TRACE.md`.
   - Artifacts: richer trace markdown.
   - Validation: presentation test for role/use lines in trace.

## Execution Order
1. Record this plan.
2. Add citation-role atom construction and tests; commit.
3. Add writer-facing role notes and tests; commit.
4. Add citation-care audit and retention integration; commit.
5. Upgrade citation trace; commit.
6. Run focused tests and inspect the latest memo report on saved artifacts.

## Acceptance Criteria
- Existing source ID normalization and deterministic source list still pass tests.
- Section prompts expose role-aware citation guidance without adding brittle domain vocabulary.
- `source_binding_report` includes citation-care warnings for a sentence that cites support and boundary sources together.
- Quantity/source adjacency behavior remains intact.
- Citation trace shows source role/use limits next to memo citation contexts.

## Red-Team Checks
- False positive risk: broad synthesis sentences may legitimately cite multiple roles. Mitigation: report warnings, not blocking failures.
- False negative risk: lexical matching may miss paraphrase. Mitigation: role mismatch and over-bundling checks do not depend on exact text matching.
- Context pollution risk: section notes may become too verbose. Mitigation: compact atom fields and bounded lists.
- Generalizability risk: role derivation could depend on local labels. Mitigation: map generic fields such as `main_use`, `reader_evidence_role`, `quantity_role`, and section role contracts into broad citation roles.

## Completion Audit
- Plan file committed.
- Each slice committed after focused verification.
- Final status includes tests run, reports changed, and remaining warnings if any.
