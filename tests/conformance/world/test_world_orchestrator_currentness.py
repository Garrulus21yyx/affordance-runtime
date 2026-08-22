import asyncio
from dataclasses import dataclass, field

import pytest

from affordance_runtime.actions import (
    ActionBinder,
    ActionBinding,
    ActionRisk,
    ActionSpaceBuilder,
)
from affordance_runtime.agent.decisions import FormFieldUpdate, SetFormFields
from affordance_runtime.agent.run_state import RunState, StepResult
from affordance_runtime.evaluation import TaskEvaluation, TaskEvaluationStatus
from affordance_runtime.execution import (
    ActionDispatchCancelled,
    ActionError,
    ActionResult,
    BoundActionRequest,
    DispatchStatus,
    ExecutionCompletion,
    ExecutionReceiptBatch,
    FormFieldsExecutionCancelled,
)
from affordance_runtime.task import RiskProfile, TaskGoal
from affordance_runtime.world import (
    CoverageState,
    ObservationOffer,
    ObservationRequestKind,
    ObservationSourceProfile,
    SelectedObservationResult,
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
    owns_physical_reset: bool = True

    @property
    def physical_environment_id(self) -> str:
        return f"fixture:{self.surface}"

    @property
    def observation_offers(self):
        if self.surface == "dom":
            return (ObservationOffer("dom", "structural", "structural", "low"),)
        return (ObservationOffer("wot", "environment_state", "authoritative", "medium"),)

    def initialize_task(self, task: TaskGoal) -> None:
        del task
        self.executions.clear()

    async def reset_physical(self) -> None:
        return None

    async def acquire(self, request) -> SelectedObservationResult:
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
        observation = SurfaceObservation(
            source_id,
            self.surface,
            revision,
            ObservationSourceProfile.dom() if self.surface == "dom" else ObservationSourceProfile.wot(),
            (SemanticTarget(target_id, "button", target_id),),
            bindings=(binding,),
            coverage=CoverageState.COMPLETE,
        )
        return SelectedObservationResult.acquired(
            request,
            observation,
            fulfilled_need_ids=tuple(item.need_id for item in request.needs),
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


@dataclass
class FormFieldsAdapter(SequencedAdapter):
    fail_index: int | None = None
    sent_unknown_index: int | None = None
    cancel_dispatch_index: int | None = None
    cancel_post_capture: bool = False

    async def acquire(self, request) -> SelectedObservationResult:
        self.sequence += 1
        if self.cancel_post_capture and self.sequence == 2:
            raise asyncio.CancelledError
        source_id = f"dom:form:{self.sequence}"
        revision = f"dom:form-rev:{self.sequence}"
        self.current_source_id = source_id
        targets = tuple(
            SemanticTarget(f"field:{name}", "textbox", label) for name, label in (("from", "From"), ("to", "To"))
        )
        bindings = tuple(
            ActionBinding(
                binding_id=f"{source_id}:binding:{name}",
                world_observation_id=source_id,
                source_observation_id=source_id,
                source_revision=revision,
                target_fingerprint=f"{source_id}:fingerprint:{name}",
                target_id=f"field:{name}",
                source_target_id=f"field:{name}",
                surface="dom",
                executor_id="dom",
                semantic_action="type_text",
                primitive_action="fill",
                effect_category="local_reversible",
                semantic_effects=("value_changed",),
                parameter_schema={
                    "type": "object",
                    "properties": {"text": {"type": "string"}},
                    "required": ["text"],
                    "additionalProperties": False,
                },
                payload={"field": name},
                risk=ActionRisk.LOW,
            )
            for name in ("from", "to")
        )
        observation = SurfaceObservation(
            source_id,
            "dom",
            revision,
            ObservationSourceProfile.dom(),
            targets,
            bindings=bindings,
            coverage=CoverageState.COMPLETE,
        )
        return SelectedObservationResult.acquired(
            request,
            observation,
            fulfilled_need_ids=tuple(item.need_id for item in request.needs),
        )

    async def execute(self, request: BoundActionRequest) -> ActionResult:
        index = len(self.executions)
        self.executions.append(request)
        if self.cancel_dispatch_index == index:
            raise ActionDispatchCancelled(
                ActionResult(
                    request.request_id,
                    DispatchStatus.SENT_UNKNOWN,
                    "dom",
                    False,
                    ActionError.CANCELLED,
                )
            )
        if self.sent_unknown_index == index:
            return ActionResult(
                request.request_id,
                DispatchStatus.SENT_UNKNOWN,
                "dom",
                False,
                ActionError.EXECUTION_FAILED,
            )
        if self.fail_index == index:
            return ActionResult(
                request.request_id,
                DispatchStatus.NOT_SENT,
                "dom",
                False,
                ActionError.EXECUTION_FAILED,
            )
        return ActionResult(request.request_id, DispatchStatus.SENT, "dom", True)


def test_set_form_fields_dispatches_ordered_receipts_with_one_final_capture() -> None:
    async def scenario() -> None:
        adapter = FormFieldsAdapter("dom")
        environment = UnifiedWorldEnvironment((adapter,))
        task = TaskGoal(
            "form",
            "Set both route endpoints",
            allowed_effects=("value_changed",),
            risk_profile=RiskProfile.LOW,
        )
        initial = await environment.reset(task)
        assert initial.observation is not None
        world = initial.observation
        builder = ActionSpaceBuilder()
        options = sorted(builder.build(task, world).options, key=lambda item: item.target_id)
        requests = tuple(
            ActionBinder().bind_for_execution(
                builder.admit(option, {"text": value}),
                world,
                "context:form",
                task,
                tool_call_id="call:form",
            )
            for option, value in zip(options, ("CMU", "PIT"), strict=True)
        )

        command = ActionBinder().seal_form_fields("form:route", requests, tool_call_id="call:form")
        outcome = await environment.execute_form_fields(command)

        assert tuple(item.intent.parameters["text"] for item in adapter.executions) == ("CMU", "PIT")
        assert tuple(item.dispatch_status for item in outcome.results) == (
            DispatchStatus.SENT,
            DispatchStatus.SENT,
        )
        assert outcome.failed_field_index is None
        assert outcome.post_acquisition is not None
        assert adapter.sequence == 2  # reset capture + one compound-command capture
        after = outcome.post_acquisition.observation
        assert after is not None
        before_evaluation = TaskEvaluation(
            task.task_id,
            world.observation_id,
            TaskEvaluationStatus.INCOMPLETE,
            "before form command",
        )
        state = RunState(world, before_evaluation, 8)
        decision = SetFormFields(
            "context:form",
            "form:route",
            tuple(
                FormFieldUpdate(
                    request.selection.action_id,
                    request.intent.semantic_action,
                    ref,
                    dict(request.intent.parameters),
                )
                for request, ref in zip(requests, ("E1", "E2"), strict=True)
            ),
            "call:form",
        )
        state.apply(
            StepResult(
                decision,
                world,
                after,
                TaskEvaluation(
                    task.task_id,
                    after.observation_id,
                    TaskEvaluationStatus.INCOMPLETE,
                    "after form command",
                ),
                feedback="form_fields_completed",
                execution_receipts=ExecutionReceiptBatch.from_form_fields(
                    outcome,
                    after.observation_id,
                ),
            )
        )
        assert state.execution_count == 2
        assert state.sent_unknown_count == 0

    asyncio.run(scenario())


def test_set_form_fields_stops_on_typed_partial_failure_then_captures_once() -> None:
    async def scenario() -> None:
        adapter = FormFieldsAdapter("dom", fail_index=1)
        environment = UnifiedWorldEnvironment((adapter,))
        task = TaskGoal(
            "form-partial",
            "Set both route endpoints",
            allowed_effects=("value_changed",),
            risk_profile=RiskProfile.LOW,
        )
        initial = await environment.reset(task)
        assert initial.observation is not None
        world = initial.observation
        builder = ActionSpaceBuilder()
        options = sorted(builder.build(task, world).options, key=lambda item: item.target_id)
        requests = tuple(
            ActionBinder().bind_for_execution(
                builder.admit(option, {"text": value}),
                world,
                "context:form-partial",
                task,
            )
            for option, value in zip(options, ("CMU", "PIT"), strict=True)
        )

        command = ActionBinder().seal_form_fields("form:route", requests)
        outcome = await environment.execute_form_fields(command)

        assert outcome.failed_field_index == 1
        assert outcome.completed_field_count == 1
        assert len(adapter.executions) == 2
        assert outcome.post_acquisition is not None
        assert adapter.sequence == 2
        batch = ExecutionReceiptBatch.from_form_fields(
            outcome,
            outcome.post_acquisition.observation.observation_id,
        )
        assert batch.completion is ExecutionCompletion.PARTIAL
        assert batch.execution_count == 1
        assert batch.terminal_failure is outcome.results[1]

    asyncio.run(scenario())


def test_form_fields_sent_unknown_is_counted_by_the_shared_step_receipt_view() -> None:
    async def scenario() -> None:
        adapter = FormFieldsAdapter("dom", sent_unknown_index=1)
        environment = UnifiedWorldEnvironment((adapter,))
        task = TaskGoal(
            "form-unknown",
            "Set both route endpoints",
            allowed_effects=("value_changed",),
            risk_profile=RiskProfile.LOW,
        )
        initial = await environment.reset(task)
        assert initial.observation is not None
        world = initial.observation
        builder = ActionSpaceBuilder()
        options = sorted(builder.build(task, world).options, key=lambda item: item.target_id)
        requests = tuple(
            ActionBinder().bind_for_execution(
                builder.admit(option, {"text": value}),
                world,
                "context:form-unknown",
                task,
                tool_call_id="call:form-unknown",
            )
            for option, value in zip(options, ("CMU", "PIT"), strict=True)
        )
        command = ActionBinder().seal_form_fields(
            "form:route",
            requests,
            tool_call_id="call:form-unknown",
        )
        outcome = await environment.execute_form_fields(command)
        assert outcome.post_acquisition is not None
        after = outcome.post_acquisition.observation
        assert after is not None
        state = RunState(
            world,
            TaskEvaluation(
                task.task_id,
                world.observation_id,
                TaskEvaluationStatus.INCOMPLETE,
                "before form command",
            ),
            8,
        )
        decision = SetFormFields(
            "context:form-unknown",
            "form:route",
            tuple(
                FormFieldUpdate(
                    request.selection.action_id,
                    request.intent.semantic_action,
                    ref,
                    dict(request.intent.parameters),
                )
                for request, ref in zip(requests, ("E1", "E2"), strict=True)
            ),
            "call:form-unknown",
        )
        state.apply(
            StepResult(
                decision,
                world,
                after,
                TaskEvaluation(
                    task.task_id,
                    after.observation_id,
                    TaskEvaluationStatus.INCOMPLETE,
                    "after uncertain form command",
                ),
                feedback="form_fields_partial_failure:1",
                execution_receipts=ExecutionReceiptBatch.from_form_fields(
                    outcome,
                    after.observation_id,
                ),
            )
        )

        assert state.execution_count == 2
        assert state.sent_unknown_count == 1

    asyncio.run(scenario())


def test_set_form_fields_propagates_dispatch_cancellation_with_partial_truth() -> None:
    async def scenario() -> None:
        adapter = FormFieldsAdapter("dom", cancel_dispatch_index=1)
        environment = UnifiedWorldEnvironment((adapter,))
        task = TaskGoal(
            "form-cancel",
            "Set both route endpoints",
            allowed_effects=("value_changed",),
            risk_profile=RiskProfile.LOW,
        )
        initial = await environment.reset(task)
        assert initial.observation is not None
        world = initial.observation
        builder = ActionSpaceBuilder()
        options = sorted(builder.build(task, world).options, key=lambda item: item.target_id)
        requests = tuple(
            ActionBinder().bind_for_execution(
                builder.admit(option, {"text": value}),
                world,
                "context:form-cancel",
                task,
            )
            for option, value in zip(options, ("CMU", "PIT"), strict=True)
        )
        command = ActionBinder().seal_form_fields("form:route", requests)

        with pytest.raises(FormFieldsExecutionCancelled) as cancelled:
            await environment.execute_form_fields(command)

        outcome = cancelled.value.outcome
        assert tuple(item.dispatch_status for item in outcome.results) == (
            DispatchStatus.SENT,
            DispatchStatus.SENT_UNKNOWN,
        )
        assert outcome.failed_field_index == 1
        assert outcome.post_acquisition is not None
        assert outcome.post_acquisition.status.value == "cancelled"

    asyncio.run(scenario())


def test_set_form_fields_propagates_final_capture_cancellation_with_receipts() -> None:
    async def scenario() -> None:
        adapter = FormFieldsAdapter("dom", cancel_post_capture=True)
        environment = UnifiedWorldEnvironment((adapter,))
        task = TaskGoal(
            "form-capture-cancel",
            "Set both route endpoints",
            allowed_effects=("value_changed",),
            risk_profile=RiskProfile.LOW,
        )
        initial = await environment.reset(task)
        assert initial.observation is not None
        world = initial.observation
        builder = ActionSpaceBuilder()
        options = sorted(builder.build(task, world).options, key=lambda item: item.target_id)
        requests = tuple(
            ActionBinder().bind_for_execution(
                builder.admit(option, {"text": value}),
                world,
                "context:form-capture-cancel",
                task,
            )
            for option, value in zip(options, ("CMU", "PIT"), strict=True)
        )
        command = ActionBinder().seal_form_fields("form:route", requests)

        with pytest.raises(FormFieldsExecutionCancelled) as cancelled:
            await environment.execute_form_fields(command)

        outcome = cancelled.value.outcome
        assert len(outcome.results) == 2
        assert all(item.dispatch_status is DispatchStatus.SENT for item in outcome.results)
        assert outcome.failed_field_index is None
        assert outcome.post_acquisition is not None
        assert outcome.post_acquisition.status.value == "cancelled"

    asyncio.run(scenario())
