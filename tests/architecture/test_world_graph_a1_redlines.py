import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "src" / "affordance_runtime"


def test_displaced_correspondence_and_provenance_owners_are_absent() -> None:
    production = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "world").glob("*.py")
    )
    assert "EntityCorrespondence" not in production
    assert "FusedEntityProvenance" not in production
    assert "entity_provenance" not in production
    assert "_canonical_maps" not in production


def test_actor_projection_consumes_links_without_rebuilding_correspondence() -> None:
    actor = (ROOT / "agent" / "context" / "actor_world_snapshot.py").read_text(encoding="utf-8")
    assert "entity_source_links" in actor
    assert ".correspondences" not in actor
    assert "collision" not in actor


def test_alignment_decisions_and_final_links_have_separate_authority() -> None:
    contracts = (ROOT / "world" / "contracts.py").read_text(encoding="utf-8")
    link_body = contracts.split("class EntitySourceLink:", 1)[1].split(
        "class SourceObservationManifest:", 1
    )[0]
    assert "class EntityAlignmentDecision:" in contracts
    assert "class EntityAllocation" in contracts
    assert "evidence_refs" not in link_body
    assert "confidence" not in link_body
    assert "reason_code" not in link_body


def test_world_fusion_is_the_only_production_decision_and_world_constructor() -> None:
    forbidden_calls = {"EntityAlignmentDecision", "WorldObservation"}
    violations: list[str] = []
    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT)
        if relative.as_posix() == "world/fusion.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = (
                node.func.id
                if isinstance(node.func, ast.Name)
                else node.func.attr
                if isinstance(node.func, ast.Attribute)
                else ""
            )
            if name in forbidden_calls:
                violations.append(f"{relative}:{node.lineno}:{name}")
    assert violations == []


def test_provider_serialization_cannot_fuse_align_or_regroup_world_identity() -> None:
    provider = (ROOT / "model" / "policy" / "grounded_policy_context.py").read_text(encoding="utf-8")
    forbidden = (
        "WorldFusion",
        "EntityAlignmentProposal",
        "EntityAlignmentDecision",
        "EntitySourceLink",
        "alignment_proposals",
        "source_target_id",
        "canonical_target_id",
    )
    assert all(item not in provider for item in forbidden)


def test_action_and_tool_owners_do_not_import_observation_alignment_authority() -> None:
    action_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "actions").glob("*.py")
    )
    assert "EntityAlignmentProposal" not in action_sources
    assert "EntitySourceLink" not in action_sources
    assert "ObservationStructureNode" not in action_sources
