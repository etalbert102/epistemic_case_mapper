# Plan: Model-Adjudicated Source Weighting In Production

## Objective
Add a production source-weighting layer that asks the model to judge how each source should be used, then uses deterministic code to validate IDs, render the weighting section, and report failures. The end state is a memo-ready packet whose source-weighting guidance is source-specific, readable, and traceable instead of grouping unrelated caveats together.

## Current Gap
The current fallback source-weighting layer is deterministic and sometimes makes semantic decisions from brittle text cues. Experiments showed that per-source model judgments produce better weighting guidance, while grouped deterministic rendering can incorrectly apply one source's limits to another source.

## Non-Goals
- Do not add source collection.
- Do not make source-weighting failures silently block memo creation.
- Do not tune prompts to the eggs case; prompts must operate on a decision question, source trail, evidence items, and existing source appraisals.
- Do not let the model rewrite source IDs or source lists.

## Design Principles
- Use the model for semantic source-use judgment.
- Use deterministic code for schema validation, source-ID validation, packet attachment, rendering, and telemetry.
- Run per-source calls in parallel using the existing model parallelism setting.
- Preserve a deterministic fallback judgment only as an explicit fallback row with warnings.
- Keep source caveats source-local; never merge limits across unrelated sources.

## Workstreams
1. Production model source-weight judgments
   - Purpose: create schema-constrained, per-source source-use judgments.
   - Changes: add a module that builds compact per-source inputs, runs parallel model calls, validates Pydantic output, and returns a report.
   - Artifacts: `model_source_weight_judgments`, prompt/raw/report summaries.
   - Validation: fake backend/unit tests for valid rows, skipped prompt backend, fallback behavior, and ID preservation.
   - QA: prompt includes decision question and only the relevant source's evidence context.

2. Packet integration
   - Purpose: make memo synthesis consume model-adjudicated source weights.
   - Changes: attach model judgments after the active memo-ready packet is built and before final synthesis.
   - Artifacts: updated `memo_ready_packet.canonical_decision_writer_packet.source_weight_judgments` and reports.
   - Validation: packet quality report count matches attached judgments.
   - QA: failures remain visible in reports.

3. Per-source presentation renderer
   - Purpose: make the reader-facing "How to Weight the Evidence" section source-specific.
   - Changes: prefer source-local `memo_weight_sentence` rows when available; keep old grouped renderer only as fallback.
   - Artifacts: deterministic section with normalized source IDs/citations.
   - Validation: test that one source's limitation is not applied to another source.
   - QA: citations use packet source IDs and later deterministic display normalization.

4. Evaluation
   - Purpose: check whether production integration improves final packet/memo quality.
   - Changes: run focused tests, full tests if feasible, then apply the production path to the saved eggs packet with a live backend.
   - Artifacts: experiment directory with enriched packet, rendered/synthesized memo, reports, and a short evaluation.
   - Validation: inspect source-weighting section, parse/report counts, citation density, and source-binding warnings.

## Execution Order
1. Add and test the source-weighting module independently.
2. Update the presentation renderer and tests.
3. Wire the source-weighting bundle into the active decision packet stage.
4. Run targeted tests, then full tests.
5. Run a live evaluation on the saved eggs artifacts and manually judge the memo impact.

## Acceptance Criteria
- Per-source source-weight calls parse or produce explicit fallback rows with report warnings.
- `prompt` backend skips model source weighting without changing deterministic test paths.
- Model-adjudicated judgments attach into the canonical packet and update quality counts.
- The weighting renderer keeps reader-facing limits source-local.
- Live evaluation produces a memo or packet artifact whose source-weighting section is clearer than the previous grouped version.

## Red-Team Checks
- Model returns invalid source IDs: deterministic validation must reject or fallback without mutating IDs.
- Model gives generic caveats: report generic/empty rows and preserve existing fallback detail.
- Renderer over-compresses: per-source bullets must preserve each source's actual role and limits.
- Evaluation gives false confidence from telemetry artifacts: inspect the memo and packet manually, not just warning counts.

## Generalizability Checks
- The prompt names no domain-specific concepts beyond fields present in the packet.
- The implementation works with any decision question and source trail.
- Long or sparse source trails produce visible fallbacks rather than fabricated certainty.
- Source labels remain normalized through existing source-identity functions rather than hard-coded names.
