# Mini Filled Example

Status: `format-example`

This is a tiny format example for a Codex goal run. It is intentionally too small to satisfy `scripts/validate_worked_regions.py`.

## Region

region_id: `example_lhc_velocity_caveat`

question: What structure should a map preserve when the cosmic-ray analogy is used to reason about LHC black-hole safety?

## Claims

claim_id: `EX_C1`

source_id: `lsag_2008_safety_review`

source_span: `lines 175-183`

excerpt: Earth has already received many cosmic-ray collisions at or above LHC-equivalent energies and still exists.

entailed_by_excerpt: yes

role: `support`

claim: Earth survival after long cosmic-ray exposure supports the safety argument for LHC-scale collisions.

claim_id: `EX_C2`

source_id: `lsag_2008_safety_review`

source_span: `lines 292-298`

excerpt: LHC products tend to have low velocities, while cosmic-ray products tend to have high velocities.

entailed_by_excerpt: yes

role: `caveat`

claim: The cosmic-ray analogy has a velocity caveat because LHC-produced massive particles may be more easily trapped than cosmic-ray products.

claim_id: `EX_C3`

source_id: `spc_2008_lsag_review`

source_span: `lines 130-137`

excerpt: White-dwarf evidence is treated as valid for LHC energies, while neutron-star arguments need further confirmation for broader energy ranges.

entailed_by_excerpt: yes

role: `scope-limit`

claim: The compact-star safety argument has different evidential scope for LHC energies and possible future higher-energy colliders.

## Relations

relation_id: `EX_R1`

source_claim: `EX_C2`

target_claim: `EX_C1`

relation_type: `caveats`

rationale: The velocity difference limits when Earth cosmic-ray exposure alone transfers to LHC-produced black holes.

relation_id: `EX_R2`

source_claim: `EX_C3`

target_claim: `EX_C1`

relation_type: `scope-limits`

rationale: The independent review treats compact-star evidence as stronger within the LHC energy range than for future-collider extrapolation.

## Example Erosion Finding

loss_id: `EX_L1`

lost_item: A flat synthesis says cosmic rays prove LHC safety but does not preserve the low-velocity trapping caveat.

source_support: `lsag_2008_safety_review` lines 292-298.

flat_baseline_omission: The caveat is absent from the hypothetical flat summary.

case_map_preserves: `EX_C2` and `EX_R1`.

adversarial_check: survives, because the caveat is in the same source subset and directly affects the strength of the analogy.
