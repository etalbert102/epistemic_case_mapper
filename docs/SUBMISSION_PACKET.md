# FLF Submission Packet

Status: `human-review-needed`

This is the judge-facing entry point. For the fastest path, start with `docs/START_HERE.md`; this packet records the fuller submission boundary.

## Core Claim

AI synthesis can be broadly correct while still erasing the structure a later investigator needs to audit: source boundaries, caveats, dependencies, cruxes, similar-but-not-identical claims, and live disagreements.

The prototype tests a simple alternative: preserve those elements as source-grounded map artifacts, compare them to ordinary flat syntheses, and audit what survived, flattened, disappeared, or distorted.

## Contest Reference Lineage

The contest reference examples are not just related work; they clarify the kind of epistemic labor this prototype is trying to support. Transparent Replications, Measurement Schmeasurement, construct-validity critiques of development RCTs, systems-theoretic safety work, Society Library-style perspective mapping, and structured analytic techniques all point toward the same need: make hidden mismatches inspectable before synthesis smooths them away.

This prototype translates that need into claim maps, relation maps, cruxes, caveats, and erosion audits. See `docs/REFERENCE_LINEAGE.md` for the compact mapping.

## One-Minute Example

Flat synthesis can say: "Cosmic-ray exposure shows LHC black-hole risk is ruled out."

That is broadly right, but it hides a dependency. Earth cosmic-ray survival is not the whole argument once LHC-produced objects may be slower and more trappable than cosmic-ray products.

The LHC map preserves the dependency as reviewable pieces:

- `lhc_c004`: the velocity caveat.
- `lhc_c012`: the trapping analysis.
- `lhc_r003` and `lhc_r004`: why compact-star arguments become relevant.

Why this matters: the map does not merely cite sources. It preserves the part of the reasoning a later reviewer would need to accept, challenge, or revise.

## What To Evaluate

Evaluate the submission against the full rubric in `docs/reference/flf_judging_rubric.md`. The shortest version is:

1. Epistemic uplift: do the maps help a thoughtful person reason better than ordinary synthesis or deep research?
2. Generalizability: does the workflow travel across differently shaped cases?
3. Compounding and shareability: can another investigator extend the artifact?
4. Scalability: does the approach improve with better models, more compute, or more reviewers?
5. Methodological transparency: are the workflow, tradeoffs, and uncertainties inspectable?
6. Adversarial robustness: does the method hold up under motivated reading and misleading sources?
7. Insight contribution: does the submission shift how judges think about AI-assisted epistemic work?

Do not evaluate it as a finished interactive product or a fully automated literature-review system. The current value is the workflow and audit surface.

## Three-Minute Path

Read these in order:

1. `docs/FLF_BEFORE_AFTER_COMPARISON.md`
2. `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`
3. `examples/lhc_black_holes/decision_space_erosion_audit.md`

For deeper review, continue with:

1. `examples/eggs/worked_region_observational_vs_rct_map.md`
2. `examples/eggs/decision_space_erosion_audit.md`
3. `examples/covid_origins_slice/worked_region_bayesian_disagreement_map.md`
4. `docs/FLF_SELF_ASSESSMENT_AND_LIMITATIONS.md`
5. `docs/GENERALIZABILITY_RED_TEAM.md`

Optional UI:

```bash
python3 -m http.server 8787
```

Then open `http://localhost:8787/ui/`. The UI is only an inspection surface; the Markdown and JSON artifacts are canonical.

## Run The Checks

From the repo root:

```bash
PYTHONPATH=src python3 scripts/run_flf_demo.py --skip-build
```

For the fuller local reproducibility check:

```bash
PYTHONPATH=src python3 scripts/reproducibility_gate.py --include-worked-regions
```

These commands validate checked-in examples, worked-region structure, blinded baselines, full-case scaffolds, UI references, and judge-path references. Passing validation means the package is reproducible and internally consistent. It does not mean the maps have been externally human-reviewed.

## Evidence In The Package

### LHC Black Holes

The LHC worked region tests whether a synthesis preserves the structure of the cosmic-ray safety argument. The map keeps separate:

- Earth, Sun, white-dwarf, neutron-star, and wider cosmic-exposure roles.
- The low-velocity/trapping caveat for LHC-produced objects.
- Hawking-radiation reasoning versus independent stable-black-hole arguments.
- Plaga's critique and Giddings/Mangano's response.

Primary files:

- `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`
- `examples/lhc_black_holes/flat_synthesis_baseline.md`
- `examples/lhc_black_holes/decision_space_erosion_audit.md`
- `examples/lhc_black_holes/BEST_REGIONS.md`

### Eggs And Health

The eggs worked region tests whether a synthesis preserves boundaries between observational outcome evidence, randomized lipid-marker evidence, guideline framing, and population caveats. The map keeps separate:

- Observational CVD endpoints versus randomized lipid markers.
- BMJ and JAMA findings as a live tension rather than a blended result.
- Guideline-process claims versus direct causal evidence.
- Baseline intake, substitution context, high-LDL guidance, diabetes caveats, and NNR evidence-grade limits.

Primary files:

- `examples/eggs/worked_region_observational_vs_rct_map.md`
- `examples/eggs/flat_synthesis_baseline.md`
- `examples/eggs/decision_space_erosion_audit.md`
- `examples/eggs/BEST_REGIONS.md`

### COVID Origins Slice

The COVID artifact is deliberately narrow. It tests whether a synthesis preserves Bayesian disagreement and subargument boundaries without pretending to settle COVID origins.

The map keeps separate:

- Debate outcome versus process critique.
- Aggregate forecast versus minority disagreement.
- Formal Bayesian decomposition assumptions.
- Early-case geography assumptions and later phylogeny critique.
- Subargument critique versus whole-case resolution.

Primary files:

- `examples/covid_origins_slice/worked_region_bayesian_disagreement_map.md`
- `examples/covid_origins_slice/flat_synthesis_baseline.md`
- `examples/covid_origins_slice/decision_space_erosion_audit.md`
- `examples/covid_origins_slice/BEST_REGIONS.md`

## Why This Is FLF-Relevant

The submission is about compounding epistemic work. A flat synthesis can be useful for immediate understanding, but it is hard for another person to revise locally. A case map gives future reviewers stable source IDs, claim IDs, relation IDs, excerpts, rationales, cruxes, and open questions.

The useful comparison is not "map good, summary bad." The useful comparison is: when a later reviewer needs to inspect a disputed distinction, which artifact still exposes the distinction as something reviewable?

## Current Boundary

What is demonstrated:

- Source-grounded worked-region maps.
- Structured claims, excerpts, relation rationales, cruxes, and open questions.
- Flat-synthesis erosion audits.
- Reproducible validation and baseline checks.
- Human-review packets and checklists.
- A generalizability red-team analysis that names where transfer is plausible, where it is under-proven, and how to test it.

What is not claimed:

- The artifacts are not human-reviewed.
- The maps are not exhaustive full-case adjudications.
- The COVID slice is not a full COVID origins case.
- The baselines are useful comparators, not final quantitative evidence.
- The UI is not an editor and does not persist review decisions.
- The method has not yet been independently applied by a second operator to a fresh, mundane contested case.

For the full risk register, use `docs/FLF_SELF_ASSESSMENT_AND_LIMITATIONS.md`. For human review, start with `docs/review/REVIEWER_START_HERE.md` and `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv`.
