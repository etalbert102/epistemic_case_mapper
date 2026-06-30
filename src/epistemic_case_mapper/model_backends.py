from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelBackendResult:
    text: str
    backend: str
    prompt_only: bool = False


def run_model_backend(prompt: str, backend: str) -> ModelBackendResult:
    spec = backend.strip()
    if not spec or spec == "prompt":
        return ModelBackendResult(text=prompt, backend="prompt", prompt_only=True)
    if spec.startswith("command:"):
        command = spec.removeprefix("command:").strip()
        if not command:
            raise ValueError("empty command backend")
        return ModelBackendResult(text=_run_command(command, prompt), backend=spec)
    if spec.startswith("ollama:"):
        model = spec.removeprefix("ollama:").strip()
        if not model:
            raise ValueError("empty ollama model")
        return ModelBackendResult(text=_run_ollama(model, prompt), backend=spec)
    raise ValueError(
        "unknown model backend. Use 'prompt', 'command:<cmd that reads stdin>', or 'ollama:<model>'."
    )


def _run_command(command: str, prompt: str) -> str:
    args = shlex.split(command)
    result = subprocess.run(
        args,
        input=prompt,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"model command failed returncode={result.returncode} stderr={stderr}")
    return result.stdout


def _run_ollama(model: str, prompt: str) -> str:
    result = subprocess.run(
        ["ollama", "run", model, "--format", "json", "--hidethinking", "--nowordwrap"],
        input=prompt,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"ollama backend failed model={model} returncode={result.returncode} stderr={stderr}")
    return result.stdout
