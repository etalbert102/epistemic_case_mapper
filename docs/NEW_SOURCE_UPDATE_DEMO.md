# New-Source Update Demo

Status: `human-review-needed`

Purpose: demonstrate the compounding workflow FLF asks for: a source can be added to an existing case artifact without rewriting the whole investigation.

## Demo Scope

This is a deterministic update demo using a source that is already acquired in the repository but was not part of the original LHC cosmic-ray worked region.

New-to-map source:

- `cern_lhc_current_page`
- File: `data/cases/lhc_black_holes/sources/text/cern_lhc_current_page.txt`
- Relevant spans: `lines 105-109`

Why this choice: the source is public-facing rather than technical. It tests whether the map can preserve the relationship between expert safety analysis and public communication without flattening them into one confidence claim.

## Before

The canonical LHC worked region used five technical sources:

- `lsag_2008_safety_review`
- `spc_2008_lsag_review`
- `giddings_mangano_2008_stable_black_holes`
- `plaga_2008_metastable_black_holes`
- `giddings_mangano_2008_comments_plaga`

The map preserved the technical dependency structure: cosmic-ray exposure, low-velocity trapping, compact-star bounds, Plaga's critique, and GM's response.

## Source Update

The CERN public page adds two public-facing claims:

claim_id: lhc_update_c001

source_id: cern_lhc_current_page

source_span: `lines 105-107`

excerpt: "The LHC can only reproduce phenomena that already happen naturally all around us... stars, galaxies and the Earth still exist."

entailed_by_excerpt: yes

role: `public safety synthesis`

claim: CERN's public FAQ compresses the LHC safety answer into a natural-phenomena analogy and survival observation.

claim_id: lhc_update_c002

source_id: cern_lhc_current_page

source_span: `lines 108-109`

excerpt: "According to Einstein's theory of relativity, it is impossible for LHC to produce black holes... speculative theories predict... microscopic black holes... disintegrate immediately."

entailed_by_excerpt: yes

role: `public black-hole synthesis`

claim: CERN's public black-hole answer separates standard relativity from speculative microscopic-black-hole theories and states that speculative microscopic black holes would immediately disintegrate.

## Relation Update

relation_id: lhc_update_r001

source_claim: `lhc_update_c001`

target_claim: `lhc_c001`

relation_type: compresses

rationale: The public FAQ carries the same broad natural-exposure reassurance as `lhc_c001`, but it does not expose the low-velocity trapping and compact-star dependency structure preserved by `lhc_c004`, `lhc_c009`, `lhc_c010`, `lhc_c011`, and `lhc_c012`.

relation_id: lhc_update_r002

source_claim: `lhc_update_c002`

target_claim: `lhc_c005`

relation_type: reframes

rationale: The public FAQ states immediate disintegration as the public-facing bottom line, while `lhc_c005` preserves the worked-region caveat that Hawking radiation is broadly accepted but not directly experimentally detected in this context.

## After

The update adds a public-communication layer rather than changing the technical conclusion. The decision-space-preserving move is to mark public-facing claims as compressed syntheses of deeper technical structure, not as replacements for that structure.

## Reviewer Tasks

- Check whether the public FAQ excerpts are faithfully represented.
- Decide whether `compresses` is the right relation label for `lhc_update_r001`.
- Decide whether the public FAQ should be part of the canonical LHC worked map or only the full-case public-communication cluster.
- Compare this update with `examples/lhc_black_holes/full_case_map.md`, cluster `lhc_full_cluster_008`.

## What This Demonstrates

Another investigator can add a source, identify the affected claims, relate it to existing map nodes, and create targeted review tasks without regenerating the entire case artifact.
