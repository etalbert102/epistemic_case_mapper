# LHC black holes Map Packet

This packet exposes the reviewable case structure: sources, claims, relations, and crux candidates.

## Sources

- `lsag_2008_safety_review`
- `spc_2008_lsag_review`
- `giddings_mangano_2008_stable_black_holes`
- `plaga_2008_metastable_black_holes`
- `giddings_mangano_2008_comments_plaga`

## Claims

- `lhc_c001` [lsag_2008_safety_review; core support]: The LSAG cosmic-ray argument says LHC-scale dangerous products should already have appeared naturally, and astronomical survival constrains that danger.
- `lhc_c002` [lsag_2008_safety_review; exposure evidence]: Earth has already received many LHC-equivalent or higher-energy cosmic-ray collisions without catastrophic destruction.
- `lhc_c003` [lsag_2008_safety_review; exposure evidence]: The cosmic-ray exposure argument extends beyond Earth to the Sun, Milky Way stars, and visible-universe stellar populations.
- `lhc_c004` [lsag_2008_safety_review; caveat]: The cosmic-ray analogy has a velocity caveat because LHC products may be slower and more trappable than cosmic-ray products.
- `lhc_c005` [lsag_2008_safety_review; theory caveat]: Hawking radiation is treated as broadly accepted theory, but not directly experimentally detected in this context.
- `lhc_c006` [lsag_2008_safety_review; independent support]: LSAG offers a decay argument independent of Hawking radiation and says stable microscopic black holes require suppressing basic quantum or relativistic principles.
- `lhc_c007` [spc_2008_lsag_review; independent endorsement]: The SPC review treats the cosmic-ray comparison as the basis for later safety proofs and endorses the survival-of-astronomical-bodies inference.
- `lhc_c008` [spc_2008_lsag_review; dependency stack]: The dangerous stable-black-hole scenario depends on an unlikely assumption stack, including TeV-scale gravity, failed decay mechanisms, and retained neutralization physics.
- `lhc_c009` [spc_2008_lsag_review; scope limit]: The SPC review distinguishes stronger white-dwarf bounds for LHC energies from neutron-star arguments that matter for higher energies but depend on cosmic-ray and neutrino assumptions.
- `lhc_c010` [giddings_mangano_2008_stable_black_holes; compact-star support]: GM argue that scenarios dangerous to Earth would disrupt white dwarfs faster than their observed lifetimes, so those scenarios are ruled out.
- `lhc_c011` [giddings_mangano_2008_stable_black_holes; model split]: GM split the compact-star argument by dimensionality, using white dwarfs for lower-dimensional cases and neutron stars as additional evidence for higher-dimensional cases.
- `lhc_c012` [giddings_mangano_2008_stable_black_holes; trapping caveat]: GM explicitly analyze the trapping difference: highly relativistic cosmic-ray black holes are hard to stop in Earth, while non-relativistic LHC black holes may slow and be captured.
- `lhc_c013` [plaga_2008_metastable_black_holes; challenge]: Plaga argues that a metastable Eddington-limited scenario might evade GM-style astrophysical exclusions because it starts from different microscopic-black-hole assumptions.
- `lhc_c014` [plaga_2008_metastable_black_holes; challenge]: Plaga's strongest technical challenge is that GM's white-dwarf stopping argument may not cover quantum-gravity-regime black holes with smaller-than-semiclassical scattering cross sections.
- `lhc_c015` [giddings_mangano_2008_comments_plaga; response]: GM respond that Plaga's dangerous power output follows from an inconsistent radius-mass calculation and differs from their estimate by 23 orders of magnitude.
- `lhc_c016` [giddings_mangano_2008_comments_plaga; response]: GM also argue that Plaga has not established Eddington-limited accretion, relies on an implausible microcanonical/Hawking split, and misrepresents GM's conservative-assumption stance.

## Relations

- `lhc_r001` (supports): `lhc_c002` -> `lhc_c001`. Earth exposure is a concrete instance of the broader LSAG natural-exposure argument.
- `lhc_r002` (supports): `lhc_c003` -> `lhc_c001`. Solar and stellar exposure increases the observational base beyond Earth alone.
- `lhc_r003` (refines): `lhc_c004` -> `lhc_c001`. The velocity difference specifies when the cosmic-ray analogy needs additional analysis.
- `lhc_r004` (supports): `lhc_c012` -> `lhc_c004`. GM's trapping analysis provides the technical version of the velocity caveat.
- `lhc_r005` (supports): `lhc_c007` -> `lhc_c001`. The independent SPC review endorses the same cosmic-ray proof structure.
- `lhc_r006` (depends_on): `lhc_c008` -> `lhc_c010`. Compact-star bounds become relevant only after the stable-black-hole assumption stack is entertained.
- `lhc_r007` (in_tension_with): `lhc_c005` -> `lhc_c008`. Hawking radiation is broadly accepted but undetected; the risk scenario requires treating that uncertainty as live.
- `lhc_r008` (challenges): `lhc_c006` -> `lhc_c008`. The independent decay argument makes the stable-black-hole assumption stack harder to satisfy.
- `lhc_r009` (refines): `lhc_c009` -> `lhc_c011`. SPC's white-dwarf/neutron-star scope distinction mirrors GM's dimensional split.
- `lhc_r010` (challenges): `lhc_c014` -> `lhc_c010`. Plaga targets the white-dwarf stopping premise used in GM's compact-star exclusion.
- `lhc_r011` (in_tension_with): `lhc_c013` -> `lhc_c015`. Plaga's metastable power-output scenario and GM's quantitative response cannot both be right as stated.
- `lhc_r012` (challenges): `lhc_c015` -> `lhc_c013`. GM directly attacks the calculation behind Plaga's proposed dangerous output.
- `lhc_r013` (challenges): `lhc_c016` -> `lhc_c014`. GM argues the Eddington-limited and microcanonical assumptions behind Plaga's claimed gap are not established.
- `lhc_r014` (crux_for): `lhc_c009` -> `lhc_c001`. The white-dwarf versus neutron-star scope is a crux for how far the safety argument can be extrapolated beyond the LHC.
- `lhc_r015` (crux_for): `lhc_c014` -> `lhc_c001`. If the white-dwarf stopping challenge survived, it would weaken a core observational layer of the cosmic-ray argument.
- `lhc_r016` (similar_to): `lhc_c004` -> `lhc_c012`. Both claims preserve the velocity/trapping distinction, with LSAG giving the high-level caveat and GM giving the technical analysis.

## Crux Candidates

- crux: Does the compact-star argument cover the relevant low-velocity LHC capture scenario once cosmic-ray products differ in velocity? Linked claims: `lhc_c004`, `lhc_c012`, `lhc_c010`.
- crux: Does Plaga's metastable/Eddington-limited scenario define a coherent physical gap in GM's bounds, or does GM's response defeat the calculation and assumptions? Linked claims: `lhc_c013`, `lhc_c014`, `lhc_c015`, `lhc_c016`.
- crux: Are white-dwarf observations sufficient for the LHC-energy risk question, while neutron-star arguments mainly affect broader extrapolation? Linked claims: `lhc_c009`, `lhc_c011`.

## Similar But Not Identical

- `lhc_c001`, `lhc_c002`, and `lhc_c003` are not duplicates: the first is the general inference, the second is Earth exposure, and the third widens the observational base.
- `lhc_c004` and `lhc_c012` both concern velocity, but `lhc_c004` states the caveat while `lhc_c012` explains the trapping/stopping mechanism.
- `lhc_c009` and `lhc_c011` both concern compact stars, but `lhc_c009` is a review-level scope judgment and `lhc_c011` is a dimensional technical split.
- `lhc_c013` and `lhc_c014` are related Plaga challenges, but one is the scenario-level risk claim and the other is the specific white-dwarf stopping objection.
