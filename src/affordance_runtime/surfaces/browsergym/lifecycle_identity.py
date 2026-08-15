"""Pure BrowserGym physical lifecycle identity helpers."""

from __future__ import annotations

import hashlib


def task_info(info: object) -> dict[str, object]:
    value = info.get("task_info") if isinstance(info, dict) else None
    if not isinstance(value, dict):
        raise RuntimeError("BrowserGym omitted environment-native task status")
    return value


def page_identity(raw: object) -> str:
    url = raw.get("url") if isinstance(raw, dict) else None
    if not isinstance(url, str) or not url:
        raise RuntimeError("BrowserGym observation omitted current page identity")
    return digest_text(url)


def episode_identity(info: dict[str, object]) -> str:
    episode = info.get("EPISODE_ID")
    if not isinstance(episode, int | str) or isinstance(episode, bool):
        raise RuntimeError("BrowserGym task status omitted episode identity")
    return str(episode)


def probe_episode(probe: object, fallback: str) -> str:
    value = probe.get("episode") if isinstance(probe, dict) else None
    return str(value) if isinstance(value, int | str) and not isinstance(value, bool) else fallback


def source_revision(page: str, episode: str, serial: int) -> str:
    return digest_text(f"{page}\0{episode}\0{serial}")


def digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()
