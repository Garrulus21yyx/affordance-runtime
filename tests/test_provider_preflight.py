import subprocess
from pathlib import Path
from typing import Any

from affordance_runtime.model.providers.preflight import inspect_ollama_gpu, write_ollama_gpu_preflight


def _request_with_vram(
    size_vram: int,
):
    def request(method: str, url: str, body: dict[str, Any] | None, timeout_s: float) -> dict[str, Any]:
        del method, body, timeout_s
        if url.endswith("/api/version"):
            return {"version": "0.32.0"}
        if url.endswith("/api/tags"):
            return {
                "models": [
                    {
                        "name": "qwen2.5:7b",
                        "digest": "model-digest",
                        "size": 4_683_087_332,
                        "details": {
                            "format": "gguf",
                            "parameter_size": "7.6B",
                            "quantization_level": "Q4_K_M",
                            "context_length": 32_768,
                        },
                    }
                ]
            }
        if url.endswith("/api/ps"):
            return {
                "models": [
                    {
                        "name": "qwen2.5:7b",
                        "digest": "model-digest",
                        "size": 4_748_056_984,
                        "size_vram": size_vram,
                        "context_length": 4_096,
                    }
                ]
            }
        return {"response": "OK", "done": True}

    return request


def _nvidia_smi(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    assert arguments[:3] == ["docker", "exec", "ollama"]
    return subprocess.CompletedProcess(arguments, 0, "NVIDIA GeForce RTX 3080, 595.58.03, 10240\n", "")


def test_ollama_preflight_records_identity_and_nonzero_gpu_residency(tmp_path: Path) -> None:
    output = tmp_path / "ollama-preflight.json"
    report = write_ollama_gpu_preflight(
        output,
        request_json=_request_with_vram(4_748_056_984),
        run_command=_nvidia_smi,
    )

    assert report.ready is True
    assert report.model_digest == "model-digest"
    assert report.quantization == "Q4_K_M"
    assert report.model_context_length == 32_768
    assert report.loaded_context_length == 4_096
    assert report.size_vram_bytes == 4_748_056_984
    assert report.gpu_name == "NVIDIA GeForce RTX 3080"
    assert report.gpu_driver_version == "595.58.03"
    assert output.exists()


def test_ollama_preflight_fails_closed_on_zero_vram() -> None:
    report = inspect_ollama_gpu(
        request_json=_request_with_vram(0),
        run_command=_nvidia_smi,
    )

    assert report.ready is False
    assert report.errors == ("model_residency:zero_vram",)
