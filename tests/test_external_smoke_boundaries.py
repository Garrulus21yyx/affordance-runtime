from pathlib import Path

EXTERNAL = Path("src/affordance_runtime/benchmarks/external_smoke")
TARGET_CORE = (
    Path("src/affordance_runtime/agent"),
    Path("src/affordance_runtime/model_boundary"),
    Path("src/affordance_runtime/model_policy"),
    Path("src/affordance_runtime/evaluation"),
    Path("src/affordance_runtime/surfaces"),
)


def test_external_package_avoids_old_core_private_execution_and_transport() -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in EXTERNAL.glob("*.py"))
    for forbidden in (
        "Coordinator", "StateKernel", "RuntimeCommitter", "ActionContract",
        "Binder", "Executor", "urllib", "httpx", "requests",
    ):
        assert forbidden not in text


def test_target_core_and_surfaces_do_not_import_external_smoke() -> None:
    for root in TARGET_CORE:
        for path in root.rglob("*.py"):
            assert "benchmarks.external_smoke" not in path.read_text(encoding="utf-8")


def test_external_optional_dependency_is_not_a_default_dependency() -> None:
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")
    default_dependencies = pyproject.split("[project.optional-dependencies]", 1)[0]
    assert "browsergym-miniwob" not in default_dependencies
    assert "external-smoke" in pyproject
