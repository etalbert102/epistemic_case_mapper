# LLM And Deterministic Work Split

Status: `implemented-core`

The optimal split is: models propose semantic structure; deterministic code constrains, validates, compares, packages, and makes uncertainty visible.

## Deterministic Code Owns

- source ingestion into stable source IDs and local source text
- source provenance metadata and quality warnings
- prompt construction from bounded source packets
- stable package/region configuration
- schema and JSON parsing
- source ID, span, and excerpt checks
- relation ontology enforcement
- package validation and freshness checks
- baseline isolation
- review checklist generation
- UI and reviewer-start generation
- generated quality risk tasks

## LLMs Own

- candidate claim extraction
- claim normalization
- relation proposal
- crux discovery
- similar-but-not-identical distinctions
- erosion-audit drafting
- adversarial critique of a candidate map
- source-upgrade and "what would change my mind" suggestions

LLM outputs remain candidates until deterministic validation and human review accept them.

## Commands

Render a source-bounded map prompt:

```bash
ecm semantic prompt map --region <region_id>
```

Render a critique prompt over a candidate map and flat baseline:

```bash
ecm semantic prompt critique --region <region_id> --map-path <candidate_map.json>
```

Validate a model-produced JSON worked map before using it as a package artifact:

```bash
ecm semantic validate map --region <region_id> --path <candidate_map.json>
```

Validate a model-produced critique:

```bash
ecm semantic validate critique --path <candidate_critique.json>
```

## Candidate Map Requirements

Semantic map candidates use `json_case_map_v1` fields:

- `title`
- `status`
- `prompt_procedure: source_mapping_prompt_v2_json`
- `evidence_mode: source_grounded`
- `sources`
- `claims`
- `relations`
- `crux_candidates`
- `similar_but_not_identical`
- `evidence_check`

The validator requires each claim to have a source ID, span, exact excerpt found in the local source text, entailment status, and role. Relation endpoints must point to known claims, and relation types must be allowed or defined in the package relation ontology.

## Candidate Critique Requirements

Semantic critiques use:

- `title`
- `status`
- `prompt_procedure: semantic_critique_prompt_v1_json`
- `findings`

Each finding has:

- `finding_id`
- `severity`
- `category`
- `target_id`
- `issue`
- `source_basis`
- `recommended_fix`

This keeps adversarial model work structured enough to feed quality warnings and follow-up tasks.

## Boundary

The deterministic starter mapper remains useful for reproducible scaffolding and regression tests. It is not the preferred production path for high-quality unseen-case maps. For serious packages, use the semantic prompt/validate loop, then run package and quality gates.
