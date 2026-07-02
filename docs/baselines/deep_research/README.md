# Deep Research Baselines

Use this folder for external Deep Research baseline runs. These are retrieval-plus-synthesis baselines used to compare the epistemic mapper against an off-the-shelf research workflow.

For each baseline run, save:

- the exact prompt used,
- the final Deep Research report,
- the retrieved source list with URLs,
- downloaded or copied source documents when licensing/access permits,
- notes on run date, model/product used, and any limitations.

Recommended layout:

```text
docs/baselines/deep_research/<case>/
  PROMPT.md
  REPORT.md
  SOURCES.md
  source_docs/
  RUN_NOTES.md
```

Do not include the curated map, quality report, stress output, or config profile in the Deep Research prompt. For controlled comparison, run the mapper separately on the same retrieved source documents with the same question.
