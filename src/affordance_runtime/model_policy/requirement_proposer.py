"""Optional model-backed producer of non-authoritative requirement hypotheses."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from dataclasses import dataclass, field
from time import monotonic
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from affordance_runtime.immutable import to_json_compatible
from affordance_runtime.model_boundary.budgets import ContextProjectionBudget
from affordance_runtime.model_boundary.world_projection import project_model_world
from affordance_runtime.model_policy.model_port_bridge import DecisionPerceptionProfile
from affordance_runtime.model_policy.provider_orchestrator import ProviderCallPolicy
from affordance_runtime.model_policy.spec import (
    FactAvailablePayload,
    FactReferenceExpectedPayload,
    LiteralExpectedPayload,
    PredicatePayload,
    TargetAbsentPayload,
    TargetFieldEqualsPayload,
    TargetPresentPayload,
    TaskOutcomeIsPayload,
)
from affordance_runtime.model_port import (
    ModelConfig,
    ModelImageURLPart,
    ModelMessage,
    ModelPort,
    ModelTextPart,
    ProviderFailureKind,
    ProviderModelError,
    StructuredModelError,
    StructuredOutputError,
)
from affordance_runtime.task.contracts import TaskGoal
from affordance_runtime.task.frontier_contracts import (
    FactAvailable,
    FactReferenceExpected,
    LiteralExpected,
    TargetAbsent,
    TargetFieldEquals,
    TargetPresent,
    TaskOutcomeIs,
    TaskOutcomeStatus,
)
from affordance_runtime.task.hypothesis_contracts import (
    HypothesisItemRejection,
    HypothesisProposalMode,
    HypothesisRejectionCode,
    RequirementHypothesisFailure,
    RequirementHypothesisFailureKind,
    RequirementHypothesisProposal,
    RequirementHypothesisProposalBatch,
)
from affordance_runtime.world.contracts import ActionSpace, WorldObservation

_Summary = Annotated[str, StringConstraints(min_length=1, max_length=240)]
_EntityId = Annotated[str, StringConstraints(min_length=1, max_length=240)]

_SYSTEM_PROMPT = """
Propose a small set of local requirement hypotheses that may help advance the public GUI task.
Hypotheses are non-authoritative and never prove task necessity, set completeness, action legality, or terminal success.
Use only candidate entity IDs present in the supplied public context and only the closed predicate schema.
Do not emit selectors, coordinates, credentials, hidden reasoning, or benchmark answers.
The hypothesis set completeness must always be unknown.
""".strip()


class RequirementHypothesisPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    summary: _Summary
    predicate: PredicatePayload
    candidate_entity_ids: Annotated[list[_EntityId], Field(max_length=8)]


class RequirementHypothesisBatchPayload(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)

    hypotheses: Annotated[list[RequirementHypothesisPayload], Field(max_length=8)]
    hypothesis_set_completeness: Literal["unknown"]


@dataclass(frozen=True)
class ModelRequirementHypothesisProposer:
    port: ModelPort
    config: ModelConfig
    perception_profile: DecisionPerceptionProfile = DecisionPerceptionProfile.TEXT_ONLY
    budget: ContextProjectionBudget = ContextProjectionBudget()
    provider_policy: ProviderCallPolicy = ProviderCallPolicy()
    last_attempt_count: int = field(default=0, init=False, compare=False)
    last_schema_repair_count: int = field(default=0, init=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "perception_profile",
            DecisionPerceptionProfile(self.perception_profile),
        )

    async def propose(
        self,
        task: TaskGoal,
        observation: WorldObservation,
        action_space: ActionSpace,
        *,
        mode: HypothesisProposalMode,
        observation_cursor: str = "",
    ) -> RequirementHypothesisProposalBatch | RequirementHypothesisFailure:
        try:
            messages = self._messages(
                task,
                observation,
                action_space,
                mode,
                observation_cursor,
            )
            output = await self._generate_with_recovery(
                messages,
                RequirementHypothesisBatchPayload,
                self.config,
            )
            proposals = []
            proposal_item_indices = []
            rejections = []
            for item_index, item in enumerate(output.hypotheses):
                try:
                    predicate = _predicate(item.predicate)
                except (TypeError, ValueError):
                    rejections.append(
                        HypothesisItemRejection(
                            item_index,
                            HypothesisRejectionCode.INVALID_PREDICATE_CONTRACT,
                        )
                    )
                    continue
                try:
                    proposal = RequirementHypothesisProposal(
                        item.summary,
                        predicate,
                        tuple(item.candidate_entity_ids),
                    )
                except (TypeError, ValueError):
                    rejections.append(
                        HypothesisItemRejection(
                            item_index,
                            HypothesisRejectionCode.INVALID_PROPOSAL_CONTRACT,
                        )
                    )
                    continue
                proposals.append(proposal)
                proposal_item_indices.append(item_index)
            return RequirementHypothesisProposalBatch(
                mode,
                tuple(proposals),
                tuple(proposal_item_indices),
                tuple(rejections),
            )
        except ProviderModelError:
            return RequirementHypothesisFailure(
                RequirementHypothesisFailureKind.PROVIDER_UNAVAILABLE,
                "requirement_hypothesis_provider_unavailable",
            )
        except StructuredModelError:
            return RequirementHypothesisFailure(
                RequirementHypothesisFailureKind.INVALID_RESPONSE,
                "requirement_hypothesis_invalid_response",
            )
        except (TypeError, ValueError, json.JSONDecodeError):
            return RequirementHypothesisFailure(
                RequirementHypothesisFailureKind.INTERNAL_ERROR,
                "requirement_hypothesis_projection_failed",
            )

    async def _generate_with_recovery(self, messages, output_schema, config):
        object.__setattr__(self, "last_attempt_count", 0)
        object.__setattr__(self, "last_schema_repair_count", 0)
        started = monotonic()
        active_messages = messages
        schema_repair_used = False
        for attempt in range(self.provider_policy.max_attempts_per_profile):
            remaining = self.provider_policy.total_elapsed_deadline_s - (monotonic() - started)
            if remaining <= 0:
                raise ProviderModelError(ProviderFailureKind.PROVIDER_CAPACITY)
            object.__setattr__(self, "last_attempt_count", attempt + 1)
            try:
                return await asyncio.wait_for(
                    self.port.generate_structured(active_messages, output_schema, config),
                    timeout=remaining,
                )
            except asyncio.CancelledError:
                raise
            except StructuredOutputError:
                if schema_repair_used or attempt + 1 >= self.provider_policy.max_attempts_per_profile:
                    raise
                schema_repair_used = True
                object.__setattr__(self, "last_schema_repair_count", 1)
                active_messages = _schema_repair_messages(messages)
                continue
            except TimeoutError:
                failure = ProviderModelError(
                    ProviderFailureKind.PROVIDER_CAPACITY,
                )
            except ProviderModelError as exc:
                failure = exc
            retryable = failure.kind in {
                ProviderFailureKind.RATE_LIMIT_TRANSIENT,
                ProviderFailureKind.PROVIDER_CAPACITY,
            }
            if not retryable or attempt + 1 >= self.provider_policy.max_attempts_per_profile:
                raise failure
            delay = self._retry_delay(attempt, failure, messages)
            remaining = self.provider_policy.total_elapsed_deadline_s - (monotonic() - started)
            if delay >= remaining:
                raise failure
            if delay:
                await asyncio.sleep(delay)
        raise AssertionError("bounded provider loop exhausted without an outcome")

    def _retry_delay(self, attempt, failure, messages) -> float:
        if failure.retry_after_s is not None:
            return min(self.provider_policy.max_delay_s, failure.retry_after_s)
        base = self.provider_policy.backoff_s[attempt]
        digest = hashlib.sha256(f"requirement-hypothesis:{attempt}:{messages[-1].content!s}".encode()).digest()
        unit = int.from_bytes(digest[:2], "big") / 65_535
        factor = 1 + (unit * 2 - 1) * self.provider_policy.jitter_ratio
        return min(self.provider_policy.max_delay_s, round(base * factor, 3))

    def _messages(
        self,
        task: TaskGoal,
        observation: WorldObservation,
        action_space: ActionSpace,
        mode: HypothesisProposalMode,
        observation_cursor: str,
    ) -> tuple[ModelMessage, ...]:
        action_targets = tuple(dict.fromkeys(item.target_id for item in action_space.options))
        world = project_model_world(
            observation,
            self.budget,
            pinned_target_ids=action_targets[: self.budget.observation_pinned_capacity],
            observation_cursor=observation_cursor,
        )
        payload = {
            "proposal_mode": mode.value,
            "task_instruction": task.instruction,
            "world": to_json_compatible(world),
            "current_actions": [
                {
                    "action_id": item.action_id,
                    "semantic_action": item.semantic_action,
                    "target_id": item.target_id,
                }
                for item in action_space.options[: self.budget.max_action_options]
            ],
            "authority": {
                "hypotheses_are_task_requirements": False,
                "hypotheses_create_actions": False,
                "hypothesis_set_completeness": "unknown",
            },
        }
        text = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        content: str | tuple[ModelTextPart | ModelImageURLPart, ...] = text
        if self.perception_profile is DecisionPerceptionProfile.SCREENSHOT_AX:
            media = next(
                (
                    item
                    for source in reversed(observation.sources)
                    for item in reversed(source.media)
                    if item.kind == "screenshot"
                ),
                None,
            )
            if media is not None:
                encoded = base64.b64encode(media.data).decode()
                content = (
                    ModelTextPart(text=text),
                    ModelImageURLPart(image_url=f"data:{media.mime_type};base64,{encoded}"),
                )
        return (
            ModelMessage(role="system", content=_SYSTEM_PROMPT),
            ModelMessage(role="user", content=content),
        )


def _predicate(payload: PredicatePayload):
    if isinstance(payload, FactAvailablePayload):
        return FactAvailable(payload.fact_ref)
    if isinstance(payload, TargetPresentPayload):
        return TargetPresent(payload.target_id)
    if isinstance(payload, TargetAbsentPayload):
        return TargetAbsent(payload.target_id)
    if isinstance(payload, TaskOutcomeIsPayload):
        return TaskOutcomeIs(TaskOutcomeStatus(payload.status))
    assert isinstance(payload, TargetFieldEqualsPayload)
    expected = payload.expected
    projected = (
        FactReferenceExpected(expected.fact_ref)
        if isinstance(expected, FactReferenceExpectedPayload)
        else LiteralExpected(expected.value)
    )
    assert isinstance(expected, FactReferenceExpectedPayload | LiteralExpectedPayload)
    return TargetFieldEquals(payload.target_id, payload.field_name, projected)


def _schema_repair_messages(messages: tuple[ModelMessage, ...]) -> tuple[ModelMessage, ...]:
    repair_instruction = (
        "The previous response was rejected because it was not one complete valid JSON object. "
        "Do not repeat, quote, summarize, or explain the supplied task context. "
        "Return only an object with top-level keys hypotheses and "
        'hypothesis_set_completeness; hypothesis_set_completeness must be "unknown".'
    )
    system = messages[0]
    if system.role != "system" or not isinstance(system.content, str):
        raise ValueError("hypothesis repair requires one public text system instruction")
    repaired_system = ModelMessage(
        role="system",
        content=f"{system.content}\n\n{repair_instruction}",
    )
    return (repaired_system, *messages[1:])
