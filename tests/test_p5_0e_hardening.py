from __future__ import annotations

import hashlib

import pytest

from affordance_runtime.artifacts import ArtifactStore


def test_artifact_registration_is_run_contained_and_streamed(tmp_path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    run_root = store.run_dir("run-1")
    payload = b"x" * (2 * 1024 * 1024)
    path = run_root / "payload.bin"
    path.write_bytes(payload)

    ref = store.register_file("run-1", path, "application/octet-stream")
    assert ref.sha256 == hashlib.sha256(payload).hexdigest()

    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")
    with pytest.raises(ValueError, match="escapes run root"):
        store.register_file("run-1", outside, "application/octet-stream")


def test_artifact_symlink_is_rejected(tmp_path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")
    run_root = store.run_dir("run-1")
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"secret")
    link = run_root / "link.bin"
    link.symlink_to(outside)
    with pytest.raises(ValueError, match="symlink"):
        store.register_file("run-1", link, "application/octet-stream")
