# Held-Out Source Map Diff

New source: `cern_lhc_current_page`

Added claims:

- `lhc_update_c001` [cern_lhc_current_page; public safety synthesis]: CERN's public FAQ compresses the LHC safety answer into a natural-phenomena analogy and survival observation.
  - excerpt: The LHC can only reproduce phenomena that already happen naturally all around us... stars, galaxies and the Earth still exist.
- `lhc_update_c002` [cern_lhc_current_page; public black-hole synthesis]: CERN's public black-hole answer separates standard relativity from speculative microscopic-black-hole theories and states that speculative microscopic black holes would immediately disintegrate.
  - excerpt: According to Einstein's theory of relativity, it is impossible for LHC to produce black holes... speculative theories predict... microscopic black holes... disintegrate immediately.

Added relations:

- `lhc_update_r001` (similar_to): `lhc_update_c001` -> `lhc_c001`. The public FAQ carries a compressed public-facing counterpart to the broad natural-exposure reassurance in `lhc_c001`, but it does not expose the low-velocity trapping and compact-star dependency structure preserved by `lhc_c004`, `lhc_c009`, `lhc_c010`, `lhc_c011`, and `lhc_c012`.
- `lhc_update_r002` (refines): `lhc_update_c002` -> `lhc_c005`. The public FAQ states immediate disintegration as the public-facing bottom line, while `lhc_c005` preserves the worked-region caveat that Hawking radiation is broadly accepted but not directly experimentally detected in this context.

Touched existing claims: `lhc_c001`, `lhc_c005`
