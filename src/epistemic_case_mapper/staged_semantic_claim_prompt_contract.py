from __future__ import annotations

from typing import Any


def claim_prompt_schema(role_options: str) -> dict[str, Any]:
    return {
        "claims": [
            {
                "source_quote": "exact substring copied from one catalog span",
                "claim": "one concise claim supported by the excerpt",
                "span_id": "the model's best span_id from the catalog; deterministic code verifies this from source_quote",
                "entailed_by_excerpt": "yes|no|uncertain",
                "role": role_options,
                "question_relevance": "direct|indirect|scope_limit|background|irrelevant",
                "relevance_rationale": "one sentence explaining how this claim bears on the case question",
                "scope_flags": ["target_population_mismatch|outcome_mismatch|intervention_or_exposure_mismatch|mechanism_only|administrative_context|none"],
            }
        ]
    }


def claim_prompt_json_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "claims": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "claim": {"type": "string"},
                        "source_quote": {"type": "string"},
                        "span_id": {"type": "string"},
                        "entailed_by_excerpt": {"type": "string", "enum": ["yes", "no", "uncertain"]},
                        "role": {"type": "string"},
                        "question_relevance": {"type": "string", "enum": ["direct", "indirect", "scope_limit", "background", "irrelevant"]},
                        "relevance_rationale": {"type": "string"},
                        "scope_flags": {"type": "array", "items": {"type": "string"}},
                    },
                    "required": ["source_quote", "claim", "span_id", "entailed_by_excerpt", "role"],
                },
            }
        },
        "required": ["claims"],
    }


def claim_prompt_examples() -> list[dict[str, Any]]:
    return [
        {
            "input_excerpt": "The program reduced processing time for eligible target cases.",
            "output": {
                "claims": [
                    {
                        "source_quote": "reduced processing time for eligible target cases",
                        "claim": "The program reduced processing time for the target cases.",
                        "span_id": "doc_s0001",
                        "entailed_by_excerpt": "yes",
                        "role": "conclusion_support",
                        "question_relevance": "direct",
                        "relevance_rationale": "The span reports an outcome that directly changes the decision read.",
                        "scope_flags": ["none"],
                    }
                ]
            },
        },
        {
            "input_excerpt": "Source: annual report appendix.",
            "output": {"claims": []},
        },
    ]
