# Epistemic Case Mapper

Epistemic Case Mapper is an AI-assisted workflow for preserving
decision-relevant reasoning as source-linked claims, relations, caveats, and
cruxes that another investigator can inspect and revise.

The core claim is deliberately narrow: structured reasoning objects make a
case easier to audit and extend. The project does not claim superior final
prose, autonomous truth discovery, or domain correctness without review.

## Review In Five Minutes

1. Read the [curated project guide](docs/START_HERE.md).
2. Compare the scripted blinded
   [Qwen LHC synthesis](examples/lhc_black_holes/blinded_flat_synthesis_baseline_qwen3_8b.md)
   with dependency objects `lhc_c004`, `lhc_c012`, `lhc_r003`, and `lhc_r004`
   in the [LHC map](examples/lhc_black_holes/worked_region_cosmic_ray_map.md).
3. Inspect the substantive seven-source
   [eggs map](examples/eggs/worked_region_observational_vs_rct_map.md), which
   preserves 19 claims, 17 relations, and 3 decision cruxes.
4. Compare it with the
   [50-source eggs stress run](examples/eggs_large_source_stress/README.md),
   where the production pipeline processed the corpus but blocked a defective
   memo from publication.
5. Read the [evidence boundary](docs/submission/EVIDENCE_AND_LIMITATIONS.md).

To verify the package after installation, run:

```bash
./.venv/bin/python scripts/run_flf_demo.py --skip-build
```

## What The Package Demonstrates

- Two source-grounded worked maps across different evidence shapes: LHC
  technical risk and a substantive seven-source eggs/health map.
- A narrow COVID disagreement map as a format stress test, not source-grounded
  adjudication.
- Eight scripted blinded local-model baselines across Gemma, Qwen, Phi, and
  Granite, with an audit that narrows or rejects unsupported loss claims.
- Paired live Gemma MLX map runs: one valid eggs candidate with review risks
  and one rejected LHC candidate with retained timeout and validation evidence.
- A separate 50-source eggs stress run that exposes corpus-scale mapping,
  adjudication, a sparse active relation graph, and fail-closed memo publication.
- Stable IDs, Markdown/JSON parity, source manifests, review packets, and
  generic package validation.
- Frozen-snapshot restoration and a prewritten source update that demonstrate
  addressability and local change accounting, not semantic repair.

The original same-context flat syntheses and their erosion audits remain in the
repository as explicitly non-evaluative examples of the audit format. They are
not baseline performance evidence.

## Pipeline Depth

```text
documents -> map -> briefing -> publication gate
```

The paired [live-model packet](examples/live_model_runs/README.md) shows map
generation producing both a reviewable candidate and an explicit failure. The
[50-source eggs trace](examples/eggs_large_source_stress/README.md) shows the
deeper map-to-memo machinery processing a large corpus and refusing publication
when critical defects remain. The implementation under
[`src/epistemic_case_mapper/pipeline/`](src/epistemic_case_mapper/pipeline/)
includes model-assisted extraction, map construction, briefing synthesis, and
fail-closed publication checks. This production machinery is implementation
depth rather than the central evidence; the strongest curated maps still
depend materially on curation.

## Reproduce

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
./.venv/bin/python scripts/run_flf_demo.py --skip-build
./.venv/bin/python scripts/reproducibility_gate.py \
  --include-worked-regions \
  --include-blinded-baselines
```

The package is configured by [`submission_manifest.yaml`](submission_manifest.yaml).
For the live backend boundary and exact commands, see
[REPRODUCE.md](docs/submission/REPRODUCE.md).

## Evidence Boundary

Demonstrated: inspectable reasoning objects, cross-case artifact reuse,
scripted baseline comparisons, deterministic package checks, and local edit
accounting.

Not demonstrated: measured improvement in reviewer accuracy or speed,
independent expert approval, unseen-case performance, low-variance second-user
operation, autonomous source integration, or consistently successful final
memo generation.

## License

Original software and documentation are available under the [MIT License](LICENSE).
Third-party source material retains its original rights; see
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
