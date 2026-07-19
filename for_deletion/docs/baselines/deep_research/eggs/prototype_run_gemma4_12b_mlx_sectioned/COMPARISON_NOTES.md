# Section-Aware Comparison Notes

Question: For generally healthy adults, should eggs be treated as meaningfully harmful, neutral, or beneficial in dietary advice, especially with respect to cardiovascular risk?

## Result

The section-aware briefing is meaningfully cleaner than the first prototype run, but Deep Research remains stronger as a final reader-facing report.

The prototype's advantage is now clearer: it produces inspectable evidence buckets and prevents the most obvious category error where concern evidence appeared under `Main Support`. Its weakness remains prose-level judgment and calibration.

## Improvements Over First Prototype Run

- `Main Support` now contains low-concern / neutrality evidence rather than mixed concern evidence.
- Spence-style concern evidence appears under `Conflicting Evidence`.
- Zhong-style positive association evidence is no longer presented as support for the bottom line.
- `Claim A` / `Claim B` wording was removed from the briefing.
- The prompt now tells the model to synthesize each section only from mechanically separated section buckets.

## Remaining Weaknesses Versus Deep Research

- The bottom line still says "neutral to potentially beneficial," which is less careful than Deep Research's "approximately neutral at moderate intake" framing.
- The diabetes implication remains too permissive. It emphasizes neutral DIABEGG biomarker trials without enough caution about concerning diabetic cohort signals.
- The conflict prose is still awkward in places, especially where relation rationales combine two claims in one sentence.
- The subgroup section is thinner than Deep Research's discussion of diabetes, high LDL/ApoB, familial hypercholesterolemia, hyper-responders, high baseline risk, and high intake.
- Quantitative details are still less rich because the reconstructed source packet is mostly PubMed abstracts.

## Updated Assessment

The new split is directionally correct. Deterministic partitioning prevents obvious category mistakes, and the model is better used for prose within bounded sections. The prototype still needs a stronger final synthesis prompt or post-pass for calibrated bottom-line wording, especially subgroup caveats.

Deep Research is still the better final report. The prototype is closer now because it offers map-backed inspectability without as much section confusion.
