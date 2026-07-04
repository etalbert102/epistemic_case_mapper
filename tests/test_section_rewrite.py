from __future__ import annotations

import json

from epistemic_case_mapper.map_briefing import (
    briefing_scaffold,
    build_compact_decision_model,
    build_source_display_lookup,
    generated_map_erosion_audit,
    render_decision_model_brief,
)
from epistemic_case_mapper.map_briefing_reader_contracts import compose_final_reader_memo_package
from epistemic_case_mapper.map_briefing_memo_slots import _rewrite_mentions_anchor_row
from epistemic_case_mapper.map_briefing_section_attempts import run_section_model_attempts
from epistemic_case_mapper.map_briefing_section_parse import parse_section_payload
from epistemic_case_mapper.map_briefing_section_rewrite import _default_answer_from_body, rewrite_reader_memo_by_section
from epistemic_case_mapper.model_backends import ModelBackendResult
from tests.test_decision_model_vertical_slice import _arbitrary_candidate_map, _quality_report


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
    assert "Previous attempt 1 was rejected" in calls[1]


def test_section_model_attempts_retry_validation_failure() -> None:
    calls = 0

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        nonlocal calls
        calls += 1
        text = "## Decision Cruxes\n\nBad section." if calls == 1 else "## Decision Cruxes\n\nGood section."
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


def test_required_evidence_can_match_strong_paraphrase_without_exact_source_title() -> None:
    row = {
        "claim": "High egg consumption was associated with a higher risk of cardiovascular disease in people with type 2 diabetes.",
        "source": "A Very Long Source Title That Would Be Awkward In Scope Prose",
        "anchor_terms": ["high", "consumption", "associated", "higher", "risk", "diabetes"],
    }
    text = "High egg consumption was associated with a higher risk of cardiovascular disease in people with type 2 diabetes."

    assert _rewrite_mentions_anchor_row(text, row)


def test_section_rewrite_accepts_valid_local_smoothing(monkeypatch) -> None:
    memo, appendix, scaffold, candidate_map = _memo_package()

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        section = prompt.split("Section to rewrite:\n", 1)[1].strip()
        return ModelBackendResult(
            text=json.dumps({"section_markdown": section + "\n\nThis transition keeps the same evidence visible."}),
            backend=backend,
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_section_rewrite.run_model_backend", fake_backend)

    result = rewrite_reader_memo_by_section(
        memo,
        appendix,
        scaffold,
        candidate_map,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["report"]["status"] == "accepted_partial"
    assert result["report"]["accepted_section_count"] > 0
    assert "This transition keeps the same evidence visible." in result["memo"]


def test_section_rewrite_falls_back_for_invalid_section(monkeypatch) -> None:
    memo, appendix, scaffold, candidate_map = _memo_package()

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        title = "Decision Cruxes" if "## Decision Cruxes" in prompt else "Why This Read"
        return ModelBackendResult(
            text=json.dumps(
                {
                    "section_markdown": (
                        f"## {title}\n\n"
                        "| Crux | Current Read | Would Change If |\n"
                        "|---|---|---|\n"
                        "| Decision-changing condition | The current packet treats this condition as relevant to the recommendation. | "
                        "New evidence showed the condition did not materially affect the decision. |"
                    )
                }
            ),
            backend=backend,
        )

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_section_rewrite.run_model_backend", fake_backend)

    result = rewrite_reader_memo_by_section(
        memo,
        appendix,
        scaffold,
        candidate_map,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["report"]["status"] in {"accepted_partial", "no_sections_accepted"}
    assert any(
        section["status"] == "rejected_fallback"
        for section in result["report"]["sections"]
    )
    assert any(
        "generic placeholder" in " ".join(section.get("issues", []))
        for section in result["report"]["sections"]
    )


def test_section_rewrite_keeps_sources_deterministic(monkeypatch) -> None:
    memo, appendix, scaffold, candidate_map = _memo_package()
    memo = memo.rstrip() + "\n\n## Sources\n\n- Source A\n- Source B\n"
    seen_prompts: list[str] = []

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        seen_prompts.append(prompt)
        section = prompt.split("Section to rewrite:\n", 1)[1].strip()
        return ModelBackendResult(text=json.dumps({"section_markdown": section}), backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_section_rewrite.run_model_backend", fake_backend)

    result = rewrite_reader_memo_by_section(
        memo,
        appendix,
        scaffold,
        candidate_map,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert "## Sources\n\n- Source A\n- Source B" in result["memo"]
    assert all("## Sources" not in prompt for prompt in seen_prompts)


def test_section_rewrite_assigns_required_evidence_to_owner_sections(monkeypatch) -> None:
    memo, appendix, scaffold, candidate_map = _memo_package()

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        section = prompt.split("Section to rewrite:\n", 1)[1].strip()
        return ModelBackendResult(text=json.dumps({"section_markdown": section}), backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_section_rewrite.run_model_backend", fake_backend)

    result = rewrite_reader_memo_by_section(
        memo,
        appendix,
        scaffold,
        candidate_map,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    ownership = result["report"]["evidence_ownership"]
    sections = result["report"]["sections"]
    assert ownership["owned_row_count"] > 0
    assert ownership["owner_counts"]
    assert any(section.get("evidence_reference_count", 0) > 0 for section in sections)


def test_section_rewrite_writes_section_synthesis_packets_with_argument_model(monkeypatch, tmp_path) -> None:
    memo, appendix, scaffold, candidate_map = _memo_package()

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        section = prompt.split("Section to rewrite:\n", 1)[1].strip()
        return ModelBackendResult(text=json.dumps({"section_markdown": section}), backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_section_rewrite.run_model_backend", fake_backend)

    result = rewrite_reader_memo_by_section(
        memo,
        appendix,
        scaffold,
        candidate_map,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
        artifacts=tmp_path,
    )

    packet_path = tmp_path / "section_synthesis_packets.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert result["section_packets_path"] == packet_path
    assert packet["schema_id"] == "section_synthesis_packets_v1"
    assert packet["packet_count"] == result["report"]["section_packet_count"]
    assert any(item["packet"].get("argument_model") for item in packet["packets"])


def test_section_rewrite_prompt_backend_still_writes_section_packets(tmp_path) -> None:
    memo, appendix, scaffold, candidate_map = _memo_package()

    result = rewrite_reader_memo_by_section(
        memo,
        appendix,
        scaffold,
        candidate_map,
        backend="prompt",
        backend_timeout=30,
        backend_retries=0,
        artifacts=tmp_path,
    )

    packet_path = tmp_path / "section_synthesis_packets.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert result["section_packets_path"] == packet_path
    assert result["report"]["status"] == "skipped_prompt_backend"
    assert result["report"]["section_packet_count"] == packet["packet_count"]
    assert any(item["title"] == "Decision Brief" for item in packet["packets"])
    assert any(item["packet"].get("argument_model") for item in packet["packets"])


def test_section_rewrite_repairs_dangling_practical_read(monkeypatch) -> None:
    memo, appendix, scaffold, candidate_map = _memo_package()

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        if "## Practical Read" in prompt:
            return ModelBackendResult(
                text=json.dumps({"section_markdown": "## Practical Read\n\nHowever, this recommendation has exceptions."}),
                backend=backend,
            )
        section = prompt.split("Section to rewrite:\n", 1)[1].strip()
        return ModelBackendResult(text=json.dumps({"section_markdown": section}), backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_section_rewrite.run_model_backend", fake_backend)

    result = rewrite_reader_memo_by_section(
        memo,
        appendix,
        scaffold,
        candidate_map,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    practical = result["memo"].split("## Practical Read", 1)[1].split("## Why This Read", 1)[0]
    assert not practical.strip().lower().startswith("however")
    assert "- " in practical


def test_final_brief_fallback_prefers_practical_default_paragraph_over_exception_bullets() -> None:
    body = """## Practical Read

For the default case, the current read is acceptable under stated conditions.

- **People with higher risk:** Treat this group separately.

## Why This Read

The evidence is scoped.
"""

    assert _default_answer_from_body(body) == "For the default case, the current read is acceptable under stated conditions."


def test_section_rewrite_rejects_crux_section_that_drops_synthesis_cruxes(monkeypatch) -> None:
    memo, appendix, scaffold, candidate_map = _memo_package()
    scaffold["decision_synthesis_model"] = {
        "cruxes": [
            {
                "crux": "Whether biomarker evidence should change the recommendation",
                "current_read": "Biomarker evidence is a caution, not the whole decision.",
                "would_change_if": "The recommendation would change if direct outcome evidence showed clinically important harm.",
            },
            {
                "crux": "Whether subgroup risk narrows the default recommendation",
                "current_read": "The subgroup remains a separate exception.",
                "would_change_if": "The recommendation would change if subgroup risk applied to the default population.",
            },
        ],
        "evidence_lines": [],
        "central_tensions": [],
    }

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        if "## Decision Cruxes" in prompt:
            return ModelBackendResult(
                text=json.dumps(
                    {
                        "section_markdown": (
                            "## Decision Cruxes\n\n"
                            "| Crux | Current read | Would change if |\n"
                            "|---|---|---|\n"
                            "| Whether cost matters | Costs are relevant. | The recommendation would change if costs were immaterial. |\n"
                            "| Whether timing matters | Timing is relevant. | The recommendation would change if timing were immaterial. |"
                        )
                    }
                ),
                backend=backend,
            )
        section = prompt.split("Section to rewrite:\n", 1)[1].strip()
        return ModelBackendResult(text=json.dumps({"section_markdown": section}), backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_section_rewrite.run_model_backend", fake_backend)

    result = rewrite_reader_memo_by_section(
        memo,
        appendix,
        scaffold,
        candidate_map,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    crux_report = next(section for section in result["report"]["sections"] if section["title"] == "Decision Cruxes")
    assert crux_report["status"] == "rejected_fallback"
    assert any("dropped required crux" in issue for issue in crux_report["issues"])


def test_section_rewrite_generates_decision_brief_last_and_rejects_exception_led_opening(monkeypatch) -> None:
    memo, appendix, scaffold, candidate_map = _memo_package()

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        if "opening Decision Brief" in prompt:
            return ModelBackendResult(
                text=json.dumps(
                    {
                        "section_markdown": (
                            "## Decision Brief\n\n"
                            f"**Decision question:** {scaffold['question']}\n\n"
                            "High-risk subgroup results are concerning and should lead the memo.\n\n"
                            "**Confidence:** medium"
                        )
                    }
                ),
                backend=backend,
            )
        section = prompt.split("Section to rewrite:\n", 1)[1].strip()
        return ModelBackendResult(text=json.dumps({"section_markdown": section}), backend=backend)

    monkeypatch.setattr("epistemic_case_mapper.map_briefing_section_rewrite.run_model_backend", fake_backend)

    result = rewrite_reader_memo_by_section(
        memo,
        appendix,
        scaffold,
        candidate_map,
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    brief_report = next(section for section in result["report"]["sections"] if section["title"] == "Decision Brief")
    first_answer = result["memo"].split("**Confidence:**", 1)[0]
    assert brief_report["status"] == "rejected_final_brief_fallback"
    assert "opens with an exception" in " ".join(brief_report["issues"])
    assert "High-risk subgroup results are concerning" not in first_answer


def _memo_package() -> tuple[str, str, dict, dict]:
    candidate_map = _arbitrary_candidate_map()
    quality_report = _quality_report()
    question = "Should the city pilot remote permitting for small building projects?"
    source_lookup = build_source_display_lookup(candidate_map)
    scaffold = briefing_scaffold(
        candidate_map,
        quality_report,
        source_lookup,
        generated_map_erosion_audit(candidate_map),
        question=question,
    )
    compact = build_compact_decision_model(
        candidate_map,
        quality_report,
        question=question,
        scaffold=scaffold,
    )
    rendered = render_decision_model_brief(compact)
    package = compose_final_reader_memo_package(rendered, scaffold)
    return str(package["memo"]), str(package["appendix"]), package["scaffold"], candidate_map
