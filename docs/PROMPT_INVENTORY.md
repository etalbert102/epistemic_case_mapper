# Prompt Inventory

Purpose: make every AI-assisted or human-simulated procedure inspectable for FLF judges and future contributors.

Current status: the checked-in starter mapper is deterministic. The prompts below define the intended repeatable procedures for the worked-region stage; generated files must record which prompt or procedure was used.

## Source Mapping Prompt

Use when converting a full source subset into a curated worked-region map.

```text
You are building a source-grounded epistemic case map.

Question:
{worked_region_question}

Source excerpts:
{source_excerpts_with_ids}

Extract only claims directly supported by the source excerpts. For each claim, return:
- claim_id
- source_id
- exact local excerpt
- normalized source span if available
- claim text
- claim type: evidence, inference, caveat, constraint, option, crux, or open question
- entailed_by_excerpt: yes, no, or uncertain
- review_state: source_supported, interpretation_candidate, or human_review_needed

Do not merge similar-but-not-identical claims. Preserve caveats, uncertainty, minority views, and source-level disagreement.
```

Executable prompt builder:

```bash
ecm semantic prompt map --region <region_id>
```

The executable prompt uses `source_mapping_prompt_v2_json` and requires JSON output that can be checked with:

```bash
ecm semantic validate map --region <region_id> --path <candidate_map.json>
```

## Relation Extraction Prompt

Use after candidate claims have source excerpts.

```text
Given the source-grounded claims below, identify relationships that help an investigator reason about the case.

Allowed relation types:
- supports
- challenges
- refines
- similar_to
- depends_on
- crux_for
- in_tension_with

For each relation, provide source_claim_id, target_claim_id, relation_type, and a one-sentence rationale. Do not create a relation unless both endpoints are source-grounded or explicitly marked as interpretation candidates.
```

Relation extraction is now folded into the JSON semantic map candidate. Deterministic validation checks relation endpoints and package relation ontology.

## Flat Baseline Prompt

Use for controlled flat-synthesis comparisons.

```text
Using only the listed source excerpts for this worked region, write a concise synthesis that answers the region question for an informed reader. Preserve important caveats where they affect the answer, but do not create a structured claim map.
```

Baseline files must record:

- the source subset,
- the prompt version,
- whether the baseline writer had access to the curated map,
- any isolation limitation.

## Blinded Ollama Baseline Procedure

Use when generating a flat baseline from a local model without exposing the curated map or erosion audit.

Command shape:

```bash
PYTHONPATH=src python3 scripts/run_blinded_baselines.py --model gemma4:e4b --case all
```

The runner builds prompts only from raw source text line spans configured in `scripts/run_blinded_baselines.py`. The prompt excludes curated maps, erosion audits, `BEST_REGIONS.md`, judge walkthroughs, and source-packet crux/loss guidance.

Blinded baseline files must record:

- model name,
- generated timestamp,
- source subset,
- source spans used,
- prompt version,
- `baseline_writer_had_access_to_curated_map: no`,
- span-limited baseline limitation.

## External Deep Research Baseline

Use when comparing the mapper against an off-the-shelf retrieval-plus-synthesis workflow. The recorded eggs / dietary cholesterol baseline prompt is in `docs/protocols/DEEP_RESEARCH_EGGS_BASELINE_PROMPT.md`.

This baseline should be run blind: do not expose the curated map, quality report, stress output, or config profile. Save both the final Deep Research report and the retrieved source list. For controlled comparison, run the mapper on the same retrieved documents with the same question.

## Decision-Space Erosion Audit Prompt

Use after the flat baseline and curated map are fixed.

```text
Compare the flat synthesis against the frozen source-grounded case map.

Identify only decision-space erosion losses that survive this adversarial check:
- Was the missing item inside the same source subset?
- Was the missing item decision-relevant to the region question?
- Could a concise synthesis reasonably omit it without reducing the reader's ability to reason?

For each counted loss, record:
- lost item
- loss type: option, frame, conflict, dependency, caveat, source provenance, population/context heterogeneity, or crux
- source support
- what the case map preserved
- adversarial check result

Do not count unsupported map items or baseline omissions outside the source subset.
```

For adversarial critique of a candidate map before accepting it, use:

```bash
ecm semantic prompt critique --region <region_id> --map-path <candidate_map.json>
ecm semantic validate critique --path <candidate_critique.json>
```

## Human Review Handoff Prompt

Use when asking a human reviewer to audit a worked region.

```text
Review this worked-region packet as an external auditor.

For each claim, check whether the excerpt entails the claim. For each relation, check whether the rationale follows from the linked claims. For each erosion finding, check whether the baseline comparison is fair.

Return decisions as:
- accept
- revise
- reject
- needs_discussion

Do not mark the artifact human-reviewed unless every required decision has a recorded reviewer note or explicit no-issue finding.
```

## Procedure Tags

Use these tags in generated or curated artifacts:

- `deterministic_marker_sentence_v1`: local deterministic starter extraction.
- `source_mapping_prompt_v1`: source-grounded claim mapping prompt above.
- `source_mapping_prompt_v2_json`: executable JSON semantic map prompt built by `ecm semantic prompt map`.
- `relation_extraction_prompt_v1`: relation extraction prompt above.
- `flat_baseline_prompt_v1`: flat baseline prompt above.
- `flat_baseline_prompt_v1_blinded_ollama`: blinded local Ollama baseline procedure above.
- `deep_research_eggs_retrieval_baseline_v1`: external Deep Research baseline prompt for the eggs / dietary cholesterol case.
- `erosion_audit_prompt_v1`: decision-space erosion audit prompt above.
- `semantic_critique_prompt_v1_json`: executable JSON critique prompt built by `ecm semantic prompt critique`.
- `human_review_handoff_v1`: human review procedure above.
