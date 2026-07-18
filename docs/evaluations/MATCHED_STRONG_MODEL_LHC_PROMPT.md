# Matched Strong-Model LHC Comparison Prompt

You are a careful research analyst. Answer using only the five source files listed below. Do not inspect the worked map, challenge answer keys, erosion audit, or any generated comparison artifacts.

Decision context: we are testing whether a strong flat synthesis from the same LHC source universe preserves the dependency structure needed by a later investigator.

Source universe:

- `data/cases/lhc_black_holes/sources/text/lsag_2008_safety_review.txt`
- `data/cases/lhc_black_holes/sources/text/spc_2008_lsag_review.txt`
- `data/cases/lhc_black_holes/sources/text/giddings_mangano_2008_stable_black_holes.txt`
- `data/cases/lhc_black_holes/sources/text/plaga_2008_metastable_black_holes.txt`
- `data/cases/lhc_black_holes/sources/text/giddings_mangano_2008_comments_plaga.txt`

Task:

Produce a concise but decision-useful answer to the following frozen investigator questions:

1. Why is Earth survival under cosmic-ray collisions not sufficient by itself?
2. Why do compact astronomical bodies become relevant?
3. Which claims and sources carry the velocity/trapping transition?
4. Which criticism most directly challenges the compact-star safety argument?
5. What would have to change for the bottom-line risk assessment to move materially?

Output format:

- Use short section headings.
- Cite source filenames inline.
- Preserve distinctions between broad natural-exposure reassurance, low-velocity/trapping caveats, compact-object bounds, Plaga's critique, and Giddings/Mangano's response.
- Do not mention claim IDs or relation IDs, because those are not exposed in this condition.

After the answer, include a short self-audit:

- Which dependencies were easy to recover from the source universe?
- Which dependencies remain hard to trace without a structured map?
- What would a later investigator need to verify manually?
