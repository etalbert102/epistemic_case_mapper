# Deterministic map_plus_sources Retrieval Proxy

Question: Does conceding the judged debate imply conceding the substantive conclusion?

The map condition can recover these frozen answer-key objects:

## debate_result_vs_substantive_conclusion

Conceding that judges ruled against Rootclaim is different from conceding the substantive lab-origin conclusion.

Claims:

- `covid_c005` [rootclaim_debate_results; participant concession]: Rootclaim concedes that Peter Miller won the judged debate.
  - excerpt: "Peter Miller won the debate"
- `covid_c006` [rootclaim_debate_results; participant disagreement]: Rootclaim maintains after the debate that lab leak remains the most likely explanation.
  - excerpt: "lab leak remains the most likely explanation"

Relations:

- `covid_r002` (in_tension_with): `covid_c005` -> `covid_c006`. Rootclaim concedes the debate result while maintaining the opposite substantive bottom line.

Sources:

- `rootclaim_debate_results`
