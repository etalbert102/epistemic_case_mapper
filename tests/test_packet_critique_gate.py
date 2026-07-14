from __future__ import annotations

from epistemic_case_mapper.map_briefing_packet_refinement import _packet_critique_skip_reason


def test_packet_critique_auto_skips_ready_packet(monkeypatch) -> None:
    monkeypatch.delenv("ECM_PACKET_CRITIQUE_MODE", raising=False)

    assert _packet_critique_skip_reason({"status": "ready", "issues": []}) == "auto_skipped_packet_ready"


def test_packet_critique_auto_skips_compression_loss_only(monkeypatch) -> None:
    monkeypatch.delenv("ECM_PACKET_CRITIQUE_MODE", raising=False)

    assert _packet_critique_skip_reason({"status": "usable_with_warnings", "issues": ["compression_loss"]}) == "auto_skipped_compression_loss_only"


def test_packet_critique_auto_skips_actionable_issue_on_live_backend(monkeypatch) -> None:
    monkeypatch.delenv("ECM_PACKET_CRITIQUE_MODE", raising=False)

    assert (
        _packet_critique_skip_reason(
            {"status": "usable_with_warnings", "issues": ["directionality_warnings"]},
            backend="ollama:gemma3:12b",
        )
        == "auto_skipped_lightweight_guidance_default"
    )


def test_packet_critique_auto_keeps_fake_backend_for_unit_tests(monkeypatch) -> None:
    monkeypatch.delenv("ECM_PACKET_CRITIQUE_MODE", raising=False)

    assert (
        _packet_critique_skip_reason(
            {"status": "usable_with_warnings", "issues": ["directionality_warnings"]},
            backend="fake",
        )
        == ""
    )


def test_packet_critique_always_override_runs_even_for_ready_packet(monkeypatch) -> None:
    monkeypatch.setenv("ECM_PACKET_CRITIQUE_MODE", "always")

    assert _packet_critique_skip_reason({"status": "ready", "issues": []}) == ""


def test_packet_critique_off_override_skips_actionable_issue(monkeypatch) -> None:
    monkeypatch.setenv("ECM_PACKET_CRITIQUE_MODE", "off")

    assert _packet_critique_skip_reason({"status": "not_sufficient_for_synthesis", "issues": ["decision_critical_omitted_evidence"]}) == "disabled_by_ecm_packet_critique_mode"
