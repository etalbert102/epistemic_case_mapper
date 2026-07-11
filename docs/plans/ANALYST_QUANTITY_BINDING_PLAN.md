# Plan: Analyst Quantity Binding Gate

## Objective
Prevent incidental or off-scope extracted quantities from becoming mandatory memo obligations. The pipeline should preserve all raw quantities for traceability, but only semantically bound, decision-relevant quantities should enter the memo-ready packet.

## Current Gap
The analyst packet path aggregates every `quantity_values` string from evidence rows covered by a decision group. Memo-ready item creation then appends those group quantities to reader claims and retention validation rewards the memo for preserving them. This can promote incidental source-scope quantities, such as toddler age ranges, into adult decision evidence.

## Non-Goals
- Do not make source extraction narrower; extraction should remain recall-oriented.
- Do not hide model calls inside pure packet construction.
- Do not delete raw quantities from ledger, groups, or trace artifacts.
- Do not add domain-specific egg logic.

## Design Principles
- Extraction preserves; packet assembly promotes.
- Deterministic code owns candidate generation, provenance, suspicious-pattern flags, schema checks, and telemetry.
- The model owns semantic binding when a live backend is available.
- Report-only or fallback behavior must fail visibly, not silently over-promote.
- Retention should validate approved quantity bindings, not raw extracted quantities.

## Workstreams
1. Quantity Binding Contract
   - Purpose: create a reusable artifact between analyst synthesis groups and memo-ready items.
   - Changes: add candidate, approved, rejected/context-only rows with provenance and warnings.
   - Artifacts: `analyst_quantity_binding_report.json`.
   - Validation: schema/status/counts and source evidence IDs.
   - QA: regression fixture for an age-scope quantity attached to an adult outcome group.

2. Deterministic Candidate Binding
   - Purpose: make all candidate promotions inspectable and provide safe fallback behavior.
   - Changes: build candidates from each group's covered ledger rows; classify obvious non-memo quantities such as age-scope and heterogeneity-only values.
   - Artifacts: warning counts and rejected/context quantities.
   - Validation: raw quantities remain visible while rejected quantities are not memo-ready obligations.

3. Optional Model Adjudication
   - Purpose: use model semantics where needed without making the builder impure.
   - Changes: add a backend runner that asks the model to set `memo_use` and interpretation for candidates; merge accepted rows with deterministic fallbacks for missing IDs.
   - Artifacts: prompt, raw output, parse report, merged binding report.
   - Validation: prompt backend uses deterministic binding; live backend can improve semantic judgments.

4. Memo-Ready Integration
   - Purpose: make final synthesis consume only approved quantity bindings.
   - Changes: `build_analyst_packet_bundle` accepts or creates a binding report and passes approved bindings into memo-ready item construction.
   - Artifacts: memo-ready packet includes the binding report.
   - Validation: retention checks no longer require rejected/context-only raw quantities.

## Acceptance Criteria
- A group covering an adult CVD proposition and a toddler-age source claim does not promote toddler age ranges into memo-ready quantities.
- A valid effect estimate or decision-relevant percentage remains available when it is semantically tied to the group proposition.
- `build_analyst_packet_bundle` returns `analyst_quantity_binding_report`.
- Full pipeline runs model-backed quantity adjudication before the final analyst memo-ready packet is promoted.
- Focused tests pass for analyst packet behavior and quantity binding regression.

## Red-Team Checks
- False rejection: a duration or age quantity may be relevant when the decision question is about duration or age. Detection: warning rows retain the candidate and rationale; live model can override deterministic fallback.
- False approval: a source-overlap quantity may still not quantify the group proposition. Detection: deterministic warnings are supplied to the model and telemetry records accepted-with-warning rows.
- Validation false confidence: retention can be green while the packet is semantically bad. Mitigation: retention only applies to approved bindings, while rejected/context-only quantities remain separately auditable.

## Generalizability Checks
- The logic is phrased in terms of source claim, group proposition, decision question, quantity type, and memo use, not egg-specific vocabulary.
- The model prompt asks what the quantity measures and whether it quantifies the proposition, which travels across domains.
- Deterministic warnings flag abstract mismatch classes such as age/scope, heterogeneity-only, unpaired intervals, and weak source/proposition overlap.
