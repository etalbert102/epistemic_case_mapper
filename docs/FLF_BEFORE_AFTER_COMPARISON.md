# FLF Before/After Comparison

Status: `human-review-needed`

Purpose: give judges a compact way to see the prototype's central claim: ordinary synthesis can be useful and broadly correct while still eroding the decision space an investigator needs to audit.

## What Counts As An Improvement

The map is not better because it is longer. It is better only when it preserves a distinction that changes what a reviewer can inspect, challenge, extend, or decide.

Count a before/after improvement when the map preserves at least one of:

- a source boundary,
- an option or frame,
- a caveat that changes the scope of a conclusion,
- a dependency between claims,
- a live disagreement or critique,
- a crux that would change the assessment,
- similar-but-not-identical claims that should not be merged.

## LHC Worked Region

Question: does the cosmic-ray safety argument, including compact-star variants and critiques, rule out decision-relevant LHC microscopic-black-hole risk?

Before: flat synthesis.

- File: `examples/lhc_black_holes/flat_synthesis_baseline.md`
- The baseline gives the right broad answer: natural cosmic-ray exposure and compact-star observations are strong evidence against decision-relevant risk.
- The weakness is that the answer compresses why the cosmic-ray analogy needed extra work. Earth cosmic-ray survival is not the whole argument once low-velocity LHC products and possible trapping are considered.

After: decision-space-preserving map.

- File: `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`
- The map keeps Earth/Sun exposure, low-velocity trapping, compact-star bounds, white-dwarf versus neutron-star scope, Plaga's stopping critique, and GM's response as separate nodes.
- A reviewer can inspect whether each node is source-grounded and whether the support/challenge/dependency relation is fair.

Fast check:

- Open `examples/lhc_black_holes/decision_space_erosion_audit.md`.
- Inspect `lhc_loss_001`, `lhc_loss_002`, `lhc_loss_005`, and `lhc_loss_006`.
- Compare those against the multi-model baseline audit in `docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md`.

Result: the LHC example demonstrates decision-space preservation most strongly for dependency structure and critique/response structure.

## Eggs Worked Region

Question: how should a synthesis preserve the relationship between observational CVD outcome evidence, randomized lipid-marker evidence, guideline framing, and population/context caveats for egg consumption?

Before: flat synthesis.

- File: `examples/eggs/flat_synthesis_baseline.md`
- The baseline is reasonable: it says moderate intake is often treated as acceptable but evidence varies by study design, dose, and population.
- The weakness is that normal nutrition prose tends to merge outcome evidence, marker evidence, guideline language, subgroup caveats, and replacement-food logic.

After: decision-space-preserving map.

- File: `examples/eggs/worked_region_observational_vs_rct_map.md`
- The map separates observational CVD endpoints from randomized lipid-marker endpoints, keeps BMJ/JAMA differences reviewable, distinguishes guideline-process claims from outcome claims, and preserves NNR evidence-grade limits.
- A reviewer can dispute individual claims without losing the whole synthesis.

Fast check:

- Open `examples/eggs/decision_space_erosion_audit.md`.
- Inspect `eggs_loss_003`, `eggs_loss_005`, `eggs_loss_006`, and `eggs_loss_007`.
- Compare those against the multi-model baseline audit in `docs/review/MULTI_MODEL_BLINDED_BASELINE_AUDIT.md`.

Result: the eggs example demonstrates decision-space preservation most strongly for evidence-grade boundaries, guideline-process provenance, and scope distinctions around moderate egg intake.

## COVID Worked Region

Question: how should a synthesis preserve disagreement about Bayesian weighting, early-case geography, and post-debate updates without pretending to settle the full COVID origins question?

Before: flat synthesis.

- File: `examples/covid_origins_slice/flat_synthesis_baseline.md`
- The baseline is reasonable: it says the judges and superforecasters leaned zoonotic while Rootclaim, Levin, and Weissman kept lab-leak-favoring arguments alive.
- The weakness is that normal prose tends to collapse debate outcome, process critique, substantive posterior disagreement, source-status caveats, and subargument boundaries into one narrative.

After: decision-space-preserving map.

- File: `examples/covid_origins_slice/worked_region_bayesian_disagreement_map.md`
- The map keeps the debate result, Rootclaim postmortem, aggregate forecast, minority forecast distribution, formal Bayesian decomposition, early-case geography assumptions, methodological replies, and later phylogeny critique as separate review targets.
- A reviewer can inspect whether a claim is evidence, a methodological caveat, a process critique, a post-debate update, or a scope boundary.

Fast check:

- Open `examples/covid_origins_slice/decision_space_erosion_audit.md`.
- Inspect `covid_loss_001`, `covid_loss_004`, and `covid_loss_006`.
- Use `docs/review/COVID_HUMAN_AUDIT_PACKET.md` before treating any relation as reviewed.

Result: the COVID slice demonstrates decision-space preservation most strongly for live disagreement, Bayesian decomposition, and subargument scope control. It is deliberately narrow and should not be read as a full COVID origins assessment.

## Why Multi-Model Baselines Matter

The local model baselines show that flat synthesis quality varies by model family:

- `qwen3:8b` preserves more detail but sometimes over-synthesizes.
- `phi4:14b` is concise but loses many reviewable distinctions.
- `granite3.3:8b` preserves some source-specific details but still flattens important disagreements.
- `gemma4:e4b` is a stronger comparator than the original illustrative baseline and forces several erosion claims to be narrowed.

This improves the FLF posture because the claim is not that every summary is bad. The claim is that preservation is brittle and model-dependent unless the workflow exposes an audit surface for checking what survived.

## Judge Takeaway

The prototype contributes a practical measurement layer for the FLF contest:

1. Build a source-grounded map.
2. Produce a normal synthesis from the same source subset.
3. Audit which decision-relevant distinctions survived, flattened, disappeared, or distorted.
4. Use the map as a reusable artifact that another investigator can extend.
