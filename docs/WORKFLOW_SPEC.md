# Workflow Spec

## Purpose

The workflow turns a messy evidence base into a reusable epistemic case map. It is designed to preserve the investigator's decision space rather than only produce a polished summary.

## Inputs

- A case question.
- A source manifest with titles, provenance, notes, and eventually source-local text spans.
- Optional investigator notes about scope, assumptions, and known missing perspectives.

## Outputs

- `case_map.json`: structured claims, sources, relations, open questions, and audit metadata.
- `report.md`: a human-readable view for review and discussion.

## Workflow

1. Scope the case.
   - Define the top-level question.
   - Identify whether the case is closed, live, adversarial, or exploratory.
   - Name the intended use of the map.

2. Ingest sources.
   - Record source provenance.
   - Extract candidate claims with source-local support.
   - Preserve uncertainty, caveats, population boundaries, and methods claims.

3. Normalize claims.
   - Split compound claims where needed.
   - Group similar but non-identical claims.
   - Preserve disagreements instead of forcing premature consensus.

4. Build relations.
   - Link support, challenge, dependency, refinement, similarity, crux, and tension relations.
   - Separate evidential links from rhetorical or contextual links.

5. Audit.
   - Check that every important claim is source-attributed.
   - Check that disagreements and caveats survive synthesis.
   - Mark missing source types or perspectives.
   - Record open questions and next investigations.

6. Synthesize.
   - Produce summaries from the map, not directly from the raw text alone.
   - Include what is settled, what remains uncertain, and which claims drive the conclusion.

## Design Principle

Do not ask a synthesis pass to remember every live option implicitly. Store the live options in the case map and synthesize from that structure.
