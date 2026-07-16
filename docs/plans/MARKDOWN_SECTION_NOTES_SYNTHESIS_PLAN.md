# Plan: Markdown Section Notes For Memo Synthesis

## Objective
Replace raw JSON section prompts with deterministic markdown analyst notes before section-level memo synthesis. The JSON section packet remains the validation record; the model sees a readable, section-local markdown rendering that preserves the same required claims, quantities, source IDs, caveats, cruxes, and writing constraints.

## Current Gap
The current section synthesis prompt appends the full `section_packet` as JSON. Live experiments showed that markdown notes can improve prose, but the renderer must preserve all section-relevant context. A sparse markdown renderer dropped Li 2020 lipid counterweights because the counterweight section relied on `top_context.lightweight_writer_guidance` and `top_context.decision_usefulness`, not `source_bound_evidence_atoms`.

## Design Principles
- Deterministic code selects and renders model-facing notes.
- Model work is reserved for prose synthesis, not deciding what evidence exists.
- JSON packets remain attached to each section for validation and retention checks.
- Markdown notes must preserve section-local evidence, top-context guidance, cruxes, quantity risks, and source-use caveats.
- No case-specific vocabulary or egg-specific logic.

## Workstreams
1. Markdown renderer
   - Add a reusable renderer for section packets.
   - Render purpose, reader question, role contract, required evidence points, obligations, protected quantities, source weighting, language contracts, lightweight guidance, decision usefulness, and paragraph flow.
   - Preserve bracketed source IDs exactly for citations.

2. Prompt integration
   - Change `build_memo_ready_section_synthesis_prompt` to call the renderer.
   - Keep output rules and validation assumptions equivalent to the previous prompt.
   - Do not expose raw JSON as the primary model-facing handoff.

3. Tests and validation
   - Update section-synthesis tests to assert markdown notes include the required context.
   - Add a regression test for sparse sections where required counterweight content lives in top context.
   - Run targeted tests and full suite.

## Acceptance Criteria
- Section prompts include markdown note headings such as `### Required evidence points`, `### Writing guidance, caveats, and quantity risks`, and `### Decision cruxes, thresholds, and update triggers` when those inputs exist.
- Prompts still contain `Output must start exactly with: ## <heading>` so existing section validators work.
- Counterweight markdown notes preserve quantity wording risks such as `8.14 mg/dL` and `0.14` when provided in top-context guidance.
- Existing section synthesis validation still rejects unknown source IDs.
- Full test suite passes.

## Red-Team Checks
- If markdown rendering omits fields, the model may write prettier prose while losing evidence.
- If markdown rendering is too verbose, it recreates the JSON context overload problem.
- If source IDs are rendered inconsistently, citation validation will fail or source binding will degrade.

## Generalizability Checks
- The renderer must operate on generic section packet fields and not inspect case-specific terms.
- It should preserve any source IDs, quantities, cruxes, and caveats regardless of domain.
- Sparse sections must still receive relevant top-context notes.
