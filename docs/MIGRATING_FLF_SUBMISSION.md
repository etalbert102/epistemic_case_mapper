# Migrating The FLF Submission

Status: `implemented-core`

The FLF submission now acts as a configured engine package.

Current migration steps already completed:

- case, region, review, UI, baseline, and path configuration moved into `submission_manifest.yaml`,
- baseline config is keyed by region/baseline identity rather than case key,
- UI data includes all worked regions for each included case,
- reference validation uses manifest-configured ID patterns,
- `ecm` and `scripts/ecm.py` expose package-facing commands,
- `run_flf_demo.py`, `reproducibility_gate.py`, and `judge_smoke_test.py` propagate manifest selection.

Remaining migration work is mostly packaging:

- move FLF-specific docs into a package directory,
- add JSON artifact adapters if future packages need non-markdown maps.
