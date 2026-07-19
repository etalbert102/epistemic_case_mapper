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
- automated map-vs-baseline stress evaluation
- reference checks for model-generated eval findings
- cross-backend disagreement summaries
- built-in metamorphic test inventory
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
- map-vs-flat-baseline insight-delta proposals
- relation-usefulness proxy judgments
- metamorphic pressure-test proposals
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

Run automated LLM stress evaluation over a worked region:

```bash
ecm eval llm-stress --region <region_id> --backend ollama:<model>
```

Run the same prompts against additional backends to surface disagreement:

```bash
ecm eval llm-stress \
  --region <region_id> \
  --backend ollama:gemma4:26b \
  --compare-backend ollama:qwen3:8b \
  --compare-backend ollama:phi4:14b
```

Use `--backend prompt` to write the stress prompts without model calls. This is useful for CI and for inspecting exactly what the evaluation asks.

Test whether stress actually improves synthesis rather than merely producing plausible critique:

```bash
PYTHONPATH=src python3 scripts/run_synthesis_uplift_eval.py \
  --region <region_id> \
  --backend ollama:<model> \
  --judge-backend ollama:<model>
```

This compiles erosion-audit losses into validated rewrite requirements, anchors them to map claims, relations, and source refs, then compares a map-only synthesis with a map-plus-stress synthesis. Deterministic coverage is treated as the primary safety signal; model judgments are retained as noisy comparison evidence.

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

## Automated Stress Evaluation

`ecm eval llm-stress` uses LLMs to propose stress signals, then deterministic code records and checks those signals. It emits:

- `llm_stress_eval.json`
- `LLM_STRESS_EVAL.md`
- prompt files
- raw model outputs
- parsed model outputs when JSON is valid

The evaluation prompts cover:

- insight deltas between the map and the flat baseline
- adversarial critique for unsupported confidence, rhetoric-as-evidence, missing caveats, and source-status confusion
- relation usefulness as distinct from relation schema validity
- metamorphic pressure tests for caveat injection, counterexample injection, loaded language, source-order shuffle, and source removal

The deterministic layer checks whether model findings cite known claim IDs, relation IDs, source IDs, and baseline excerpts. A finding with an invalid ID or missing baseline excerpt is retained as a model/backend weakness rather than silently accepted.

The synthesis uplift harness adds another gate: stress findings may only improve synthesis through map-anchored rewrite requirements. Requirements include claim anchors, relation anchors, source refs, coverage terms, and directional phrases. If a model draft misses or reverses a required mapped distinction, the harness attempts a repair and then applies a narrow deterministic patch as a last resort.

## Boundary

The deterministic starter mapper remains useful for reproducible scaffolding and regression tests. It is not the preferred production path for high-quality unseen-case maps. For serious packages, use the semantic prompt/validate loop, then run package and quality gates.
