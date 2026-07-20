# COVID Worked Region: Bayesian Disagreement And Update Structure

Status: `human-review-needed`
Prompt/procedure: `covid_worked_region_v1_source_notes_manual_audit`
Evidence mode: `seed`

## Source Subset

- `flf_covid_case_brief`
- `acx_rootclaim_review`
- `rootclaim_debate_results`
- `good_judgment_superforecasting`
- `debarre_worobey_reply`
- `levin_2025_bayesian_assessment`
- `weissman_2026_phylogeny_comment`

## What To Notice

This slice is not a COVID origins adjudication or source-grounded evidence
packet. Its local files are investigator-authored notes and excerpts that have
not been verified against the cited originals. It is a representational stress
test that makes disagreement structure reviewable by separating:

- debate outcome from substantive posterior disagreement,
- aggregate forecasts from minority forecasts,
- Bayesian decomposition assumptions from source-status caveats,
- early-case geography arguments from whole-case resolution.

## Curated Claims

claim_id: covid_c001
source_id: flf_covid_case_brief
source_span: `source notes paragraph 2`
excerpt: "judges ruled for zoonosis; Bayesian analyses diverged sharply"
entailed_by_excerpt: yes
role: `case framing`
claim: The case brief frames COVID origins as a hard epistemic case because expert judgment favored zoonosis while Bayesian analyses of the evidence diverged sharply.

claim_id: covid_c002
source_id: flf_covid_case_brief
source_span: `source notes paragraph 2`
excerpt: "hard to navigate, requires significant expertise, and continues to evolve"
entailed_by_excerpt: yes
role: `case difficulty`
claim: The case brief treats the COVID record as difficult because it is expert-heavy, hard to navigate, and still evolving after the debate.

claim_id: covid_c003
source_id: acx_rootclaim_review
source_span: `source notes paragraph 2`
excerpt: "Rootclaim as an attempt to apply explicit Bayesian reasoning"
entailed_by_excerpt: yes
role: `method framing`
claim: Scott Alexander frames the Rootclaim debate as a test of explicit Bayesian reasoning applied to a fuzzy real-world dispute.

claim_id: covid_c004
source_id: acx_rootclaim_review
source_span: `source notes paragraph 3`
excerpt: "a busy, poorly ventilated market could be a plausible superspreading location"
entailed_by_excerpt: yes
role: `market-location caveat`
claim: The Huanan market can be relevant as a superspreading location even if that fact alone does not establish the first infection occurred there.

claim_id: covid_c005
source_id: rootclaim_debate_results
source_span: `source notes paragraph 2`
excerpt: "Peter Miller won the debate"
entailed_by_excerpt: yes
role: `participant concession`
claim: Rootclaim concedes that Peter Miller won the judged debate.

claim_id: covid_c006
source_id: rootclaim_debate_results
source_span: `source notes paragraph 2`
excerpt: "lab leak remains the most likely explanation"
entailed_by_excerpt: yes
role: `participant disagreement`
claim: Rootclaim maintains after the debate that lab leak remains the most likely explanation.

claim_id: covid_c007
source_id: rootclaim_debate_results
source_span: `source notes paragraph 3`
excerpt: "live format advantaged the debater with more memorized detail"
entailed_by_excerpt: yes
role: `process critique`
claim: Rootclaim argues that the live debate format rewarded memorized detail and disadvantaged its preferred reasoning process.

claim_id: covid_c008
source_id: rootclaim_debate_results
source_span: `source notes paragraph 3`
excerpt: "judges' probabilistic inference assigned unrealistic numbers"
entailed_by_excerpt: yes
role: `Bayesian critique`
claim: Rootclaim's postmortem criticizes the judges' probabilistic inference rather than merely rejecting the bottom-line ruling.

claim_id: covid_c009
source_id: good_judgment_superforecasting
source_span: `source notes paragraph 2`
excerpt: "natural zoonosis as the most likely cause at 74%"
entailed_by_excerpt: yes
role: `forecast aggregate`
claim: Good Judgment's aggregate forecast favored natural zoonosis over biomedical research-related accident.

claim_id: covid_c010
source_id: good_judgment_superforecasting
source_span: `source notes paragraph 2`
excerpt: "10 of 54 forecasters saw a biomedical research-related accident as most likely"
entailed_by_excerpt: yes
role: `forecast disagreement`
claim: Good Judgment also preserves persistent minority disagreement: some forecasters considered a biomedical research-related accident most likely.

claim_id: covid_c011
source_id: good_judgment_superforecasting
source_span: `source notes paragraph 3`
excerpt: "would update on evidence such as an identified ancestor virus"
entailed_by_excerpt: yes
role: `update trigger`
claim: Good Judgment identifies concrete update triggers on both sides, including an ancestor virus, a definitive animal host, or strong lab-leak evidence.

claim_id: covid_c012
source_id: debarre_worobey_reply
source_span: `source notes paragraph 2`
excerpt: "no internal evidence of major bias"
entailed_by_excerpt: yes
role: `methodological rebuttal`
claim: Debarre and Worobey reject the inference that early Wuhan case geography reveals major proximity ascertainment bias.

claim_id: covid_c013
source_id: debarre_worobey_reply
source_span: `source notes paragraph 3`
excerpt: "infection locations were not limited to residential neighborhoods"
entailed_by_excerpt: yes
role: `geography caveat`
claim: Their rebuttal depends partly on distinguishing residential locations from infection locations and allowing stochasticity.

claim_id: covid_c014
source_id: levin_2025_bayesian_assessment
source_span: `source notes paragraph 2`
excerpt: "decomposes the Bayes factor into four components"
entailed_by_excerpt: yes
role: `Bayesian decomposition`
claim: Levin's Bayesian assessment decomposes the origins question into four conditional factors rather than one undifferentiated probability.

claim_id: covid_c015
source_id: levin_2025_bayesian_assessment
source_span: `source notes paragraph 3`
excerpt: "14,900:1 favoring accidental lab leak"
entailed_by_excerpt: yes
role: `lab-leak-favoring result`
claim: Levin reports a very large odds ratio favoring accidental lab leak.

claim_id: covid_c016
source_id: levin_2025_bayesian_assessment
source_span: `source notes paragraph 3`
excerpt: "NBER working papers are circulated for discussion"
entailed_by_excerpt: yes
role: `review-status caveat`
claim: Levin's source status should be kept distinct from a peer-reviewed consensus result because it is an NBER working paper.

claim_id: covid_c017
source_id: weissman_2026_phylogeny_comment
source_span: `source notes paragraph 2`
excerpt: "larger likelihood for a single introduction than for two introductions"
entailed_by_excerpt: yes
role: `phylogeny critique`
claim: Weissman's later critique argues that correcting a Bayesian error favors a single introduction over two introductions.

claim_id: covid_c018
source_id: weissman_2026_phylogeny_comment
source_span: `source notes paragraph 3`
excerpt: "subissue, not the whole origins question"
entailed_by_excerpt: yes
role: `scope caveat`
claim: The multiple-introduction critique is a subargument and should not be automatically treated as a full COVID origins resolution.

## Relations

relation_id: covid_r001
source_claim: covid_c001
target_claim: covid_c002
relation_type: supports
rationale: The sharp divergence between expert judgment and Bayesian analyses explains why the case is hard to navigate.

relation_id: covid_r002
source_claim: covid_c005
target_claim: covid_c006
relation_type: in_tension_with
rationale: Rootclaim concedes the debate result while maintaining the opposite substantive bottom line.

relation_id: covid_r003
source_claim: covid_c007
target_claim: covid_c005
relation_type: refines
rationale: The process critique narrows what Rootclaim accepts from the loss: debate outcome, not epistemic settlement.

relation_id: covid_r004
source_claim: covid_c008
target_claim: covid_c014
relation_type: similar_to
rationale: Both claims concern Bayesian inference, but one criticizes debate judgments while the other describes a formal decomposition.

relation_id: covid_r005
source_claim: covid_c009
target_claim: covid_c010
relation_type: refines
rationale: The minority distribution qualifies the aggregate forecast and prevents flattening Good Judgment into unanimity.

relation_id: covid_r006
source_claim: covid_c011
target_claim: covid_c009
relation_type: refines
rationale: Update triggers turn the aggregate forecast into a conditional belief state rather than a fixed conclusion.

relation_id: covid_r007
source_claim: covid_c012
target_claim: covid_c015
relation_type: challenges
rationale: The Debarre/Worobey reply challenges one kind of geography-based lab-leak-favoring inference, although it does not evaluate all of Levin's decomposition.

relation_id: covid_r008
source_claim: covid_c013
target_claim: covid_c012
relation_type: depends_on
rationale: The rejection of major ascertainment bias depends partly on the residential-location versus infection-location distinction.

relation_id: covid_r009
source_claim: covid_c014
target_claim: covid_c015
relation_type: supports
rationale: The reported odds ratio follows from Levin's factor decomposition and factor estimates.

relation_id: covid_r010
source_claim: covid_c016
target_claim: covid_c015
relation_type: refines
rationale: The working-paper status qualifies how much authority a reviewer should assign to the reported odds ratio.

relation_id: covid_r011
source_claim: covid_c017
target_claim: covid_c018
relation_type: in_tension_with
rationale: The critique may weaken a two-spillover subclaim, but the scope caveat prevents treating it as whole-case resolution.

relation_id: covid_r012
source_claim: covid_c004
target_claim: covid_c012
relation_type: in_tension_with
rationale: Market relevance can be framed as superspreading location or origin-site evidence, which changes how geography is weighted.

relation_id: covid_r013
source_claim: covid_c014
target_claim: covid_c001
relation_type: crux_for
rationale: Whether Bayesian decompositions are robust is central to explaining the sharp divergence highlighted in the case brief.

relation_id: covid_r014
source_claim: covid_c012
target_claim: covid_c001
relation_type: crux_for
rationale: Whether early-case geography survives bias critiques affects a major evidence family in the COVID origins dispute.

relation_id: covid_r015
source_claim: covid_c011
target_claim: covid_c002
relation_type: supports
rationale: Explicit update triggers show why the case remains evolving rather than settled once and for all.

## Crux Candidates

- crux: Are Huanan-market spatial patterns best treated as origin-site evidence, superspreading evidence, or an artifact of ascertainment/infection-location assumptions? Linked claims: `covid_c004`, `covid_c012`, `covid_c013`.
- crux: Are Bayesian decompositions like Levin's robust, or do correlated/contestable factors drive extreme odds ratios? Linked claims: `covid_c014`, `covid_c015`, `covid_c016`.
- crux: Should post-debate process critiques change confidence in the debate outcome, or only the design of future adjudication? Linked claims: `covid_c005`, `covid_c007`, `covid_c008`.

## Similar But Not Identical

- `covid_c009` and `covid_c010`: aggregate forecast and minority disagreement are related but not interchangeable.
- `covid_c004`, `covid_c012`, and `covid_c013`: all concern location evidence, but they represent different roles for market geography.
- `covid_c015` and `covid_c017`: both favor lab-leak-compatible updates, but one is whole-decomposition odds and one is a phylogenetic subargument.

## Audit Notes

- This is a worked region, not a full COVID origins map.
- The source notes are deliberately short and must be checked against original sources before any human-reviewed status.
- The map is strongest as a demonstration of disagreement preservation and weakest as a substantive origins adjudication.

## Evidence Check

| Probe | Evidence | Boundary |
| --- | --- | --- |
| Local reasoning value | Separates debate outcome, forecasting aggregate, Bayesian decomposition, and methodological replies. | Needs human/domain review. |
| Transfer beyond this case | Adds the adversarial case as a narrow slice after LHC and eggs. | Still not full COVID. |
| Ability to absorb more work | Uses same source/claim/relation/audit pattern as other worked regions. | Source ingestion is source-note based, not full-corpus automated. |
| Reuse by later reviewers | Stable IDs and update triggers identify where future evidence would attach. | No multi-reviewer disagreement handling yet. |
