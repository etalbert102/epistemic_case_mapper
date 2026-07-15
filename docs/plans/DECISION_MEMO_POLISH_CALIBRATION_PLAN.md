# Plan: Decision Memo Polish And Calibration

## Objective
Make generated decision memos crisper, more calibrated, and more readable without weakening source traceability. The target output should answer first, keep observational and guidance evidence within appropriate language bounds, present source weighting cleanly, and use section-local polish only where it can be validated.

## Current Gap
Recent live eggs memos are decision-useful but not yet polished. The main issues are:

- the bottom line is too hedged or generic;
- observational evidence can be phrased too causally;
- source caveats appear as a dense reader-facing footnote;
- prose polishing is either too narrow or risks broad evidence drift.

## Non-Goals
- Do not add a new expensive global rewrite call.
- Do not hard-code egg, nutrition, cardiovascular, or source-specific vocabulary.
- Do not let deterministic code make semantic claims; it may structure, surface, and validate model or upstream judgments.
- Do not weaken source IDs, citation trace, deterministic source list, or retention checks.

## Design Principles
- Put reusable semantic contracts in the canonical writer packet, not only in prompts.
- Let model calls write and judge language; let deterministic code enforce stable identities, source references, quantities, and known evidence-design limits.
- Prefer reportable warnings over silent fallbacks.
- Keep prompts section-local when polishing so context stays relevant and validation remains tractable.
- Make every slice produce a testable artifact or invariant.

## Fact Ownership
- Canonical writer packet owns the BLUF contract and evidence-language calibration rows.
- Memo synthesis prompts consume those contracts and should not re-derive them from prose.
- Presentation normalization owns deterministic source sections, readable citation labels, citation trace links, and source-note placement.
- Section polish owns local prose smoothing only; it may not create new facts or new source references.

## Workstreams
1. **BLUF Contract**
   - Purpose: make the answer-first paragraph crisp and scoped.
   - Changes: add `bluf_contract` to the canonical packet and reader synthesis packet.
   - Validation: tests assert fields exist and prompts mention the contract.

2. **Evidence-Language Calibration**
   - Purpose: prevent causal overreach and preserve design-specific wording.
   - Changes: add per-evidence `evidence_language_contract` rows with design, allowed verbs, avoid verbs, and source IDs.
   - Validation: tests cover observational/guidance wording constraints and reader packet exposure.

3. **Clean Source Weighting Presentation**
   - Purpose: remove dense source-weight footnotes from the memo body.
   - Changes: replace the caveat footnote with concise prose and move source-specific use notes into the deterministic source list and citation trace.
   - Validation: tests assert no source-weight caveat footnote is generated and source lines include use notes when available.

4. **Section-Local Polish Guardrails**
   - Purpose: allow more natural prose without broad memo drift.
   - Changes: pass section-local relevant calibration contracts into polish guardrails and reject/diagnose new unsupported causal wording when source design forbids it.
   - Validation: tests assert polish prompts include calibration contracts and candidate validation catches new causal verbs for constrained source IDs.

## Execution Order
1. Record this plan and commit it as the baseline.
2. Implement BLUF contract and prompt consumption; run canonical and section synthesis tests; commit.
3. Implement evidence-language calibration; run canonical, prompt, and calibration tests; commit.
4. Clean source weighting presentation; run presentation tests; commit.
5. Harden section-local polish; run polish tests; commit.
6. Run the full fast test suite and, if practical, regenerate a live memo for qualitative inspection.

## Acceptance Criteria
- Canonical packets include `bluf_contract` and `evidence_language_contracts`.
- Synthesis prompts instruct the model to use the BLUF contract for the opening answer and language contracts for causal/confidence wording.
- Presentation normalization no longer emits `[^source-weight-caveats]` in the main memo.
- The deterministic source list or citation trace provides compact, source-specific use notes.
- Section-local polish prompts carry only relevant guardrails and reject obvious unsupported causal additions.
- `PYTHONPATH=src:scripts python3 -m pytest -q` passes.

## Red-Team Checks
- If the memo becomes crisper by hiding uncertainty, the language contracts and source notes should expose the lost caveat.
- If source-note presentation becomes too long, source list entries should stay one line where possible and full trace details should remain in `CITATION_TRACE.md`.
- If polish rejects too much, validators should report exact offending source IDs and verbs rather than silently blocking.
- If the implementation only improves eggs, tests should use generic scaffold data and source-design vocabulary.

## Generalizability Checks
- The contracts must be driven by source appraisal, evidence roles, and answer-frame fields, not domain keywords.
- The same mechanism should apply to policy, technical-risk, medical, social-science, and business decision questions.
- Source IDs remain the stable identity layer through model calls; reader-facing labels are presentation-only.

## Completion Audit
- Record each slice commit in the final response.
- Report verification commands and any skipped live/e2e run.
- Manually evaluate the newest memo for the four target issues: crispness, calibration, source-weight readability, and polish without drift.
