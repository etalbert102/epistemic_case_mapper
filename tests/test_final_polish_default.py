from epistemic_case_mapper.pipeline.briefing.map_briefing_final_polish_policy import (
    disabled_final_polish_result,
    final_polish_enabled,
    run_optional_final_polish,
)


def test_final_polish_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ECM_FINAL_POLISH_MODE", raising=False)
    monkeypatch.delenv("ECM_FINAL_POLISH_BACKEND", raising=False)

    assert final_polish_enabled() is False
    result = disabled_final_polish_result("# Memo\n")
    assert result["memo"] == "# Memo\n"
    assert result["report"]["accepted"] is True
    assert result["report"]["applied"] is False
    assert result["report"]["status"] == "disabled_by_default"


def test_optional_final_polish_does_not_call_model_path_by_default(monkeypatch) -> None:
    monkeypatch.delenv("ECM_FINAL_POLISH_MODE", raising=False)
    monkeypatch.delenv("ECM_FINAL_POLISH_BACKEND", raising=False)

    result = run_optional_final_polish(
        "# Memo\n",
        {},
        backend="fake",
        backend_timeout=30,
        backend_retries=0,
    )

    assert result["report"]["status"] == "disabled_by_default"


def test_final_polish_can_be_enabled_explicitly(monkeypatch) -> None:
    monkeypatch.setenv("ECM_FINAL_POLISH_MODE", "on")
    monkeypatch.delenv("ECM_FINAL_POLISH_BACKEND", raising=False)
    assert final_polish_enabled() is True

    monkeypatch.setenv("ECM_FINAL_POLISH_MODE", "off")
    monkeypatch.setenv("ECM_FINAL_POLISH_BACKEND", "ollama:polish")
    assert final_polish_enabled() is True
