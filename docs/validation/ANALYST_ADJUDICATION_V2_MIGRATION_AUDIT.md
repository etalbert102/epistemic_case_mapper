# Analyst Adjudication v2 Migration Audit

## Outcome

The model-facing analyst adjudication contract is reduced from 19 canonical row fields to seven compact fields. The model owns semantic routing; code restores ledger-owned provenance, quantities, ranks, and the canonical `analyst_adjudication_v1` surface. v2 is the default, with `ECM_ANALYST_ADJUDICATION_SCHEMA=v1` retained as a temporary rollback bridge.

## Design constraints

The migration applies the repository guidance as follows:

- `README.md`: source-linked reasoning remains fail-closed through canonical parsing and source-faithfulness repair.
- `docs/methodology/WORKFLOW.md`: live answer options, caveats, disagreement, and cruxes remain explicit model inputs or compact outputs.
- `docs/protocols/epistemic_case_map_v0.md`: stable evidence IDs and provenance remain inspectable; provenance is copied from the ledger rather than regenerated.
- Prototype and reproducibility criteria: coverage, unknown IDs, ranks, and schema accounting are deterministic and testable.
- Original decision-pipeline plan: the model retains semantic role assignment while code owns IDs, schema projection, accounting, chunking, and complete-coverage repair.
- FLF evaluation criteria: gates cover closed, heterogeneous, and adversarial packet behavior without encoding an eggs-specific classification rule.

## Bounded slices

1. `c0b1085` freezes representative v1 behavior and downstream routing.
2. `0219332` introduces the five-required, two-optional compact response contract.
3. `3446029` adds deterministic projection onto the canonical v1 artifact.
4. `7f69ef6` adds schema selection, chunking, focused missing-row repair, telemetry, and comparison reporting.
5. `5daffb6` adds semantic, invariance, source-faithfulness, and downstream quality gates.
6. The final migration slice makes v2 the default after Gemma acceptance and retains explicit v1 rollback.

## Verification evidence

- The frozen fixture prompt fell from 6,610 to 3,632 characters, a 45.1% reduction.
- Focused schema/runtime/quality verification passed after adding bounded compatibility for Gemma root lists, a `results` wrapper, and known enum aliases. Unknown wrappers and unknown enum values remain invalid.
- `ollama:gemma4:12b-mlx` completed the full 20-row eggs ledger with 20 canonical rows, zero initial failures, zero failed chunks, zero repair calls, and a valid parse in 44.423 seconds.
- An earlier full Gemma run exposed transport-shape variance and failed at 8/20 rows. That failure was retained as the reason for the narrowly tested response normalization; the rollout gate was not weakened.
- A Qwen canary also completed 20/20 rows after target-option validation was aligned with canonical `candidate_answer_id` values. Qwen is supporting evidence only; Gemma MLX 12B is the exemplar acceptance backend.

The prior checked artifact was produced by an unknown backend, so its semantic differences are not treated as an apples-to-apples regression result. Independent domain-expert review of role choices remains required before relying on a generated briefing as substantive adjudication.

## Rollback and removal

Set `ECM_ANALYST_ADJUDICATION_SCHEMA=v1` to restore the legacy model-facing path. Keep this bridge for one release or until two additional full-corpus Gemma MLX 12B runs pass complete coverage and semantic review, whichever is later. Then remove the v1 prompt/runtime path. Keep the compact-to-canonical adapter until downstream consumers migrate from `analyst_adjudication_v1`.
