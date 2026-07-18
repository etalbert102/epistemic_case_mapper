# COVID origins slice Map Packet

This packet exposes the reviewable case structure: sources, claims, relations, and crux candidates.

## Sources

- `flf_covid_case_brief`
- `acx_rootclaim_review`
- `rootclaim_debate_results`
- `good_judgment_superforecasting`
- `debarre_worobey_reply`
- `levin_2025_bayesian_assessment`
- `weissman_2026_phylogeny_comment`

## Claims

- `covid_c001` [flf_covid_case_brief; case framing]: FLF frames COVID origins as a hard epistemic case because expert judgment favored zoonosis while Bayesian analyses of the evidence diverged sharply.
- `covid_c002` [flf_covid_case_brief; case difficulty]: FLF treats the COVID record as difficult because it is expert-heavy, hard to navigate, and still evolving after the debate.
- `covid_c003` [acx_rootclaim_review; method framing]: Scott Alexander frames the Rootclaim debate as a test of explicit Bayesian reasoning applied to a fuzzy real-world dispute.
- `covid_c004` [acx_rootclaim_review; market-location caveat]: The Huanan market can be relevant as a superspreading location even if that fact alone does not establish the first infection occurred there.
- `covid_c005` [rootclaim_debate_results; participant concession]: Rootclaim concedes that Peter Miller won the judged debate.
- `covid_c006` [rootclaim_debate_results; participant disagreement]: Rootclaim maintains after the debate that lab leak remains the most likely explanation.
- `covid_c007` [rootclaim_debate_results; process critique]: Rootclaim argues that the live debate format rewarded memorized detail and disadvantaged its preferred reasoning process.
- `covid_c008` [rootclaim_debate_results; Bayesian critique]: Rootclaim's postmortem criticizes the judges' probabilistic inference rather than merely rejecting the bottom-line ruling.
- `covid_c009` [good_judgment_superforecasting; forecast aggregate]: Good Judgment's aggregate forecast favored natural zoonosis over biomedical research-related accident.
- `covid_c010` [good_judgment_superforecasting; forecast disagreement]: Good Judgment also preserves persistent minority disagreement: some forecasters considered a biomedical research-related accident most likely.
- `covid_c011` [good_judgment_superforecasting; update trigger]: Good Judgment identifies concrete update triggers on both sides, including an ancestor virus, a definitive animal host, or strong lab-leak evidence.
- `covid_c012` [debarre_worobey_reply; methodological rebuttal]: Debarre and Worobey reject the inference that early Wuhan case geography reveals major proximity ascertainment bias.
- `covid_c013` [debarre_worobey_reply; geography caveat]: Their rebuttal depends partly on distinguishing residential locations from infection locations and allowing stochasticity.
- `covid_c014` [levin_2025_bayesian_assessment; Bayesian decomposition]: Levin's Bayesian assessment decomposes the origins question into four conditional factors rather than one undifferentiated probability.
- `covid_c015` [levin_2025_bayesian_assessment; lab-leak-favoring result]: Levin reports a very large odds ratio favoring accidental lab leak.
- `covid_c016` [levin_2025_bayesian_assessment; review-status caveat]: Levin's source status should be kept distinct from a peer-reviewed consensus result because it is an NBER working paper.
- `covid_c017` [weissman_2026_phylogeny_comment; phylogeny critique]: Weissman's later critique argues that correcting a Bayesian error favors a single introduction over two introductions.
- `covid_c018` [weissman_2026_phylogeny_comment; scope caveat]: The multiple-introduction critique is a subargument and should not be automatically treated as a full COVID origins resolution.

## Relations

- `covid_r001` (supports): `covid_c001` -> `covid_c002`. The sharp divergence between expert judgment and Bayesian analyses explains why FLF treats the case as hard to navigate.
- `covid_r002` (in_tension_with): `covid_c005` -> `covid_c006`. Rootclaim concedes the debate result while maintaining the opposite substantive bottom line.
- `covid_r003` (refines): `covid_c007` -> `covid_c005`. The process critique narrows what Rootclaim accepts from the loss: debate outcome, not epistemic settlement.
- `covid_r004` (similar_to): `covid_c008` -> `covid_c014`. Both claims concern Bayesian inference, but one criticizes debate judgments while the other describes a formal decomposition.
- `covid_r005` (refines): `covid_c009` -> `covid_c010`. The minority distribution qualifies the aggregate forecast and prevents flattening Good Judgment into unanimity.
- `covid_r006` (refines): `covid_c011` -> `covid_c009`. Update triggers turn the aggregate forecast into a conditional belief state rather than a fixed conclusion.
- `covid_r007` (challenges): `covid_c012` -> `covid_c015`. The Debarre/Worobey reply challenges one kind of geography-based lab-leak-favoring inference, although it does not evaluate all of Levin's decomposition.
- `covid_r008` (depends_on): `covid_c013` -> `covid_c012`. The rejection of major ascertainment bias depends partly on the residential-location versus infection-location distinction.
- `covid_r009` (supports): `covid_c014` -> `covid_c015`. The reported odds ratio follows from Levin's factor decomposition and factor estimates.
- `covid_r010` (refines): `covid_c016` -> `covid_c015`. The working-paper status qualifies how much authority a reviewer should assign to the reported odds ratio.
- `covid_r011` (in_tension_with): `covid_c017` -> `covid_c018`. The critique may weaken a two-spillover subclaim, but the scope caveat prevents treating it as whole-case resolution.
- `covid_r012` (in_tension_with): `covid_c004` -> `covid_c012`. Market relevance can be framed as superspreading location or origin-site evidence, which changes how geography is weighted.
- `covid_r013` (crux_for): `covid_c014` -> `covid_c001`. Whether Bayesian decompositions are robust is central to explaining the sharp divergence FLF flags.
- `covid_r014` (crux_for): `covid_c012` -> `covid_c001`. Whether early-case geography survives bias critiques affects a major evidence family in the COVID origins dispute.
- `covid_r015` (supports): `covid_c011` -> `covid_c002`. Explicit update triggers show why the case remains evolving rather than settled once and for all.

## Crux Candidates

- crux: Are Huanan-market spatial patterns best treated as origin-site evidence, superspreading evidence, or an artifact of ascertainment/infection-location assumptions? Linked claims: `covid_c004`, `covid_c012`, `covid_c013`.
- crux: Are Bayesian decompositions like Levin's robust, or do correlated/contestable factors drive extreme odds ratios? Linked claims: `covid_c014`, `covid_c015`, `covid_c016`.
- crux: Should post-debate process critiques change confidence in the debate outcome, or only the design of future adjudication? Linked claims: `covid_c005`, `covid_c007`, `covid_c008`.

## Similar But Not Identical

- `covid_c009` and `covid_c010`: aggregate forecast and minority disagreement are related but not interchangeable.
- `covid_c004`, `covid_c012`, and `covid_c013`: all concern location evidence, but they represent different roles for market geography.
- `covid_c015` and `covid_c017`: both favor lab-leak-compatible updates, but one is whole-decomposition odds and one is a phylogenetic subargument.
