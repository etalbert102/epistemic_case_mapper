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
from epistemic_case_mapper.map_briefing_section_rewrite import _decision_brief_slots, _default_answer_from_body, rewrite_reader_memo_by_section
from epistemic_case_mapper.map_briefing_section_ownership import (
    build_section_evidence_ownership,
    repeated_owned_evidence_issues,
)
from epistemic_case_mapper.main_memo_obligations import section_obligations_for_title
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


def test_section_ownership_flags_full_repeat_outside_owner_section() -> None:
    row = {
        "slot": "hard-outcome support",
        "claim": "The pilot reduced permit review time by 34 percent without increasing error rates.",
        "source": "Evaluation",
        "anchor_terms": ["pilot", "reduced", "permit", "review", "34", "error"],
    }
    sections = [
        {
            "title": "Why This Read",
            "markdown": "## Why This Read\n\nThe pilot reduced permit review time by 34 percent without increasing error rates.",
        },
        {
            "title": "Evidence Carrying the Conclusion",
            "markdown": "## Evidence Carrying the Conclusion\n\nThe pilot reduced permit review time by 34 percent without increasing error rates.",
        },
    ]
    contract = {"required_evidence": [row]}
    contract["_section_evidence_ownership"] = build_section_evidence_ownership(sections, contract)

    owned = contract["_section_evidence_ownership"]["rows"]
    assert next(iter(owned.values()))["primary_owner_section"] == "Evidence Carrying the Conclusion"
    assert repeated_owned_evidence_issues("Why This Read", sections[0]["markdown"], contract)
    assert not repeated_owned_evidence_issues(
        "Why This Read",
        "## Why This Read\n\nThe main outcome evidence is discussed in the evidence section.",
        contract,
    )


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


def test_decision_brief_slots_skip_top_line_ineligible_caveat() -> None:
    contract = {
        "_main_memo_obligation_plan": [
            {
                "obligation_id": "scope_01",
                "category": "scope_boundary",
                "stage_owner": "decision_synthesis",
                "priority": 90,
                "statement": "Eating too many amino acids may increase cardiovascular disease and death risk.",
                "eligibility": {"top_line_eligible": False, "appendix_only": False},
            },
            {
                "obligation_id": "counter_01",
                "category": "strongest_counterargument",
                "stage_owner": "decision_synthesis",
                "priority": 89,
                "statement": "High exposure was associated with higher risk in a named high-risk subgroup.",
                "eligibility": {"top_line_eligible": True, "appendix_only": False},
            },
            {
                "obligation_id": "support_01",
                "category": "strongest_support",
                "stage_owner": "decision_synthesis",
                "priority": 88,
                "statement": "Moderate exposure was not associated with higher risk in the target population.",
                "eligibility": {"top_line_eligible": True, "appendix_only": False},
            },
        ],
    }
    body = """## Practical Read

For the target population, use the default read under stated conditions.
"""

    slots = _decision_brief_slots(contract, body)

    assert "amino acids" not in slots["caveat"]
    assert "high-risk subgroup" in slots["caveat"]


def test_section_obligations_skip_section_ineligible_scope_boundary() -> None:
    obligations = [
        {
            "obligation_id": "scope_01",
            "category": "scope_boundary",
            "stage_owner": "decision_synthesis",
            "priority": 90,
            "statement": "Eating too many amino acids may increase cardiovascular disease and death risk.",
            "eligibility": {
                "top_line_eligible": False,
                "appendix_only": False,
                "section_eligibility": {"scope_and_exceptions": False, "limits": False},
            },
        },
        {
            "obligation_id": "scope_02",
            "category": "scope_boundary",
            "stage_owner": "decision_synthesis",
            "priority": 89,
            "statement": "People with type 2 diabetes should be handled as a separate decision scope.",
            "eligibility": {
                "top_line_eligible": True,
                "appendix_only": False,
                "section_eligibility": {"scope_and_exceptions": True, "limits": False},
            },
        },
    ]

    selected = section_obligations_for_title("Practical Scope and Exceptions", obligations)

    assert [row["obligation_id"] for row in selected] == ["scope_02"]


def test_section_rewrite_uses_structured_cruxes_instead_of_model_crux_rewrite(monkeypatch) -> None:
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
            raise AssertionError("Decision Cruxes should not be model-rewritten when structured cruxes exist")
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
    assert crux_report["status"] == "accepted_structured_cruxes"
    assert "Whether" in result["memo"]
    assert "would change if" in result["memo"].lower()


def test_section_rewrite_rejects_section_that_drops_main_memo_obligation(monkeypatch) -> None:
    memo, appendix, scaffold, candidate_map = _memo_package()
    scaffold["argument_model"]["quantitative_anchors"] = [
        {
            "statement": "The tracked estimate was 42 units in the main comparison.",
            "why_it_matters": "This estimate is the main quantitative anchor.",
            "quantities": ["42 units"],
            "source_ids": [],
            "claim_ids": [],
            "quantity_ids": [],
        }
    ]
    seen_prompt = ""

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        nonlocal seen_prompt
        section = prompt.split("Section to rewrite:\n", 1)[1].strip()
        if prompt.startswith("You are writing one section") and section.startswith("## Evidence Carrying the Conclusion"):
            seen_prompt = prompt
            return ModelBackendResult(
                text=json.dumps({"section_markdown": "## Evidence Carrying the Conclusion\n\nThe answer follows from the source packet."}),
                backend=backend,
            )
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

    why_report = next(section for section in result["report"]["sections"] if section["title"] == "Evidence Carrying the Conclusion")
    assert "required_main_memo_obligations" in seen_prompt
    assert why_report["status"] == "rejected_fallback"
    assert any("dropped required main-memo obligation" in issue for issue in why_report["issues"])


def test_section_rewrite_generates_decision_brief_last_deterministically(monkeypatch) -> None:
    memo, appendix, scaffold, candidate_map = _memo_package()
    calls: list[str] = []

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        calls.append(prompt)
        if "opening Decision Brief" in prompt:
            raise AssertionError("Decision Brief should be deterministic, not model-rewritten")
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
    assert brief_report["status"] == "accepted_deterministic_slots"
    assert brief_report["accepted"] is True
    assert "Key evidence:" in result["memo"]
    assert "Key caveat:" in result["memo"]
    assert not any("opening Decision Brief" in prompt for prompt in calls)


def test_section_rewrite_renders_decision_cruxes_from_structured_objects(monkeypatch) -> None:
    memo, appendix, scaffold, candidate_map = _memo_package()
    scaffold["decision_argument_artifacts"]["structured_decision_cruxes"] = {
        "schema_id": "structured_decision_cruxes_v1",
        "cruxes": [
            {
                "crux": "Whether review capacity narrows the default recommendation",
                "why_it_matters": "Capacity determines whether the default read travels.",
                "current_read": "The current read treats capacity as a boundary.",
                "would_change_if": "The recommendation would change if capacity constraints applied to all target users.",
                "supporting_finding_ids": ["finding_01"],
                "challenging_finding_ids": ["finding_02"],
                "source_ids": ["audit"],
            }
        ],
    }
    calls: list[str] = []

    def fake_backend(prompt: str, backend: str, timeout_seconds=None, max_retries=0):
        calls.append(prompt)
        if "## Decision Cruxes" in prompt:
            raise AssertionError("Decision Cruxes should be deterministically rendered from structured cruxes")
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
    assert crux_report["status"] == "accepted_structured_cruxes"
    assert "Whether review capacity narrows" in result["memo"]
    assert "Claim A" not in result["memo"]
    assert not any("## Decision Cruxes" in prompt for prompt in calls)


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
