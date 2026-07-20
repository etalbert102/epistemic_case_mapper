# Start Here: FLF Submission

The contest question is concrete:

> Can an AI-assisted workflow preserve the evidence, distinctions, dependencies,
> and review state that another investigator needs to audit or revise a memo?

Epistemic Case Mapper answers with a durable review surface rather than a claim
to better prose: source-bound claims, explicit relations, caveats, cruxes,
erosion findings, and fail-closed briefing handoffs.

## One-Minute Example

A flat synthesis can correctly conclude that cosmic-ray exposure makes
catastrophic LHC black-hole risk negligible. That conclusion hides an important
dependency: Earth survival is not sufficient by itself if LHC-produced objects
may be slower and more trappable than cosmic-ray products.

The worked map keeps the dependency inspectable:

- `lhc_c004` records the velocity caveat.
- `lhc_c012` records the trapping analysis.
- `lhc_r003` and `lhc_r004` connect those objects to the need for compact-star
  evidence.

A later reviewer can now accept, challenge, or update the inference locally
instead of reconstructing it from a polished paragraph.

## Five-Minute Review Path

1. Read the LHC [flat baseline](../examples/lhc_black_holes/flat_synthesis_baseline.md).
2. Inspect the same issue in the [worked map](../examples/lhc_black_holes/worked_region_cosmic_ray_map.md),
   especially `lhc_c004`, `lhc_c012`, `lhc_r003`, and `lhc_r004`.
3. Check the [baseline-relative erosion audit](../examples/lhc_black_holes/decision_space_erosion_audit.md).
4. Open the [investigator challenge](../examples/investigator_challenge/README.md)
   for an artifact-addressability, frozen-snapshot restoration, and prewritten
   update-locality replay.
5. Read the [matched strong-model comparison](evaluations/MATCHED_STRONG_MODEL_LHC_COMPARISON.md),
   which narrows the claim: a capable model can reconstruct much of the chain,
   while the map makes it persistent and locally revisable.

Then use the [formal writeup](submission/WRITEUP.md) for the full competition
argument and [Evidence and Limitations](submission/EVIDENCE_AND_LIMITATIONS.md)
before assigning credit beyond the demonstrated mechanism.

## Transfer Check

The [eggs case](../examples/eggs/README.md) tests whether observational outcomes,
randomized lipid-marker evidence, guideline roles, and subgroup caveats remain
separate. The [COVID slice](../examples/covid_origins_slice/README.md) tests
whether debate outcomes, process critiques, Bayesian disagreement, and
subargument boundaries can coexist without a false consensus. These selected
examples show the same artifact contract across different evidence shapes; they
do not establish broad generalization.

## What Is And Is Not Demonstrated

Demonstrated narrowly: source-linked reasoning objects, baseline-relative loss
audits, direct addressability of frozen map objects, one localized
frozen-snapshot restoration, one prewritten source-delta application,
reproducible exports, and publication checks.

Not established: automatic domain correctness, exhaustive retrieval, superior
final prose, lower human review time, unseen-case performance, or successful
multi-reviewer operation. The artifacts are agent-curated and mechanically
validated; independent expert review remains outstanding. The full boundary is
recorded in [Evidence and Limitations](submission/EVIDENCE_AND_LIMITATIONS.md).

## Run The Checks

From an installed checkout:

```bash
python scripts/run_flf_demo.py --skip-build
python scripts/reproducibility_gate.py --include-worked-regions --include-blinded-baselines
```

Passing means the package is internally consistent and reproducible, not that
its substantive judgments are expert-approved. See
[REPRODUCE.md](submission/REPRODUCE.md) for setup and a live model-assisted run,
or serve the repository with `python -m http.server 8787` and open
`http://localhost:8787/ui/` for the static viewer.
