# Target Runtime entrypoints

Status: current product entrypoint reference; `target-run` is explicit and is not yet
the default `run` command.

## Python API

Product callers compose once and retain the typed client/session lifecycle:

```python
from affordance_runtime import (
    NaturalLanguageTaskRequest,
    RiskProfile,
    TargetRuntimeClient,
    TaskBoundary,
    compose_target_client_from_environment,
)

client: TargetRuntimeClient = compose_target_client_from_environment()
request = NaturalLanguageTaskRequest(
    "task:save",
    "Save the current form",
    TaskBoundary(
        allowed_effects=("form_saved",),
        risk_profile=RiskProfile.LOW,
        success_criteria=({
            "id": "saved",
            "kind": "fact_equals",
            "predicate": "saved",
            "expected_value": True,
        },),
    ),
)
```

`TargetRuntimeClient.run` performs intake, creates one `AgentRunSession`, and runs
until terminal status or a typed user/confirmation pause. Long-lived callers keep the
session and use `submit_user_input` or `resolve_confirmation`; the CLI is intentionally
one-shot and only projects a pending request.

## Explicit target CLI

Create a stable boundary file. It may describe task meaning, risk, effects, inputs,
completion criteria, outputs, material bindings, and loop budget. It may not contain
selectors, coordinates, action IDs, bindings, executors, or other current-GUI routes.

```json
{
  "allowed_effects": ["shared_state_enabled"],
  "risk_profile": "low",
  "success_criteria": [
    {
      "id": "shared-enabled",
      "kind": "fact_equals",
      "predicate": "expanded",
      "expected_value": true
    }
  ],
  "loop_budget": {"max_turns": 8, "max_observations": 16}
}
```

Run the configured model through the target path:

```bash
affordance-runtime target-run \
  --target http://127.0.0.1:3000/settings \
  --instruction "Enable shared state" \
  --request-id task:enable-shared \
  --boundary boundary.json
```

The product target protocol is explicitly `grounded_tools.v2`. The model selects a
public action tool/action ID from the current `AgentContext`; Runtime alone resolves
the internal binding and executor route. Composition requires select-action,
observation-request, and action-page controls before browser allocation.

Execution order is:

```text
boundary JSON
→ NaturalLanguageTaskRequest
→ ThinTaskIntake
→ ReadyTask
→ ThreadBoundBrowserSession
→ DomSurfaceAdapter / UnifiedWorldEnvironment
→ TargetRuntimeClient / AgentLoop
→ grounded model action selection
→ Runtime bind + execute
→ ProductionActionEvaluator / ProductionTaskEvaluator
→ typed result or pause
```

Non-ready intake exits before browser launch. Exit status is zero only for `done`;
blocked, failed, rejected, unsupported, and one-shot pause outcomes return non-zero
with typed status/reason fields.

## Legacy compatibility

`affordance-runtime run` and `RuntimeClient` still use the staged Coordinator path.
The latter is also exported as `LegacyRuntimeClient`. They remain feature-frozen until
reference-scenario consumers are retargeted, a predeclared target-default held-out
multi-seed gate passes, and a fresh topology review confirms that API, CLI, and current
benchmark share the product composition owner.
