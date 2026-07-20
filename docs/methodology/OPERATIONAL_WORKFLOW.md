# Operational Workflow And Realism

Status: `human-review-needed`

Purpose: consolidate how the prototype is meant to be used, what is realistic now, how full-case scaffolds extend worked regions, and what operational gaps remain.

## Roles

| Role | Responsibility |
| --- | --- |
| Investigator | Defines case question, source set, and review priorities. |
| AI coding agent | Generates or revises structured artifacts, runs validators, and records residual risks. |
| Reviewer | Accepts, revises, rejects, or escalates claims, relations, cruxes, and erosion findings. |

## Realistic Workflow

1. Start with a case manifest and local source corpus.
2. Inspect the full-case index to understand source coverage and broad clusters.
3. Pick a worked region where decision-space erosion would matter.
4. Extract or revise source-grounded claims with stable IDs and excerpts.
5. Add support, challenge, dependency, tension, crux, refinement, and similarity relations.
6. Generate or inspect flat synthesis baselines.
7. Audit what the flat synthesis preserved, flattened, omitted, or distorted.
8. Record reviewer decisions in the case-specific audit packet.
9. Use the task queue to extend one cluster, relation family, or source update at a time.

## Full-Case Scaffold Design

The full-case maps are broad scaffolds, not fully audited case maps. They show coverage, navigability, and compounding potential while clearly marking the worked regions as deeper curated anchors.

The COVID origins material is intentionally handled as a narrow worked region rather than a full-case scaffold. Its purpose is to stress-test adversarial disagreement, Bayesian decomposition, and scope preservation without claiming to resolve the full origins question.

Each full case has:

- a source coverage index,
- a full-case map with broad clusters and cross-cluster relations,
- an illustrative full-case flat baseline,
- a task queue for realistic expansion,
- a deeper worked-region anchor.

Review status semantics:

- `broad-source-scaffold`: source-grounded at the manifest/metadata level, but not yet fully source-excerpt audited.
- `human-review-needed`: ready for review, not externally validated.
- `draft extension`: useful artifact outside the canonical validator set.

## What Is Realistic Now

| Feature | Current evidence | Realism judgment |
| --- | --- | --- |
| Source provenance | Case manifests, raw/text sources, source inventories, checksums. | Strong for current LHC and eggs sources; source-note based for the COVID slice. |
| Worked-region audit | Curated LHC, eggs, and COVID-slice worked regions with source excerpts, relations, cruxes, and erosion audits. | Realistic for a focused investigator workflow; the COVID slice needs especially strict review. |
| Full-case navigation | Full-case indexes and maps cover all acquired LHC and eggs sources. | Useful case-level scaffold, not a full audited knowledge base. |
| Baseline comparison | Illustrative and blinded local-model flat syntheses exist across multiple model families. | Useful, but span-limited. |
| Full-case synthesis comparison | Full-case flat baselines exist for LHC and eggs. | Stronger realism check, still human-review-needed. |
| Human handoff | Review packets, checklists, and CSVs exist. | Operationally plausible, not yet executed. |
| UI inspection | Static dashboard over curated artifacts. | Good inspection surface, not an editor. |
| Source-update workflow | `docs/evaluations/investigator_challenge/NEW_SOURCE_UPDATE.md` shows how a new-to-map source affects claims and relations. | Useful demonstration; needs a future fresh external-source update. |

## Remaining Gaps

| Gap | Why it matters | Current mitigation | Next step |
| --- | --- | --- | --- |
| No completed external human audit | Scrutiny resistance remains untested by an independent reviewer. | Human audit packets and checklists are ready. | Have one reviewer complete priority items for both main cases and the COVID slice. |
| Full-case maps are cluster scaffolds | Real investigations need source-excerpt claims across the whole case. | Scaffolds are clearly labeled and validated for source coverage. | Expand one additional full-case cluster into a worked region. |
| COVID is only a slice | Adversarial COVID origins material can be overread as a full case assessment. | COVID artifacts are labeled as a worked region with a dedicated audit packet. | Expand only if reviewers can audit a broader source set. |
| Fresh external-source updates are not demonstrated | Living knowledge bases must handle new evidence arriving after the initial source corpus. | Update demo uses an already acquired source. | Add one newly acquired external source and show the diff through the map. |
| Multi-reviewer conflict handling is not implemented | Collaboration needs disagreement tracking. | Stable IDs make conflict localization possible. | Add a small review-merge protocol after first human audit. |
| UI cannot persist decisions | Review workflow remains file-based. | Canonical Markdown/CSV packets are explicit. | Add persistence only if provenance can remain clear. |

## Realism Verdict

The prototype is realistic as a repository-native workflow for a technical investigator or AI-assisted analyst trying to preserve decision-relevant structure across a complex case. It is not yet realistic as a hands-free autonomous knowledge-base system or a polished collaborative product.
