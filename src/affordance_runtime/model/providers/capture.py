"""Explicit opt-in private capture for exact model exchanges."""

from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence


@dataclass
class PrivateModelCapture:
    """Append exact prompts/responses to a private, non-public JSONL artifact."""

    directory: Path
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)
    _sequence: int = field(default=0, init=False, repr=False)

    def __post_init__(self) -> None:
        path = Path(self.directory).resolve()
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        if path.is_symlink() or not path.is_dir():
            raise ValueError("private model capture path must be a real directory")
        os.chmod(path, 0o700)
        self.directory = path

    @property
    def path(self) -> Path:
        return self.directory / "model-exchanges.jsonl"

    def record(
        self,
        *,
        provider: str,
        model: str,
        schema_name: str,
        messages: Sequence[Any],
        status: str,
        response_content: object | None = None,
        response_id: str = "",
        error: str = "",
    ) -> None:
        with self._lock:
            self._sequence += 1
            context_id = _context_id(messages)
            payload = {
                "schema_version": "private-model-exchange.v1",
                "sequence": self._sequence,
                "provider": provider,
                "model": model,
                "schema_name": schema_name,
                "status": status,
                "context_id": context_id,
                "policy_request_id": (
                    "model-request:" + hashlib.sha256(context_id.encode()).hexdigest()[:24]
                    if context_id else ""
                ),
                "request_messages": [_message_payload(item) for item in messages],
                "response_content": response_content,
                "response_id": response_id,
                "error": error,
            }
            encoded = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
            descriptor = os.open(
                self.path,
                os.O_WRONLY | os.O_CREAT | os.O_APPEND,
                0o600,
            )
            try:
                remaining = memoryview(encoded)
                while remaining:
                    written = os.write(descriptor, remaining)
                    if written <= 0:
                        raise OSError("private model capture write made no progress")
                    remaining = remaining[written:]
                os.fsync(descriptor)
                os.fchmod(descriptor, 0o600)
            finally:
                os.close(descriptor)


def _context_id(messages: Sequence[Any]) -> str:
    for message in reversed(messages):
        role = (
            message.get("role", "")
            if isinstance(message, Mapping)
            else getattr(message, "role", "")
        )
        if role != "user":
            continue
        content = (
            message.get("content", "")
            if isinstance(message, Mapping)
            else getattr(message, "content", "")
        )
        if not isinstance(content, str):
            content = next(
                (
                    item.get("text", "")
                    if isinstance(item, Mapping)
                    else getattr(item, "text", "")
                    for item in content
                    if (
                        item.get("type", "")
                        if isinstance(item, Mapping)
                        else getattr(item, "type", "")
                    )
                    == "text"
                ),
                "",
            )
        try:
            value = json.loads(content)
        except (TypeError, ValueError, json.JSONDecodeError):
            return ""
        if isinstance(value, dict) and isinstance(value.get("agent_context"), dict):
            value = value["agent_context"]
        candidate = value.get("context_id") if isinstance(value, dict) else None
        return candidate if isinstance(candidate, str) and candidate.startswith("context:") else ""
    return ""


def _message_payload(message: Any) -> Any:
    if isinstance(message, Mapping):
        return dict(message)
    return message.model_dump()


def private_capture_from_environment(
    environment: Mapping[str, str],
) -> PrivateModelCapture | None:
    enabled = environment.get("LLM_ENABLE_PRIVATE_MODEL_CAPTURE", "").strip().casefold()
    if enabled not in {"1", "true", "yes", "on"}:
        return None
    raw = environment.get("LLM_PRIVATE_MODEL_CAPTURE_DIR", "").strip()
    if not raw:
        raise ValueError("private model capture requires LLM_PRIVATE_MODEL_CAPTURE_DIR")
    return PrivateModelCapture(Path(raw))
