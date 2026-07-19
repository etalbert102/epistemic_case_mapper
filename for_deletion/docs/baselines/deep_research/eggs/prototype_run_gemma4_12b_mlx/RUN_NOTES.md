# Prototype Run Notes

Run purpose: compare the epistemic mapper against the checked-in Deep Research eggs baseline report.

Baseline report:

- `docs/baselines/deep_research/deep_research_eggs_Claude_Opus4.8.md`

Important isolation rule:

- The Deep Research final report was not used as evidence input to the mapper.
- The report was used only to identify the cited/high-weight source list.

Source packet:

- 13 cited sources were reconstructed from accessible URLs.
- Most publisher pages rejected direct automated fetching with HTTP 403.
- The source packet therefore uses PubMed XML abstract records for most sources plus stripped open full-text pages where available.
- This is a source-held comparison against Deep Research's cited sources, not a full retrieval-trace reproduction.

Prototype command shape:

```bash
PYTHONPATH=src python3 -m epistemic_case_mapper.cli \
  --repo-root artifacts/deep_research_eggs_mapper/workspace \
  --package package.yaml \
  case init \
  --case-id deep_research_eggs_sources \
  --title "Deep Research Eggs Source-Held Comparison" \
  --question "For generally healthy adults, should eggs be treated as meaningfully harmful, neutral, or beneficial in dietary advice, especially with respect to cardiovascular risk?" \
  --docs <reconstructed_source_packet> \
  --model-backend ollama:gemma4:12b-mlx \
  --recommend-config \
  --config-backend ollama:gemma4:12b-mlx
```

```bash
ECM_OLLAMA_NUM_PREDICT=2048 PYTHONPATH=src python3 -m epistemic_case_mapper.cli \
  --repo-root artifacts/deep_research_eggs_mapper/workspace \
  --package package.yaml \
  semantic staged brief \
  --region deep_research_eggs_sources_initial_region \
  --backend ollama:gemma4:12b-mlx \
  --chunk-lines 35 \
  --chunk-overlap-lines 0 \
  --max-chunks-per-source 1 \
  --max-total-chunks 16 \
  --max-claims-per-chunk 3 \
  --max-relation-pairs 30 \
  --relation-batch-size 5 \
  --briefing-max-claims 18 \
  --backend-timeout 240 \
  --backend-retries 0 \
  --no-validate
```

Run result:

- Config profile selected: `empirical_policy_decision`
- Backend: `ollama:gemma4:12b-mlx`
- Claims: `39`
- Relations: `27`
- Quality status: `usable_with_review`
- Quality score: `88`
- Briefing confidence: `medium`

Saved artifacts:

- `PROTOTYPE_BRIEFING.md`
- `briefing_summary.json`
- `map_quality_report.json`
- `source_packet_manifest.json`

