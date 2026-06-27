# Operational Realism Audit

Status: `human-review-needed`

Purpose: assess whether the prototype resembles a workflow that a serious investigator could use beyond the curated demo.

## What Is Realistic Now

| Realism Dimension | Evidence In Repo | Assessment |
| --- | --- | --- |
| Source provenance | Case manifests, raw/text sources, source inventories, checksums. | Strong for current LHC and eggs sources. |
| Case-level navigation | Full-case indexes and maps cover every acquired source. | Strong as broad scaffolds. |
| Deep local audit | Worked-region maps include claims, excerpts, relation rationales, cruxes, and erosion audits. | Strongest part of the prototype. |
| Baseline comparison | Illustrative and blinded local-model flat syntheses exist across multiple model families. | Useful, but span-limited. |
| Full-case synthesis comparison | Full-case flat baselines exist for LHC and eggs. | Stronger realism check, still human-review-needed. |
| Human review handoff | Review packets and CSV checklists exist. | Operationally plausible, but no completed human review yet. |
| Compounding | Stable IDs, Markdown, JSON exports, validators, and task queues support incremental work. | Strong for repo-native users. |
| Source-update workflow | `docs/NEW_SOURCE_UPDATE_DEMO.md` shows how a new-to-map source affects claims and relations. | Useful demonstration; needs a future fresh external-source update. |
| Judge reproducibility | `scripts/run_flf_demo.py` and the reproducibility gate validate the package. | Strong. |

## Remaining Realism Gaps

| Gap | Why It Matters | Current Mitigation | Next Step |
| --- | --- | --- | --- |
| No completed external human audit | FLF wants scrutiny-resistant artifacts. | Human audit packets and checklists are ready. | Have one reviewer complete priority items for both cases. |
| Full-case maps are cluster scaffolds | Real investigations need source-excerpt claims across the whole case. | Scaffolds are clearly labeled and validated for source coverage. | Expand one additional full-case cluster into a worked region. |
| Full-case baselines are not human-scored | A realistic whole-case synthesis comparison needs more than generated prose. | Full-case flat baselines now exist for both cases. | Have a reviewer score which distinctions survive and fail. |
| No interactive navigator | Non-technical judges may prefer graph browsing. | Judge packet gives a linear path and JSON exports exist. | Optional: create a static HTML navigator. |
| Source updates are not demonstrated | Living knowledge bases must handle new evidence. | Workflow playbook and task queues specify update procedure. | Add one new source and show the diff through the map. |

## Realism Verdict

The prototype is realistic as a **repository-native epistemic investigation workflow**: a serious investigator can inspect sources, follow clusters, audit worked-region claims, compare baselines, and continue from task queues.

It is not yet realistic as a **hands-free autonomous knowledge-base system** or polished product. The submission should present the former and avoid implying the latter.
