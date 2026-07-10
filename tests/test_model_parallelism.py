from __future__ import annotations

from epistemic_case_mapper.model_backends import model_parallelism, run_parallel


def test_model_parallelism_defaults_to_eight_and_allows_overrides(monkeypatch) -> None:
    monkeypatch.delenv("ECM_MODEL_PARALLELISM", raising=False)
    monkeypatch.delenv("ECM_OLLAMA_PARALLELISM", raising=False)

    assert model_parallelism("ollama:test-model") == 8
    assert model_parallelism("command:fake") == 8

    monkeypatch.setenv("ECM_MODEL_PARALLELISM", "3")
    assert model_parallelism("command:fake") == 3
    assert model_parallelism("ollama:test-model") == 3

    monkeypatch.setenv("ECM_OLLAMA_PARALLELISM", "5")
    assert model_parallelism("ollama:test-model") == 5
    assert model_parallelism("command:fake") == 3


def test_run_parallel_preserves_input_order() -> None:
    result = run_parallel([3, 1, 2], lambda value: value * 10, max_workers=3)

    assert result == [30, 10, 20]


def test_run_parallel_preserves_none_results() -> None:
    result = run_parallel([1, 2, 3], lambda value: None if value == 2 else value, max_workers=3)

    assert result == [1, None, 3]
