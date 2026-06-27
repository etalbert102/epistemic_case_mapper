# Investigator Workflow Playbook

Status: `human-review-needed`

Purpose: make the FLF prototype operationally realistic by showing how a human investigator and AI coding agent would use the repository after the initial demo.

## Roles

| Role | Responsibility | Must Not Do |
| --- | --- | --- |
| Investigator | Chooses case scope, accepts or rejects claims, decides what matters. | Treat generated claims as reviewed without checking sources. |
| AI extraction agent | Drafts source-grounded claims, candidate relations, and baseline syntheses. | Hide uncertainty or merge similar-but-not-identical claims. |
| Reviewer | Audits claim support, relation correctness, and erosion findings. | Review only the final synthesis while ignoring the map. |
| Maintainer | Runs validators, keeps IDs stable, merges reviewed changes. | Break source provenance or rewrite IDs casually. |

## Realistic Workflow

1. Define the investigation context.
   - What decision is the artifact meant to support?
   - Which audience is expected to reuse it?
   - Which sources are in scope for the current pass?

2. Build or update the source manifest.
   - Add source provenance to `data/cases/<case_id>/case.yaml`.
   - Store raw and text versions under `data/cases/<case_id>/sources/`.
   - Update source role, method, independence, and stakeholder metadata.

3. Create a broad full-case scaffold.
   - Add every source to a cluster.
   - Preserve source role and correlation risks.
   - Mark the scaffold as `broad-source-scaffold`, not reviewed.

4. Select a worked-region anchor.
   - Choose a high-leverage cluster where synthesis is likely to lose important structure.
   - Extract source-grounded claims with excerpts.
   - Add relation rationales and crux candidates.

5. Generate a fair flat synthesis comparator.
   - Use the same source subset.
   - Record the prompt and whether the writer saw the map.
   - Add blinded local-model baselines where possible.

6. Audit decision-space erosion.
   - Count only losses that are source-supported, decision-relevant, and fair to a concise synthesis.
   - Mark losses as rejected or narrowed when stronger baselines preserve them.

7. Hand off for human review.
   - Use the case audit packet and CSV checklist.
   - Record accept/revise/reject decisions.
   - Keep `human-review-needed` until explicit human review is recorded.

8. Compound rather than restart.
   - Add new claims, relations, and clusters incrementally.
   - Preserve stable IDs where possible.
   - Run the full demo and reproducibility gate before submission.

## Realism Guardrails

- Every broad full-case source must appear in both the index and map.
- Worked-region anchors must remain distinguishable from broad scaffolds.
- Public explanations, institutional reviews, technical analyses, critiques, and governance sources must not be counted as the same evidence type.
- Reviewer-facing files must say what is not reviewed.
- The demo must be runnable without local model generation.

## Current Realism Boundary

This prototype is operationally realistic as a file-based investigator workflow. It is not yet realistic as a polished end-user application. The intended use is a serious analyst or judge inspecting, extending, and auditing durable artifacts in a repository.
