from __future__ import annotations

import json

from epistemic_case_mapper.model_backends import run_model_backend


def test_ollama_http_backend_honors_per_call_num_predict(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"message": {"content": "{\\"ok\\": true}"}}'

    def fake_urlopen(req, timeout=None):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("epistemic_case_mapper.model_backends.request.urlopen", fake_urlopen)

    result = run_model_backend("prompt", "ollama:test-model", timeout_seconds=7, num_predict=12_288)

    assert result.text == '{"ok": true}'
    assert captured["timeout"] == 7
    assert captured["payload"]["options"]["num_predict"] == 12_288


def test_ollama_http_backend_can_disable_json_mode_for_markdown(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self) -> bytes:
            return b'{"message": {"content": "# Memo\\n\\nBody"}}'

    def fake_urlopen(req, timeout=None):
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr("epistemic_case_mapper.model_backends.request.urlopen", fake_urlopen)

    result = run_model_backend("prompt", "ollama:test-model", json_mode=False)

    assert result.text == "# Memo\n\nBody"
    assert "format" not in captured["payload"]
