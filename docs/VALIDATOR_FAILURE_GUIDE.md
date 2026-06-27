# Validator Failure Guide

This guide explains common failures from `scripts/validate_worked_regions.py` and how to fix them without weakening the artifact.

Run one region while developing:

```bash
PYTHONPATH=src python3 scripts/validate_worked_regions.py --region lhc_cosmic_ray_argument
PYTHONPATH=src python3 scripts/validate_worked_regions.py --region eggs_observational_vs_rct
```

Run the final gate:

```bash
PYTHONPATH=src python3 scripts/validate_worked_regions.py
PYTHONPATH=src python3 scripts/reproducibility_gate.py --include-worked-regions
```

## Failure Meanings

`template_not_filled`

The file still has `Status: template`. Replace template status with the actual artifact status, such as `Status: human-review-needed`.

`todo_remaining`

The file still contains a placeholder marker. Replace the placeholder with specific content or record the issue as a named limitation without using placeholder wording.

`required_source_missing`

The plan references a source ID that is not in the case manifest. Usually this means the source ID was mistyped or a `_pmc` filename was used instead of the manifest source ID.

`definition_missing_source`

The worked-region definition does not name every required source. Add the missing source to the source subset and explain its role.

`worked_map_claim_count`

The curated map has fewer than 12 or more than 25 `claim_id:` entries. Prefer 12-18 high-quality claims over padding.

`worked_map_missing_source_ids`

At least one claim lacks a `source_id:` field. Every claim needs a local manifest source ID.

`unknown_worked_map_source`

A claim cites a source ID not found in `case.yaml`. Use the manifest source ID, not the filename.

`worked_map_missing_excerpts`

At least one claim lacks an `excerpt:` field. Use a short source-grounded excerpt or paraphrased local cue tied to a line span.

`worked_map_missing_entailment_checks`

At least one claim lacks `entailed_by_excerpt:`. Mark each claim `yes`, `uncertain`, or `no`. Supported map claims should normally be `yes`.

`unsupported_claim_not_moved_to_audit`

A claim is marked `entailed_by_excerpt: no` but is still presented as part of the supported map. Revise the claim, mark it as an audit concern, or remove it.

`worked_map_missing_relations`

The map has no `relation_id:` entries. Add explicit support, caveat, dependency, tension, and crux relations.

`worked_map_too_few_relation_types`

The map uses fewer than three relation types. Add meaningful types only when supported by the sources.

`worked_map_missing_relation_rationales`

At least one relation lacks `rationale:`. Every relation needs a short explanation of why that edge is justified.

`worked_map_too_few_cruxes`

The map uses the word `crux` fewer than two times. Add real crux candidates, not decorative labels.

`worked_map_missing_flf_scores`

The map lacks a judge-facing FLF score table. Include at least four rows covering reasoning help, generalization, scaling, and compounding.

`worked_map_flf_score_zero`

One of the first four FLF score rows is zero. A zero means the worked region does not yet demonstrate that criterion.

`baseline_missing_prompt_version`

The flat baseline does not record `flat_baseline_prompt_v1`. Add the prompt version and exact prompt used.

`baseline_missing_isolation_note`

The flat baseline does not record whether the writer saw the curated map. Add `baseline_writer_had_access_to_curated_map: yes/no/uncertain`.

`baseline_missing_source`

The baseline does not list every required source. Add the fixed source subset; do not silently change the subset.

`baseline_too_short`

The baseline is too short to be a fair synthesis comparator. Expand it using only the fixed source subset.

`erosion_audit_too_few_losses`

The audit has fewer than five counted `loss_id:` entries. Add losses only if they survive adversarial checks.

`erosion_audit_too_few_surviving_checks`

Fewer than five losses include `adversarial_check: survives`. Borderline losses can be recorded but do not count.

`erosion_audit_missing_field`

At least five counted losses must include `lost_item:`, `source_support:`, `flat_baseline_omission:`, and `case_map_preserves:`.

`best_regions_missing_section`

The region's `BEST_REGIONS.md` lacks a judge pointer section. Add the missing section with a file path and short reason.

## Anti-Patterns

- Do not satisfy the validator by adding weak claims.
- Do not invent source support from memory.
- Do not use generated heuristic reports as final evidence.
- Do not count a loss if the baseline prompt did not ask for that kind of information.
- Do not claim human review unless a human has reviewed the specific artifact.
