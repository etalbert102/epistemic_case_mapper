# Epistemic Case Mapper

An AI-assisted evidence workflow for preserving decision-relevant reasoning
before and during memo synthesis. It turns a bounded source packet into
source-linked claims, relations, caveats, cruxes, and briefing inputs, while
mechanical gates keep unsupported or incomplete outputs from being published
as official results.

## Judge In Ten Minutes

1. Read the [contest guide](docs/START_HERE.md).
2. Compare the LHC [flat synthesis](examples/lhc_black_holes/flat_synthesis_baseline.md),
   [worked map](examples/lhc_black_holes/worked_region_cosmic_ray_map.md), and
   [erosion audit](examples/lhc_black_holes/decision_space_erosion_audit.md).
3. Inspect the [recover/repair/update challenge](examples/investigator_challenge/README.md)
   and its [matched strong-model boundary](docs/evaluations/MATCHED_STRONG_MODEL_LHC_COMPARISON.md).
4. Read the [formal writeup](docs/submission/WRITEUP.md) and
   [evidence limits](docs/submission/EVIDENCE_AND_LIMITATIONS.md).
5. Check transfer on the [eggs example](examples/eggs/README.md).

The shortest example is one hidden dependency. A flat answer can correctly say
that natural cosmic-ray exposure makes catastrophic LHC black-hole risk
negligible while obscuring why Earth survival is not sufficient by itself if
LHC products are slower and more trappable. The map preserves that caveat, the
technical trapping analysis, and the relations that make compact-star evidence
relevant as separately reviewable objects.

## Pipeline

```text
documents -> map -> briefing -> publication gate
```

- `documents/` bounds and prepares the evidence packet.
- `map/` extracts claims, proposes relations, identifies cruxes, and repairs
  source or structure failures.
- `briefing/` prioritizes the map and synthesizes a decision memo.
- The publication gate checks provenance, citations, source binding, retained
  obligations, and readiness; failures produce an inspection packet instead of
  an official memo.

The stage implementation lives under
[`src/epistemic_case_mapper/pipeline/`](src/epistemic_case_mapper/pipeline/).
Curated review evidence lives under [`examples/`](examples/), with methodology,
evaluation, operating guides, and review packets indexed from
[`docs/`](docs/README.md).

## Run The Contest Gate

```bash
python -m venv .venv
python -m pip install -e ".[dev]"
python scripts/run_flf_demo.py --skip-build
python scripts/reproducibility_gate.py --include-worked-regions --include-blinded-baselines
```

For a live model-assisted example, prerequisites, outputs, and the fail-closed
boundary, see [REPRODUCE.md](docs/submission/REPRODUCE.md).

## Review Boundary

The checked-in maps are agent-curated and mechanically validated, not
independently domain-expert reviewed. The package demonstrates inspectable
dependencies, local repair, update locality, and artifact fidelity on selected
cases; it does not establish automatic truth, universal prose superiority, or
broad generalization.
