# LHC Black Hole Risk Source Inventory

Retrieval date: 2026-06-26

This directory stores source documents for the source-grounded LHC black-hole-risk case.

- Raw downloaded files: `sources/raw/`
- Extracted text for mapping: `sources/text/`
- Case manifest: `../case.yaml`

## Source Set

| Source ID | Role | Raw file | Text file |
| --- | --- | --- | --- |
| `lsag_2008_safety_review` | formal safety assessment | `raw/lsag_2008_safety_review.pdf` | `text/lsag_2008_safety_review.txt` |
| `spc_2008_lsag_review` | independent review | `raw/spc_2008_lsag_review.pdf` | `text/spc_2008_lsag_review.txt` |
| `giddings_mangano_2008_stable_black_holes` | technical stable-black-hole safety analysis | `raw/giddings_mangano_2008_stable_black_holes.pdf` | `text/giddings_mangano_2008_stable_black_holes.txt` |
| `cern_lhc_current_page` | current CERN public explanation | `raw/cern_lhc_current_page.html` | `text/cern_lhc_current_page.txt` |
| `cern_tiny_black_holes_page` | current CERN public tiny-black-hole explanation | `raw/cern_tiny_black_holes_page.html` | `text/cern_tiny_black_holes_page.txt` |
| `cms_2011_black_hole_search` | CMS public search summary | `raw/cms_2011_black_hole_search.html` | `text/cms_2011_black_hole_search.txt` |
| `cms_2010_black_hole_search_paper` | CMS technical search paper | `raw/cms_black_hole_search_paper.pdf` | `text/cms_black_hole_search_paper.txt` |
| `plaga_2008_metastable_black_holes` | technical critique | `raw/plaga_2008_metastable_black_holes.pdf` | `text/plaga_2008_metastable_black_holes.txt` |
| `giddings_mangano_2008_comments_plaga` | technical response to critique | `raw/giddings_mangano_2008_comments_plaga.pdf` | `text/giddings_mangano_2008_comments_plaga.txt` |
| `johnson_2009_black_hole_case` | legal/public-risk framing | `raw/johnson_2009_black_hole_case.pdf` | `text/johnson_2009_black_hole_case.txt` |

## Source URLs

- `lsag_2008_safety_review`: https://cds.cern.ch/record/1111112
- `spc_2008_lsag_review`: https://indico.cern.ch/event/35065/contributions/1757729/attachments/693082/951703/SPC_on_LSAG_report.pdf
- `giddings_mangano_2008_stable_black_holes`: https://arxiv.org/abs/0806.3381
- `cern_lhc_current_page`: https://home.cern/science/accelerators/large-hadron-collider/
- `cern_tiny_black_holes_page`: https://home.cern/science/physics/extra-dimensions-gravitons-and-tiny-black-holes/
- `cms_2011_black_hole_search`: https://cms.cern/news/search-microscopic-black-hole-signatures-large-hadron-collider
- `cms_2010_black_hole_search_paper`: https://arxiv.org/abs/1012.3375
- `plaga_2008_metastable_black_holes`: https://arxiv.org/abs/0808.1415
- `giddings_mangano_2008_comments_plaga`: https://arxiv.org/abs/0808.4087
- `johnson_2009_black_hole_case`: https://arxiv.org/abs/0912.5480

## Checksums

Run from `data/cases/lhc_black_holes/`:

```bash
shasum -a 256 sources/raw/* sources/text/*
```

Expected SHA-256 values:

```text
403953c88f99f0ac7fd002c3a2c03279f0d0f72da435caf9830406601f0c4c9a  sources/raw/cern_lhc_current_page.html
ba752e6c724dd0992bccfde5ce3c3c5b2da8178e7d5bd03170adfc9313206441  sources/raw/cern_tiny_black_holes_page.html
b03b5f9e596f95dae4148f99873316f640183a9e2698ff7511d85680ec32fed6  sources/raw/cms_2011_black_hole_search.html
768f8d2de5cccd86b3f22caa094ed25b477ab8f8aac154eed91bdefbb27d593c  sources/raw/cms_black_hole_search_paper.pdf
5a2d40abae63463b0a26f0ab02d0a9c475e2164a21e718b989a169012651f6c1  sources/raw/giddings_mangano_2008_comments_plaga.pdf
939f8daa4ce9a6e93712ddb4f21a3118fdc618dc4c7fd5eaea0171a74429e365  sources/raw/giddings_mangano_2008_stable_black_holes.pdf
afdf520d0a190fcfaa65b32eebfc66ada824099af82a440c4c048242086c53e9  sources/raw/johnson_2009_black_hole_case.pdf
ab0bec65c077f2dc169c7dcb42bf7d07b06ef056332795e428db6a801bc6771a  sources/raw/lsag_2008_safety_review.pdf
0f41a2c1385df8e03d9d05bc23f011aeb03a888836cb02638875db5dfa88260a  sources/raw/plaga_2008_metastable_black_holes.pdf
2b1c01842b07cbe50f60930350db0217987ce7f36891d31120bffb4c8c1a919e  sources/raw/spc_2008_lsag_review.pdf
9e2f2209d84ed28bf39743a3ce652e9d55db26acc4dd69128e4f87145a391344  sources/text/cern_lhc_current_page.txt
9cb2ce750f2d0e67077a9e9879598e20fd3a2e9aac15a41f77abdb5f4722b264  sources/text/cern_tiny_black_holes_page.txt
8928acae67ebbcc6014ef3734144e9b25d3dda3ae3b6928880a9273b0c458830  sources/text/cms_2011_black_hole_search.txt
d08e7e7ab9fc09b83d4ccb18009c9da8be3142b651b212ae44931f2a64acac0f  sources/text/cms_black_hole_search_paper.txt
05ba8af2a0608a30b2ebd915f899cd772ed543e4dd85148b3e66e9902c0f4e09  sources/text/giddings_mangano_2008_comments_plaga.txt
a505a320b5c0617a02fc04385e9286cac717f6c8d2a80f3b9d8cc8ec55b4da6a  sources/text/giddings_mangano_2008_stable_black_holes.txt
4da129e3192b0b40704cb0a45b22836cfd3af0c3bdba5a9a9e4599f9096ee039  sources/text/johnson_2009_black_hole_case.txt
6e4f5244885bae3d208a754477226c7b55c3796aa7111acb231ccb8397830b56  sources/text/lsag_2008_safety_review.txt
7016e150794f26f2caafcbc56dec33125a7bfa5b869df26acfd70fa501037d7d  sources/text/plaga_2008_metastable_black_holes.txt
034c4484e39be57629311976d5ae86e31da7329f5a7608e319da3dab5effeefe  sources/text/spc_2008_lsag_review.txt
```

## Notes

- The CERN archived Angels & Demons black-hole FAQ was not retained as a primary public explanation because the archived page available during retrieval did not expose the original content cleanly. Current CERN public pages were retained instead.
- The source-grounded manifest now points to extracted text files rather than raw PDFs/HTML so the current mapper can operate without PDF or HTML parsing at runtime.
