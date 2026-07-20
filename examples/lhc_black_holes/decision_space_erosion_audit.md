# Illustrative LHC Decision-Space Erosion Audit

Status: `illustrative_non_evaluative`
Prompt/procedure: `erosion_audit_prompt_v1`

Baseline comparator: `examples/lhc_black_holes/flat_synthesis_baseline.md`
Map comparator: `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`

Interpretation limit: the baseline writer had access to the curated task
context. These findings illustrate the audit schema but are not model
performance evidence. Comparative claims should use the scripted blinded
baselines and `docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md`.

## Counted Losses

loss_id: lhc_loss_001

loss_type: `hidden dependency`

lost_item: The flat baseline says the velocity issue was studied but does not preserve the explicit dependence between low LHC product velocities, Earth trapping, and why Earth cosmic-ray survival alone is not the whole argument.

source_support: `lsag_2008_safety_review` lines 292-298; `giddings_mangano_2008_stable_black_holes` lines 3600-3641.

flat_baseline_omission: The baseline mentions slower LHC products in one sentence without the trapping mechanism or relation to the natural-exposure proof.

case_map_preserves: `lhc_c004`, `lhc_c012`, `lhc_r003`, `lhc_r004`, `lhc_r016`.

adversarial_check: survives, because the caveat is in the fixed source subset and directly affects the strength of the cosmic-ray analogy.

loss_id: lhc_loss_002

loss_type: `scope collapse`

lost_item: The flat baseline treats compact-star evidence as one safety layer and loses the white-dwarf versus neutron-star split, including the stronger LHC-energy scope of white dwarfs and the broader but more assumption-dependent neutron-star argument.

source_support: `spc_2008_lsag_review` lines 130-137; `giddings_mangano_2008_stable_black_holes` lines 2415-2460.

flat_baseline_omission: The baseline lists white dwarfs and neutron stars together and says the technical arguments vary by assumptions, but it does not keep their different evidential roles navigable.

case_map_preserves: `lhc_c009`, `lhc_c011`, `lhc_r009`, `lhc_r014`.

adversarial_check: survives, because the distinction is source-supported and important for LHC-specific versus future-collider inference.

loss_id: lhc_loss_003

loss_type: `assumption stack flattened`

lost_item: The flat baseline says the ordinary expectation is rapid decay, but it does not preserve the full dangerous-scenario assumption stack: TeV-scale gravity, failed Hawking/general decay, retained Schwinger or neutralization effects, and worst-case substitution under uncertainty.

source_support: `spc_2008_lsag_review` lines 101-128; `giddings_mangano_2008_stable_black_holes` lines 2465-2477.

flat_baseline_omission: The baseline combines stable-black-hole assumptions into broad language about conservative worst cases rather than showing which assumptions must all hold.

case_map_preserves: `lhc_c005`, `lhc_c006`, `lhc_c008`, `lhc_r006`, `lhc_r007`, `lhc_r008`.

adversarial_check: survives, because the baseline prompt asked for important caveats where they affect the answer and this stack affects whether compact-star bounds need to be invoked.

loss_id: lhc_loss_004

loss_type: `critique collapsed`

lost_item: The flat baseline preserves that Plaga objected, but it compresses the objection into a generic metastable scenario and loses the specific white-dwarf stopping challenge based on semiclassical assumptions and possible smaller scattering cross sections.

source_support: `plaga_2008_metastable_black_holes` lines 439-471.

flat_baseline_omission: The baseline says Plaga challenged completeness but does not identify the stopping-premise target of that challenge.

case_map_preserves: `lhc_c014`, `lhc_r010`, `lhc_r015`.

adversarial_check: survives, because the specific objection is in the source subset and matters to whether the compact-star proof survives adversarial pressure.

loss_id: lhc_loss_005

loss_type: `response rationale weakened`

lost_item: The flat baseline reports that GM found Plaga's assumptions inconsistent but does not preserve the two separate response threads: a 23-order-of-magnitude power-output dispute and a challenge to Eddington-limited accretion/microcanonical assumptions.

source_support: `giddings_mangano_2008_comments_plaga` lines 61-105.

flat_baseline_omission: The baseline mentions an erroneous power calculation but does not show how the response splits into calculation, accretion, and literature/quotation objections.

case_map_preserves: `lhc_c015`, `lhc_c016`, `lhc_r011`, `lhc_r012`, `lhc_r013`.

adversarial_check: survives, because the response rationale determines whether the critique is merely institutionally rejected or technically answered.

loss_id: lhc_loss_006

loss_type: `similar claims merged`

lost_item: The flat baseline merges Earth, Sun, and broader stellar exposure into one natural-exposure claim, making it harder to see how the observational base scales from Earth-specific reassurance to wider astronomical constraints.

source_support: `lsag_2008_safety_review` lines 175-207; `spc_2008_lsag_review` lines 43-65.

flat_baseline_omission: The baseline gives examples of astronomical survival but does not preserve Earth exposure, solar exposure, and universe-wide exposure as distinct support nodes.

case_map_preserves: `lhc_c001`, `lhc_c002`, `lhc_c003`, `lhc_c007`, `lhc_r001`, `lhc_r002`, `lhc_r005`.

adversarial_check: survives, because the source subset explicitly separates these scales and they affect how robust the analogy appears.

## Borderline Or Rejected Losses

- Not counted: The baseline does not discuss current post-2010 CMS searches, because those sources are outside this fixed worked-region subset.
- Not counted: The baseline does not evaluate legal or public-risk governance implications, because the Johnson legal source is optional context and not part of the fixed subset.
