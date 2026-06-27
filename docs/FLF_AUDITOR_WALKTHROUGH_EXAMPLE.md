# FLF Auditor Walkthrough Example

Purpose: show the review workflow a judge or external auditor should follow before trusting a worked-region artifact.

This example uses the LHC black-hole risk case because the source base contains a closed technical safety argument, a critique, a response, public communication, and later experimental context.

## 1. Audit The Source Subset Before Model Outputs

Region question:

```text
Which assumptions make the natural cosmic-ray analogue relevant to LHC microscopic-black-hole risk?
```

Minimum source subset:

| Source ID | Role |
| --- | --- |
| `lsag_2008_safety_review` | formal safety review and cosmic-ray argument |
| `spc_2008_lsag_review` | review of LSAG and Giddings-Mangano arguments |
| `giddings_mangano_2008_stable_black_holes` | technical astrophysical constraints |
| `plaga_2008_metastable_black_holes` | critique / residual-risk argument |
| `giddings_mangano_2008_comments_plaga` | response to critique |

Pre-output audit questions:

- Do all source IDs exist in `data/cases/lhc_black_holes/case.yaml`?
- Does each source have a local text file and retrieval date where applicable?
- Are critique and response sources both present?
- Is public reassurance separated from technical safety evidence?

## 2. Freeze The Curated Map Before Comparing Outputs

A valid worked-region map should include:

- source-local claims about the cosmic-ray analogy,
- assumptions that could make collider conditions different from cosmic-ray conditions,
- support/challenge/dependency/tension relations,
- explicit cruxes,
- caveats about Hawking radiation, stable black-hole assumptions, and astrophysical constraints.

The reviewer should mark each claim:

| Decision | Meaning |
| --- | --- |
| `accept` | excerpt entails the claim |
| `revise` | claim is plausible but too strong or unclear |
| `reject` | excerpt does not support the claim |
| `needs_discussion` | source or inference requires adjudication |

Do not revise the map after seeing the flat baseline unless the map is moved back to draft status and the baseline comparison is rerun.

## 3. Generate Or Inspect The Flat Baseline

The flat baseline must use the same source subset and `flat_baseline_prompt_v1` from `docs/PROMPT_INVENTORY.md`.

The baseline should be judged as a normal synthesis, not as a claim map. A concise synthesis can omit detail. Count an omission as decision-space erosion only if the omission reduces the reader's ability to recover a decision-relevant option, frame, conflict, dependency, caveat, or source provenance.

## 4. Audit Erosion Findings

For each proposed erosion finding, the auditor checks:

| Check | Pass Condition |
| --- | --- |
| Source support | The lost item appears in the same source subset. |
| Decision relevance | The lost item affects how the question should be reasoned about. |
| Fairness | The baseline was not asked to produce the exact structured artifact. |
| Case-map contrast | The case map actually preserves the lost item. |

Example finding shape:

```yaml
loss_id: lhc_loss_001
loss_type: dependency
lost_item: "The cosmic-ray analogy depends on whether natural collisions cover the relevant low-velocity capture scenarios."
source_support:
  - lsag_2008_safety_review
  - giddings_mangano_2008_stable_black_holes
case_map_preserves: "depends_on relation between cosmic-ray analogue claims and stable-black-hole capture assumptions"
adversarial_check: survives
reviewer_decision: pending
```

## 5. Final Review Decision

The reviewer can assign:

- `draft`: not ready for audit.
- `human-review-needed`: ready for human audit but not approved.
- `human-reviewed-revise`: reviewed with required changes.
- `human-reviewed-showable`: suitable for demo use with stated limits.

Codex or another model must not assign a human-reviewed status without explicit human review notes.

## What This Demonstrates For FLF

The prototype is useful if a reviewer can see not only a polished answer, but also:

- which claims were source-grounded,
- which relationships carried the reasoning,
- which caveats and critiques survived,
- what a flat synthesis lost,
- where a future investigator could extend the case map.
