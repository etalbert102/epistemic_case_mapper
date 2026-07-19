from __future__ import annotations

import json

from epistemic_case_mapper.pipeline.briefing.map_briefing_section_attempts import run_section_model_attempts
from epistemic_case_mapper.pipeline.briefing.map_briefing_section_parse import parse_section_payload
from epistemic_case_mapper.model_backends import ModelBackendResult


def test_section_parser_accepts_raw_markdown_section() -> None:
    payload = parse_section_payload(
        "## Why This Read\n\nThe section was returned directly as Markdown.",
        expected_title="Why This Read",
    )

    assert payload == {
        "section_markdown": "## Why This Read\n\nThe section was returned directly as Markdown."
    }


def test_section_parser_accepts_json_section_alias() -> None:
    raw = '''```json
{"action": "rewrite", "section": "## Practical Scope and Exceptions

A scoped section.
- A bullet with a literal newline."}
```'''

    payload = parse_section_payload(raw, expected_title="Practical Scope and Exceptions")

    assert payload == {
        "section_markdown": "## Practical Scope and Exceptions\n\nA scoped section.\n- A bullet with a literal newline."
    }


def test_section_parser_skips_large_prompt_backend_text_quickly() -> None:
    raw = (
        "You are an analyst producing decision-ready analysis for one section.\n"
        "Return only valid JSON with this schema: {\"section_markdown\": \"## Same Heading\\n\\nRewritten section\"}.\n\n"
        "Section contract:\n"
        + ("x" * 120_000)
        + "\n\nSection to rewrite:\n## Why This Read\n\nDraft text."
    )

    assert parse_section_payload(raw, expected_title="Why This Read") is None


def test_section_model_attempts_retry_parse_failure() -> None:
    calls: list[str] = []

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        calls.append(prompt)
        if len(calls) == 1:
            return ModelBackendResult(text="not a section", backend=backend)
        return ModelBackendResult(text="## Why This Read\n\nValid section.", backend=backend)

    result = run_section_model_attempts(
        prompt="Base prompt",
        expected_title="Why This Read",
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        validate=lambda text: (text, []),
        run_backend=fake_backend,
    )

    assert result["accepted"] is True
    assert result["attempt_count"] == 2
    assert [attempt["status"] for attempt in result["attempts"]] == ["parse_failed", "accepted"]
    assert result["attempts"][0]["raw"] == "not a section"
    assert result["attempts"][1]["raw"].startswith("## Why This Read")
    assert "Previous attempt 1 was rejected" in calls[1]


def test_section_model_attempts_retry_validation_failure() -> None:
    calls: list[str] = []

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0, response_schema=None):
        calls.append(prompt)
        text = "## Decision Cruxes\n\nBad section." if len(calls) == 1 else "## Decision Cruxes\n\nGood section."
        return ModelBackendResult(text=text, backend=backend)

    def validate(text: str):
        return text, ["missing crux"] if "Bad" in text else []

    result = run_section_model_attempts(
        prompt="Base prompt",
        expected_title="Decision Cruxes",
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        validate=validate,
        run_backend=fake_backend,
    )

    assert result["accepted"] is True
    assert result["attempt_count"] == 2
    assert result["attempts"][0]["issues"] == ["missing crux"]
    assert result["attempts"][0]["raw"].startswith("## Decision Cruxes")
    assert "Rejected section to correct:" in calls[1]
    assert "## Decision Cruxes\n\nBad section." in calls[1]
    assert "Correct the rejected section instead of starting over" in calls[1]


def test_section_model_attempts_accepts_when_adjudicator_disagrees_with_validator() -> None:
    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        return ModelBackendResult(text="## Decision Brief\n\nReasonable section.", backend=backend)

    def validate(text: str):
        return text, ["final brief does not preserve the body default answer"]

    def adjudicate(text: str, issues: list[str]):
        return {
            "schema_id": "section_validation_adjudication_v1",
            "status": "no_confirmed_blocking_issues",
            "confirmed_issues": [],
            "unconfirmed_issues": issues,
            "repair_instructions": [],
            "issue_assessments": [
                {
                    "issue_index": 0,
                    "issue": issues[0],
                    "blocking": False,
                    "reason": "The section preserves the controlling answer frame.",
                }
            ],
        }

    result = run_section_model_attempts(
        prompt="Base prompt",
        expected_title="Decision Brief",
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        validate=validate,
        adjudicate=adjudicate,
        run_backend=fake_backend,
    )

    assert result["accepted"] is True
    assert result["status"] == "accepted_after_adjudication"
    assert result["attempt_count"] == 1
    assert result["attempts"][0]["status"] == "accepted_after_adjudication"
    assert result["attempts"][0]["issues"] == []
    assert result["attempts"][0]["deterministic_issues"] == ["final brief does not preserve the body default answer"]
    assert result["attempts"][0]["validator_warnings"] == ["final brief does not preserve the body default answer"]


def test_section_model_attempts_retries_when_adjudicator_confirms_validator_issue() -> None:
    calls: list[str] = []

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        calls.append(prompt)
        text = "## Practical Read\n\nBad section." if len(calls) == 1 else "## Practical Read\n\nGood section."
        return ModelBackendResult(text=text, backend=backend)

    def validate(text: str):
        return text, ["section dropped required evidence"] if "Bad" in text else []

    def adjudicate(text: str, issues: list[str]):
        return {
            "schema_id": "section_validation_adjudication_v1",
            "status": "confirmed_blocking_issues",
            "confirmed_issues": issues,
            "unconfirmed_issues": [],
            "repair_instructions": ["Add the required evidence without inventing facts."],
            "issue_assessments": [
                {
                    "issue_index": 0,
                    "issue": issues[0],
                    "blocking": True,
                    "reason": "The required evidence is absent.",
                    "repair_instruction": "Add the required evidence without inventing facts.",
                }
            ],
        }

    result = run_section_model_attempts(
        prompt="Base prompt",
        expected_title="Practical Read",
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        validate=validate,
        adjudicate=adjudicate,
        run_backend=fake_backend,
    )

    assert result["accepted"] is True
    assert result["attempt_count"] == 2
    assert result["attempts"][0]["status"] == "rejected"
    assert result["attempts"][0]["issues"] == ["section dropped required evidence"]
    assert result["attempts"][0]["adjudication"]["repair_instructions"] == ["Add the required evidence without inventing facts."]
    assert "Previous attempt 1 was rejected" in calls[1]
