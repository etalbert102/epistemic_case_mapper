# Regulatory Full-Document Protocol

Purpose: record how a later experiment should use realistic regulatory documents without turning audit anchors into hand-selected model inputs.

## Role In The Prototype

The regulatory slice is a realism extension after the LHC and eggs worked regions are stable. Its job is to test whether the same case-map workflow helps with operational public decision documents.

## Primary Input Rule

The primary synthesis input is the full regulatory document, subject only to a declared context-handling policy.

Audit anchors may be used for:

- human review,
- label verification,
- compact worked examples,
- diagnostic excerpt-budget ablations.

Audit anchors must not become the primary synthesis input unless the condition is explicitly labeled as an excerpt-budget ablation.

## Source Requirements

Each regulatory task should record:

- official source URL,
- agency,
- document number or docket identifier when available,
- publication date,
- retrieval date,
- local raw/text path,
- checksum or text hash,
- context-handling policy.

Preferred first source family: Federal Register proposed rules with explanatory preambles.

## Option Derivation Hierarchy

Do not invent arbitrary options. Derive options in this order:

1. Explicit alternatives named in the document.
2. Agency proposed action.
3. Status quo or no-action baseline.
4. Narrower or less burdensome version.
5. Stricter or broader version.
6. Delayed, phased, or conditional implementation.

If fewer than two options can be supported, exclude the task from confirmatory use.

## Annotation Anchors

Record anchors for:

- proposed action,
- agency rationale or public-interest benefit,
- costs, burdens, feasibility, or implementation constraints,
- legal authority or regulatory requirement,
- alternatives, phased implementation, or rejected options,
- stakeholder concern or public-comment opposition if stable to retrieve.

Target `6-10` anchors for ordinary tasks. Dense contested tasks may use `10-12`.

## Document-Map Intervention

Document-map extraction is part of the intervention, not neutral preprocessing.

Direct and prompt-only baselines receive the full document under the same context policy, but not a hand-curated document map. Structured-map comparison conditions may receive their own generated maps if clearly labeled.

## Failure Categories

Regulatory audits should distinguish:

- source insufficiency: expected item is absent from visible input,
- retrieval or chunking failure: expected item exists in full document but was not surfaced under the policy,
- mapping failure: item is visible but missing from the document map,
- synthesis erosion: item appears in map/input but disappears from final synthesis,
- unsupported invention: output adds unsupported decision structure.

## Status

This protocol applies to a later full-document experiment and does not block the current LHC and eggs worked regions.
