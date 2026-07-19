# Deterministic Starter Snapshots

These snapshots demonstrate the heuristic builder's reproducible artifact
shape. They are validated fixtures, not the canonical competition maps and not
decision-worthy memos.

- [`lhc_black_holes/`](lhc_black_holes/)
- [`eggs/`](eggs/)

Regenerate both by running `python scripts/run_flf_demo.py`; working copies are
written under the ignored `artifacts/` directory. To refresh the checked-in
fixtures intentionally, use `--output-root examples/starter_snapshots` with
`scripts/build_case_map.py` and review the diff.
