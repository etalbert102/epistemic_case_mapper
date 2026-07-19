# Plan: Two-Pass Final Memo Editor

## Objective

Split the whole-memo edit pass into two constrained final-editor passes that improve decision-brief readability without weakening source grounding. The pass is now part of the normal final briefing path for real model backends; prompt-only backends still emit diagnostics without model synthesis.

The target end state is a final decision memo that:

- answers the decision question directly;
- keeps the BLUF, body sections, caveats, confidence, and source list aligned;
- reduces repetition and over-weighted caveats;
- improves transitions and analyst prose;
- preserves headings, source labels, quantities, evidence IDs, confidence labels, and the exact decision question;
- never gives the model a second uncontrolled synthesis job.

## Current Gap

The current whole-memo pass is architecturally safer than a free rewrite because it asks the model for exact JSON edit suggestions and lets deterministic code apply only safe replacements. The weakness is that it combines two different jobs:

1. Coherence editing: BLUF/body alignment, caveat weighting, section redundancy, and decision-flow issues.
2. Prose polishing: awkward wording, clunky transitions, long sentences, and mechanical phrasing.

It also feeds a broad evidence contract into the edit prompt. That contract is useful for deterministic validation, but it can pollute the model context with answer-frame, option-comparison, practical-action, required-evidence, gap, and crux material that the final editor should not re-synthesize. The editor should mostly see the memo, a deterministic diagnosis, and protected spans.

## Non-Goals

- Do not implement a full-document model rewrite.
- Do not let the model add new claims, sources, quantities, evidence labels, or recommendations.
- Do not change extraction, relation construction, evidence partitioning, or section synthesis in this plan.
- Do not tune behavior to one biomedical or eggs-specific case.
- Do not make prose quality pass by weakening source preservation.

## Design Principles

- Model proposes, deterministic code disposes.
- Separate structure/coherence from surface prose.
- Feed each model call only the context needed for its job.
- Keep validation and model-visible protected spans derived from the same source of truth.
- Prefer safe abstention over polished but ungrounded edits.
- Record before/after telemetry so improvements are inspectable.

## Context Hygiene Policy

The final editor passes should receive:

- the current memo text;
- the decision question;
- confidence label;
- protected spans generated from the memo and scaffold;
- deterministic diagnosis items relevant to the pass;
- a compact schema and edit rules.

The final editor passes should not receive:

- full section synthesis packets;
- full debug packets;
- full decision memo slot models;
- full answer-frame or option-comparison scaffolds;
- required evidence rows except as protected source-bearing spans already present in the memo;
- negative anchor terms that could cause the model to repeat forbidden material;
- raw claim, relation, or source IDs unless already visible in the memo.

Validators may use broader scaffold records, but those records should remain artifact-facing and deterministic-only.

## Workstreams

### 1. Deterministic Memo Diagnosis

Purpose:
Create compact, pass-specific context for final editing.

Changes:

- Add `memo_final_diagnosis.json`.
- Classify issues into `coherence` and `prose`.
- Detect repeated sentences, repeated caveat phrases, weak section openings, long sentences, awkward internal process language, sparse source attachment, and BLUF/body mismatch signals.

Artifacts:

- `memo_final_diagnosis.json`
- before/after metric block in the final briefing report

Validation:

- Synthetic memo tests for repeated caveats, awkward section starts, missing question, and long sentences.
- Ensure diagnosis is domain-neutral.

### 2. Shared Protected-Span Builder

Purpose:
Prevent prompt/validator divergence.

Changes:

- Build one protected-span object used by prompts, edit application, and validators.
- Include decision question, headings, confidence line, source list, source labels, quantities, evidence IDs, and required gap wording.
- Store source of each protected span.

Artifacts:

- `memo_protected_spans.json`

Validation:

- Tests prove edits touching protected spans are rejected.
- Tests prove prompt-visible protected spans match validator-visible protected spans.

### 3. Pass 1: Coherence Edit

Purpose:
Improve the memo as decision support before surface polish.

Allowed edit types:

- `tighten_bluf`
- `deduplicate_caveat`
- `rebalance_emphasis`
- `clarify_section_role`
- `remove_redundant_sentence`
- `align_scope_with_answer`

Model input:

- memo;
- decision question;
- confidence label;
- coherence diagnosis only;
- protected spans;
- exact-edit schema.

Model output:

- JSON only:
  - `target`
  - `replacement`
  - `target_section`
  - `edit_type`
  - `reason`

Validation:

- Reject edits that touch protected spans.
- Reject edits that introduce new numbers, source labels, or named recommendations.
- Reject edits that remove the only occurrence of a required caveat.
- Accept only if coherence metrics improve or record `no_safe_improvement`.

Artifacts:

- `memo_coherence_edits.json`
- `memo_after_coherence.md`
- `memo_coherence_validation.json`

### 4. Pass 2: Prose Polish Edit

Purpose:
Improve readability after coherence is stable.

Allowed edit types:

- `smooth_transition`
- `shorten_sentence`
- `fix_awkward_phrase`
- `remove_internal_process_language`
- `improve_reader_voice`
- `clarify_local_sentence`

Model input:

- memo after coherence pass;
- prose diagnosis only;
- protected spans;
- exact-edit schema.

Model output:

- same exact-edit JSON shape as Pass 1.

Validation:

- Same protected-span checks.
- Reject broad paragraph rewrites unless source-neutral and local.
- Reject edits that change uncertainty strength.
- Accept only if prose lint metrics improve or record `no_safe_improvement`.

Artifacts:

- `memo_prose_edits.json`
- `memo_after_prose.md`
- `memo_prose_validation.json`

### 5. Shared Edit Application Engine

Purpose:
Make both passes use the same safe edit machinery.

Changes:

- Add typed edit schema.
- Support pass-specific edit budgets.
- Preserve exact target matching.
- Track applied and rejected edits by reason.
- Cap total changed characters and changed source-bearing sentences.

Validation:

- Reject ambiguous targets.
- Reject heading, source, confidence, question, quantity, and evidence-ID changes.
- Reject new source labels and new numbers.
- Confirm safe local replacements apply cleanly.

### 6. Context Audit Extension

Purpose:
Catch accidental prompt pollution before it affects memo quality.

Changes:

- Extend model context audit to flag final-editor prompts that include broad scaffold fields.
- Add flags for answer-frame, option-comparison, section-packet, debug-packet, raw-ID, and negative-anchor leakage.
- Keep broad scaffold data available to deterministic validators but out of model-facing final-editor prompts.

Validation:

- Unit test that current broad prompt shape is flagged.
- Unit test that compact final-editor prompt shape is clean.

## Execution Order

1. Record this plan and add context-audit flags for current/future final-editor prompts.
2. Add protected-span builder.
3. Add deterministic memo diagnosis.
4. Refactor the existing whole-memo edit pass into a shared edit engine.
5. Implement coherence pass.
6. Implement prose pass.
7. Wire both passes behind the existing optional reader memo rewrite flag.
8. Emit telemetry and artifacts.
9. Run focused tests, full pytest, and maintainability gate.
10. Run the eggs case and one unrelated case to verify safe improvement or safe abstention.

## Acceptance Criteria

- Existing tests pass.
- New tests cover diagnosis, protected spans, coherence edits, prose edits, and context audit flags.
- Final-editor prompts do not expose broad scaffold/debug packets.
- On at least one existing memo, repetition or transition metrics improve without source/question/confidence loss.
- On at least one unrelated memo fixture, the passes improve or safely abstain.
- Rejected edits include actionable reasons.

## Red-Team Checks

- The model compresses a repeated caveat that is actually required in multiple sections.
- The model makes the BLUF more confident than the body supports.
- The model preserves source labels but moves them away from the claims they support.
- The editor improves lint metrics while weakening decision usefulness.
- The prompt hides too much context and the model cannot make useful edits.
- The prompt includes too much context and the model starts re-synthesizing.

## Generalizability Checks

Test the passes on:

- a biomedical decision memo;
- a technical or policy decision memo;
- a sparse-evidence memo with high uncertainty.

The correct behavior is either safe improvement or explicit abstention. A polished but less grounded memo is a failure.

## Completion Audit

The plan is complete when the repo contains:

- recorded final-editor plan;
- compact final-editor prompt context audit;
- protected-span builder;
- deterministic memo diagnosis;
- coherence edit pass;
- prose polish edit pass;
- pass-specific telemetry artifacts;
- focused tests and full verification results;
- before/after memo comparison on at least two cases.
