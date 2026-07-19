# Deterministic map_plus_sources Retrieval Proxy

Question: Which disagreement concerns process, which concerns evidence, and which concerns Bayesian structure?

The map condition can recover these frozen answer-key objects:

## process_evidence_bayesian_disagreements

The disagreement spans debate process, evidentiary interpretation, and Bayesian structural assumptions.

Claims:

- `covid_c001` [flf_covid_case_brief; case framing]: FLF frames COVID origins as a hard epistemic case because expert judgment favored zoonosis while Bayesian analyses of the evidence diverged sharply.
  - excerpt: "judges ruled for zoonosis; Bayesian analyses diverged sharply"
- `covid_c005` [rootclaim_debate_results; participant concession]: Rootclaim concedes that Peter Miller won the judged debate.
  - excerpt: "Peter Miller won the debate"
- `covid_c011` [good_judgment_superforecasting; update trigger]: Good Judgment identifies concrete update triggers on both sides, including an ancestor virus, a definitive animal host, or strong lab-leak evidence.
  - excerpt: "would update on evidence such as an identified ancestor virus"
- `covid_c017` [weissman_2026_phylogeny_comment; phylogeny critique]: Weissman's later critique argues that correcting a Bayesian error favors a single introduction over two introductions.
  - excerpt: "larger likelihood for a single introduction than for two introductions"

Relations:

- `covid_r001` (supports): `covid_c001` -> `covid_c002`. The sharp divergence between expert judgment and Bayesian analyses explains why FLF treats the case as hard to navigate.
- `covid_r011` (in_tension_with): `covid_c017` -> `covid_c018`. The critique may weaken a two-spillover subclaim, but the scope caveat prevents treating it as whole-case resolution.

Sources:

- `flf_covid_case_brief`
- `rootclaim_debate_results`
- `levin_2025_bayesian_assessment`
