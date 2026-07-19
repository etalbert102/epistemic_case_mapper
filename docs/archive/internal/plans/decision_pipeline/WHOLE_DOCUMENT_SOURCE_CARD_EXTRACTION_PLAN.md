# Plan: Whole-Document Source-Card Extraction

## Objective
Make whole-document source-card extraction the primary staged-map claim extraction path. The target end state is that a user can provide documents plus a decision question, and the mapper asks the model to read each source as a source-level unit, return a compact set of canonical decision-relevant claims, repair common schema drift, and preserve exact source anchoring for downstream map and briefing synthesis.

## Current Gap
Chunk-level extraction was reliable for schema control, but it encouraged fragmented claims, duplicate local observations, and weak source-level salience. Live probes showed that whole-document extraction produced better canonical claims, but first-pass model output often used nearby schemas such as top-level `claims` or bare arrays. The switch therefore needs a repair/normalization layer and deterministic quote validation rather than trusting a single strict model pass.

## Non-Goals
- Remove the legacy chunk extractors once whole-document extraction is the only intended path.
- Do not use deterministic fallback claims for whole-document extraction; emit warnings and rejected records instead.
- Do not overfit extraction prompts to the eggs case or any specific domain vocabulary.
- Do not make final synthesis depend on raw unvalidated model claims.

## Design Principles
- Use the model for semantic salience: reading an entire source, choosing canonical claims, and rating decision importance.
- Use deterministic code for schema repair boundaries, exact quote validation, IDs, progress records, cache paths, and rejection accounting.
- Keep whole-document extraction as an interchangeable backend option, not a special case spread through the runner.
- Preserve inspectable artifacts: prompts, raw outputs, repair outputs, canonical payloads, reports, and accepted/rejected claims.
- Keep legacy chunk extraction available and explicitly selectable.

## Workstreams
1. Whole-document source-card adapter
   - Purpose: Add a reusable model-facing extractor for one whole source document.
   - Changes: Prompt with the decision question, full numbered source text, source-card schema, and compact canonical-claim instructions.
   - Artifacts: Per-source prompt, raw output, repair prompt/output, canonical payload, extraction report.
   - Validation: Unit tests cover schema repair, exact quote anchoring, role normalization, and cache/report behavior.
   - Risks: Long documents may exceed backend context; this should fail visibly with backend errors rather than silently fabricating claims.

2. Pipeline integration
   - Purpose: Make source-card extraction the only staged claim extraction path.
   - Changes: The CLI no longer exposes extractor selection; staged runner calls the whole-document adapter directly; stress harness records `claim_extraction_method`.
   - Artifacts: `claim_sources/` outputs for all staged runs.
   - Validation: Regression tests exercise source-card extraction and no longer pin legacy chunk extractors.
   - Risks: Fake-model tests can accidentally emit obsolete chunk-claim payloads; tests should return source-card-shaped JSON.

3. Schema repair and deterministic validation
   - Purpose: Make useful model outputs salvageable without accepting ungrounded claims.
   - Changes: Repair common schema drift into `canonical_claims`, coerce common source-card variants, and reject claims without exact or normalized quote matches.
   - Artifacts: Repair reports with counts for exact quote hits, rejected quote misses, repair use, and accepted claim count.
   - Validation: Tests simulate a first pass with a wrong schema and verify the repair pass produces accepted source-grounded claims.
   - Risks: Repair could launder bad claims; deterministic quote validation remains the acceptance boundary.

4. Maintainability split
   - Purpose: Prevent the runner from accumulating semantic extraction complexity.
   - Changes: Keep whole-document extraction in `staged_semantic_whole_doc_pipeline.py`; remove alternate extractor dispatch modules.
   - Artifacts: Smaller runner and focused tests.
   - Validation: Static maintainability gate remains blocking.
   - Risks: Cross-module imports can create cycles; the runner imports whole-doc dispatch locally only when needed.

## Execution Order
1. Probe whole-document extraction on representative sources to verify claim quality and identify schema drift.
2. Implement the source-card adapter with repair and exact quote validation.
3. Integrate it as the only staged claim extractor.
4. Add focused regression tests for the source-card path and remove legacy fake-model tests.
5. Run maintainability and full-suite verification.

## Acceptance Criteria
- `semantic staged map` and `semantic staged brief` do not expose extractor selection.
- Staged claim extraction always writes `claim_sources/` artifacts.
- Whole-document extraction writes source-level prompts, raw output, repair output, canonical payload, report, progress, and accepted/rejected claim artifacts.
- Claims accepted from whole-document extraction must include exact source alignment and `extraction_method: whole_doc_source_card`.
- Static maintainability gate passes without raising file or function limits.
- Full test suite passes with `PYTHONPATH=src:scripts python3 -m pytest -q`.

## Red-Team Checks
- Failure: The model returns a plausible but nonconforming schema.
  - Detection: Repair path and report show `repair_used`; canonical payload remains schema-normalized.
- Failure: The model invents or paraphrases source quotes.
  - Detection: Quote validation rejects claims without exact/normalized quote matches.
- Failure: Legacy chunk extraction silently reappears.
  - Detection: Static scans and tests reject selectable extractor flags, alternate extractor modules, and chunk-prompt artifact assumptions.
- Failure: Import cycles creep back into the runner.
  - Detection: Focused imports and full pytest collection fail; maintainability gate catches runner growth.

## Generalizability Checks
- The prompt names decision relevance and source-level salience, not case-specific entities.
- Roles map from source-card roles into existing general claim roles.
- Rejection reasons are generic: backend error, invalid payload, quote alignment failure, relevance rejection, duplicate claim.
- Stress reports include the extractor choice so cross-case comparisons are interpretable.
- Future unseen-case tests should track source-card claim fragmentation, quote anchoring, duplicate rate, and briefing usefulness.
