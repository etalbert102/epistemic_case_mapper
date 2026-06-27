# Eggs And Health Source Inventory

Retrieval date: 2026-06-26

This directory stores source documents for the source-grounded eggs-and-health case.

- Raw downloaded files: `sources/raw/`
- Extracted text for mapping: `sources/text/`
- Case manifest: `../case.yaml`

## Source Set

| Source ID | Role | Raw file | Text file |
| --- | --- | --- | --- |
| `aha_2019_dietary_cholesterol_pubmed` | AHA science advisory record | `raw/aha_2019_dietary_cholesterol_pubmed.html` | `text/aha_2019_dietary_cholesterol_pubmed.txt` |
| `aha_2023_dietary_cholesterol_news` | AHA public guidance explainer | `raw/aha_2023_dietary_cholesterol_news.html` | `text/aha_2023_dietary_cholesterol_news.txt` |
| `dga_2020_2025_pmc_summary` | U.S. federal dietary guideline summary | `raw/dga_2020_2025_pmc_summary.html` | `text/dga_2020_2025_pmc_summary.txt` |
| `bmj_2020_egg_consumption_cvd` | large cohorts plus updated meta-analysis | `raw/bmj_2020_egg_consumption_cvd_pmc.html` | `text/bmj_2020_egg_consumption_cvd_pmc.txt` |
| `bmj_2013_egg_consumption_chd_stroke` | dose-response prospective-cohort meta-analysis | `raw/bmj_2013_egg_consumption_chd_stroke_pmc.html` | `text/bmj_2013_egg_consumption_chd_stroke_pmc.txt` |
| `jama_2019_dietary_cholesterol_eggs` | pooled cohort study with cautionary findings | `raw/jama_2019_dietary_cholesterol_eggs_pmc.html` | `text/jama_2019_dietary_cholesterol_eggs_pmc.txt` |
| `li_2020_egg_cholesterol_rct_meta` | randomized-trial lipid meta-analysis | `raw/li_2020_egg_cholesterol_rct_meta_pmc.html` | `text/li_2020_egg_cholesterol_rct_meta_pmc.txt` |
| `ma_2021_egg_cvd_dose_response` | later dose-response CVD meta-analysis | `raw/ma_2021_egg_cvd_dose_response_pmc.html` | `text/ma_2021_egg_cvd_dose_response_pmc.txt` |
| `huang_2020_egg_health_outcomes_evidence_mapping` | global evidence map | `raw/huang_2020_egg_health_outcomes_evidence_mapping_pmc.html` | `text/huang_2020_egg_health_outcomes_evidence_mapping_pmc.txt` |
| `nnr_2023_eggs_scoping_review` | Nordic Nutrition Recommendations scoping review | `raw/nnr_2023_eggs_scoping_review_pmc.html` | `text/nnr_2023_eggs_scoping_review_pmc.txt` |
| `eggs_dietary_cholesterol_cvd_review` | narrative review | `raw/eggs_dietary_cholesterol_cvd_pmc.html` | `text/eggs_dietary_cholesterol_cvd_pmc.txt` |
| `dietary_cholesterol_lack_evidence_cvd_review` | narrative review arguing evidence is limited | `raw/dietary_cholesterol_lack_evidence_cvd_pmc.html` | `text/dietary_cholesterol_lack_evidence_cvd_pmc.txt` |

## Source URLs

- `aha_2019_dietary_cholesterol_pubmed`: https://pubmed.ncbi.nlm.nih.gov/31838890/
- `aha_2023_dietary_cholesterol_news`: https://www.heart.org/en/news/2023/08/25/heres-the-latest-on-dietary-cholesterol-and-how-it-fits-in-with-a-healthy-diet
- `dga_2020_2025_pmc_summary`: https://pmc.ncbi.nlm.nih.gov/articles/PMC8713704/
- `bmj_2020_egg_consumption_cvd`: https://pmc.ncbi.nlm.nih.gov/articles/PMC7190072/
- `bmj_2013_egg_consumption_chd_stroke`: https://pmc.ncbi.nlm.nih.gov/articles/PMC3538567/
- `jama_2019_dietary_cholesterol_eggs`: https://pmc.ncbi.nlm.nih.gov/articles/PMC6439941/
- `li_2020_egg_cholesterol_rct_meta`: https://pmc.ncbi.nlm.nih.gov/articles/PMC7400894/
- `ma_2021_egg_cvd_dose_response`: https://pmc.ncbi.nlm.nih.gov/articles/PMC8137614/
- `huang_2020_egg_health_outcomes_evidence_mapping`: https://pmc.ncbi.nlm.nih.gov/articles/PMC7723562/
- `nnr_2023_eggs_scoping_review`: https://pmc.ncbi.nlm.nih.gov/articles/PMC10870976/
- `eggs_dietary_cholesterol_cvd_review`: https://pmc.ncbi.nlm.nih.gov/articles/PMC6790443/
- `dietary_cholesterol_lack_evidence_cvd_review`: https://pmc.ncbi.nlm.nih.gov/articles/PMC6024687/

## Notes

- Direct BMJ and AHA publisher downloads blocked automated access; PMC/PubMed/AHA public pages were used where available.
- Direct Dietary Guidelines PDF retrieval stalled during acquisition. The guideline role is represented by the PMC summary of the Dietary Guidelines for Americans, AHA guidance, and the Nordic Nutrition Recommendations scoping review; a future pass can add the full USDA/HHS PDF if needed.
- The corpus intentionally includes neutral, cautionary, mechanistic, and guideline-oriented sources so the map can preserve disagreement and heterogeneity.

## Checksums

Run from `data/cases/eggs/`:

```bash
shasum -a 256 sources/raw/* sources/text/*
```

Expected SHA-256 values for referenced source files:

```text
f7b5966117376b79c062c238ee3323032e7b958d3ae62c17c8f111e4c24f5eb1  sources/raw/aha_2019_dietary_cholesterol_pubmed.html
6d54bb38225fb88c4de55d187f5e392cd0f96034ea67e35436e72c05f87240a0  sources/raw/aha_2023_dietary_cholesterol_news.html
e5489946ce8d0d6adbf05e66138d0323b8d8c2c829a10649c620cc00701131df  sources/raw/bmj_2013_egg_consumption_chd_stroke_pmc.html
031ca4cb317415e1bf09a535913b901b5abe71e53d8925a1c70f888247e22c81  sources/raw/bmj_2020_egg_consumption_cvd_pmc.html
78e0a4c4ba15404fe7ceaa2d6d4780869905c96f6fe8b2fa9517edce85e6481c  sources/raw/dietary_cholesterol_lack_evidence_cvd_pmc.html
16ebde5b1efde928e418b7fb434b6835defeaf9d89e3c9c3731554dc0e027408  sources/raw/eggs_dietary_cholesterol_cvd_pmc.html
16ac792c7d64298cfa6a8fcb517a25591159a39c4de222391cca5479380dabf5  sources/raw/huang_2020_egg_health_outcomes_evidence_mapping_pmc.html
c273421d1cf0d00c7dacbeda4615111ff417c108d24a31108dd094e35a725e6d  sources/raw/jama_2019_dietary_cholesterol_eggs_pmc.html
5dbe316cc43d65e9ca3e01c256aebabda2c521ecd59bc517c3cefefd6beb283f  sources/raw/li_2020_egg_cholesterol_rct_meta_pmc.html
330de32159a68de60a62576b6da775ca3124103c1295c9e27e7275512e3eb6f0  sources/raw/ma_2021_egg_cvd_dose_response_pmc.html
6753e6baad23d0e51e7c6272f494a3149d8e78a039bb04af96979b0f2f522ea0  sources/raw/nnr_2023_eggs_scoping_review_pmc.html
ecb2c2637641144f59f7964345ba26e8683cb41cdc18fda369042164e826fab6  sources/text/aha_2019_dietary_cholesterol_pubmed.txt
1924e10645a154b2431a97cb1c11db5e99e3eacca5aedbbc172ccf10a738abbe  sources/text/aha_2023_dietary_cholesterol_news.txt
78528c14135789cc115beb34621f7666c25e5e76064beeaa6adaad4e5f12d0ca  sources/text/bmj_2013_egg_consumption_chd_stroke_pmc.txt
a902fbe879ee9356f1a18635736cae1b98fd3a28f4aaefd932df6b056a996f63  sources/text/bmj_2020_egg_consumption_cvd_pmc.txt
f42380c63d1ded76f08286a684c5eabf5b859c0a9ff6ee465e40e42d1fa23eb5  sources/text/dietary_cholesterol_lack_evidence_cvd_pmc.txt
0dd3f0f747b0de9078013f7e07f64488354fbbcbb0695d3278583c08340e7fa0  sources/text/eggs_dietary_cholesterol_cvd_pmc.txt
4d05ab4d05ff22d0024bb27fd30708555f76c7335ccd68e10a0bba0ef9609632  sources/text/huang_2020_egg_health_outcomes_evidence_mapping_pmc.txt
bd8237dee5cf3dc937d799fa1e73f0a5fe601d33dcf670fbb8a08883b9888495  sources/text/jama_2019_dietary_cholesterol_eggs_pmc.txt
308cf2076a639367dd7c7a685e72d7c52abdb59cff5163d7ca6c31f238db2dff  sources/text/li_2020_egg_cholesterol_rct_meta_pmc.txt
ebbee5bef5744a090dbee71e06733b998d4350b10ad9199e7542786680a2c897  sources/text/ma_2021_egg_cvd_dose_response_pmc.txt
3fe0e299dff7d77391a64d7734d7b17c29f1b76b4fae5cd09d068ec3729f9193  sources/text/nnr_2023_eggs_scoping_review_pmc.txt
```
