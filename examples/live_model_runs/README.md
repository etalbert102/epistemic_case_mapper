# Live Gemma MLX Map Runs

Status: `machine-generated-human-review-needed`

This packet preserves one successful and one failed live map-generation run
from the same production pipeline and backend: `ollama:gemma4:12b-mlx`. The
pair demonstrates automation behavior and fail-closed inspection, not domain
correctness or hands-free production quality.

## Read The Pair

| Run | Result | What to inspect |
| --- | --- | --- |
| [Eggs success](eggs_success/README.md) | Valid semantic candidate; quality score 78, `usable_with_review`; 26 claims, 22 relations, and 15 crux candidates. | Generated map, initial candidate, prompt/raw transcripts, critique, targeted relation repair, and remaining duplicate/count risks. |
| [LHC failure](lhc_failure/README.md) | Invalid semantic candidate; quality score 0, `needs_repair`; one claim, no relations, and no cruxes. | Two backend timeouts, rejected repair output, validation failures, and the retained non-publication artifact. |

The successful eggs map is not the curated eggs example. It remains one claim
over the configured target, contains two near-duplicate pairs, and was built
under a chunk budget that skipped 83 chunks. The LHC output is deliberately
retained as a failure rather than repaired manually or presented as a map.

## How The Eggs Artifacts Fit Together

The [seven-source curated map](../eggs/worked_region_observational_vs_rct_map.md)
is the substantive eggs example. This packet demonstrates live map generation
over the same bounded region. The separate
[50-source stress run](../eggs_large_source_stress/README.md) demonstrates
larger-corpus intake, adjudication, memo construction, and fail-closed
publication. None of the machine-generated artifacts supersedes the curated
map or removes its `human-review-needed` boundary.

## Provenance

The packet copies outputs from the original ignored run directories. Artifact
paths inside run metadata are normalized to repository-root-relative logical
paths; the corresponding files are relocated beneath this packet. Aside from
that path normalization, prompt, raw output, canonical parse, and report files
are retained without content edits for every recorded source-extraction call.
The eggs packet also retains relation-generation and targeted relation-repair
transcripts.

The original shell transcript was not retained. The configured parameters in
each `run_summary.json` support this equivalent rerun shape:

```bash
ecm --repo-root . --package submission_manifest.yaml semantic staged map \
  --region <region> \
  --backend ollama:gemma4:12b-mlx \
  --output <output.json> \
  --artifact-dir <artifact-directory> \
  --chunk-lines 35 \
  --chunk-overlap-lines 0 \
  --max-chunks-per-source 1 \
  --max-claims-per-source 3 \
  --backend-timeout 240 \
  --backend-retries 0 \
  --repair-quality
```

The eggs run used `--max-total-chunks 8 --max-relation-pairs 20
--relation-batch-size 5`; LHC used `--max-total-chunks 6
--max-relation-pairs 16 --relation-batch-size 4`. Local model nondeterminism
means a rerun need not reproduce byte-identical model outputs.

## Validate

```bash
PYTHONPATH=src python3 scripts/validate_live_model_examples.py
```

The validator checks every packet file against
`examples/live_model_runs/artifact_manifest.json`, requires the eggs map to
pass semantic validation, requires the LHC map to fail for the recorded
structural reasons, and checks the backend and quality boundaries.
