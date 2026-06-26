# Examples

This directory stores checked-in snapshots of judge-facing demo outputs.

Generated working artifacts belong under `artifacts/`, which is gitignored. Curated examples belong here so reviewers and future Codex goal runs can inspect stable outputs without relying on local untracked files.

Each case example should contain:

- `case_map.json`
- `report.md`
- `audit.md`
- `README.md`

Each case `README.md` must state:

- evidence mode: `seed` or `source-grounded`,
- review status,
- generation command,
- source manifest path,
- known limitations.
