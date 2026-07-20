# LHC Live-Model Failure

Status: `machine-generated-invalid-candidate`

Backend: `ollama:gemma4:12b-mlx`

Decision question: Why did investigators conclude that LHC operation would not
create a catastrophic black hole risk?

## Result

- Semantic candidate validation: expected failure.
- Pipeline quality: `needs_repair`, score 0.
- Final structure: 1 claim, 0 relations, 0 crux candidates, 5 declared sources.
- Backend calls: 7 recorded with 2 timeouts.
- Quality repair: attempted, rejected because the model repair response failed
  the semantic schema and omitted required sources, claims, relations, and
  evidence checks.

This output is not a usable map. Its value is operational: the pipeline keeps
the inadequate candidate, backend diagnostics, repair attempt, and explicit
validation failures instead of presenting a polished result.

Start with [map_quality_report.json](records/map_quality_report.json),
[pipeline_progress.json](records/pipeline_progress.json), and
[map_quality_repair_validation.json](records/map_quality_repair_validation.json).
The [generated map](generated_map.json) is retained only as the rejected output.
