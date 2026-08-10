import asyncio
from dataclasses import dataclass, field

from affordance_runtime.execution import ActionResult, BoundActionRequest, DispatchStatus
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    ActionBinder,
    ActionBinding,
    ActionRisk,
    ActionSpaceBuilder,
    CoverageState,
    ObservationRequestKind,
    ObservationSourceProfile,
    SemanticTarget,
    SurfaceObservation,
    WorldObservationRequest,
)
from affordance_runtime.world.orchestrator import UnifiedWorldEnvironment


@dataclass
class SequencedAdapter:
    surface: str
    sequence: int = 0
    executions: list[BoundActionRequest] = field(default_factory=list)
    current_source_id: str = ""

    async def reset(self, task: TaskGoal) -> None:
        del task
        self.executions.clear()

    async def observe(self, reason: str) -> SurfaceObservation:
        del reason
        self.sequence += 1
        source_id = f"{self.surface}:obs:{self.sequence}"
        revision = f"{self.surface}:rev:{self.sequence}"
        target_id = f"{self.surface}:target"
        self.current_source_id = source_id
        binding = ActionBinding(
            binding_id=f"{source_id}:binding",
            world_observation_id=source_id,
            source_observation_id=source_id,
            source_revision=revision,
            target_fingerprint=f"{source_id}:fingerprint",
            target_id=target_id,
            source_target_id=target_id,
            surface=self.surface,
            executor_id=self.surface,
            semantic_action="activate",
            primitive_action="click",
            effect_category="local_reversible",
            semantic_effects=("shared_state_enabled",),
            parameter_schema={"type": "object", "properties": {}, "additionalProperties": False},
            payload={"private": source_id},
            risk=ActionRisk.LOW,
        )
        return SurfaceObservation(
            source_id,
            self.surface,
            revision,
            ObservationSourceProfile.dom() if self.surface == "dom" else ObservationSourceProfile.wot(),
            (SemanticTarget(target_id, "button", target_id),),
            bindings=(binding,),
            coverage=CoverageState.COMPLETE,
        )

    def is_current(self, request: BoundActionRequest) -> bool:
        return request.binding.source_observation_id == self.current_source_id

    async def execute(self, request: BoundActionRequest) -> ActionResult:
        self.executions.append(request)
        return ActionResult(request.request_id, DispatchStatus.SENT, self.surface, True)


def test_multi_adapter_old_binding_cannot_be_relabelled_as_current() -> None:
    async def scenario() -> None:
        dom = SequencedAdapter("dom")
        wot = SequencedAdapter("wot")
        environment = UnifiedWorldEnvironment((dom, wot))
        task = TaskGoal(
            "shared",
            "Enable shared state",
            allowed_effects=("shared_state_enabled",),
            risk_profile=RiskProfile.LOW,
        )
        acquisition = await environment.reset(task)
        assert acquisition.observation is not None
        old = acquisition.observation
        option = ActionSpaceBuilder().build(task, old).options[0]
        request = ActionBinder().bind(ActionSpaceBuilder().admit(option, {}), old, "context:test")

        await environment.capture(WorldObservationRequest(ObservationRequestKind.CURRENTNESS_REFRESH, "new"))
        result = (await environment.execute(request)).result

        assert not environment.is_current(request)
        assert result.dispatch_status == DispatchStatus.NOT_SENT
        assert dom.executions == [] and wot.executions == []
        assert request.binding.source_observation_id.endswith(":obs:1")

    asyncio.run(scenario())


def test_reset_invalidates_old_world_identity_before_next_observation() -> None:
    async def scenario() -> None:
        adapter = SequencedAdapter("dom")
        environment = UnifiedWorldEnvironment((adapter,))
        task = TaskGoal(
            "shared",
            "Enable shared state",
            allowed_effects=("shared_state_enabled",),
            risk_profile=RiskProfile.LOW,
        )
        acquisition = await environment.reset(task)
        assert acquisition.observation is not None
        old = acquisition.observation
        builder = ActionSpaceBuilder()
        option = builder.build(task, old).options[0]
        request = ActionBinder().bind(builder.admit(option, {}), old, "context:test")

        await environment.reset(task)
        result = (await environment.execute(request)).result

        assert not environment.is_current(request)
        assert result.dispatch_status == DispatchStatus.NOT_SENT
        assert adapter.executions == []

    asyncio.run(scenario())
