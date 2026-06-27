# LHC Cosmic-Ray Argument Worked Region

Status: `template`

## Narrow Question

Which assumptions make the natural cosmic-ray analogue relevant to LHC microscopic-black-hole risk?

## Fixed Source Subset

Use only these sources unless a blocker is recorded and the user authorizes source acquisition:

- `lsag_2008_safety_review`
- `spc_2008_lsag_review`
- `giddings_mangano_2008_stable_black_holes`
- `plaga_2008_metastable_black_holes`
- `giddings_mangano_2008_comments_plaga`

Optional supporting context, not required for the curated map:

- `cern_lhc_current_page`
- `cern_tiny_black_holes_page`
- `johnson_2009_black_hole_case`

## Why This Region Matters

This is the strongest LHC slice because the conclusion depends on an argument structure, not only a headline safety claim. A flat synthesis can say "cosmic rays already do this naturally" while hiding the dependencies that make that analogy valid or contested.

## Expected Cruxes

- Whether natural cosmic-ray collisions cover the relevant LHC risk conditions.
- Whether stable or metastable microscopic black holes require separate treatment from evaporating black holes.
- Whether critique and response sources disagree about assumptions or only about framing.
- How astrophysical constraints support or limit the safety inference.

## What Ordinary Synthesis May Flatten

- Public reassurance versus technical argument.
- Institutional endorsement versus independent technical support.
- Critique and response.
- Stable-black-hole capture assumptions.
- The difference between direct evidence, physical theory, and astrophysical constraint.

## Completion Criteria

- [ ] Curated map exists at `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`.
- [ ] Flat baseline exists at `examples/lhc_black_holes/flat_synthesis_baseline.md`.
- [ ] Erosion audit exists at `examples/lhc_black_holes/decision_space_erosion_audit.md`.
- [ ] Best-region index exists at `examples/lhc_black_holes/BEST_REGIONS.md`.
- [ ] `PYTHONPATH=src python3 scripts/validate_worked_regions.py` passes.
