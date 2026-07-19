# Plan: Analytical Balance Contract

## Objective
Make decision memos analytically balanced without adding another model call. The memo writer should see a compact, general-purpose contract that requires the final memo to state the bounded answer, weigh load-bearing support, weigh the strongest counterweights, name scope boundaries, interpret decision-relevant quantities, and explain how counterweights affect the answer.

## Current Gap
The current source-ID and source-boundary work improves citation presentation and evidence retention, but a memo can still pass retention while omitting analytically important `should_include` counterweights. The eggs memo did this with a high-ranked counterweight about elevated CVD risk at high egg intake. The failure is not domain-specific: any decision memo can become too smooth if high-salience counterevidence is demoted from mandatory retention but still needed for balanced reasoning.

## Non-Goals
- Do not add a new model call.
- Do not introduce domain vocabulary such as eggs, cholesterol, diabetes, nuclear, HEPA, or RCT as required slots.
- Do not make every `should_include` item mandatory.
- Do not replace source appraisal, source identity, or existing memo obligations.

## Design Principles
- Use deterministic code for coverage contracts, IDs, ranking, and validation.
- Use the existing synthesis model call for prose and semantic integration.
- Require balance by abstract decision function: support, challenge, scope, crux, evidence-type contrast, and quantity calibration.
- Promote only high-priority, decision-shaping non-mandatory evidence into balance requirements.
- Keep validation report-only enough to diagnose misses, but strong enough to surface dropped counterweights as retention warnings.

## Workstreams
1. Analytical Contract Builder
   - Purpose: Compile a compact `analytical_balance_contract` from existing packet fields.
   - Changes: Add a module that selects top support, counterweight, scope, and crux cards; marks high-priority non-mandatory balance cards as required; includes validation terms and source lineage.
   - Artifacts: `analytical_balance_contract` in the synthesis prompt.
   - Validation: Unit tests with generic decision fixtures.

2. Prompt Integration
   - Purpose: Make the existing synthesis call use the contract.
   - Changes: Add the contract to `writer_model_context`; instruct the model to weigh required balance cards and state how counterweights affect the answer.
   - Artifacts: Prompt contains `analytical_balance_contract` and source IDs.
   - Validation: Prompt tests confirm no verbose source labels leak.

3. Retention Integration
   - Purpose: Detect analytically important omissions.
   - Changes: Add retention statuses for required balance cards, using the same source alias handling as memo obligations.
   - Artifacts: `analytical_balance_statuses`, required/retained counts, and `missing_analytical_balance_card` issues.
   - Validation: A memo omitting a high-ranked counterweight warns; a memo that weighs it passes.

## Acceptance Criteria
- The synthesis prompt includes `analytical_balance_contract`.
- The contract is source-ID projected for model calls.
- High-ranked `should_include` counterweights are required for balance without making all `should_include` rows mandatory.
- Retention reports warn when a required balance card is omitted.
- Full test suite passes.

## Red-Team Checks
- False confidence: validators might pass if a memo mentions terms without weighing the evidence. Mitigation: card writing jobs require disposition language, and future work can add model adjudication if deterministic term checks remain too weak.
- Over-inclusion: too many `should_include` cards could make memos clunky. Mitigation: role-specific caps and rank thresholds.
- Overfitting: thresholds could accidentally fit eggs. Mitigation: tests use generic option/adoption cases and abstract roles only.

## Generalizability Checks
- The contract uses packet roles and answer relations, not domain terms.
- The same logic should apply to policy, health, engineering, contract, and scientific-evidence decisions.
- If a case has no counterweights, the contract should not invent one; if it has high-ranked counterweights, the memo should visibly weigh them.
