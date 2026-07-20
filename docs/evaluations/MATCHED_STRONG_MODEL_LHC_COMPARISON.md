# Matched Strong-Model LHC Comparison

Status: reported single-run response, not an auditable control or benchmark

This comparison records a response to instructions asking a strong model to
recover the LHC dependency chain from the same source universe without seeing
the worked map, answer keys, erosion audit, or generated challenge artifacts.
The invocation transcript was not retained, so the isolation condition cannot
be independently verified.

Artifacts:

- prompt: `docs/evaluations/MATCHED_STRONG_MODEL_LHC_PROMPT.md`
- model answer: `docs/evaluations/MATCHED_STRONG_MODEL_LHC_ANSWER.md`

## Condition

Model: `gpt-5.6-sol` through Codex CLI.

Sources:

- `data/cases/lhc_black_holes/sources/text/lsag_2008_safety_review.txt`
- `data/cases/lhc_black_holes/sources/text/spc_2008_lsag_review.txt`
- `data/cases/lhc_black_holes/sources/text/giddings_mangano_2008_stable_black_holes.txt`
- `data/cases/lhc_black_holes/sources/text/plaga_2008_metastable_black_holes.txt`
- `data/cases/lhc_black_holes/sources/text/giddings_mangano_2008_comments_plaga.txt`

The prompt asked the same five substantive questions used to inspect the LHC challenge: Earth survival, compact bodies, velocity/trapping, Plaga's compact-star critique, and what would move the risk assessment.

## Result

The strong model produced a good source-grounded explanation. It recovered:

- the fixed-target velocity caveat,
- why white dwarfs and neutron stars matter,
- the production to stopping to compact-star chain,
- Plaga's quantum-regime stopping critique and metastable-radiation critique,
- the distinction between LSAG/GM/SPC's no-significant-risk conclusion and Plaga's residual-risk path.

The model also named what remained hard without structure: dimensional case splits, necessary premises versus conservative assumptions, and the separation between Plaga's different critiques.

## Interpretation

This narrows the prototype claim in a useful way. A strong model with all sources and a targeted prompt can reconstruct much of the dependency. The map's value is not that a model could never recover the argument. The value is that the dependency is already available as stable, inspectable objects:

- `lhc_c004` for the velocity caveat,
- `lhc_c012` for trapping,
- `lhc_r003` and `lhc_r004` for the dependency bridge,
- snapshot-restoration and prewritten-delta ledgers for change locality.

The comparison supports a narrower interpretation: the prototype is a review and compounding surface, not proof of prose superiority.

## Failure Boundary

This is one reported strong-model response on one source universe. It does not
settle model-vs-map performance and is not performance evidence. It helps set
the conservative claim boundary: decision-space persistence and stable object
addressability, with final prose quality and investigator performance treated
as separate evaluation layers.
