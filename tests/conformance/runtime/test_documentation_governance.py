from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).parents[3]
README = ROOT / "README.md"
DOCS = ROOT / "docs"
CORE_DOCS = {
    DOCS / "architecture.md",
    DOCS / "benchmark.md",
    DOCS / "extending.md",
}


def test_project_has_four_maintained_markdown_documents() -> None:
    markdown = {README, *DOCS.rglob("*.md")}

    assert markdown == {README, *CORE_DOCS}


def test_readme_links_every_core_document() -> None:
    text = README.read_text(encoding="utf-8")
    linked_paths = {
        (README.parent / match).resolve()
        for match in re.findall(r"\[[^]]+\]\(([^)#]+\.md)(?:#[^)]+)?\)", text)
    }

    assert {path.resolve() for path in CORE_DOCS} <= linked_paths


def test_core_docs_state_the_simplified_contract() -> None:
    architecture = (DOCS / "architecture.md").read_text(encoding="utf-8")
    benchmark = (DOCS / "benchmark.md").read_text(encoding="utf-8")
    extending = (DOCS / "extending.md").read_text(encoding="utf-8")

    assert all(term in architecture for term in ("RunState", "StepResult", "WorldObservation"))
    assert "task success" in benchmark.casefold()
    assert all(term in extending for term in ("SurfaceAdapter", "ActionBinding", "ModelPort"))
