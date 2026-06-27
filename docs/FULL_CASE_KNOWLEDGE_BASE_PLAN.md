# Full-Case Knowledge Base Plan

Status: `implemented-scaffold`

Purpose: document how the prototype expands beyond worked-region anchors into broader full-case knowledge bases.

## Design Choice

The full-case maps are broad scaffolds, not fully audited case maps. They should show coverage, navigability, and compounding potential while clearly marking the existing worked regions as the deeper curated anchors.

## Artifact Shape

Each full case has:

- `full_case_index.md`: source coverage, cluster index, and human review path.
- `full_case_map.md`: broad source set, knowledge clusters, cross-cluster relations, cruxes, and remaining expansion work.

Current artifacts:

- `examples/lhc_black_holes/full_case_index.md`
- `examples/lhc_black_holes/full_case_map.md`
- `examples/eggs/full_case_index.md`
- `examples/eggs/full_case_map.md`

## Review Status Semantics

- `worked-region anchor`: more deeply curated, source-excerpt-grounded, and erosion-audited.
- `broad scaffold`: source-grounded at the manifest/metadata level, but not yet fully source-excerpt audited.

## FLF Value

The full-case scaffolds strengthen the contest submission by showing how the method moves from a hand-picked region to a reusable case-level knowledge base:

1. Every currently acquired source is represented.
2. Source roles are separated from evidence roles.
3. Correlated evidence clusters are visible.
4. Worked regions are placed inside broader maps.
5. Future contributors can expand one cluster without rewriting the whole case.

## Next Expansion Step

Full-case flat baselines now exist for LHC and eggs as illustrative, non-blinded comparison surfaces. The next high-value addition is a broader human-scored erosion audit that asks whether a normal whole-case synthesis preserves the same cluster structure.
