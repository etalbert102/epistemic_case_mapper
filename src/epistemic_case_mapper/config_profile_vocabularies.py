from __future__ import annotations

import json
from typing import Any


READER_ABBREVIATION_EXPANSIONS = {
    "RCTs": "randomized controlled trials",
    "HR": "hazard ratio",
    "CI": "confidence interval",
    "CVD": "cardiovascular disease",
    "LDL-c": "LDL cholesterol",
}


_BASE_PROFILE_VOCABULARY: dict[str, Any] = {
    "rewrite_rank_markers": ["unsafe", "not safe", "risk", "hazard", "cost", "maintenance", "capacity", "implementation", "randomized", "confounding"],
    "secondary_alternative_markers": [],
    "answer_frame_rules": [],
    "option_inference_markers": {},
    "option_aliases": {},
    "display_acronyms": {
        "acx": "ACX",
        "aha": "AHA",
        "bmj": "BMJ",
        "cdc": "CDC",
        "covid": "COVID",
        "dga": "DGA",
        "epa": "EPA",
        "flf": "FLF",
        "guv": "GUV",
        "jama": "JAMA",
        "nnr": "NNR",
        "pm": "PM",
        "pmc": "PMC",
        "rct": "RCT",
        "who": "WHO",
    },
    "display_regex_replacements": [],
    "anchor_term_patterns": [
        r"\b\d+(?:\.\d+)?%?\b",
    ],
    "reader_quality_bonus_markers": [
        "risk",
        "mortality",
        "compared",
        "versus",
        "rather than",
        "supplemental",
        "per day",
        "per week",
        "unsafe",
    ],
    "quantity_decision_markers": [
        "per day",
        "/day",
        "daily",
        "serving",
        "mg",
        "%",
        "percent",
    ],
    "quantity_role_markers": {
        "scope_or_subgroup_boundary": ["subgroup", "older", "boundary", "scope", "high-risk", "higher-risk"],
        "comparator_context": ["replace", "substitution", "comparator", "processed", "full fat"],
        "risk_estimate": ["hazard ratio", "relative risk", "odds ratio", "risk", "incident"],
        "biomarker_calibration": ["biomarker", "ratio", "mean difference", "md ="],
        "dose_boundary": ["per day", "/day", "daily", "dose", "serving"],
    },
    "concern_negated_markers": [
        " not associated ",
        " no association ",
        " no increase ",
        " no increased ",
        " no significant association ",
        " no significant difference ",
        " no adverse ",
        " did not have adverse ",
        " did not result in adverse ",
        " not independently associated ",
        " not statistically significant ",
        " lower risk ",
    ],
    "concern_contrast_markers": [" however ", " although ", " but ", " whereas "],
    "concern_markers": [
        " higher risk ",
        " increased risk ",
        " increase in risk ",
        " elevated risk ",
        " positive association ",
        " dose-response positive ",
        " associated with higher ",
        " associated with increased ",
        " all-cause mortality ",
        " harmful ",
        " adverse effect ",
        " adverse effects ",
        " should limit ",
        " avoid ",
        " caution ",
        " concern ",
    ],
    "support_markers": [
        " not associated ",
        " no association ",
        " no increase ",
        " no increased ",
        " no significant association ",
        " no significant difference ",
        " no adverse ",
        " did not have adverse ",
        " did not result in adverse ",
        " not independently associated ",
        " lower risk ",
        " reduced risk ",
        " neutral ",
    ],
    "scope_or_subgroup_markers": [
        " subgroup",
        " high baseline",
        " higher-risk",
        " adults aged",
        " population",
        " cohort",
        " duration",
        " follow-up",
        " high intake",
        " moderate intake",
        " not necessarily full text",
    ],
    "hard_outcome_signal_markers": [
        " mortality ",
        " death ",
        " hospitalization ",
        " incident ",
        " disease risk ",
        " all-cause ",
    ],
    "surrogate_signal_markers": [
        " biomarker",
        " surrogate",
        " marker",
        " intermediate endpoint",
    ],
    "support_signal_profile_markers": {
        "absence_of_harm_or_null": [
            "not associated",
            "no association",
            "no significant",
            "no adverse",
            "did not have adverse",
            "did not result in adverse",
            "not independently associated",
        ],
        "direct_benefit": [
            "reduced mortality",
            "reduced risk",
            "lower risk",
            "improved hard outcome",
            "improved survival",
            "beneficial effect",
        ],
        "surrogate_benefit": [
            "reduced biomarker",
            "improved biomarker",
        ],
    },
    "scope_dimension_markers": {
        "population_or_actor": [" subgroup", " patients", " adults", " children", " workers", " high risk", " higher-risk", " actor"],
        "dose_intensity_or_scale": [" dose", " per day", " per week", " high-", " low-", " moderate", " scale", " intensity", " ≥", " >", " <"],
        "time_horizon": [" months", " years", " follow-up", " short-term", " long-term", " over ", " duration"],
        "geography_jurisdiction_or_setting": [" setting", " jurisdiction", " country", " region"],
        "implementation_context": [" guideline", " implement", " practical", " feasible", " compliance"],
        "measurement_endpoint": [" biomarker", " endpoint", " mortality", " event", " surrogate", " measured"],
        "source_completeness": [" abstract", " pubmed", " metadata", " full text", " source document", " not necessarily", " unavailable"],
        "adversarial_or_incentive_concern": [" industry", " funded", " incentive", " conflict of interest", " misleading", " advocacy", " adversarial"],
    },
    "method_or_source_limit_markers": [
        " abstract",
        " pubmed metadata",
        " full text",
        " source document contains",
        " measurement",
        " biomarker",
        " surrogate",
        " guideline",
        " advisory",
        " implementation",
        " method",
        " not powered",
        " not necessarily",
    ],
    "memo_slot_direction_markers": {
        "alternatives_or_comparators": [
            " compared",
            " versus",
            " vs ",
            " over ",
            " rather than ",
            " instead of",
            " alternative",
            " supplemental",
            " replacement",
            " replace",
            " substitut",
        ],
    },
    "memo_slot_rank_markers": {
        "alternatives_or_comparators": ["compared", "versus", "rather than", "instead of", "alternative", "supplemental"],
        "implementation_constraints": ["depends", "requires", "feasible", "capacity", "size", "setting", "maintenance", "standard", "should"],
        "scope_conditions": ["depends", "requires", "feasible", "capacity", "size", "setting", "maintenance", "standard", "should"],
        "safety_or_risk": ["unsafe", "risk", "harm", "adverse", "failure"],
    },
    "expected_slot_question_markers": {
        "default_population": [" for ", " among ", " in ", " adults", " people", " patients", " population", " users"],
        "dose_or_intensity_threshold": [" consumption", " intake", " dose", " threshold", " exposure", " use", " using", " intervention", " treatment", " treated"],
        "high_risk_subgroup": [" subgroup", " especially", " high-risk", " higher-risk", " people with", " patients with", " adults with"],
        "mechanism": [" why ", " mechanism", " causal", " pathway", " mediated", " biomarker"],
        "substitution_or_comparator": [" compared", " versus", " vs ", " replace", " instead of", " rather than ", " alternative", " relative to", " over "],
        "implementation_constraint": [" feasible", " implementation", " maintenance", " cost", " noise", " upgrade", " operate", " serviced"],
        "safety_or_risk": [" safety", " unsafe", " adverse", " harm", " risk", " failure"],
        "setting_or_context": [" setting", " site"],
        "practical_recommendation": [" should ", " prioritize", " recommend", " guidance", " advice", " decision", " policy", " treat ", " use "],
    },
    "slot_value_patterns": {
        "dose_or_intensity_threshold": [
            r"(?:up to|less than|more than|at least|at most|around|approximately|about)?\s*[<≥≤>]?\s*(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:per|/)\s*(?:day|week|month)",
            r"\b(?:high|moderate|low)[-\s]?(?:intake|consumption|use|dose|exposure)[A-Za-z0-9/ <≥≤.,-]{0,60}",
        ],
        "high_risk_subgroup": [
            r"(?:people|patients|adults|individuals|participants) with [A-Za-z0-9 /\-]{3,80}",
            r"\b(?:subgroup|high-risk|higher-risk|vulnerable|priority population)[A-Za-z0-9 ,/\-]{0,80}",
        ],
        "mechanism": [
            r"[A-Za-z0-9 ,/\-]{0,70}\b(?:mechanism|causal|pathway|driven by|influenced by|mediated by)\b[A-Za-z0-9 ,/\-]{0,70}",
        ],
        "substitution_or_comparator": [
            r"[A-Za-z0-9 ,/\-]{0,80}\b(?:replace|replacing|substitut(?:e|ing|ion)|compared with|versus|instead of)\b[A-Za-z0-9 ,/\-]{0,90}",
            r"[A-Za-z0-9 ,/\-]{0,80}\b(?:compared to|rather than|alternative to|supplement(?:al|ary)? to|over)\b[A-Za-z0-9 ,/\-]{0,90}",
        ],
        "technical_or_capacity": [
            r"[A-Za-z0-9 .,%/\-]{0,80}\b(?:capacity|performance|throughput|coverage|technical fit)\b[A-Za-z0-9 .,%/\-]{0,100}",
        ],
        "implementation_constraint": [
            r"[A-Za-z0-9 .,%/\-]{0,80}\b(?:feasible|not feasible|maintenance|operate|operated|serviced|upgrade|standard|cost|noise|capacity)\b[A-Za-z0-9 .,%/\-]{0,100}",
            r"[A-Za-z0-9 .,%/\-]{0,80}\b(?:should|recommend|guidance|policy|implementation|practical)\b[A-Za-z0-9 .,%/\-]{0,100}",
        ],
        "safety_or_risk": [
            r"[A-Za-z0-9 .,%/\-]{0,80}\b(?:unsafe|not safe|adverse|harm|risk|hazard|failure)\b[A-Za-z0-9 .,%/\-]{0,100}",
        ],
        "setting_or_context": [
            r"[A-Za-z0-9 .,%/\-]{0,80}\b(?:setting|site|region|location|context|organization)\b[A-Za-z0-9 .,%/\-]{0,100}",
        ],
        "study_design": [
            r"\b(?:prospective cohort|cohort study|randomized controlled trial|randomised controlled trial|RCT|trial|meta-analysis|systematic review|pooled analysis|observational)[A-Za-z0-9 ,/\-]{0,70}",
        ],
        "endpoint_type": [
            r"\b(?:mortality|all-cause mortality|risk|endpoint|outcome|biomarker)[A-Za-z0-9 ,/\-]{0,70}",
        ],
        "default_population": [
            r"\b(?:generally healthy adults|healthy adults|general population|free-living individuals|participants without [A-Za-z0-9 ,/\-]{3,80})",
            r"\b(?:participants|adults|individuals|people) (?:free of|without|with no history of) [A-Za-z0-9 ,/\-]{3,90}",
        ],
    },
    "decision_slot_markers": {
        "default_population": ["participants", "patients", "people with", "general population", "without history"],
        "dose_or_intensity_threshold": ["dose", "threshold", "intensity", "per day", "per week", "up to", "<", ">", "≥", "≤"],
        "high_risk_subgroup": ["subgroup", "high-risk", "higher-risk", "patients with", "people with"],
        "mechanism": ["mechanism", "causal", "pathway", "biomarker", "particle", "transmission"],
        "substitution_or_comparator": ["replace", "substitut", "compared with", "compared to", "versus", "vs ", "instead of", "rather than", "alternative", "supplemental", "over "],
        "endpoint_type": ["mortality", "injury", "crash", "risk", "endpoint", "infection", "exposure", "outcome", "safety"],
        "study_design": ["cohort", "trial", "rct", "meta-analysis", "systematic review", "pooled", "prospective", "observational", "evaluation"],
        "practical_recommendation": ["guidance", "recommend", "should", "prioritize", "use", "consider", "policy"],
        "technical_or_capacity": ["capacity", "performance", "technical", "airflow", "filtration", "ventilation"],
        "implementation_constraint": ["feasible", "not feasible", "maintenance", "operate", "operated", "serviced", "upgrade", "standard", "cost", "noise", "capacity"],
        "safety_or_risk": ["unsafe", "adverse", "harm", "risk", "hazard", "not safe", "failure"],
        "setting_or_context": ["setting", "site", "building", "home", "workplace", "county", "region"],
    },
    "evidence_slot_markers": {
        "population_scope": ["participants", "patients", "people with", "students", "teachers", "site", "setting", "corridor"],
        "intervention_or_option": ["intervention", "program", "policy", "option", "implementation"],
        "comparator": ["compared with", "compared to", "versus", "rather than", "instead of", "over ", "alternative", "substitut", "replace"],
        "outcome_or_endpoint": ["mortality", "injury", "crash", "risk", "endpoint", "biomarker", "infection", "exposure", "comfort", "safety", "outcome"],
        "evidence_design": ["randomized", "trial", "cohort", "observational", "before-after", "before after", "evaluation", "systematic review", "meta-analysis", "guidance", "memo"],
        "causal_identification": ["not randomized", "confounding", "regression to the mean", "cannot be attributed", "causal", "package", "alongside", "concurrent", "mechanism"],
        "implementation_condition": ["maintenance", "maintain", "operate", "implementation", "feasible", "capacity", "access"],
        "harm_or_failure_mode": ["harm", "hazard", "unsafe", "failure", "blocked", "conflict", "risk", "degradation", "unusable"],
        "cost_or_feasibility": ["cost", "budget", "staff", "capital", "cheap", "inexpensive", "quick", "faster", "limited resources", "construction"],
        "equity_or_distribution": ["equity", "distribution", "access", "neighborhood", "subgroup", "higher-risk", "high-risk"],
        "missing_evidence_gap": ["not randomized", "limitations", "cannot be assigned", "not assessed", "missing", "uncertain", "not establish"],
    },
    "claim_concept_markers": {
        "default_population": ["participants", "patients", "people with", "general population", "without"],
        "dose_or_threshold": ["per day", "per week", "dose", "threshold", "intensity", "%", "<", ">", "≥", "≤"],
        "hard_outcome_endpoint": ["mortality", "injury", "crash", "risk", "outcome", "endpoint", "incident"],
        "surrogate_or_biomarker_endpoint": ["biomarker", "surrogate", "proxy", "particulate", "particle"],
        "mechanism_or_causal_path": ["mechanism", "causal", "pathway", "mediated", "exposure", "transmission"],
        "substitution_or_comparator": ["replace", "replacing", "substitut", "compared with", "versus", "vs ", "instead of"],
        "alternative_or_comparator": ["compared with", "compared to", "versus", "vs ", "rather than", "instead of", "alternative", "supplemental", "over "],
        "subgroup_diabetes_or_metabolic_risk": ["subgroup", "high-risk", "higher-risk", "metabolic"],
        "technical_performance_or_capacity": ["capacity", "technical", "performance", "airflow", "ventilation", "filtration"],
        "implementation_constraint": ["feasible", "not feasible", "maintenance", "operate", "operated", "serviced", "upgrade", "standard", "cost", "noise", "capacity"],
        "safety_or_adverse_effect": ["unsafe", "adverse", "harm", "risk", "hazard", "not safe", "failure"],
        "setting_or_context": ["setting", "site", "building", "home", "workplace", "county", "region"],
        "study_design_rct": ["randomized", "randomised", " rct", "trial", "crossover", "intervention"],
        "study_design_cohort": ["cohort", "prospective", "follow-up", "observational", "participants"],
        "guideline_or_policy": ["guideline", "advisory", "recommendation", "policy", "should"],
        "source_quality_or_incentive": ["funding", "conflict of interest", "disclosure", "industry", "consultant", "grant", "abstract", "full text"],
    },
    "profile_detection_markers": [],
    "profile_detection_threshold": 2,
    "crux_templates": [
        {
            "markers": ["maintenance", "maintain", "capacity", "staff", "budget", "operate", "operation"],
            "current_read": "The recommendation holds only where the actor can keep the intervention usable after adoption.",
            "would_change_if": "The actor lacked the staff, equipment, funding, or operating capacity to keep the intervention usable.",
        },
        {
            "markers": ["attribution", "randomized", "confounding", "regression", "causal"],
            "current_read": "The observed result is decision-relevant, but it should be read with causal-attribution limits attached.",
            "would_change_if": "Better evidence separated the intervention effect from confounding or concurrent changes.",
        },
        {
            "markers": ["exposure", "volume", "participation", "usage"],
            "current_read": "Exposure changes matter because an outcome signal is stronger if it is not explained by suppressed use or participation.",
            "would_change_if": "The apparent outcome gain was explained by reduced exposure, suppressed use, or changed participation.",
        },
        {
            "markers": ["site", "constraint", "geometry", "access", "local", "setting"],
            "current_read": "Local setting and access constraints determine how far the default recommendation travels.",
            "would_change_if": "The target setting was shown to lack workable local conditions for the intervention.",
        },
    ],
    "crux_label_rules": [
        {
            "label": "Maintenance and operating capacity",
            "markers": ["maintenance", "maintain", "staff", "capacity", "operate", "operation"],
            "why_it_matters": "The preferred option can fail if it cannot be kept usable after adoption.",
            "current_read": "The option remains attractive only where it can be maintained and operated.",
            "would_change_if": "The actor lacked the staff, equipment, or budget to keep the option usable.",
        },
        {
            "label": "Budget and implementation feasibility",
            "markers": ["cost", "budget", "capital", "cheap", "inexpensive", "quick", "feasible"],
            "why_it_matters": "A lower-impact option can become preferable if the higher-impact option is not feasible on the decision timeline.",
            "current_read": "Feasibility constraints bound how much of the preferred option can be delivered.",
            "would_change_if": "Only the lower-resource option could be delivered at meaningful scale.",
        },
        {
            "label": "Causal attribution of the observed effect",
            "markers": ["not randomized", "regression", "confounding", "cannot be attributed", "package"],
            "why_it_matters": "The observed effect may reflect a package or context rather than the named option alone.",
            "current_read": "The evidence is decision-relevant but should be read with causal-attribution limits attached.",
            "would_change_if": "Better evidence showed the benefit came entirely from other concurrent changes.",
        },
        {
            "label": "Equity and high-need targeting",
            "markers": ["equity", "high-need", "higher-risk", "underserved", "distribution"],
            "why_it_matters": "A broad program can miss the people or places where the decision stakes are highest.",
            "current_read": "Value is strongest when the option reaches higher-need settings or groups.",
            "would_change_if": "The option could not be targeted to higher-need settings or groups.",
        },
    ],
    "fallback_crux_labels": [
        "Maintenance and operating capacity",
        "Budget and implementation feasibility",
        "Causal attribution of the observed effect",
    ],
    "crux_option_scope_markers": ["feasibility", "maintenance", "implementation", "capacity"],
    "coverage_preferred_markers": {
        "alternative_or_comparator": [["compared with", "compared to", "versus"], ["rather than", "instead of", "over "], ["alternative", "supplemental"]],
        "guideline_or_policy": [["guideline", "guidance"], ["recommendation", "advisory"], ["clinicians", "consumers", "should"]],
        "implementation_constraint": [["not feasible", "feasible"], ["maintenance", "serviced", "operate", "operated"], ["cost", "noise", "capacity"]],
        "safety_or_adverse_effect": [["unsafe", "not safe"], ["adverse", "harm", "risk"], ["failure", "hazard"]],
        "setting_or_context": [["setting", "site", "region"], ["building", "home", "workplace"]],
    },
    "coverage_visible_markers": {
        "default_population": ["generally healthy", "healthy adults", "general population", "free of", "without", "free-living"],
        "dose_or_threshold": ["per day", "per week", "up to", "moderate", "high intake", "low intake", "≥", "≤", "<", ">"],
        "hard_outcome_endpoint": ["mortality", "risk", "outcome", "endpoint", "incident"],
        "surrogate_or_biomarker_endpoint": ["biomarker", "surrogate", "proxy"],
        "mechanism_or_causal_path": ["mechanism", "causal", "pathway", "mediated", "exposure"],
        "substitution_or_comparator": ["replace", "replacing", "substitut", "compared with", "versus", "instead of"],
        "alternative_or_comparator": ["compared with", "compared to", "versus", " vs ", "rather than", "instead of", "alternative", "supplemental", "over "],
        "subgroup_diabetes_or_metabolic_risk": ["subgroup", "high-risk", "higher-risk"],
        "study_design_rct": ["randomized", "randomised", "rct", "trial", "crossover", "intervention"],
        "study_design_cohort": ["cohort", "prospective", "follow-up", "observational", "participants"],
        "guideline_or_policy": ["guideline", "advisory", "recommendation", "clinicians", "consumers", "should"],
        "technical_performance_or_capacity": ["capacity", "technical", "performance"],
        "implementation_constraint": ["feasible", "not feasible", "maintenance", "operate", "operated", "serviced", "upgrade", "standard", "cost", "noise", "capacity"],
        "safety_or_adverse_effect": ["unsafe", "adverse", "harm", "risk", "hazard", "not safe", "failure"],
        "setting_or_context": ["setting", "site", "region"],
    },
    "evidence_family_markers": {
        "guideline_or_recommendation": ["guideline", "advisory", "recommendation", "guidance", "policy", "should"],
        "evidence_synthesis": ["meta-analysis", "systematic review", "pooled relative risk", "pooled rr"],
        "rct_or_intervention": ["randomized", "randomised", " rct", "trial", "crossover", "intervention"],
        "cohort_or_observational": ["cohort", "prospective", "pooled analysis", "observational", "participants", "follow-up"],
        "substitution_or_comparator": ["replace", "substitut", "instead of", "compared with", "compared to", "versus", "vs ", "rather than", "alternative", "supplemental", "over "],
        "technical_or_performance": ["airflow", "ventilation", "filtration", "capacity"],
        "safety_or_risk": ["unsafe", "adverse", "harm", "hazard", "not safe"],
        "mechanism_or_biomarker": ["mechanism", "biomarker", "causal", "pathway", "transmission", "source control"],
    },
    "concept_family_markers": {
        "comparator_or_substitution": [
            ["replace", "replacing", "replacement", "substitut", "instead of", "compared with", "versus", "vs "],
            ["alternative", "counterfactual", "comparator"],
        ],
        "subgroup_or_scope": [
            ["subgroup", "population", "participants with", "patients with", "people with"],
        ],
        "guideline_or_recommendation": [
            ["guideline", "recommendation", "recommended", "advisory", "guidance"],
            ["clinicians", "consumers", "policy", "should", "limit"],
        ],
        "study_design": [
            ["randomized", "randomised", "rct", "trial", "crossover", "intervention"],
            ["cohort", "prospective", "observational", "meta-analysis", "systematic review", "pooled"],
        ],
        "endpoint_or_outcome": [
            ["mortality", "injury", "crash", "risk", "endpoint", "events", "outcome"],
        ],
        "dose_or_threshold": [
            ["per day", "per week", "dose", "threshold", "intake", "consumption"],
            ["high intake", "moderate intake", "low intake", "up to"],
        ],
        "method_limit": [
            ["limitation", "residual confounding", "self-report", "misclassification", "measurement error"],
            ["adjusted for", "sensitivity analysis", "not significant after adjusting"],
        ],
    },
    "concept_family_strong_markers": {
        "comparator_or_substitution": ["replacement", "substitut", "instead of"],
        "guideline_or_recommendation": ["guideline", "recommendation", "recommended"],
        "study_design": ["randomized", "rct", "cohort", "meta-analysis"],
    },
}




def _merged_profile_vocabulary(vocabulary: dict[str, Any] | None) -> dict[str, Any]:
    merged = json.loads(json.dumps(_BASE_PROFILE_VOCABULARY))
    if isinstance(vocabulary, dict):
        _deep_merge_vocab(merged, vocabulary)
    return merged


def _deep_merge_vocab(base: dict[str, Any], override: dict[str, Any]) -> None:
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge_vocab(base[key], value)
        elif isinstance(value, list) and isinstance(base.get(key), list):
            base[key] = [*base[key], *value]
        else:
            base[key] = value


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _empirical_policy_vocabulary() -> dict[str, Any]:
    return {
            "profile_detection_markers": ["policy", "program", "implementation", "evaluation", "guideline", "city", "county", "district", "corridor", "public"],
            "profile_detection_threshold": 2,
            "crux_templates": [
                {
                    "markers": ["exposure", "volume", "usage", "participation"],
                    "current_read": "Exposure changes matter because an outcome signal is stronger if it is not explained by suppressed use or participation.",
                    "would_change_if": "The apparent outcome gain was explained by reduced exposure, suppressed use, or changed participation.",
                },
                {
                    "markers": ["right-of-way", "geometry", "site", "access", "intersection"],
                    "current_read": "Local geometry, access needs, and operating constraints determine how far the default recommendation travels.",
                    "would_change_if": "The target sites were shown to lack workable geometry or manageable access conflicts.",
                },
            ],
            "crux_label_rules": [
                {
                    "label": "Site design and access constraints",
                    "markers": ["intersection", "turning", "signal", "access", "driveway", "parking", "right-of-way", "geometry"],
                    "why_it_matters": "Implementation benefits can be dominated by site-specific access, conflict, or geometry constraints.",
                    "current_read": "The option should be paired with site-specific design and access treatments.",
                    "would_change_if": "Site conflicts could not be mitigated in the target settings.",
                },
                {
                    "label": "Higher-impact option versus lighter-weight alternative",
                    "markers": ["paint", "painted", "protected", "separation", "quick-build", "physical"],
                    "why_it_matters": "The answer depends on when the lighter-weight alternative is enough and when the higher-impact option is needed.",
                    "current_read": "The lighter-weight option is secondary where the higher-impact option is feasible and decision-relevant.",
                    "would_change_if": "The lighter-weight option was shown to deliver the relevant outcome at sufficient scale.",
                },
                {
                    "label": "Exposure and participation changes",
                    "markers": ["volume", "exposure", "rider", "participation", "usage"],
                    "why_it_matters": "Outcome changes are harder to interpret if they are explained by changed exposure or participation.",
                    "current_read": "The outcome signal is stronger if it is not explained by reduced exposure or suppressed use.",
                    "would_change_if": "The apparent gain was explained by exposure or participation changes.",
                },
            ],
            "fallback_crux_labels": [
                "Higher-impact option versus lighter-weight alternative",
                "Maintenance and operating capacity",
                "Budget and implementation feasibility",
                "Causal attribution of the observed effect",
            ],
            "crux_option_scope_markers": ["paint", "protected", "feasibility", "maintenance", "intersection"],
    }


def _technical_safety_vocabulary() -> dict[str, Any]:
    return {
            "profile_detection_markers": ["safety", "hazard", "failure", "mitigation", "control", "monitoring", "ventilation", "filtration", "hvac", "hepa", "cadr", "merv"],
            "profile_detection_threshold": 2,
            "display_acronyms": {
                "ashrae": "ASHRAE",
                "cadr": "CADR",
                "hepa": "HEPA",
                "hvac": "HVAC",
                "merv": "MERV",
            },
            "display_regex_replacements": [
                {"pattern": r"\bpm\s*2\.5\b", "replacement": "PM 2.5"},
            ],
            "anchor_term_patterns": [
                r"\bPM\s?2\.5\b",
                r"\bMERV\s?\d+\b",
                r"\bCADR\b",
            ],
            "rewrite_rank_markers": ["cadr", "room size", "ozone", "unsafe", "not safe", "hazard", "failure", "residual risk", "monitoring"],
            "secondary_alternative_markers": ["germicidal ultraviolet", " guv "],
            "reader_quality_bonus_markers": ["hepa", "hvac", "cadr", "merv", "ventilation", "filtration", "pm2.5", "pm 2.5", "unsafe", "ozone"],
            "expected_slot_question_markers": {
                "technical_or_capacity": [" capacity", " technical", " performance", " cadr", " merv", " hvac", " hepa", " filtration", " ventilation"],
                "setting_or_context": [" school", " classroom", " district", " building", " setting", " site"],
                "safety_or_risk": [" ozone", " unsafe", " not safe"],
            },
            "slot_value_patterns": {
                "technical_or_capacity": [
                    r"[A-Za-z0-9 .,%/\-]{0,80}\b(?:CADR|MERV|HEPA|HVAC|airflow|filtration|ventilation|room size|capacity|PM\s?2\.5)\b[A-Za-z0-9 .,%/\-]{0,100}",
                    r"[A-Za-z0-9 .,%/\-]{0,80}\b(?:clean air delivery rate|particulate matter|outdoor air|filter)\b[A-Za-z0-9 .,%/\-]{0,100}",
                ],
                "implementation_constraint": [
                    r"[A-Za-z0-9 .,%/\-]{0,80}\b(?:feasible|not feasible|maintenance|operate|operated|serviced|upgrade|standard|cost|noise|capacity|room size)\b[A-Za-z0-9 .,%/\-]{0,100}",
                ],
                "safety_or_risk": [
                    r"[A-Za-z0-9 .,%/\-]{0,80}\b(?:unsafe|not safe|ozone|adverse|harm|risk|hazard|failure)\b[A-Za-z0-9 .,%/\-]{0,100}",
                ],
                "setting_or_context": [
                    r"[A-Za-z0-9 .,%/\-]{0,80}\b(?:classroom|school|district|building|home|workplace|setting|county|region|site)\b[A-Za-z0-9 .,%/\-]{0,100}",
                ],
            },
            "option_inference_markers": {
                "portable HEPA filtration": ["hepa", "portable air cleaner", "portable air cleaners", "portable filtration"],
                "HVAC or ventilation upgrade": ["hvac", "ventilation", "outdoor air"],
            },
            "option_aliases": {
                "hepa": ["portable", "filtration", "filter"],
                "hvac": ["ventilation", "outdoor", "upgrade"],
            },
            "decision_slot_markers": {
                "technical_or_capacity": ["cadr", "merv", "hvac", "hepa", "airflow", "ventilation", "filtration", "room size", "pm2.5", "pm 2.5"],
                "endpoint_type": ["pm2.5", "pm 2.5", "particulate", "infection", "transmission"],
                "mechanism": ["filtration", "ventilation", "source control", "transmission"],
                "setting_or_context": ["classroom", "school", "district", "building"],
            },
            "evidence_slot_markers": {
                "intervention_or_option": ["hepa", "hvac", "filtration"],
                "outcome_or_endpoint": ["pm2.5", "pm 2.5", "particulate", "infection", "transmission"],
                "implementation_condition": ["room size", "airflow", "ventilation"],
                "harm_or_failure_mode": ["ozone"],
                "population_scope": ["classroom", "school", "district", "building"],
            },
            "claim_concept_markers": {
                "surrogate_or_biomarker_endpoint": ["pm2.5", "pm 2.5", "particulate", "particle"],
                "mechanism_or_causal_path": ["filtration", "ventilation", "source control", "transmission"],
                "technical_performance_or_capacity": ["cadr", "merv", "hvac", "hepa", "airflow", "ventilation", "filtration", "room size", "pm2.5", "pm 2.5"],
                "setting_or_context": ["classroom", "school", "district"],
            },
            "coverage_preferred_markers": {
                "technical_performance_or_capacity": [["cadr", "merv", "hvac", "hepa"], ["ventilation", "filtration", "airflow"], ["room size", "capacity"]],
                "implementation_constraint": [["not feasible", "feasible"], ["maintenance", "serviced", "operate", "operated"], ["cost", "noise", "capacity"]],
                "safety_or_adverse_effect": [["unsafe", "not safe", "ozone"], ["adverse", "harm", "risk"], ["failure", "hazard"]],
                "setting_or_context": [["classroom", "school", "district"], ["building", "home", "workplace"], ["setting", "site", "region"]],
            },
            "coverage_visible_markers": {
                "surrogate_or_biomarker_endpoint": ["pm2.5", "pm 2.5", "particulate", "particle"],
                "mechanism_or_causal_path": ["transmission", "filtration", "ventilation", "source control"],
                "technical_performance_or_capacity": ["cadr", "merv", "hvac", "hepa", "airflow", "ventilation", "filtration", "room size", "pm2.5", "pm 2.5"],
                "setting_or_context": ["classroom", "school", "district", "building", "home", "workplace"],
                "safety_or_adverse_effect": ["ozone"],
            },
            "evidence_family_markers": {
                "guideline_or_recommendation": ["cdc", "epa"],
                "technical_or_performance": ["cadr", "merv", "hvac", "hepa", "airflow", "ventilation", "filtration", "room size", "capacity", "pm2.5", "pm 2.5"],
                "safety_or_risk": ["ozone"],
                "mechanism_or_biomarker": ["ventilation", "filtration", "transmission", "source control"],
            },
            "answer_frame_rules": [
                {
                    "required_question_terms": ["prioritize", "hepa"],
                    "direct_answer": "Answer whether portable filtration should be prioritized for near-term targeted risk reduction, then state whether it is supplemental or a substitute for source-control and ventilation work.",
                }
            ],
            "practical_action_rules": [
                {
                    "markers": ["cadr", "room size"],
                    "action": "Verify that each unit's technical capacity is appropriate for the room or setting size.",
                },
                {
                    "markers": ["limited airflow", "targeted filtration", "sick individuals"],
                    "action": "Deploy units first in spaces with limited airflow, targeted filtration needs, or higher-risk occupancy.",
                },
                {
                    "markers": ["outdoor ventilation", "source control", "adequate ventilation"],
                    "action": "Continue source control and ventilation rather than treating portable filtration as a replacement.",
                },
                {
                    "markers": ["ozone", "unsafe"],
                    "action": "Exclude unsafe or ozone-generating devices from occupied spaces.",
                },
            ],
            "crux_templates": [
                {
                    "markers": ["air cleaning alone may not be sufficient", "source control"],
                    "current_read": "Portable filtration is a supplement, not a standalone replacement for source control and ventilation.",
                    "would_change_if": "Portable filtration alone was shown to achieve the relevant risk reduction without source control or ventilation.",
                },
                {
                    "markers": ["health benefits", "translate", "pm levels", "pm2.5", "pm 2.5"],
                    "current_read": "Measured exposure reductions are relevant, but health-outcome translation remains uncertain.",
                    "would_change_if": "Direct health outcomes improved at the observed exposure-reduction levels.",
                },
                {
                    "markers": ["cadr", "room size", "technical capacity"],
                    "current_read": "Room-size and capacity fit gate whether the intervention can deliver the intended performance.",
                    "would_change_if": "The intervention worked reliably without matching capacity to room or setting size.",
                },
            ],
    }


def _biomedical_nutrition_vocabulary() -> dict[str, Any]:
    return {
            "profile_detection_markers": ["egg", "eggs", "diet", "dietary", "nutrition", "cholesterol", "ldl", "apob", "saturated fat", "cardiovascular"],
            "profile_detection_threshold": 2,
            "domain_leakage_terms": [" egg", " eggs", " dietary", " cholesterol", " apob", " saturated fat", " replacement foods"],
            "reader_quality_bonus_markers": ["cardiovascular", "ldl", "apob", "diabetes", "replace", "substitut", "per day", "per week"],
            "quantity_decision_markers": ["egg", "eggs", "ldl", "hdl", "apob", "cholesterol"],
            "quantity_role_markers": {
                "scope_or_subgroup_boundary": ["diabetes", "high ldl", "high apob", "older", "type 2"],
                "biomarker_calibration": ["ldl", "hdl", "apob", "cholesterol", "lipid"],
                "dose_boundary": ["egg", "eggs"],
            },
            "concern_negated_markers": [" lowers ldl ", " lowered ldl "],
            "concern_markers": [
                " cvd mortality ",
                " cardiovascular harm ",
                " raises ldl ",
                " raised ldl ",
                " risk of cvd ",
                " risk of cardiovascular diseases ",
                " not for patients at risk ",
            ],
            "support_markers": [" lowers ldl ", " lowered ldl ", " lower cvd "],
            "scope_or_subgroup_markers": [
                " diabetes",
                " t2d",
                " prediabetes",
                " familial hypercholesterolemia",
                " high ldl",
                " prior cardiovascular event",
                " up to one egg",
                " over 4 months",
            ],
            "hard_outcome_signal_markers": [
                " cardiovascular event ",
                " cvd ",
                " stroke ",
            ],
            "surrogate_signal_markers": [
                " ldl",
                " hdl",
                " apob",
            ],
            "support_signal_profile_markers": {
                "surrogate_benefit": ["lowered ldl", "lowers ldl", "improved lipid"],
            },
            "scope_dimension_markers": {
                "population_or_actor": [" diabetes", " t2d", " familial", " prior cardiovascular"],
                "dose_intensity_or_scale": [" intake"],
                "geography_jurisdiction_or_setting": [" asian", " china", " us ", " european"],
                "implementation_context": [" clinicians", " consumers", " dietary pattern"],
                "measurement_endpoint": [" ldl", " hdl", " apob"],
            },
            "method_or_source_limit_markers": [
                " challenging for clinicians",
                " dietary patterns",
            ],
            "memo_slot_direction_markers": {
                "high_risk_subgroup": [" diabetes", " type 2", " t2d", " prediabetes", " familial", " hyper", " high ldl", " high apob", " kidney", " vascular disease"],
                "comparator_substitution": [" replace", " replacing", " substitut", " instead of", " compared with", " versus", " egg white", " plant protein"],
                "mechanism_surrogate": [" ldl", " apob", " hdl", " cholesterol", " saturated fat", " biomarker", " tmao", " triglyceride"],
            },
            "memo_slot_reject_markers": {
                "high_risk_subgroup": [["free of", "baseline"]],
            },
            "memo_slot_rank_markers": {
                "hard_outcome_support": ["mortality", "cardiovascular", "cvd", "stroke", "myocardial infarction"],
                "hard_outcome_counter": ["mortality", "cardiovascular", "cvd", "stroke", "myocardial infarction"],
                "mechanism_surrogate": ["ldl", "apob", "hdl", "cholesterol", "saturated fat", "biomarker"],
                "comparator_substitution": ["replace", "replacing", "substitut", "instead of", "compared with"],
                "high_risk_subgroup": ["diabetes", "familial", "hyper", "high ldl", "kidney", "vascular"],
            },
            "slot_value_patterns": {
                "dose_or_intensity_threshold": [
                    r"(?:up to|less than|more than|at least|at most|around|approximately|about)?\s*[<≥≤>]?\s*(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:eggs?|egg)?\s*(?:per|/)\s*(?:day|week|month)",
                    r"\b(?:\d+(?:\.\d+)?|one|two|three|four|five|six|seven|eight|nine|ten)\s*(?:eggs?|egg)/(?:day|week|month)\b",
                    r"\b(?:high|moderate|low)[-\s]?(?:egg|intake|consumption|use)[A-Za-z0-9/ <≥≤.,-]{0,60}",
                ],
                "high_risk_subgroup": [
                    r"(?:people|patients|adults|individuals|participants) with type 2 diabetes",
                    r"(?:people|patients|adults|individuals|participants) with impaired (?:kidney|renal) function(?:, including the elderly)?",
                    r"\b(?:type 2 diabetes|diabetes|t2d|impaired kidney function|impaired renal function|elderly|familial hypercholesterolemia|high LDL|high ApoB|hyper-responders?)\b(?:, including the elderly)?",
                ],
                "mechanism": [
                    r"\b(?:LDL|HDL|ApoB|cholesterol|homeostasis|metabolites?|microbiome|particle)[A-Za-z0-9 ,/\-]{0,90}",
                ],
                "substitution_or_comparator": [
                    r"\b(?:egg whites?|plant protein|animal protein|red meat|processed meat|low-egg diet|high-egg diet)[A-Za-z0-9 ,/\-]{0,90}",
                ],
                "endpoint_type": [
                    r"\b(?:mortality|all-cause mortality|CVD|cardiovascular disease|cardiovascular risk|stroke|myocardial infarction|LDL|HDL|ApoB|biomarker|endpoint)[A-Za-z0-9 ,/\-]{0,70}",
                ],
                "default_population": [
                    r"\bfree of (?:cardiovascular disease|type 2 diabetes|cancer|chronic disease)[A-Za-z0-9 ,/\-]{0,90}",
                ],
            },
            "option_inference_markers": {
                "whole-food exposure": ["egg", "eggs", "dietary cholesterol"],
                "replacement or substitution option": ["replacement", "substitut", "plant protein", "egg white"],
            },
            "option_aliases": {
                "egg": ["eggs", "whole egg", "whole eggs"],
                "eggs": ["egg", "whole egg", "whole eggs"],
                "plant": ["plant protein", "plant-based"],
            },
            "decision_slot_markers": {
                "default_population": ["healthy adults", "generally healthy", "free-living", "free of cardiovascular", "free of type 2 diabetes", "free of cancer"],
                "dose_or_intensity_threshold": ["egg/day", "eggs/wk", "high intake", "moderate", "up to one", "up to 1"],
                "high_risk_subgroup": ["diabetes", "t2d", "impaired kidney", "renal", "elderly", "familial", "high ldl", "high apob", "hyper-responder"],
                "mechanism": ["ldl", "apob", "cholesterol", "homeostasis", "metabolite", "microbiome", "lipid"],
                "substitution_or_comparator": ["low-egg", "high-egg", "egg white", "plant protein"],
                "endpoint_type": ["cvd", "cardiovascular", "stroke", "myocardial", "ldl", "hdl", "apob"],
                "practical_recommendation": ["dietary pattern", "mediterranean", "dash", "limit", "focus"],
            },
            "evidence_slot_markers": {
                "intervention_or_option": ["egg", "eggs", "dietary cholesterol"],
                "outcome_or_endpoint": ["cvd", "cardiovascular", "stroke", "myocardial", "ldl", "hdl", "apob", "cholesterol", "lipid"],
                "population_scope": ["healthy adults", "generally healthy", "free-living", "people with diabetes"],
                "comparator": ["egg white", "plant protein", "replacement", "substitution"],
            },
            **_biomedical_nutrition_concept_vocabulary(),
    }


def _biomedical_nutrition_concept_vocabulary() -> dict[str, Any]:
    return {
        "claim_concept_markers": {
            "default_population": ["generally healthy", "healthy adults", "free of cardiovascular", "free-living"],
            "dose_or_threshold": ["egg/day", "eggs/wk", "up to one", "up to 1", "moderate", "high intake"],
            "hard_outcome_endpoint": ["cvd", "cardiovascular disease", "stroke", "myocardial infarction", "coronary heart disease"],
            "surrogate_or_biomarker_endpoint": ["ldl", "hdl", "apob", "cholesterol", "lipid", "tmao", "trimethylamine"],
            "mechanism_or_causal_path": ["homeostasis", "metabolite", "microbiome"],
            "mechanism_ldl_apob": ["ldl", "apob", "atherosclerosis", "cholesterol homeostasis", "tmao", "trimethylamine", "metabolite", "microbiome"],
            "dietary_context_or_saturated_fat": ["saturated fat", "dietary pattern", "red meat", "processed meat", "bacon", "sausage", "co-consum", "dietary cholesterol"],
            "substitution_or_comparator": ["egg white", "plant protein", "low-egg", "high-egg"],
            "subgroup_diabetes_or_metabolic_risk": ["type 2 diabetes", "diabetes", "t2d", "prediabetes", "impaired kidney", "renal", "vascular disease"],
            "subgroup_fh_hyper_responder": ["familial hypercholesterolemia", "hyper-responder", "hyper responder", "high ldl", "high apob", "elevated ldl", "elevated apob"],
        },
        "concept_visible_required_markers": {
            "mechanism_ldl_apob": [["ldl", "ldl-c"], ["apo b", "apob"], ["cholesterol"], ["atherosclerosis"], ["tmao"], ["trimethylamine"], ["lipid"]],
            "dietary_context_or_saturated_fat": [["dietary"], ["diet "], ["saturated fat"], ["red meat"], ["processed meat"], ["bacon"], ["sausage"], ["cholesterol"]],
        },
        "coverage_preferred_markers": {
            "mechanism_ldl_apob": [["apob", "apo b"], ["ldl", "ldl-c"], ["cholesterol"]],
            "surrogate_or_biomarker_endpoint": [["apob", "apo b"], ["ldl", "hdl", "lipid", "particle"], ["cholesterol", "biomarker"]],
            "dietary_context_or_saturated_fat": [["saturated fat"], ["dietary pattern", "diet quality"], ["dietary cholesterol", "red meat", "processed meat", "overnutrition"]],
            "substitution_or_comparator": [["plant protein", "egg white"], ["replace", "replacing", "substitut"], ["compared with", "versus", "instead of"]],
            "guideline_or_policy": [["guideline", "dietary guidance"], ["recommendation", "advisory"], ["clinicians", "consumers", "should"]],
        },
        "coverage_visible_markers": {
            "hard_outcome_endpoint": ["cvd", "cardiovascular", "stroke", "myocardial infarction", "coronary"],
            "surrogate_or_biomarker_endpoint": ["ldl", "hdl", "apob", "cholesterol", "lipid"],
            "mechanism_ldl_apob": ["ldl", "apob", "cholesterol", "atherosclerosis", "tmao", "trimethylamine", "metabolite"],
            "dietary_context_or_saturated_fat": ["saturated fat", "dietary pattern", "dietary cholesterol", "red meat", "processed meat", "overnutrition"],
            "substitution_or_comparator": ["egg white", "plant protein"],
            "subgroup_diabetes_or_metabolic_risk": ["type 2 diabetes", "diabetes", "t2d", "prediabetes", "metabolic", "renal", "kidney"],
            "subgroup_fh_hyper_responder": ["familial", "hyper-responder", "hyper responder", "high ldl", "high apob", "elevated ldl", "elevated apob"],
            "guideline_or_policy": ["dietary guidance"],
        },
        "evidence_family_markers": {
            "guideline_or_recommendation": ["dietary guidance"],
            "mechanism_or_biomarker": ["metabolite", "homeostasis", "ldl", "apob", "cholesterol", "microbiome"],
        },
        "concept_family_markers": {
            "comparator_or_substitution": [["plant protein", "plant-based", "plant‐based", "plant based", "egg white", "protein source"]],
            "mechanism_or_biomarker": [
                ["biomarker", "mechanism", "pathway", "mediated", "homeostasis"],
                ["ldl", "hdl", "apob", "apo b", "cholesterol", "lipid", "particle", "tmao", "metabolite", "microbiome"],
            ],
            "dietary_context": [
                ["saturated fat", "dietary pattern", "diet quality", "overall diet", "overnutrition"],
                ["red meat", "processed meat", "animal protein", "dietary cholesterol"],
            ],
            "subgroup_or_scope": [["diabetes", "t2d", "prediabetes", "kidney", "renal", "elderly", "familial", "hyper-responder", "hyper responder"]],
            "endpoint_or_outcome": [["cardiovascular disease", "cvd", "stroke", "myocardial infarction", "coronary", "incident"]],
        },
        "concept_family_strong_markers": {
            "comparator_or_substitution": ["plant protein", "plant-based", "plant‐based", "plant based", "replacement", "substitut", "instead of"],
            "mechanism_or_biomarker": ["apob", "apo b", "ldl", "biomarker"],
            "dietary_context": ["saturated fat", "dietary pattern", "diet quality"],
        },
    }
