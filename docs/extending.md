# Extending

Extensions attach to an existing owner. `CoreAgentLoop` is the only run-control engine; extensions must not add
another loop, world, action authority, compatibility facade, or benchmark oracle.

## Add a source adapter

Implement the existing `SurfaceAdapter` contract:

1. declare stable observation offers with modality, assurance, purposes, and cost;
2. initialize task-relative projection without parsing benchmark IDs;
3. acquire a normalized source observation;
4. expose private bindings only to Runtime;
5. return typed unavailable, failed, or acquired results;
6. implement currentness and execution only for routes the adapter owns.

Register the adapter with `UnifiedWorldEnvironment`. Do not modify the agent loop. Source choice belongs to
`ObservationOrchestrator`; cross-source alignment belongs to `WorldFusion`.

Code entry points: `world/surface_adapter.py` defines the port; `world/orchestrator.py` composes adapter instances;
`surfaces/` contains concrete examples. Registration is explicit construction of
`UnifiedWorldEnvironment((adapter_a, adapter_b, ...))`, not a global plugin registry.

Required tests:

- adapter contract and normalization;
- stale and unsupported behavior;
- private binding non-disclosure;
- fusion with at least one existing source;
- one real or faithful integration witness.

## Add a semantic action

Extend the shared interaction-capability contract rather than branching on task text or page identity:

1. define the semantic verb, subject type, parameters, effect class, and verification family;
2. project the action only when the current world supports it;
3. validate it through normal admission;
4. resolve a current private `ActionBinding` in the owning adapter;
5. execute once and acquire a fresh post-action observation;
6. verify the expected effect through generic evidence.

An action implementation may not depend on a benchmark case, fixed selector, known label, action ID, or task order.
Adding an action should not require edits to core run control.

Code entry points: `actions/capabilities.py` owns the closed `InteractionCapabilityRegistry` and verification families;
an adapter publishes matching `ActionBinding` values in its normalized observation; `actions/action_space.py` projects
and admits model-visible actions; `actions/binder.py` resolves the selected current binding. A new semantic verb changes
the capability registry and its owning adapters, not `CoreAgentLoop`.

## Add a model provider

Implement the existing provider-neutral `ModelPort` and serialize the public context into provider messages and tool
schemas. Preserve provider `call_id` values through the typed call/result boundary. Use strict tool schemas when the
provider supports them, then retain Runtime validation as the provider-independent authority. Normalize provider
errors and timeouts at the provider boundary. The provider may choose one current semantic tool; it cannot select
private observation routes or execution bindings.

The composition chain is `model/providers/port.py: ModelPort` → a structured adapter under `model/policy/` →
`ModelBackedAgentPolicy` → `AgentDecisionPorts` in `app/composition.py`. Capability declarations belong to the policy
adapter; `TargetRuntime` validates required decisions at composition time.

Do not create a provider-specific system prompt. Every provider receives the one stable prompt in Architecture; only
wire encoding, image representation, strict-schema support, and tool-call transport vary. Native-tool providers receive
the current catalog through their tools field. Compact-JSON providers may receive the same catalog in context, but it
must not be duplicated for native providers.

Required tests cover schema generation, `call_id` preservation, response parsing, unsupported tools, timeout/error
normalization, bounded repair, and secret-free logging.

## Change the model prompt or context

The stable prompt defines role, authority, decision policy, progress, and the Runtime boundary. Tool-specific parameter
rules belong to `ToolSpec`; current facts belong to context; repair instructions belong to the matching tool result.
Do not copy these into the system prompt.

The public context has one task, one current observation, one verified progress view, and at most eight nested
action/result `StepView` records. A context change must remove or replace an existing field rather than add another
projection of the same fact. Budget counters, backend data, old worlds, benchmark data, and telemetry are forbidden.

Required tests snapshot the complete public shape, prove that current observation overrides history, verify mechanical
action/result pairing and truncation, and reject private-field leakage.

## Add an evaluator

Action evaluation receives the task, before-world, bound request, dispatch result, and fresh after-world. It returns
`effect_confirmed`, `no_effect_confirmed`, `unknown`, or `rejected` with evidence references. Task evaluation receives
the current world and returns complete, incomplete, unknown, or blocked.

Evaluators interpret evidence; they do not execute actions, acquire sources, or mutate `RunState`.

## Add a benchmark

Keep benchmark code outside product semantics. A benchmark adapter may translate task inputs and official terminal
results, but it may not expose task IDs, rewards, reference actions, hidden state, or expected answers to the model.

Predeclare the cohort, seed, model, budget, and comparison before the run. Persist raw per-case results before
aggregation. Report task success separately from infrastructure and provider failures.

## Review checklist

- Does the change have exactly one semantic owner?
- Does it reuse the unified world and semantic action protocol?
- Can unsupported input fail with a typed reason?
- Is private routing absent from model-visible values?
- Does it avoid benchmark-specific production logic?
- Can its value be measured in a live benchmark?
