"""Fail-closed local provider identity, capacity, and GPU-residency preflight."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class OllamaPreflightReport:
    schema_version: str
    ready: bool
    container_name: str
    ollama_version: str
    model: str
    model_digest: str
    model_format: str
    parameter_size: str
    quantization: str
    model_context_length: int
    loaded_context_length: int
    model_size_bytes: int
    size_vram_bytes: int
    gpu_name: str
    gpu_driver_version: str
    gpu_memory_total_mib: int
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def inspect_ollama_gpu(
    *,
    base_url: str = "http://127.0.0.1:11434",
    model: str = "qwen2.5:7b",
    container_name: str = "ollama",
    timeout_s: float = 120.0,
    request_json: Callable[[str, str, dict[str, Any] | None, float], dict[str, Any]] | None = None,
    run_command: Callable[[list[str]], subprocess.CompletedProcess[str]] | None = None,
) -> OllamaPreflightReport:
    request = request_json or _request_json
    command = run_command or _run_command
    errors: list[str] = []
    version_payload: dict[str, Any] = {}
    tags_payload: dict[str, Any] = {}
    ps_payload: dict[str, Any] = {}
    gpu_name = ""
    gpu_driver = ""
    gpu_memory_mib = 0
    try:
        version_payload = request("GET", f"{base_url.rstrip('/')}/api/version", None, min(timeout_s, 10.0))
        tags_payload = request("GET", f"{base_url.rstrip('/')}/api/tags", None, min(timeout_s, 10.0))
        request(
            "POST",
            f"{base_url.rstrip('/')}/api/generate",
            {
                "model": model,
                "prompt": "Reply with OK.",
                "stream": False,
                "keep_alive": "10m",
                "options": {"temperature": 0, "num_predict": 1},
            },
            timeout_s,
        )
        ps_payload = request("GET", f"{base_url.rstrip('/')}/api/ps", None, min(timeout_s, 10.0))
    except (OSError, ValueError, urllib.error.URLError) as exc:
        errors.append(f"ollama_api:{type(exc).__name__}")
    try:
        completed = command(
            [
                "docker",
                "exec",
                container_name,
                "nvidia-smi",
                "--query-gpu=name,driver_version,memory.total",
                "--format=csv,noheader,nounits",
            ]
        )
        if completed.returncode != 0:
            errors.append("container_nvidia_smi:failed")
        else:
            first = completed.stdout.strip().splitlines()[0]
            parts = [part.strip() for part in first.split(",")]
            if len(parts) != 3:
                errors.append("container_nvidia_smi:invalid_output")
            else:
                gpu_name, gpu_driver = parts[:2]
                gpu_memory_mib = int(float(parts[2]))
    except (FileNotFoundError, IndexError, ValueError, subprocess.SubprocessError) as exc:
        errors.append(f"container_nvidia_smi:{type(exc).__name__}")

    tag = _named_model(tags_payload, model)
    loaded = _named_model(ps_payload, model)
    raw_details = tag.get("details")
    details: dict[str, Any] = raw_details if isinstance(raw_details, dict) else {}
    size_vram = int(loaded.get("size_vram") or 0)
    if not tag:
        errors.append("model_identity:not_found")
    if not loaded:
        errors.append("model_residency:not_loaded")
    elif size_vram <= 0:
        errors.append("model_residency:zero_vram")
    if not gpu_name:
        errors.append("gpu_identity:missing")
    return OllamaPreflightReport(
        schema_version="ollama-gpu-preflight-v1",
        ready=not errors,
        container_name=container_name,
        ollama_version=str(version_payload.get("version") or ""),
        model=model,
        model_digest=str(tag.get("digest") or loaded.get("digest") or ""),
        model_format=str(details.get("format") or ""),
        parameter_size=str(details.get("parameter_size") or ""),
        quantization=str(details.get("quantization_level") or ""),
        model_context_length=int(details.get("context_length") or 0),
        loaded_context_length=int(loaded.get("context_length") or 0),
        model_size_bytes=int(loaded.get("size") or tag.get("size") or 0),
        size_vram_bytes=size_vram,
        gpu_name=gpu_name,
        gpu_driver_version=gpu_driver,
        gpu_memory_total_mib=gpu_memory_mib,
        errors=tuple(dict.fromkeys(errors)),
    )


def write_ollama_gpu_preflight(output: Path, **kwargs: Any) -> OllamaPreflightReport:
    report = inspect_ollama_gpu(**kwargs)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
    return report


def _request_json(method: str, url: str, body: dict[str, Any] | None, timeout_s: float) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - explicit local provider
        payload = json.loads(response.read())
    if not isinstance(payload, dict):
        raise ValueError("Ollama returned a non-object response")
    return payload


def _run_command(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, check=False, capture_output=True, text=True, timeout=10)


def _named_model(payload: dict[str, Any], model: str) -> dict[str, Any]:
    models = payload.get("models")
    if not isinstance(models, list):
        return {}
    return next(
        (
            item
            for item in models
            if isinstance(item, dict) and str(item.get("name") or item.get("model") or "") == model
        ),
        {},
    )
