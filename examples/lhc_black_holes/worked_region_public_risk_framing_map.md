# LHC Draft Worked Region: Public-Risk And Governance Framing

Status: `human-review-needed`
Prompt/procedure: `source_mapping_prompt_v1`, `relation_extraction_prompt_v1`
Evidence mode: `source_grounded`
Review note: draft extension artifact; not yet part of the canonical validated worked-region set.

## Source Subset

- `johnson_2009_black_hole_case`
- `cern_lhc_current_page`
- `cern_tiny_black_holes_page`
- `cms_2011_black_hole_search`
- `lsag_2008_safety_review`
- `spc_2008_lsag_review`

## Curated Claims

claim_id: lhc_public_c001

source_id: johnson_2009_black_hole_case

source_span: `lines 96-118`

excerpt: "The case-file is replete with the infinite and the unknowable... Erring on the side of caution would suspend a great scientific adventure... if we side with the experimenters... the planet itself will wink out of existence."

entailed_by_excerpt: yes

role: `decision context`

claim: Johnson frames the LHC dispute as a high-stakes decision problem where both false alarm and false reassurance have unusually large consequences.

claim_id: lhc_public_c002

source_id: johnson_2009_black_hole_case

source_span: `lines 145-155`

excerpt: "Traditional preliminary-injunction analysis begins to unravel... Evidentiary law regarding expert testimony collapses... jurists... are confronted with a kind of knowledge horizon."

entailed_by_excerpt: yes

role: `legal epistemology`

claim: Johnson argues that ordinary legal tools strain when the alleged harm is catastrophic and the scientific merits are difficult for courts to observe directly.

claim_id: lhc_public_c003

source_id: johnson_2009_black_hole_case

source_span: `lines 168-178`

excerpt: "I intend to provide a set of analytical and theoretical tools... courts need analytical methods that will allow for making fair and principled decisions despite the challenges."

entailed_by_excerpt: yes

role: `method proposal`

claim: Johnson's legal project is to develop analytical tools for principled decisions under extreme technological-risk uncertainty.

claim_id: lhc_public_c004

source_id: johnson_2009_black_hole_case

source_span: `lines 849-866`

excerpt: "The scientific issues... are exceedingly complicated... insiders against outsiders... arguments are commissioned in response to media attention and published to meet accelerator-program schedules."

entailed_by_excerpt: yes

role: `institutional caveat`

claim: Johnson characterizes the controversy as involving insider/outsider dynamics and time pressure around safety arguments.

claim_id: lhc_public_c005

source_id: johnson_2009_black_hole_case

source_span: `lines 1427-1450`

excerpt: "Faced with this potential gap... sought to bolster the cosmic-ray argument... Earth... could well be incapable of stopping any black holes... LHC-created black holes... could end up loitering."

entailed_by_excerpt: yes

role: `technical caveat translated`

claim: Johnson's public-risk account preserves the technical reason why the simple Earth cosmic-ray analogy was insufficient: trapping differs between cosmic-ray products and LHC products.

claim_id: lhc_public_c006

source_id: johnson_2009_black_hole_case

source_span: `lines 1474-1495`

excerpt: "neutron stars were helpful but not definitive... only white dwarfs could provide... empirical evidence... eight observed white dwarf stars... no risk of any significance whatsoever."

entailed_by_excerpt: yes

role: `technical dependency`

claim: Johnson emphasizes that the safety case narrowed to particular compact-star evidence rather than generic astronomical survival.

claim_id: lhc_public_c007

source_id: johnson_2009_black_hole_case

source_span: `lines 1521-1546`

excerpt: "LSAG proceeded to write a report... confirm, update and extend... LSAG Report's self-characterization was misleading... presented Earth's continuing existence as ruling out any danger."

entailed_by_excerpt: yes

role: `rhetorical escalation`

claim: Johnson argues that LSAG presented a broader Earth-survival assurance than the more specific Giddings-Mangano compact-star argument warranted.

claim_id: lhc_public_c008

source_id: johnson_2009_black_hole_case

source_span: `lines 1570-1624`

excerpt: "from insignificant to inconceivable to impossible... doing so instead on the basis of white dwarfs and neutron stars... characterization of the observational data as 'irrefutable' came from the SPC."

entailed_by_excerpt: yes

role: `rhetorical escalation`

claim: Johnson describes institutional review language as escalating from insignificant risk to stronger claims of impossibility or proof.

claim_id: lhc_public_c009

source_id: johnson_2009_black_hole_case

source_span: `lines 1630-1671`

excerpt: "Plaga's paper was less alarmist... focused specifically on... the Giddings and Mangano paper... did not exclude all possibilities of disaster."

entailed_by_excerpt: yes

role: `outside critique`

claim: Johnson treats Plaga as a relatively careful outsider critique focused on residual catastrophic risk rather than as merely alarmist opposition.

claim_id: lhc_public_c010

source_id: cern_lhc_current_page

source_span: `lines 105-109`

excerpt: "The LHC can only reproduce phenomena that already happen naturally... stars, galaxies and the Earth still exist... speculative theories predict... disintegrate immediately."

entailed_by_excerpt: yes

role: `public reassurance`

claim: CERN's current public FAQ gives a compact assurance based on natural phenomena, astronomical survival, and immediate disintegration under speculative microscopic-black-hole theories.

claim_id: lhc_public_c011

source_id: cern_tiny_black_holes_page

source_span: `lines 73-74`

excerpt: "If micro black holes do appear... they would disintegrate rapidly, in around 10 -27 seconds... events containing an exceptional number of tracks."

entailed_by_excerpt: yes

role: `public physics framing`

claim: CERN's tiny-black-hole page frames microscopic black holes as a detectable exotic-physics signal that would decay rapidly, not as a catastrophe mechanism.

claim_id: lhc_public_c012

source_id: cms_2011_black_hole_search

source_span: `lines 19-23`

excerpt: "No evidence for their production was found... excluded up to a black hole mass of 3.5-4.5 TeV... No experimental evidence... has been found."

entailed_by_excerpt: yes

role: `later experimental update`

claim: CMS later reported no evidence for microscopic black holes in searched 2010 collision data and excluded production in model-specific mass ranges.

## Relations

relation_id: lhc_public_r001

source_claim: `lhc_public_c005`

target_claim: `lhc_public_c010`

relation_type: refines

rationale: The technical trapping caveat qualifies the simple public-facing natural-phenomena analogy.

relation_id: lhc_public_r002

source_claim: `lhc_public_c006`

target_claim: `lhc_public_c010`

relation_type: refines

rationale: Compact-star evidence refines generic astronomical survival into a narrower support structure.

relation_id: lhc_public_r003

source_claim: `lhc_public_c007`

target_claim: `lhc_public_c008`

relation_type: supports

rationale: Johnson's account of LSAG broadening supports the broader claim of rhetorical escalation through institutional review.

relation_id: lhc_public_r004

source_claim: `lhc_public_c009`

target_claim: `lhc_public_c008`

relation_type: challenges

rationale: A careful outsider critique challenges the implication that review language alone settled every residual risk claim.

relation_id: lhc_public_r005

source_claim: `lhc_public_c011`

target_claim: `lhc_public_c010`

relation_type: supports

rationale: The tiny-black-hole page gives a more specific version of the public black-hole disintegration claim.

relation_id: lhc_public_r006

source_claim: `lhc_public_c012`

target_claim: `lhc_public_c010`

relation_type: refines

rationale: The CMS non-observation is later empirical context for public confidence, though it does not replace the safety argument.

relation_id: lhc_public_r007

source_claim: `lhc_public_c001`

target_claim: `lhc_public_c002`

relation_type: supports

rationale: Extreme stakes and epistemic difficulty motivate Johnson's claim that ordinary legal tools strain.

relation_id: lhc_public_r008

source_claim: `lhc_public_c002`

target_claim: `lhc_public_c003`

relation_type: supports

rationale: The failure mode in ordinary legal tools motivates the proposed need for special analytical methods.

## Crux Candidates

- Does public communication need to preserve the low-velocity/trapping caveat, or is the compact natural-phenomena reassurance adequate for nontechnical audiences?
- Does later CMS non-observation change the safety decision, or only the public evidence environment?
- Should Johnson's critique of rhetorical escalation be treated as a governance concern even if the technical conclusion remains stable?

## Similar But Not Identical

- "No risk of any significance," "no conceivable danger," "excluded any possibility," and "perfectly safe" are not equivalent confidence statements.
- Earth survival, compact-star survival, and CMS non-observation are different evidence types.
- Legal adequacy, public reassurance, and technical sufficiency are related but separate decision contexts.

## FLF Judge Questions

Scale: 0 means not demonstrated, 1 means partially demonstrated, and 2 means demonstrated enough to inspect as a draft extension.

| Criterion | Score | Rationale |
| --- | ---: | --- |
| Helps reasoning | 2 | Separates public reassurance from technical and legal decision layers. |
| Generalizes | 2 | Demonstrates mapping beyond technical evidence into governance framing. |
| Scales | 1 | Draft region is manually curated and needs validation before promotion. |
| Compounds | 2 | Adds a new layer without rewriting the cosmic-ray worked region. |
