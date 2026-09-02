"""把自然语言任务请求转换为系统内部权威的 TaskGoal。

这个模块只负责“任务入口”的类型和权限校验：
- 不理解或改写用户的自然语言意图；
- 不观察 GUI；
- 不制定执行计划；
- 不执行任何动作。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Protocol, TypeAlias

from affordance_runtime.immutable import freeze_json
from affordance_runtime.task.contracts import (
    EvaluationSpec,
    LoopBudget,
    MaterialBinding,
    RiskProfile,
    TaskGoal,
)
from affordance_runtime.task.intent_context import IntentContext


class TaskIntakeStatus(StrEnum):
    """任务进入 Runtime 前可能出现的四种状态。"""

    # 请求合法且信息完整，已经生成 TaskGoal。
    READY = "ready"
    # 缺少必须由用户明确提供的信息，不能自行猜测。
    NEEDS_USER_INPUT = "needs_user_input"
    # 请求中的权限声明互相冲突，因策略原因拒绝。
    POLICY_REJECTED = "policy_rejected"
    # 输入无法构造成合法的 TaskGoal，当前合同不支持。
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class TaskBoundary:
    """由调用方明确声明的稳定任务边界，不描述当前 GUI 的结构。"""

    # 执行任务时始终需要遵守的约束。
    constraints: tuple[str, ...] = ()
    # 允许任务产生的语义副作用，例如发送、删除、购买。
    allowed_effects: tuple[str, ...] = ()
    # 明确禁止产生的语义副作用。
    forbidden_effects: tuple[str, ...] = ()
    # 调用方已经提供的结构化输入。
    inputs: Mapping[str, Any] = field(default_factory=dict)
    # 用于判断任务是否成功的结构化条件。
    success_criteria: tuple[Mapping[str, Any], ...] = ()
    # 用户要求返回或生成的输出。
    requested_outputs: tuple[str, ...] = ()
    # 默认按只读任务处理；非只读任务必须明确声明 allowed_effects。
    risk_profile: RiskProfile = RiskProfile.READ_ONLY
    # 对文件、账号或其他外部材料的显式绑定。
    material_bindings: tuple[MaterialBinding, ...] = ()
    # 对循环步数、时间或资源消耗的限制。
    loop_budget: LoopBudget = field(default_factory=LoopBudget)
    # 可选的任务评估方式。
    evaluation_spec: EvaluationSpec | None = None

    def __post_init__(self) -> None:
        # 将这些字段统一转换成 tuple，并拒绝空白项和重复项。
        for name in ("constraints", "allowed_effects", "forbidden_effects", "requested_outputs"):
            values = tuple(getattr(self, name))
            if any(not value.strip() for value in values) or len(values) != len(set(values)):
                raise ValueError(f"task boundary {name} must be nonblank and unique")
            object.__setattr__(self, name, values)

        # 要求关键合同对象使用明确类型，避免传入随意的字符串或字典。
        if not isinstance(self.risk_profile, RiskProfile):
            raise TypeError("task boundary risk profile must be typed")
        if not isinstance(self.loop_budget, LoopBudget):
            raise TypeError("task boundary loop budget must be typed")
        if self.evaluation_spec is not None and not isinstance(self.evaluation_spec, EvaluationSpec):
            raise TypeError("task boundary evaluation spec must be typed")

        # 冻结 JSON 数据，防止 TaskBoundary 创建后被外部代码修改。
        object.__setattr__(self, "inputs", freeze_json(self.inputs))
        object.__setattr__(
            self,
            "success_criteria",
            tuple(freeze_json(item) for item in self.success_criteria),
        )
        object.__setattr__(self, "material_bindings", tuple(self.material_bindings))


@dataclass(frozen=True)
class NaturalLanguageTaskRequest:
    """一条自然语言指令，以及调用方明确提供的稳定权限边界。"""

    # 请求的唯一标识。
    request_id: str
    # 用户的原始自然语言指令。
    instruction: str
    # 权限、约束、成功条件和资源预算等稳定边界。
    boundary: TaskBoundary = field(default_factory=TaskBoundary)
    # 可选的意图上下文；这里只携带，不在这里解释。
    intent_context: IntentContext | None = None
    # 可选的请求来源引用。
    source_ref: str = ""
    # 同一任务的修订版本，从 1 开始。
    revision: int = 1

    def __post_init__(self) -> None:
        # 一个有效请求必须同时具备 ID 和非空指令。
        if not self.request_id.strip() or not self.instruction.strip():
            raise ValueError("natural-language task request requires identity and instruction")
        if type(self.revision) is not int or self.revision < 1:
            raise ValueError("natural-language task request revision must be a positive integer")
        if not isinstance(self.boundary, TaskBoundary):
            raise TypeError("natural-language task request requires a typed boundary")
        if self.intent_context is not None and not isinstance(self.intent_context, IntentContext):
            raise TypeError("natural-language task request intent context must be typed")
        if self.source_ref and not self.source_ref.strip():
            raise ValueError("task source reference cannot be blank")


@dataclass(frozen=True)
class ReadyTask:
    """入口校验成功，task 是接下来唯一权威的任务目标。"""

    request_id: str
    task: TaskGoal
    intent_context: IntentContext | None = None
    source_ref: str = ""
    status: TaskIntakeStatus = field(default=TaskIntakeStatus.READY, init=False)


@dataclass(frozen=True)
class TaskInputRequired:
    """缺少只能由用户提供的信息，并说明要问什么、缺哪些字段。"""

    request_id: str
    question: str
    requested_fields: tuple[str, ...]
    reason_code: str
    status: TaskIntakeStatus = field(default=TaskIntakeStatus.NEEDS_USER_INPUT, init=False)


@dataclass(frozen=True)
class TaskPolicyRejected:
    """任务边界违反权限或风险策略。"""

    request_id: str
    reason_code: str
    status: TaskIntakeStatus = field(default=TaskIntakeStatus.POLICY_REJECTED, init=False)


@dataclass(frozen=True)
class TaskUnsupported:
    """请求无法满足当前 TaskGoal 合同。"""

    request_id: str
    reason_code: str
    status: TaskIntakeStatus = field(default=TaskIntakeStatus.UNSUPPORTED, init=False)


# compile() 的调用方必须处理这四种结果，而不能假定一定成功。
TaskIntakeOutcome: TypeAlias = ReadyTask | TaskInputRequired | TaskPolicyRejected | TaskUnsupported


class TaskIntake(Protocol):
    """任务入口实现需要遵守的接口。"""

    def compile(self, request: NaturalLanguageTaskRequest) -> TaskIntakeOutcome: ...


@dataclass(frozen=True)
class ThinTaskIntake:
    """接纳稳定的任务含义，但不规划，也不提前猜测 GUI 元素身份。"""

    def compile(self, request: NaturalLanguageTaskRequest) -> TaskIntakeOutcome:
        # 入口只接受经过类型化的自然语言任务请求。
        if not isinstance(request, NaturalLanguageTaskRequest):
            raise TypeError("thin intake requires a NaturalLanguageTaskRequest")
        boundary = request.boundary
        allowed = frozenset(boundary.allowed_effects)
        forbidden = frozenset(boundary.forbidden_effects)

        # 同一种副作用不能既允许又禁止，否则权限合同自相矛盾。
        if allowed.intersection(forbidden):
            return TaskPolicyRejected(request.request_id, "allowed_forbidden_effect_conflict")

        # 只读任务不应该允许任何会改变外部状态的副作用。
        if boundary.risk_profile is RiskProfile.READ_ONLY and allowed:
            return TaskPolicyRejected(request.request_id, "read_only_effect_conflict")

        # 非只读任务必须明确列出允许的副作用；Runtime 不替用户猜权限。
        if boundary.risk_profile is not RiskProfile.READ_ONLY and not allowed:
            return TaskInputRequired(
                request.request_id,
                "Which semantic effects may this task perform?",
                ("allowed_effects",),
                "effect_authority_required",
            )

        # 权限和必要信息通过校验后，把入口数据原样装配成 TaskGoal。
        try:
            task = TaskGoal(
                request.request_id,
                request.instruction,
                constraints=boundary.constraints,
                allowed_effects=boundary.allowed_effects,
                forbidden_effects=boundary.forbidden_effects,
                inputs=dict(boundary.inputs),
                success_criteria=tuple(dict(item) for item in boundary.success_criteria),
                requested_outputs=boundary.requested_outputs,
                risk_profile=boundary.risk_profile,
                material_bindings=boundary.material_bindings,
                loop_budget=boundary.loop_budget,
                evaluation_spec=boundary.evaluation_spec,
                revision=request.revision,
            )
        # TaskGoal 还有自己的合同校验；失败时返回 typed outcome，
        # 不让一个不合法的任务进入后续执行循环。
        except (TypeError, ValueError):
            return TaskUnsupported(request.request_id, "task_goal_contract_invalid")

        # 成功结果携带 TaskGoal，以及原请求附带的上下文和来源。
        return ReadyTask(request.request_id, task, request.intent_context, request.source_ref)
