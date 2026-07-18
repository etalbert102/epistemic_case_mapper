# Start Here: FLF Submission

Status: `human-review-needed`

This prototype is easiest to judge through one concrete question:

> Can an AI-assisted workflow preserve operational judgment as evidence is retrieved, normalized, mapped, synthesized, reviewed, repaired, and updated?

The demonstrated answer is not "a nicer summary." It is a reusable review surface: source-grounded claims, relation IDs, caveats, cruxes, erosion losses, and human-review handoff packets that operate as judgment anchors.

The governing mechanism chain is:

```text
retrieval gate -> claim normalization -> decision-space construction -> judgment anchors -> artifact fidelity -> auditable authority
```

That means the project is not only asking whether a final memo is good. It is asking whether the workflow preserves enough evidence, distinctions, dependencies, source identity, and review state for another investigator to understand and change the reasoning locally.

## What To Judge

Judge the package on whether it makes later reasoning easier to audit and extend:

- Can you see which evidence entered the case and which boundaries shaped retrieval?
- Can you see how source material was normalized into claims without losing caveats?
- Can you see which distinctions carry the conclusion?
- Can you tell what a flat synthesis compressed or lost?
- Can another investigator accept, revise, reject, or extend a local piece without redoing the whole case?
- Does the same workflow plausibly transfer from a closed technical risk case to messy evidence and adversarial disagreement?

Do not judge it as a final literature review, finished UI, or externally validated knowledge base.

## Reference Lineage

The contest examples point to a family of epistemic work where progress comes from finding hidden mismatches: the measure is not the construct, the same label hides different interventions, the dataset is not what it appears to be, or a broadly true result is framed as more decisive than it is.

This prototype is built for that kind of scrutiny. It gives reviewers stable handles for source boundaries, measurement or endpoint fit, same-label differences, relation dependencies, caveats, cruxes, and update triggers.

For the fuller mapping from contest references to prototype design, see `docs/REFERENCE_LINEAGE.md`.

## One-Minute Demo

Flat synthesis can say:

> Cosmic-ray exposure shows LHC black-hole risk is ruled out.

That is broadly right, but it hides a dependency. Earth cosmic-ray survival is not the whole argument once LHC-produced objects may be slower and more trappable than cosmic-ray products.

The LHC map preserves that dependency as reviewable pieces:

- `lhc_c004`: the velocity caveat.
- `lhc_c012`: the trapping analysis.
- `lhc_r003` and `lhc_r004`: why compact-star arguments become relevant.

This is the submission's value proposition: the map keeps the part of the reasoning a later reviewer would need to accept, challenge, or revise.

## Five-Minute Path

1. Read the one-minute demo above.
2. Open `docs/DECISION_SPACE_FRAMEWORK_INTEGRATION.md` for the concept-to-artifact map.
3. Open `docs/INVESTIGATOR_CHALLENGE.md` for the runnable challenge boundary.
4. Open `docs/RECOVER_REPAIR_UPDATE_DEMO.md` and inspect the three-part recover, repair, and update result.
5. Open `docs/evaluations/MATCHED_STRONG_MODEL_LHC_COMPARISON.md` to see the honest comparison: a strong model can recover much of the LHC chain, but the map supplies stable handles for review and update.
6. Open `examples/lhc_black_holes/worked_region_cosmic_ray_map.md` and read only `What To Notice` plus claims `lhc_c001` through `lhc_c006`.
7. Open `examples/lhc_black_holes/decision_space_erosion_audit.md` and inspect `lhc_loss_001`.
8. Open `docs/FLF_BEFORE_AFTER_COMPARISON.md` and compare the LHC flat synthesis against the mapped dependency.

That path should be enough to see whether the core mechanism is interesting. Then use eggs for transfer across evidence types and COVID as a narrow adversarial disagreement stress test.

For runnable examples keyed to ingestion, structure, assessment, handoff, and reproducibility, use `docs/PIPELINE_DEMONSTRATION_EXAMPLES.md`.

For the strongest end-to-end demonstration of investigator value, run or inspect `docs/INVESTIGATOR_CHALLENGE.md`. It compares flat and map conditions on frozen follow-up tasks, then shows local relation repair and a held-out-source update. `docs/RECOVER_REPAIR_UPDATE_DEMO.md` is the compact judge-facing version.

## Fifteen-Minute Path

After the LHC check:

1. Open `examples/eggs/worked_region_observational_vs_rct_map.md` and read `What To Notice`.
2. Open `examples/eggs/decision_space_erosion_audit.md` and look for how observational outcomes, randomized lipid markers, guidelines, and subgroup caveats are kept separate.
3. Open `examples/covid_origins_slice/worked_region_bayesian_disagreement_map.md` and check whether disagreement is represented without claiming to settle origins.

## Risk Check

Read these before giving the submission credit beyond the core mechanism:

- `docs/EVIDENCE_AND_LIMITATIONS.md`: what is demonstrated versus still unproven.
- `docs/GENERALIZABILITY_RED_TEAM.md`: where transfer is plausible and where it may fail.
- `docs/review/REVIEWER_START_HERE.md`: how a human reviewer would audit the highest-risk claims and relations.

## What The Prototype Shows

- LHC: dependency structure and critique/response structure survive as reviewable nodes.
- Eggs: outcome evidence, lipid-marker evidence, guideline framing, and population caveats stay separate.
- COVID slice: Bayesian disagreement and subargument boundaries stay visible without claiming to settle origins.

## Claim Boundary

Demonstrated:

- structured maps provide queryable judgment anchors for dependency tracing, local correction, and held-out-source update in deterministic replay,
- the LHC velocity/trapping dependency is easier to recover from map artifacts than from the checked-in flat baseline under the frozen challenge,
- the workflow records what changed and what stayed stable, preserving artifact fidelity across repair and update.

Plausible but under-tested:

- the same surface will improve multi-investigator handoff,
- the same pattern will transfer cleanly to fresh cases outside the included examples.

Not established:

- the prototype consistently beats strong models on final prose quality,
- the maps are domain-correct without human review,
- the current metrics are a scientific benchmark.

## What To Ignore At First

- Do not start with the full-case maps.
- Do not start with the generated scaffold artifacts under `artifacts/`.
- Do not treat the UI as the source of truth.
- Do not read every planning document before checking the worked examples.
- Do not treat `human-review-needed` as a flaw in itself; it is the current review boundary.

## Run The Checks

```bash
PYTHONPATH=src python3 scripts/run_flf_demo.py --skip-build
PYTHONPATH=src python3 scripts/reproducibility_gate.py --include-worked-regions
```

Passing checks mean the package is reproducible and internally consistent. They do not mean the maps have been externally reviewed.

## Visual Mode

```bash
python3 -m http.server 8787
```

Then open `http://localhost:8787/ui/`.

Use the top Judge Mode section for orientation, then use the case tabs only after the basic value is clear.

## Current Boundary

The submission is a polished prototype workflow. It is not a finished product, not an exhaustive case adjudication, and not a human-validated knowledge base. The next credibility upgrade is one completed external review pass over a small set of claims, relations, and erosion losses.
