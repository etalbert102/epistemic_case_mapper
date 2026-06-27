# Submission Limitations And Risk Register

Status: `human-review-needed`

Purpose: state the prototype's limits plainly so the FLF submission does not overclaim.

| Risk | Why it matters | Current mitigation | Remaining work |
| --- | --- | --- | --- |
| No completed human review | Agent-authored maps and audits can be biased or subtly wrong. | Human audit packets and checklists are included. | A named reviewer should record claim, relation, and erosion decisions. |
| Full-case maps are broad scaffolds | Judges may want full source-excerpt-level maps, not just coverage scaffolds. | Every acquired LHC and eggs source is represented in a full-case index and map. | Add source-excerpt-level claims for every full-case cluster. |
| Baselines are span-limited | A full-document or better-prompted baseline might preserve more structure. | Multi-model blinded baselines make this limitation visible. | Add full-document blinded baselines for final paper-grade evidence. |
| File-based workflow | Less usable than an interactive knowledge-base tool. | Markdown and JSON exports are inspectable and reusable. | Build a lightweight navigator if contest time permits. |
| Relation labels need domain review | Incorrect support/challenge/dependency labels can mislead reviewers. | Relation rationales and source excerpts are explicit. | Domain reviewers should score relation correctness. |
| Extraction is not fully automated | Manual curation limits scale. | Deterministic scripts and prompt inventory make the process repeatable. | Add LLM extraction passes with reproducible prompt/model logging. |
| Decision-space erosion is a new framing | Judges may see it as a relabeling of known provenance or argument-mining concerns. | Submission packet explicitly distinguishes preservation/audit of decision-relevant structure from generic faithfulness. | Related-work framing should cite provenance, summarization faithfulness, argument mining, and evidence synthesis. |
| Evidence is not quantitative enough for a paper | The contest accepts prototypes, but a paper needs stronger evaluation. | Artifact counts, multi-model baselines, and audit packets provide a measurement scaffold. | Run human-scored evaluations across more tasks and models. |

## Boundary Statement

This submission should be judged as a working methodology and reference prototype. It demonstrates how to preserve and audit decision-relevant structure in two worked regions. It does not claim to be a complete epistemic stack, a fully automated literature-review system, or a replacement for expert judgment.
