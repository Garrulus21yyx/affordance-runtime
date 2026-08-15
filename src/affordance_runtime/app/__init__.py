"""Product façade, composition, and command entrypoint."""

from affordance_runtime.app.composition import (
    compose_target_runtime,
    compose_target_runtime_from_environment,
)
from affordance_runtime.app.runtime import (
    TargetRuntime,
    TargetRuntimeRunOutcome,
    TargetRuntimeStartOutcome,
    TargetRuntimeUserInputOutcome,
)

__all__ = [
    "TargetRuntime",
    "TargetRuntimeRunOutcome",
    "TargetRuntimeStartOutcome",
    "TargetRuntimeUserInputOutcome",
    "compose_target_runtime",
    "compose_target_runtime_from_environment",
]
