# Staged Map Quality Report

Status: `usable_with_review`
Score: `76`

## Summary

- claim_count: `81`
- relation_count: `5`
- relation_type_count: `3`
- relation_contract_count: `5`
- fallback_relation_count: `0`
- required_source_count: `7`
- sources_with_claims: `7`
- all_chunk_count: `47`
- selected_chunk_count: `14`
- skipped_chunk_count: `33`
- coverage_backfilled_claim_count: `27`
- consolidated_claim_count: `9`
- rejected_claim_count: `2`
- rejected_relation_count: `115`

## Issues

- `risk` `high_claim_count`: Accepted 81 claims; region target is at most 25.
- `risk` `near_duplicate_claims`: Near-duplicate claim pairs: eggs_c032/eggs_c034, eggs_c034/eggs_c035, eggs_c045/eggs_c046, eggs_c093/eggs_c094, eggs_c021/eggs_c077, eggs_c026/eggs_c077
- `note` `high_rejected_relation_ratio`: Rejected 115 relation proposals vs. 5 accepted relations.
- `note` `chunk_budget_backfilled_content`: Skipped 33 source chunks due to configured chunk budgets; added 27 deterministic coverage claims.

## Scaffold

```json
{
  "case_question": "What should an investigator believe about the health effects of eating eggs?",
  "epistemic_config_profile": {
    "profile_id": "general_decision_support",
    "label": "General Decision Support",
    "description": "A broad profile for mixed evidence packets and decision-relevant synthesis."
  },
  "required_sources": [
    "dga_2020_2025_pmc_summary",
    "aha_2019_dietary_cholesterol_pubmed",
    "aha_2023_dietary_cholesterol_news",
    "bmj_2020_egg_consumption_cvd",
    "jama_2019_dietary_cholesterol_eggs",
    "li_2020_egg_cholesterol_rct_meta",
    "nnr_2023_eggs_scoping_review"
  ],
  "source_roles": {
    "dga_2020_2025_pmc_summary": {
      "display_title": "Dietary Guidelines for Americans, 2020-2025",
      "evidence_role": "policy or guidance",
      "provenance_level": "official_guidance",
      "limitations": [
        "Guidance may combine evidence with policy judgment and may lag new evidence."
      ],
      "needs_upgrade": true,
      "inferred": true
    },
    "aha_2019_dietary_cholesterol_pubmed": {
      "display_title": "Dietary Cholesterol and Cardiovascular Risk: A Science Advisory From the American Heart Association",
      "evidence_role": "policy or guidance",
      "provenance_level": "official_guidance",
      "limitations": [
        "Guidance may combine evidence with policy judgment and may lag new evidence."
      ],
      "needs_upgrade": true,
      "inferred": true
    },
    "aha_2023_dietary_cholesterol_news": {
      "display_title": "Here's the latest on dietary cholesterol and how it fits in with a healthy diet",
      "evidence_role": "policy or guidance",
      "provenance_level": "official_guidance",
      "limitations": [
        "Guidance may combine evidence with policy judgment and may lag new evidence."
      ],
      "needs_upgrade": true,
      "inferred": true
    },
    "bmj_2020_egg_consumption_cvd": {
      "display_title": "Egg consumption and risk of cardiovascular disease: three large prospective US cohort studies, systematic review, and updated meta-analysis",
      "evidence_role": "empirical study",
      "provenance_level": "peer_reviewed",
      "limitations": [
        "Check population, endpoint, and design limits before treating as direct decision evidence."
      ],
      "needs_upgrade": true,
      "inferred": true
    },
    "jama_2019_dietary_cholesterol_eggs": {
      "display_title": "Associations of Dietary Cholesterol or Egg Consumption With Incident Cardiovascular Disease and Mortality",
      "evidence_role": "empirical study",
      "provenance_level": "peer_reviewed",
      "limitations": [
        "Check population, endpoint, and design limits before treating as direct decision evidence."
      ],
      "needs_upgrade": true,
      "inferred": true
    },
    "li_2020_egg_cholesterol_rct_meta": {
      "display_title": "Association between Egg Consumption and Cholesterol Concentration: A Systematic Review and Meta-Analysis of Randomized Controlled Trials",
      "evidence_role": "empirical study",
      "provenance_level": "peer_reviewed",
      "limitations": [
        "Check population, endpoint, and design limits before treating as direct decision evidence."
      ],
      "needs_upgrade": true,
      "inferred": true
    },
    "nnr_2023_eggs_scoping_review": {
      "display_title": "Eggs - a scoping review for Nordic Nutrition Recommendations 2023",
      "evidence_role": "evidence synthesis",
      "provenance_level": "secondary_summary",
      "limitations": [
        "Review conclusions depend on included-study quality and inclusion criteria."
      ],
      "needs_upgrade": true,
      "inferred": true
    }
  },
  "source_role_taxonomy": [
    {
      "role_id": "source_document",
      "description": "Provided source whose role is not yet known.",
      "keyword_markers": [],
      "limitations": [
        "Source role may need review."
      ]
    }
  ],
  "target_claim_roles": [
    {
      "role_id": "conclusion_support",
      "description": "Evidence or reasoning that supports a candidate answer.",
      "use_when": "A claim bears directly on the likely answer."
    },
    {
      "role_id": "crux",
      "description": "A claim whose truth would materially change the answer.",
      "use_when": "The decision turns on this uncertainty."
    },
    {
      "role_id": "scope_limit",
      "description": "A boundary on where a claim applies.",
      "use_when": "Population, context, timing, or evidence limits matter."
    },
    {
      "role_id": "implementation_constraint",
      "description": "A practical condition for applying a recommendation.",
      "use_when": "Feasibility, compliance, cost, operations, or rollout matters."
    },
    {
      "role_id": "background",
      "description": "Context needed to interpret the evidence.",
      "use_when": "Useful context that is not itself load-bearing."
    },
    {
      "role_id": "other",
      "description": "A useful claim that does not fit the other roles.",
      "use_when": "Use sparingly when no sharper role fits."
    }
  ],
  "relation_goals": [
    "Prefer crux_for, depends_on, in_tension_with, or challenges when those sharper relations fit.",
    "Use similar_to only when the claims are redundant enough to merge.",
    "connect at least one crux/scope-limit claim to a conclusion-support claim",
    "preserve tensions instead of flattening them",
    "use source limitations to bound claim strength",
    "prefer cross-source relations when they clarify disagreement or scope"
  ],
  "profile_evidence_sections": [
    {
      "section_id": "answer_drivers",
      "title": "Answer Drivers",
      "description": "Load-bearing evidence and cruxes.",
      "claim_roles": [
        "conclusion_support",
        "crux"
      ],
      "relation_types": [
        "supports",
        "crux_for"
      ]
    },
    {
      "section_id": "bounds_and_tensions",
      "title": "Bounds and Tensions",
      "description": "Limits, disagreements, and dependencies.",
      "claim_roles": [
        "scope_limit",
        "implementation_constraint"
      ],
      "relation_types": [
        "depends_on",
        "in_tension_with",
        "challenges"
      ]
    }
  ],
  "profile_relation_types": [
    {
      "relation_type": "supports",
      "description": "One claim increases support for another without being the decisive dependency.",
      "use_when": "Use for direct evidence or argument support.",
      "sharpness_markers": [
        "supports",
        "consistent with",
        "evidence for"
      ]
    },
    {
      "relation_type": "challenges",
      "description": "One claim undercuts or contradicts another.",
      "use_when": "Use for contrary evidence, validity objections, or failed assumptions.",
      "sharpness_markers": [
        "contradicts",
        "undercuts",
        "casts doubt"
      ]
    },
    {
      "relation_type": "refines",
      "description": "One claim narrows the population, endpoint, mechanism, condition, or interpretation of another.",
      "use_when": "Use when the boundary being refined is explicit.",
      "sharpness_markers": [
        "only for",
        "specifically",
        "boundary",
        "population",
        "endpoint"
      ]
    },
    {
      "relation_type": "similar_to",
      "description": "Claims are close enough that a reviewer may consider merging them.",
      "use_when": "Use only for near-duplicate or strongly overlapping claims.",
      "sharpness_markers": [
        "same as",
        "duplicates",
        "substantially overlaps"
      ]
    },
    {
      "relation_type": "depends_on",
      "description": "The force of one claim depends on a condition, implementation detail, or prerequisite.",
      "use_when": "Use for conditional recommendations, feasibility dependencies, and assumptions.",
      "sharpness_markers": [
        "depends",
        "requires",
        "only if",
        "unless",
        "condition"
      ]
    },
    {
      "relation_type": "crux_for",
      "description": "One claim is a decision crux for another or for the question.",
      "use_when": "Use when changing belief in one claim would materially change the decision read.",
      "sharpness_markers": [
        "crux",
        "decisive",
        "would change",
        "key uncertainty"
      ]
    },
    {
      "relation_type": "in_tension_with",
      "description": "Claims can both be partly true but pull the decision in different directions.",
      "use_when": "Use for tradeoffs, external-validity limits, and evidence-vs-implementation tensions.",
      "sharpness_markers": [
        "however",
        "tradeoff",
        "tension",
        "limited",
        "unclear"
      ]
    }
  ],
  "allowed_relation_types": [
    "challenges",
    "crux_for",
    "depends_on",
    "in_tension_with",
    "refines",
    "similar_to",
    "supports"
  ],
  "quality_checks": [
    "every required source should contribute at least one useful claim unless genuinely irrelevant",
    "claims must be entailed by exact excerpts",
    "relations must use only accepted claim IDs and ontology relation types",
    "the final map should expose cruxes, scope limits, and source-role boundaries",
    "near-duplicate claims should be merged or given distinct roles"
  ]
}
```
