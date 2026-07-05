from __future__ import annotations

import json
import os
import shlex
import subprocess
from dataclasses import dataclass
from urllib import error, request


@dataclass(frozen=True)
class ModelBackendResult:
    text: str
    backend: str
    prompt_only: bool = False
    attempts: int = 1


def run_model_backend(
    prompt: str,
    backend: str,
    timeout_seconds: int | None = None,
    max_retries: int = 1,
    response_schema: dict | None = None,
) -> ModelBackendResult:
    spec = backend.strip()
    if not spec or spec == "prompt":
        return ModelBackendResult(text=prompt, backend="prompt", prompt_only=True)
    if spec.startswith("command:"):
        command = spec.removeprefix("command:").strip()
        if not command:
            raise ValueError("empty command backend")
        text, attempts = _run_with_retries(
            lambda: _run_command(command, prompt, timeout_seconds),
            max_retries=max_retries,
        )
        return ModelBackendResult(text=text, backend=spec, attempts=attempts)
    if spec.startswith("ollama:"):
        model = spec.removeprefix("ollama:").strip()
        if not model:
            raise ValueError("empty ollama model")
        text, attempts = _run_with_retries(
            lambda: _run_ollama(model, prompt, timeout_seconds, response_schema=response_schema),
            max_retries=max_retries,
        )
        return ModelBackendResult(text=text, backend=spec, attempts=attempts)
    raise ValueError(
        "unknown model backend. Use 'prompt', 'command:<cmd that reads stdin>', or 'ollama:<model>'."
    )


def _run_with_retries(call, max_retries: int) -> tuple[str, int]:
    attempts = max(1, max_retries + 1)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return call(), attempt
        except RuntimeError as exc:
            last_error = exc
            if attempt == attempts:
                break
    assert last_error is not None
    raise last_error


def _run_command(command: str, prompt: str, timeout_seconds: int | None) -> str:
    args = shlex.split(command)
    try:
        result = subprocess.run(
            args,
            input=prompt,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"model command timed out after {timeout_seconds}s") from exc
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"model command failed returncode={result.returncode} stderr={stderr}")
    return result.stdout


def _run_ollama(model: str, prompt: str, timeout_seconds: int | None, *, response_schema: dict | None = None) -> str:
    if os.environ.get("ECM_OLLAMA_BACKEND", "http").strip().lower() == "cli":
        return _run_ollama_cli(model, prompt, timeout_seconds)
    try:
        return _run_ollama_http(model, prompt, timeout_seconds, response_schema=response_schema)
    except RuntimeError as exc:
        if not _should_fallback_to_ollama_cli(exc):
            raise
        return _run_ollama_cli(model, prompt, timeout_seconds)


def _run_ollama_http(
    model: str,
    prompt: str,
    timeout_seconds: int | None,
    *,
    response_schema: dict | None = None,
) -> str:
    host = _ollama_host()
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": response_schema or "json",
        "think": False,
        "options": {
            "temperature": float(os.environ.get("ECM_OLLAMA_TEMPERATURE", "0")),
            "num_predict": int(os.environ.get("ECM_OLLAMA_NUM_PREDICT", "2048")),
        },
    }
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{host}/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            data = json.loads(response.read().decode("utf-8"))
    except TimeoutError as exc:
        raise RuntimeError(f"ollama http backend timed out model={model} after {timeout_seconds}s") from exc
    except error.URLError as exc:
        raise RuntimeError(f"ollama http backend unavailable model={model} error={exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ollama http backend returned non-json envelope model={model}") from exc
    message = data.get("message", {}) if isinstance(data, dict) else {}
    content = message.get("content", "") if isinstance(message, dict) else ""
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(f"ollama http backend returned empty content model={model}")
    return content


def _ollama_host() -> str:
    host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").strip().rstrip("/")
    if not host:
        return "http://127.0.0.1:11434"
    if "://" not in host:
        host = f"http://{host}"
    return host


def _should_fallback_to_ollama_cli(exc: RuntimeError) -> bool:
    message = str(exc)
    return "unavailable" in message or "non-json envelope" in message or "empty content" in message


def _run_ollama_cli(model: str, prompt: str, timeout_seconds: int | None) -> str:
    try:
        result = subprocess.run(
            ["ollama", "run", model, "--format", "json", "--hidethinking", "--nowordwrap"],
            input=prompt,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"ollama backend timed out model={model} after {timeout_seconds}s") from exc
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"ollama backend failed model={model} returncode={result.returncode} stderr={stderr}")
    return result.stdout
