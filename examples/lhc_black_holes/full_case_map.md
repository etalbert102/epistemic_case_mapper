# LHC Black Hole Risk Full-Case Knowledge Map

Status: `broad-source-scaffold`
Evidence mode: `source_grounded_manifest_and_metadata`
Review note: broad full-case scaffold from all acquired sources; worked-region anchors are more deeply curated and should be trusted more than broad clusters until human review occurs.

## Source Set

- `lsag_2008_safety_review`
- `spc_2008_lsag_review`
- `giddings_mangano_2008_stable_black_holes`
- `cern_lhc_current_page`
- `cern_tiny_black_holes_page`
- `cms_2011_black_hole_search`
- `cms_2010_black_hole_search_paper`
- `plaga_2008_metastable_black_holes`
- `giddings_mangano_2008_comments_plaga`
- `johnson_2009_black_hole_case`

## Full-Case Thesis

The LHC black-hole safety case is not a single reassurance claim. It is a layered argument: institutional safety assessment, physical decay assumptions, stable-object worst-case analysis, astrophysical natural-exposure constraints, critique/response exchange, later empirical search evidence, public communication, and legal/governance framing.

## Knowledge Clusters

cluster_id: lhc_full_cluster_001

topic: Institutional safety conclusion

sources: `lsag_2008_safety_review`, `spc_2008_lsag_review`

decision_space_preserved: formal review and independent review should be separated from the underlying physics arguments they summarize or endorse.

map_status: broad scaffold

cluster_claim: LSAG provides the formal safety assessment, while SPC reviews and endorses that assessment with attention to scope and assumptions.

cluster_id: lhc_full_cluster_002

topic: Natural cosmic-ray exposure

sources: `lsag_2008_safety_review`, `spc_2008_lsag_review`, `giddings_mangano_2008_stable_black_holes`

decision_space_preserved: Earth, Sun, wider stellar exposure, velocity/trapping caveats, and compact-object extensions should remain separate.

map_status: worked-region anchor

cluster_claim: Natural high-energy collisions provide a central empirical constraint, but the collider-specific low-velocity/trapping issue requires additional analysis beyond a simple Earth-survival analogy.

anchor_claims: `lhc_c001`, `lhc_c002`, `lhc_c003`, `lhc_c004`, `lhc_c012`

cluster_id: lhc_full_cluster_003

topic: Hawking radiation and independent decay

sources: `lsag_2008_safety_review`, `spc_2008_lsag_review`, `cern_tiny_black_holes_page`

decision_space_preserved: rapid-decay arguments should be distinguished from stable-black-hole worst-case arguments.

map_status: broad scaffold

cluster_claim: The safety case includes the expectation that microscopic black holes would decay rapidly, but the stronger decision case also considers what follows if decay assumptions are suppressed.

cluster_id: lhc_full_cluster_004

topic: Stable black-hole worst-case assumptions

sources: `giddings_mangano_2008_stable_black_holes`, `spc_2008_lsag_review`, `lsag_2008_safety_review`

decision_space_preserved: worst-case reasoning depends on multiple assumptions that should not be flattened into "scientists considered the risk."

map_status: broad scaffold

cluster_claim: Stable dangerous scenarios require a stack of assumptions about TeV-scale gravity, suppressed decay, accretion, charge/neutralization behavior, and astrophysical survival constraints.

anchor_claims: `lhc_c005`, `lhc_c006`, `lhc_c008`

cluster_id: lhc_full_cluster_005

topic: Compact-star bounds

sources: `giddings_mangano_2008_stable_black_holes`, `spc_2008_lsag_review`

decision_space_preserved: white-dwarf and neutron-star arguments have different scope and assumption dependencies.

map_status: worked-region anchor

cluster_claim: Compact-object survival is a key observational layer for stable-black-hole scenarios, but the evidential role differs across white dwarfs and neutron stars.

anchor_claims: `lhc_c009`, `lhc_c010`, `lhc_c011`

cluster_id: lhc_full_cluster_006

topic: Critique and technical response

sources: `plaga_2008_metastable_black_holes`, `giddings_mangano_2008_comments_plaga`

decision_space_preserved: residual-risk critiques and technical rebuttals should remain reviewable instead of being compressed into "there was a dispute."

map_status: worked-region anchor

cluster_claim: Plaga challenges whether some metastable scenarios evade exclusions; GM respond that the scenario relies on inconsistent assumptions and unsupported accretion reasoning.

anchor_claims: `lhc_c013`, `lhc_c014`, `lhc_c015`, `lhc_c016`

cluster_id: lhc_full_cluster_007

topic: Later empirical searches

sources: `cms_2010_black_hole_search_paper`, `cms_2011_black_hole_search`

decision_space_preserved: non-observation in model searches is a later empirical update, not the same thing as the original catastrophic-risk proof.

map_status: broad scaffold

cluster_claim: CMS searches provide model-specific empirical evidence that no microscopic-black-hole signatures were observed in the tested ranges, supporting the public settled picture without replacing the safety proof.

cluster_id: lhc_full_cluster_008

topic: Public communication

sources: `cern_lhc_current_page`, `cern_tiny_black_holes_page`, `cms_2011_black_hole_search`

decision_space_preserved: public-facing reassurance should be linked back to the technical layers it compresses.

map_status: broad scaffold

cluster_claim: Current CERN communication presents the settled public-facing view that LHC black-hole danger is not expected, while simplifying the technical dependencies.

cluster_id: lhc_full_cluster_009

topic: Legal and governance framing

sources: `johnson_2009_black_hole_case`

decision_space_preserved: legal burden-of-proof and public-risk questions are not physics evidence, but they explain why preserving the dispute structure matters.

map_status: broad scaffold

cluster_claim: Johnson reframes the LHC controversy as a problem of legal and institutional decision-making under speculative catastrophic risk, not just a physics question.

## Cross-Cluster Relations

relation_id: lhc_full_rel_001

source_cluster: `lhc_full_cluster_002`

target_cluster: `lhc_full_cluster_004`

relation_type: depends_on

rationale: Natural-exposure evidence becomes most decision-relevant after the stable-black-hole worst-case assumption stack is entertained.

relation_id: lhc_full_rel_002

source_cluster: `lhc_full_cluster_006`

target_cluster: `lhc_full_cluster_005`

relation_type: challenges

rationale: Plaga's critique targets whether compact-star stopping and accretion assumptions close all relevant scenarios.

relation_id: lhc_full_rel_003

source_cluster: `lhc_full_cluster_007`

target_cluster: `lhc_full_cluster_008`

relation_type: supports

rationale: Later CMS non-observation supports public communication but should be kept separate from original risk-proof logic.

relation_id: lhc_full_rel_004

source_cluster: `lhc_full_cluster_009`

target_cluster: `lhc_full_cluster_001`

relation_type: refines

rationale: Legal/governance sources ask how institutional conclusions should be handled under low-probability catastrophic uncertainty.

## Full-Case Cruxes

- Does the safety case remain strong after separating rapid-decay assumptions from stable-black-hole worst-case assumptions?
- How much independent evidential weight should be assigned to LSAG, SPC, and Giddings-Mangano given their correlated technical basis?
- Which parts of the safety case are empirical constraints, which are theoretical assumptions, and which are public communication?
- How should later CMS search non-observation update confidence without being mistaken for a direct proof of no catastrophic risk?
- What decision standard should institutions use for speculative catastrophic risks when public critics identify residual theoretical gaps?

## Worked-Region Anchor

The best current deep anchor is `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`. It gives source-level claims and relation rationales for `lhc_full_cluster_002`, `lhc_full_cluster_005`, and `lhc_full_cluster_006`.

## Remaining Expansion Work

- Add source-excerpt-level claims for public CERN pages.
- Add source-excerpt-level claims for CMS technical and public search evidence.
- Promote the draft Johnson legal/public-risk worked region into the canonical validated worked-region set after human/source review.
- Human-score the full-case flat baseline against this scaffold.
