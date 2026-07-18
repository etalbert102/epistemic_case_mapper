# FLF Submission Packet

Status: `human-review-needed`

This is the fuller submission boundary. For the fastest path, start with `docs/START_HERE.md`.

## Core Claim

AI synthesis can be broadly correct while still losing the structure a later investigator needs to audit: source boundaries, caveats, dependencies, cruxes, similar-but-not-identical claims, and live disagreements.

The prototype tests a simple alternative: treat the research output as an authority-bearing artifact. It records the retrieval boundary, normalizes source material into reviewable claims, constructs a decision space of options and dependencies, turns claims and relations into judgment anchors, preserves artifact fidelity across synthesis and update, and gives reviewers local operational authority to accept, revise, reject, or extend the case.

The short mechanism chain is:

```text
retrieval gate -> claim normalization -> decision-space construction -> judgment anchors -> artifact fidelity -> auditable authority
```

## Contest Reference Lineage

The contest reference examples are not just related work; they clarify the kind of epistemic labor this prototype is trying to support. Transparent Replications, Measurement Schmeasurement, construct-validity critiques of development RCTs, systems-theoretic safety work, Society Library-style perspective mapping, and structured analytic techniques all point toward the same need: make hidden mismatches inspectable before synthesis smooths them away.

This prototype translates that need into claim maps, relation maps, cruxes, caveats, erosion audits, update ledgers, and review packets. See `docs/REFERENCE_LINEAGE.md` for the compact mapping and `docs/DECISION_SPACE_FRAMEWORK_INTEGRATION.md` for the decision-space mechanism map.

## One-Minute Example

Flat synthesis can say: "Cosmic-ray exposure shows LHC black-hole risk is ruled out."

That is broadly right, but it hides a dependency. Earth cosmic-ray survival is not the whole argument once LHC-produced objects may be slower and more trappable than cosmic-ray products.

The LHC map preserves the dependency as reviewable pieces:

- `lhc_c004`: the velocity caveat.
- `lhc_c012`: the trapping analysis.
- `lhc_r003` and `lhc_r004`: why compact-star arguments become relevant.

Why this matters: the map does not merely cite sources. It preserves the part of the reasoning a later reviewer would need to accept, challenge, or revise.

## What The Package Is Trying To Show

The package is built around one empirical bet: when a later reviewer needs to inspect a disputed distinction, a structured artifact leaves better operational handles than a fluent synthesis alone.

The most relevant handles are:

- declared source and retrieval boundaries,
- normalized claims with source anchors,
- source-grounded claim IDs and relation IDs,
- visible caveats and scope limits,
- critique/response structure,
- cruxes and update triggers,
- flat-synthesis loss audits,
- human-review packets that preserve local accept/revise/reject work.

The current value is the workflow and audit surface, not a finished interactive product or a fully automated literature-review system.

## Judge Inspection Path

For the fastest orientation, use `docs/START_HERE.md`. It gives the shorter version of this path.

Read these in order if you want the fuller package boundary:

1. `docs/INVESTIGATOR_CHALLENGE.md`: run or inspect the frozen flat-vs-map investigator challenge, local correction exercise, and held-out-source update.
2. `docs/DECISION_SPACE_FRAMEWORK_INTEGRATION.md`: see how the decision-space writing concepts map onto concrete artifacts.
3. `docs/RECOVER_REPAIR_UPDATE_DEMO.md`: read the compact recover, repair, and update packet.
4. `docs/evaluations/MATCHED_STRONG_MODEL_LHC_COMPARISON.md`: inspect the matched strong-model comparison that clarifies the claim boundary.
5. `docs/DECISION_SPACE_EROSION_DIFFERENTIATION.md`: see how this differs from provenance, faithful summarization, argument mapping, and knowledge graphs.
6. `examples/lhc_black_holes/worked_region_cosmic_ray_map.md`: read `What To Notice` plus claims `lhc_c001` through `lhc_c006`.
7. `examples/lhc_black_holes/decision_space_erosion_audit.md`: inspect `lhc_loss_001`.
8. `docs/FLF_BEFORE_AFTER_COMPARISON.md`: compare the flat LHC synthesis to the mapped dependency.
9. `docs/PIPELINE_DEMONSTRATION_EXAMPLES.md`: run or inspect examples for intake, structure, assessment, resume, and reproducibility.

Then check transfer and limits:

1. `examples/eggs/worked_region_observational_vs_rct_map.md`
2. `examples/eggs/decision_space_erosion_audit.md`
3. `examples/covid_origins_slice/worked_region_bayesian_disagreement_map.md`
4. `docs/EVIDENCE_AND_LIMITATIONS.md`
5. `docs/GENERALIZABILITY_RED_TEAM.md`
6. `docs/review/REVIEWER_START_HERE.md`

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

The decision-space claim is stronger than "map good, summary bad." AI workflows exercise practical authority when they decide what evidence enters context, how claims are normalized, which distinctions remain visible, and which artifact a reviewer can contest. The useful comparison is: when a later reviewer needs to inspect or change a disputed distinction, which artifact still gives them operational authority to do it?

## Claim Hierarchy

Demonstrated:

- Source-grounded worked-region maps preserve dependencies, caveats, critique/response structure, and review handles that flat syntheses can compress.
- The investigator challenge shows better deterministic recoverability for selected hidden-dependency tasks.
- Local repair and held-out-source update can preserve stable IDs for unaffected map objects.
- The package demonstrates artifact fidelity across Markdown, JSON, review packets, mutation repair, and update ledgers.

Plausible but under-tested:

- The same artifacts will improve multi-investigator handoff.
- The same method will transfer to more fresh cases without author selection.
- More complete review logs will make expert disagreement easier to adjudicate.

Not established:

- The current prototype consistently beats strong models on final prose quality.
- The artifacts are domain-correct without human review.
- The challenge is a statistically powered benchmark.

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

For the full risk register, use `docs/EVIDENCE_AND_LIMITATIONS.md`. For human review, start with `docs/review/REVIEWER_START_HERE.md` and `docs/review/TIER1_HUMAN_REVIEW_CHECKLIST.csv`.
