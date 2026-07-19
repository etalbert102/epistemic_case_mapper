# Plan: Analytical Decision Calibration Contract

## Objective
Make memo synthesis more decision-grade by giving the existing writer model a compact calibration contract: answer the exact decision frame, use scope and dose quantities correctly, preserve subgroup boundaries, avoid unsupported causal wording, and include the most decision-relevant quantities by analytical role.

## Current Gap
The analytical balance contract now forces high-priority support and counterweights into the memo, but the produced memo can still be weak in more specific ways. It may answer around the decision categories rather than naming the supported stance, turn study-specific quantities into broad recommendations, overstate causal interpretation, underplay subgroup boundaries, or preserve quantities without explaining why each quantity matters.

## Non-Goals
- Do not add a new model call.
- Do not make deterministic code decide domain truth.
- Do not add domain-specific vocabulary or case-specific slots.
- Do not block synthesis on brittle semantic validators.
- Do not make every candidate evidence item mandatory.

## Design Principles
- Deterministic code should build compact contracts, preserve IDs, route quantities, and detect language-risk patterns.
- The model should handle semantic synthesis, calibrated prose, and final answer framing.
- Existing packet fields remain the source of truth; new contract fields should be projections of the packet, not parallel evidence.
- Add warnings and writing jobs that generalize across decision domains.
- Prefer role-based quantity requirements over raw number dumping.

## Workstreams
1. Answer Calibration
   - Purpose: Make the memo open by answering the actual decision question.
   - Changes: Add an answer-classification contract that exposes the decision question, current answer state, detected option frame, and a writing job to state supported and unsupported options when the question presents choices.
   - Validation: Unit test with a generic harmful/neutral/beneficial-style question that does not mention any domain.

2. Scope And Quantity Guardrails
   - Purpose: Stop study- or context-specific quantities from becoming broad recommendations.
   - Changes: Add role-based dose/scope guardrails and targeted quantity requirements for support, counterweight, boundary, and uncertainty quantities.
   - Validation: Unit test that distinguishes a general moderate-use quantity from a study-specific context quantity.

3. Causal And Evidence-Type Discipline
   - Purpose: Keep synthesis faithful to what the evidence type can establish.
   - Changes: Add causal-language discipline rows from causal phrasing, source appraisal, and evidence-proximity signals; strengthen evidence-type writing jobs.
   - Validation: Unit test that a causal-sounding observational claim produces a calibrated-language instruction.

4. Boundary Promotion
   - Purpose: Ensure subgroup, applicability, and boundary cards are visible in the memo when they affect the decision read.
   - Changes: Promote high-priority subgroup/scope boundary cards into required balance cards and expose a separate subgroup-boundary section.
   - Validation: Retention test warns when a promoted boundary card is omitted and passes when it is included.

5. Prompt Integration
   - Purpose: Make the existing writer call use the new contract fields naturally.
   - Changes: Extend the synthesis prompt rules for answer classification, quantity guardrails, causal discipline, subgroup boundaries, and targeted quantities.
   - Validation: Prompt test confirms the fields are source-ID projected and available to the model without verbose source labels.

## Execution Order
1. Extend the contract builder and tests for answer, quantity, causal, and boundary fields.
2. Integrate the fields into the synthesis prompt.
3. Run focused contract/prompt/retention tests.
4. Run the full suite and inspect the resulting contract on saved egg artifacts if available.

## Acceptance Criteria
- `analytical_balance_contract` includes answer classification, scope/dose guardrails, causal-language discipline, subgroup-boundary cards, targeted quantity requirements, and strengthened evidence-type instructions.
- High-priority boundary cards can become required balance cards without making all boundaries mandatory.
- Prompt text tells the writer how to use these fields but still lets the model write natural prose.
- Tests cover the general behavior without domain terms.
- Full test suite passes.

## Red-Team Checks
- If the option-frame detector is too weak, it should still emit a general answer-writing job rather than false categories.
- If quantity classification is uncertain, the contract should present the uncertainty as a guardrail instead of deleting the quantity.
- If causal language is detected from a legitimate causal source, the contract should ask for calibrated language tied to source appraisal, not forbid causal claims.
- If too many boundary cards are promoted, role caps and rank thresholds should keep the memo readable.

## Generalizability Checks
- Fixtures use generic option decisions, implementation outcomes, and populations rather than eggs, health, or other case-specific terms.
- The contract keys describe analytical functions rather than domains.
- The implementation avoids old fallback paths and does not encode a preferred answer for any case.
