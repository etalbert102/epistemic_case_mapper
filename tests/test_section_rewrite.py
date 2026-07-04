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
from epistemic_case_mapper.map_briefing_section_rewrite import rewrite_reader_memo_by_section
from epistemic_case_mapper.model_backends import ModelBackendResult
from tests.test_decision_model_vertical_slice import _arbitrary_candidate_map, _quality_report


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
