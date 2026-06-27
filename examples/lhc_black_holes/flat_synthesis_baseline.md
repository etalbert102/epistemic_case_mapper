# LHC Flat Synthesis Baseline

Status: `human-review-needed`
Prompt/procedure: `flat_baseline_prompt_v1`

## Source Subset

- `lsag_2008_safety_review`
- `spc_2008_lsag_review`
- `giddings_mangano_2008_stable_black_holes`
- `plaga_2008_metastable_black_holes`
- `giddings_mangano_2008_comments_plaga`

## Prompt

```text
Using only the listed source excerpts for this worked region, write a concise synthesis that answers the region question for an informed reader. Preserve important caveats where they affect the answer, but do not create a structured claim map.
```

## Baseline Protocol Notes

- baseline_writer_had_access_to_curated_map: `yes`
- baseline_protocol_limitation: This baseline is illustrative rather than evaluative because the same Codex run had access to the curated-map task and source-packet orientation before this file was finalized.

## Baseline Output

The LHC black-hole safety argument rests mainly on the fact that nature has already produced collisions at or above LHC energies through ultra-high-energy cosmic rays. The LSAG review argues that the Earth, Sun, and many other astronomical bodies have been exposed to enormous numbers of such events over long timescales and still exist. The CERN Scientific Policy Committee endorsed this reasoning, noting that the survival of these bodies is difficult to reconcile with a scenario in which LHC-scale collisions could produce objects that catastrophically destroy matter.

For microscopic black holes, the ordinary expectation is that they would rapidly decay through Hawking radiation or related quantum-mechanical decay channels. Even if one assumes a conservative worst case in which black holes could be stable, the Giddings-Mangano analysis argues that dangerous scenarios would also lead cosmic-ray-produced black holes to be trapped in compact astronomical objects. White dwarfs and neutron stars have survived for long periods, so the relevant dangerous parameter ranges are treated as excluded by observation. The SPC review presents this as a stronger, more observationally grounded safety layer than relying on theory alone.

The argument does contain caveats. Cosmic-ray products are not exactly the same as LHC products, because products from cosmic-ray collisions can be highly relativistic while LHC products can be slower. The reviews say this issue has been studied and does not undermine the safety conclusion. The compact-star arguments are also technical and vary by assumptions about extra dimensions, black-hole production, accretion, cosmic-ray composition, and neutrinos.

Plaga challenged the completeness of the GM analysis by proposing a metastable black-hole scenario with Eddington-limited accretion that might evade existing astrophysical exclusions. Giddings and Mangano responded that the proposed scenario used inconsistent assumptions, including an erroneous power-output calculation differing by many orders of magnitude, and that Eddington-limited accretion was not established. On this source subset, the overall synthesis is that the cosmic-ray and compact-star arguments provide strong source-grounded reassurance for LHC operation, while the main decision-relevant caveats concern analogy conditions, compact-star scope, and the technical coherence of proposed metastable exceptions.
