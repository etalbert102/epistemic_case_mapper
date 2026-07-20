# LHC Starter Snapshot

Evidence mode: `source_grounded`

Review status: `draft`

This deterministic heuristic fixture demonstrates the starter artifact shape;
it is not the curated source-grounded LHC map. Regenerate it from the repository
root with:

```bash
python scripts/build_case_map.py --case data/cases/lhc_black_holes/case.yaml --output-root examples/starter_snapshots
```

The source manifest is `data/cases/lhc_black_holes/case.yaml`. Candidate claims
and heuristic relations require review; use
[`../../lhc_black_holes/README.md`](../../lhc_black_holes/README.md) for the
curated reviewer path and limitations.
