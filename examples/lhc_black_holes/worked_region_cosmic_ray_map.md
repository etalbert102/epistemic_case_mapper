# LHC Worked Region: Cosmic-Ray Argument Map

Status: `human-review-needed`
Prompt/procedure: `source_mapping_prompt_v1`, `relation_extraction_prompt_v1`
Evidence mode: `source_grounded`
Review note: agent-curated from local source excerpts; human review has not occurred.

## Source Subset

- `lsag_2008_safety_review`
- `spc_2008_lsag_review`
- `giddings_mangano_2008_stable_black_holes`
- `plaga_2008_metastable_black_holes`
- `giddings_mangano_2008_comments_plaga`

## Curated Claims

claim_id: lhc_c001

source_id: lsag_2008_safety_review

source_span: `lines 119-138`

excerpt: "The Universe is replicating the total number of collisions to be made by the LHC... astronomical bodies withstand cosmic-ray bombardment... If some microscopic black holes were produced by the LHC, they would also have been produced by cosmic rays."

entailed_by_excerpt: yes

role: `core support`

claim: The LSAG cosmic-ray argument says LHC-scale dangerous products should already have appeared naturally, and astronomical survival constrains that danger.

claim_id: lhc_c002

source_id: lsag_2008_safety_review

source_span: `lines 175-183`

excerpt: "Over 3x1022 cosmic rays... equal to or greater than the LHC energy, have struck the Earth's surface... and the planet still exists."

entailed_by_excerpt: yes

role: `exposure evidence`

claim: Earth has already received many LHC-equivalent or higher-energy cosmic-ray collisions without catastrophic destruction.

claim_id: lhc_c003

source_id: lsag_2008_safety_review

source_span: `lines 193-207`

excerpt: "Nature has therefore already conducted the LHC experimental programme about one billion times... via the collisions of cosmic rays with the Sun... Cosmic rays have been hitting all these stars."

entailed_by_excerpt: yes

role: `exposure evidence`

claim: The cosmic-ray exposure argument extends beyond Earth to the Sun, Milky Way stars, and visible-universe stellar populations.

claim_id: lhc_c004

source_id: lsag_2008_safety_review

source_span: `lines 292-298`

excerpt: "One significant difference... any massive new particles produced by the LHC collisions will tend to have low velocities, whereas cosmic-ray collisions would produce them with high velocities."

entailed_by_excerpt: yes

role: `caveat`

claim: The cosmic-ray analogy has a velocity caveat because LHC products may be slower and more trappable than cosmic-ray products.

claim_id: lhc_c005

source_id: lsag_2008_safety_review

source_span: `lines 315-327`

excerpt: "There is broad consensus among physicists on the reality of Hawking radiation, but so far no experiment has had the sensitivity required to find direct evidence for it."

entailed_by_excerpt: yes

role: `theory caveat`

claim: Hawking radiation is treated as broadly accepted theory, but not directly experimentally detected in this context.

claim_id: lhc_c006

source_id: lsag_2008_safety_review

source_span: `lines 329-350`

excerpt: "Independently of the reasoning based on Hawking radiation... the expected lifetime would be very short... stable microscopic black hole... would require a violation of some of the basic principles of quantum mechanics... and/or of general relativity."

entailed_by_excerpt: yes

role: `independent support`

claim: LSAG offers a decay argument independent of Hawking radiation and says stable microscopic black holes require suppressing basic quantum or relativistic principles.

claim_id: lhc_c007

source_id: spc_2008_lsag_review

source_span: `lines 43-65`

excerpt: "The results and the considerations given in this section are the basis for the safety proofs... irreconcilable with the fact that the Earth, the Sun and other objects... have persisted."

entailed_by_excerpt: yes

role: `independent endorsement`

claim: The SPC review treats the cosmic-ray comparison as the basis for later safety proofs and endorses the survival-of-astronomical-bodies inference.

claim_id: lhc_c008

source_id: spc_2008_lsag_review

source_span: `lines 101-128`

excerpt: "A number of increasingly unlikely conditions should be satisfied... fundamental scale of gravity... Hawking radiation... should fail... Schwinger mechanism... should still work... conservative or 'worst-case' scenario."

entailed_by_excerpt: yes

role: `dependency stack`

claim: The dangerous stable-black-hole scenario depends on an unlikely assumption stack, including TeV-scale gravity, failed decay mechanisms, and retained neutralization physics.

claim_id: lhc_c009

source_id: spc_2008_lsag_review

source_span: `lines 130-137`

excerpt: "At the LHC energy... ruled out... by... white dwarf stars... valid for the LHC... future colliders... neutron stars... relies on properties of cosmic rays and neutrinos that... require confirmation."

entailed_by_excerpt: yes

role: `scope limit`

claim: The SPC review distinguishes stronger white-dwarf bounds for LHC energies from neutron-star arguments that matter for higher energies but depend on cosmic-ray and neutrino assumptions.

claim_id: lhc_c010

source_id: giddings_mangano_2008_stable_black_holes

source_span: `lines 2402-2411`

excerpt: "Cosmic rays will produce black holes on such astronomical objects... accreting black holes will disrupt such objects... white dwarf ages exceeding 10^9 years... scenarios... are ruled out."

entailed_by_excerpt: yes

role: `compact-star support`

claim: GM argue that scenarios dangerous to Earth would disrupt white dwarfs faster than their observed lifetimes, so those scenarios are ruled out.

claim_id: lhc_c011

source_id: giddings_mangano_2008_stable_black_holes

source_span: `lines 2415-2460`

excerpt: "D = 5... contrary to observations... D = 7... contrary to observation... D >= 8... neutron stars... provide therefore additional evidence."

entailed_by_excerpt: yes

role: `model split`

claim: GM split the compact-star argument by dimensionality, using white dwarfs for lower-dimensional cases and neutron stars as additional evidence for higher-dimensional cases.

claim_id: lhc_c012

source_id: giddings_mangano_2008_stable_black_holes

source_span: `lines 3600-3641`

excerpt: "For a black hole to get trapped... its speed should not exceed the escape velocity... Earth density does not provide enough material to stop a highly relativistic black hole, such as those produced by cosmic rays... some slow-down will typically arise for non-relativistic black holes produced at the LHC."

entailed_by_excerpt: yes

role: `trapping caveat`

claim: GM explicitly analyze the trapping difference: highly relativistic cosmic-ray black holes are hard to stop in Earth, while non-relativistic LHC black holes may slow and be captured.

claim_id: lhc_c013

source_id: plaga_2008_metastable_black_holes

source_span: `lines 18-31`

excerpt: "A plausible scenario... accrete ambient matter at the Eddington limit... remain undetectable in existing astrophysical observations and thus evade... Giddings & Mangano... different initial assumptions."

entailed_by_excerpt: yes

role: `challenge`

claim: Plaga argues that a metastable Eddington-limited scenario might evade GM-style astrophysical exclusions because it starts from different microscopic-black-hole assumptions.

claim_id: lhc_c014

source_id: plaga_2008_metastable_black_holes

source_span: `lines 439-471`

excerpt: "This exclusion depends on... 'dangerous' mBHs are stopped in white dwarfs... based on an assumed validity of the semiclassical approximation... might have smaller scattering cross section... This would void G & M's exclusion."

entailed_by_excerpt: yes

role: `challenge`

claim: Plaga's strongest technical challenge is that GM's white-dwarf stopping argument may not cover quantum-gravity-regime black holes with smaller-than-semiclassical scattering cross sections.

claim_id: lhc_c015

source_id: giddings_mangano_2008_comments_plaga

source_span: `lines 61-90`

excerpt: "One readily finds... a negligible power output... differing by a factor of 10^23... inconsistent application... four-dimensional relationship between radius and mass... clearly wrong."

entailed_by_excerpt: yes

role: `response`

claim: GM respond that Plaga's dangerous power output follows from an inconsistent radius-mass calculation and differs from their estimate by 23 orders of magnitude.

claim_id: lhc_c016

source_id: giddings_mangano_2008_comments_plaga

source_span: `lines 91-105`

excerpt: "One can in fact not establish Eddington-limited accretion in a white dwarf... the bounds of that paper would apply... microcanonical picture... appears implausible... misquoted our paper."

entailed_by_excerpt: yes

role: `response`

claim: GM also argue that Plaga has not established Eddington-limited accretion, relies on an implausible microcanonical/Hawking split, and misrepresents GM's conservative-assumption stance.

## Relations

relation_id: lhc_r001

source_claim: `lhc_c002`

target_claim: `lhc_c001`

relation_type: supports

rationale: Earth exposure is a concrete instance of the broader LSAG natural-exposure argument.

relation_id: lhc_r002

source_claim: `lhc_c003`

target_claim: `lhc_c001`

relation_type: supports

rationale: Solar and stellar exposure increases the observational base beyond Earth alone.

relation_id: lhc_r003

source_claim: `lhc_c004`

target_claim: `lhc_c001`

relation_type: refines

rationale: The velocity difference specifies when the cosmic-ray analogy needs additional analysis.

relation_id: lhc_r004

source_claim: `lhc_c012`

target_claim: `lhc_c004`

relation_type: supports

rationale: GM's trapping analysis provides the technical version of the velocity caveat.

relation_id: lhc_r005

source_claim: `lhc_c007`

target_claim: `lhc_c001`

relation_type: supports

rationale: The independent SPC review endorses the same cosmic-ray proof structure.

relation_id: lhc_r006

source_claim: `lhc_c008`

target_claim: `lhc_c010`

relation_type: depends_on

rationale: Compact-star bounds become relevant only after the stable-black-hole assumption stack is entertained.

relation_id: lhc_r007

source_claim: `lhc_c005`

target_claim: `lhc_c008`

relation_type: in_tension_with

rationale: Hawking radiation is broadly accepted but undetected; the risk scenario requires treating that uncertainty as live.

relation_id: lhc_r008

source_claim: `lhc_c006`

target_claim: `lhc_c008`

relation_type: challenges

rationale: The independent decay argument makes the stable-black-hole assumption stack harder to satisfy.

relation_id: lhc_r009

source_claim: `lhc_c009`

target_claim: `lhc_c011`

relation_type: refines

rationale: SPC's white-dwarf/neutron-star scope distinction mirrors GM's dimensional split.

relation_id: lhc_r010

source_claim: `lhc_c014`

target_claim: `lhc_c010`

relation_type: challenges

rationale: Plaga targets the white-dwarf stopping premise used in GM's compact-star exclusion.

relation_id: lhc_r011

source_claim: `lhc_c013`

target_claim: `lhc_c015`

relation_type: in_tension_with

rationale: Plaga's metastable power-output scenario and GM's quantitative response cannot both be right as stated.

relation_id: lhc_r012

source_claim: `lhc_c015`

target_claim: `lhc_c013`

relation_type: challenges

rationale: GM directly attacks the calculation behind Plaga's proposed dangerous output.

relation_id: lhc_r013

source_claim: `lhc_c016`

target_claim: `lhc_c014`

relation_type: challenges

rationale: GM argues the Eddington-limited and microcanonical assumptions behind Plaga's claimed gap are not established.

relation_id: lhc_r014

source_claim: `lhc_c009`

target_claim: `lhc_c001`

relation_type: crux_for

rationale: The white-dwarf versus neutron-star scope is a crux for how far the safety argument can be extrapolated beyond the LHC.

relation_id: lhc_r015

source_claim: `lhc_c014`

target_claim: `lhc_c001`

relation_type: crux_for

rationale: If the white-dwarf stopping challenge survived, it would weaken a core observational layer of the cosmic-ray argument.

relation_id: lhc_r016

source_claim: `lhc_c004`

target_claim: `lhc_c012`

relation_type: similar_to

rationale: Both claims preserve the velocity/trapping distinction, with LSAG giving the high-level caveat and GM giving the technical analysis.

## Crux Candidates

- crux: Does the compact-star argument cover the relevant low-velocity LHC capture scenario once cosmic-ray products differ in velocity? Linked claims: `lhc_c004`, `lhc_c012`, `lhc_c010`.
- crux: Does Plaga's metastable/Eddington-limited scenario define a coherent physical gap in GM's bounds, or does GM's response defeat the calculation and assumptions? Linked claims: `lhc_c013`, `lhc_c014`, `lhc_c015`, `lhc_c016`.
- crux: Are white-dwarf observations sufficient for the LHC-energy risk question, while neutron-star arguments mainly affect broader extrapolation? Linked claims: `lhc_c009`, `lhc_c011`.

## Similar But Not Identical

- `lhc_c001`, `lhc_c002`, and `lhc_c003` are not duplicates: the first is the general inference, the second is Earth exposure, and the third widens the observational base.
- `lhc_c004` and `lhc_c012` both concern velocity, but `lhc_c004` states the caveat while `lhc_c012` explains the trapping/stopping mechanism.
- `lhc_c009` and `lhc_c011` both concern compact stars, but `lhc_c009` is a review-level scope judgment and `lhc_c011` is a dimensional technical split.
- `lhc_c013` and `lhc_c014` are related Plaga challenges, but one is the scenario-level risk claim and the other is the specific white-dwarf stopping objection.

## Audit Notes

- No claim in this map is marked human-reviewed.
- The baseline comparison is illustrative because this same Codex run had access to the curated-map task and source-packet orientation.
- The map intentionally preserves critique and response even though the bottom-line risk assessment remains strongly against catastrophic LHC danger.

## FLF Judge Questions

| Question | Score | Evidence | Residual risk |
| --- | ---: | --- | --- |
| Would this help someone reason better about this case? | 2 | It separates exposure, velocity caveat, compact-star bounds, assumption stack, critique, and response. | A physicist should review whether relation labels are technically fair. |
| Does it generalize? | 2 | The same pattern applies to other technical-risk arguments with analogies, caveats, and adversarial critiques. | Other domains may need richer quantitative uncertainty fields. |
| Does it scale with improvements to AI or more compute? | 2 | Better extraction can fill more source spans while preserving the same claim/relation protocol. | Automated relation typing remains a hard problem. |
| Does it compound with multiple people or teams? | 2 | Stable claim IDs, source IDs, and explicit cruxes let reviewers add objections without rewriting the artifact. | Human review workflow still needs actual reviewer decisions. |
