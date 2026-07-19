# Plan: Section-Use Projections For Reusable Evidence

## Objective
Make memo sections reuse the same evidence without producing near-identical prose. Evidence cards should remain available to multiple sections, but each section should receive a deterministic instruction for how that card contributes to that section's distinct job.

## Current Gap
The pipeline currently gives adjacent sections overlapping evidence cards and broadly similar section theses. The model then summarizes the same source facts in Practical Read, Why This Read, Evidence Carrying, and Practical Scope. Prior strict ownership rules reduced repetition by hiding evidence, but that also removed useful cross-section reasoning.

## Non-Goals
- Do not assign each evidence card to only one section.
- Do not add domain-specific food, medicine, or egg vocabulary.
- Do not make source collection part of this change.
- Do not require the model to invent new facts or unsupported implications.

## Design Principles
- Separate evidence availability from evidence use.
- Keep discourse roles generic across domains.
- Let deterministic code create stable section-use contracts.
- Use the model for language synthesis, not role bookkeeping.
- Validate value-added reuse rather than banning repeated evidence.

## Workstreams
1. Section-use projection schema
   - Add `section_use_projections` to each `model_section_packet`.
   - Include card id, source role, section use, expected section value, and avoid-repeat guidance.
   - Validation: unit tests inspect packets for Practical Read, Why This Read, Evidence Carrying, and Scope.

2. Prompt integration
   - Tell the model to use evidence through section-use projections.
   - Make evidence reuse acceptable only when it performs the section's assigned discourse role.
   - Validation: prompt tests check for section-use projection guidance.

3. Repetition validation
   - Keep repeated source-detail checks, but evaluate whether the repeated sentence adds section-specific value.
   - Validation: repeated evidence with a reasoning/value move passes; source-detail replay without value fails.

4. Telemetry and live check
   - Preserve section packet artifacts so repeated cards and section uses are inspectable.
   - Run the eggs memo and compare section statuses, coherence warnings, and memo readability.

## Acceptance Criteria
- Evidence cards can appear in multiple section packets.
- Each reused card has a section-specific use label.
- Full test suite and maintainability gate pass.
- Live memo has fewer generic repeated source summaries, or failures identify missing section-use projections rather than ownership conflicts.

## Red-Team Checks
- If every section receives the same `section_use`, the system has only renamed the old problem.
- If prompts still say "fully explain owned evidence" without section-use constraints, the model will keep summarizing.
- If validation only counts duplicate sentences, it will miss paraphrased repetition.

## Generalizability Checks
- Section uses must be generic discourse roles: answer support, counterweight, scope boundary, exception case, mechanism, quantity anchor, method limit, practical implication, crux input.
- Tests should use synthetic non-food examples where possible.
- No domain-specific vocabulary may be introduced outside configured vocabulary paths.
