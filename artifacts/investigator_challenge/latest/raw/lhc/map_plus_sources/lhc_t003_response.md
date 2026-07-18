# Deterministic map_plus_sources Retrieval Proxy

Question: Which claims and sources carry the velocity/trapping transition?

The map condition can recover these frozen answer-key objects:

## velocity_to_trapping_transition

The velocity/trapping transition is carried by the caveat that LHC products may be slower than cosmic-ray products and by the compact-star bounds that address that caveat.

Claims:

- `lhc_c004` [lsag_2008_safety_review; caveat]: The cosmic-ray analogy has a velocity caveat because LHC products may be slower and more trappable than cosmic-ray products.
  - excerpt: "One significant difference... any massive new particles produced by the LHC collisions will tend to have low velocities, whereas cosmic-ray collisions would produce them with high velocities."
- `lhc_c012` [giddings_mangano_2008_stable_black_holes; trapping caveat]: GM explicitly analyze the trapping difference: highly relativistic cosmic-ray black holes are hard to stop in Earth, while non-relativistic LHC black holes may slow and be captured.
  - excerpt: "For a black hole to get trapped... its speed should not exceed the escape velocity... Earth density does not provide enough material to stop a highly relativistic black hole, such as those produced by cosmic rays... some slow-down will typically arise for non-relativistic black holes produced at the LHC."

Relations:

- `lhc_r003` (refines): `lhc_c004` -> `lhc_c001`. The velocity difference specifies when the cosmic-ray analogy needs additional analysis.
- `lhc_r004` (supports): `lhc_c012` -> `lhc_c004`. GM's trapping analysis provides the technical version of the velocity caveat.

Sources:

- `giddings_mangano_2008_stable_black_holes`
- `lsag_2008_safety_review`
