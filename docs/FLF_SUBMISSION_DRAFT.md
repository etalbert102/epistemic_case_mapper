# FLF Submission Draft

Status: `template`

## Problem Framing

TODO

## Workflow Summary

TODO

## Artifact Format

TODO

## LHC Worked-Region Summary

TODO

## Eggs Worked-Region Summary

TODO

## Evidence That Flat Synthesis Loses Decision-Relevant Structure

TODO

## Limitations

TODO

## Install And Run

```bash
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
PYTHONPATH=src python3 scripts/reproducibility_gate.py
PYTHONPATH=src python3 scripts/validate_worked_regions.py
```

## Remaining Human-Review Needs

TODO
