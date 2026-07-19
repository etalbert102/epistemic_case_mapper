# Direct Gemma MLX Baseline Comparison

| Output | Words | Citations | Term hits | Notes |
|---|---:|---:|---:|---|
| gemma12b_mlx_direct_constrained | 661 | 14 | 4/22 | Obeys citation format but drops almost all numeric anchors. |
| gemma12b_mlx_direct_no_requirements | 574 | 0 | 1/22 | Readable but generic; no source-ID citations. |
| gpt56_direct_constrained | 1264 | 30 | 20/22 | Best evidence retention and source binding. |
| gpt56_direct_no_requirements | 942 | 9 | 17/22 | Best natural prose, weaker retention than constrained GPT-5.6. |
| current_gemma_pipeline | 1290 | 47 | 4/22 | Traceable but still mechanically written and quantity-thin. |

## Metric Caveat
Term hits are a lightweight retention proxy over known eggs-case anchors, not a complete factuality evaluation.
