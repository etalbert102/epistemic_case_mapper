# Quality Risk Gate Improvement Plan

Status: `implemented`

This plan tracks improvements from the unseen classroom HEPA test. That run showed the engine can package a new case, but it was too forgiving: a polished map over weak local source notes passed structural validation, while the quality concerns lived only in manual review notes.

## Findings To Address

- Source provenance was not first-class. The package could use local notes without generated warnings.
- Reviewer-facing generated artifacts did not foreground risk/fail quality rows.
- The UI made the package look cleaner than the scorecard.
- Custom relation labels were accepted without definition.
- Risk/fail scorecard rows did not generate concrete follow-up work.
- Baseline uplift could be mild while the package still passed structural checks.

## Implemented Changes

1. Source metadata
   - `case.yaml` source entries now support `provenance_level`, `evidence_role`, `limitations`, and `needs_upgrade`.
   - Explicit weak provenance levels are `secondary_summary`, `local_note`, and `synthetic_note`.

2. Relation ontology
   - `package.yaml` now supports `relation_ontology.allowed_types` and `relation_ontology.custom_definitions`.
   - Worked-region validation fails if a relation type is neither allowed nor defined.

3. Reviewer warnings
   - `ecm package prepare` adds quality warnings to `docs/review/REVIEWER_START_HERE.md` when it finds weak source provenance, source-upgrade flags, source limitations, risk/fail scorecard rows, low quality scores, or non-passing quality results.

4. UI warnings
   - `ui/data.json` now includes source provenance metadata, quality summaries, and quality warnings.
   - The static UI includes a quality panel that surfaces overall result and warning rows.

5. Generated risk tasks
   - `ecm quality gate` writes `docs/unseen_case_tests/<case>/GENERATED_RISK_TASKS.md`.
   - Tasks are generated from source provenance risks, source limitations, risk/fail scorecard rows, low quality scores, and non-passing overall results.

## Remaining Work

- The gate does not fail on weak provenance by default; it surfaces the weakness. A stricter profile could fail when load-bearing claims depend on weak provenance.
- The engine does not yet infer which claims are load-bearing. Claim role conventions exist in artifacts, but they are not schema-validated.
- Baseline-uplift thresholds are surfaced through low-score and risk rows, not enforced as a hard failure.
- Quantitative policy-strength checks remain domain-specific and are not yet enforced by the generic engine.
