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

## Add a local deterministic tool

Add one entry to the existing per-turn catalog. The entry must pair its current `ToolSpec` with one private binding
that implements the same `resolve` contract as every other tool. Its handler may compute only from the current public
snapshot captured by that binding and must return a generic local tool result. Do not add the tool name, arguments, or
semantics to `CoreAgentLoop`, `RunState`, context projection, instrumentation, or a second executor/registry.

## Add or extend goal planning

The production planning contract has three owners:

- `GoalCompiler` owns open-ended task interpretation and proposes a typed, immutable semantic skeleton;
- `GoalPlanBoundary` owns bounded five-field/DAG validation, task revision, version, and digest;
- `ActionPolicy` owns the current interpretation of each plan item against fresh `WorldObservation`.

`TaskGoal` remains user-intent authority and `TaskEvaluator`/native verifier remains completion authority. A plan may
not decide `RunStatus`, legal actions, risk, confirmation, effect, or completion. Compiler `Failed` and `Unsupported`
outcomes preserve the ordinary ActionPolicy turn.

Each item contains only `id`, `objective`, `done_when`, `depends_on`, and `final`. Add no entity filter, relation,
predicate, World path, selector, coordinate, current ref, GUI step, item status, or helper-node ID. Unknown descriptive
provider fields are ignored; required fields, bounds, dependency existence/acyclicity, and the single-final invariant
are validated. The only phase-one compile triggers are task start and user revision.

A new planning field requires evidence that the existing semantic text and dependency DAG cannot express a shared
held-out failure. It must not duplicate current World facts, recent steps, action effects, bindings, or formal task
evaluation. Required tests cover malformed shapes, text/item bounds, surplus-field tolerance, DAG properties, revision
invalidation, advisory failure, and direct context projection.

## Add a model provider

Prefer a PydanticAI `Model` and `Provider`. OpenAI-compatible services should configure `OpenAIChatModel` with an
`OpenAIProvider`; do not add another project-owned HTTP client, response envelope, retry orchestrator, or general model
port. The current semantic catalog is supplied as an `ExternalToolset`, and its deferred call is returned to Runtime
with the provider `call_id` intact. Runtime then performs currentness, binding, risk, execution, and final validation.

Only add a narrow compatibility adapter when a required model has live evidence that it cannot emit native tool
calls. That adapter may translate one compact JSON decision into the same current semantic call, but it must not
become another provider framework or duplicate the Runtime loop. `LLM_MODEL_ADAPTER=pydantic-ai` selects native tool
transport; `LLM_MODEL_ADAPTER=compact-json` selects the bounded compatibility path currently required by
`glm-4.1v-thinking-flashx`.

Do not create a provider-specific system prompt. Every provider receives the one stable prompt in Architecture; only
wire encoding, image representation, strict-schema support, and tool-call transport vary. Native-tool providers receive
the current catalog through their tools field. Compact-JSON providers may receive the same catalog in context, but it
must not be duplicated for native providers.

Required tests cover dynamic schema generation, `call_id` preservation, unsupported tools, timeout/error
normalization, bounded repair, secret-free logging, and one real provider witness through `CoreAgentLoop`.

## Change the model prompt or context

The stable prompt defines role, authority, rolling decision policy, and the Runtime boundary. Tool parameter rules
belong to `ToolSpec`; current facts belong to context; repair instructions belong to the matching result.

The public context has one Task, one Current Observation, one Current Goal Plan, at most eight nested action/result
`StepView` records, and Current Tools. A Ready plan is an immutable semantic skeleton, not a computed progress view.
ActionPolicy interprets it against the fresh observation every turn. A context change must remove or replace an
existing field rather than add another projection of the same fact. Budgets, backend data, old worlds, benchmark data,
telemetry, provider transcripts, item statuses, and frontiers are forbidden.

`WorldObservation` is Runtime authority, `ActorWorldSnapshot` is the policy's only current-world projection, and
`GroundedPolicyContextBinder` is the only provider-message assembler. Required tests snapshot the complete public
shape, prove fresh observation precedence, verify action/result pairing and truncation, and reject private leakage.

## Add a model-backed cognitive role

A cognitive role such as goal compilation, visual grounding, or a future open-world semantic judge may reuse the configured
provider and model, but it is not another `CoreAgentLoop`. Give the role:

- one typed request and response;
- one narrow prompt owned by the semantic role rather than the provider;
- one explicit invocation trigger and budget;
- one typed unavailable/unknown/needs-input outcome;
- one provider-boundary transcript with its semantic phase.

Do not reuse the action-policy response schema, invent a second general model API, or let provider transport decide
when the role runs. A model-backed verifier is appropriate only for a genuinely open-world judgment that deterministic
facts cannot close. It must return typed evidence or a proposal to its owning boundary; it may not become the final
task-completion authority or hide inside task evaluation.

Use one role call at task start/revision for the phase-one goal compiler; `NotRequired` is an explicit result. A task
revision invalidates old goal state before the call. There is no automatic phase-one recompile trigger. Compiler
failure is traced as unavailable guidance and does not fail/block the run. Per-step Manager,
Worker, planner, evaluator, and summarizer calls require separate benchmark evidence and are not the default design.

The compiler proposes outcome descriptions and dependencies, not website trajectory or current progress. The existing
ActionPolicy owns rolling interpretation and tactical planning: on every turn it consumes fresh World, the static
GoalPlan, recent steps, and current tools, then emits one action or evidence request. No separate evaluator computes or
patches item state.

Do not route generic failure, repetition, elapsed steps, or long-horizon classification to a visual role. Visual
admission requires a typed epistemic gap that a current visual source offers: irreducibly visual facts, explicit
target disambiguation, structural truncation, or a postcondition that structural evidence cannot close. Under an
adaptive profile, image delivery must carry exact current acquisition lineage; a recent summary saying that an
observation was acquired is insufficient. Visual results enter only through a SurfaceAdapter and WorldFusion.

## Add an evaluator

Action evaluation receives the task, before-world, bound request, dispatch result, and fresh after-world. It returns a
typed local-effect outcome with evidence references. Task evaluation receives formal criteria/requested outputs,
fresh `WorldObservation`, and any native verifier receipt; it alone returns task completion status. Runtime/provider
failure remains a separate typed path.

Do not add a GoalPlan progress evaluator. ActionPolicy makes the open-world working judgment each turn, while
`ActionEffect` proves only a local UI transition and TaskEvaluator/native verifier owns completion. An optional future
model-backed semantic judge requires a named benchmark gap, a separate typed port and explicit consumer; it cannot
execute actions, acquire sources, mutate RunState, compile goals, or become completion authority.

## Add a benchmark

Keep benchmark code outside product semantics. A benchmark adapter may translate task inputs and official terminal
results, but it may not expose task IDs, rewards, reference actions, hidden state, or expected answers to the model.

Predeclare the cohort, seed, model, budget, and comparison before the run. Persist raw per-case results before
aggregation. Report task success separately from infrastructure and provider failures.

## Review checklist

- Does the change have exactly one semantic owner?
- Are authoritative inputs distinguished from cached or model-visible projections?
- Does it reuse the unified world and semantic action protocol?
- Does an action extension reuse `SelectAction -> BoundActionRequest` rather than add another intent owner?
- Can unsupported input fail with a typed reason?
- Is private routing absent from model-visible values?
- Does it avoid benchmark-specific production logic?
- Is semantic decomposition owned by the compiler while per-step tactical planning remains in the one action policy?
- Does any VLM call correspond to a typed visual evidence gap rather than generic no-progress or trajectory length?
- If it calls a model, is the cognitive role, trigger, typed contract, and failure outcome explicit?
- Does a context-enrichment failure remain context-unavailable instead of becoming a run failure or action ban?
- If it adds memory, is there evidence that the required fact cannot be recovered from current authority?
- Does deterministic evaluation remain reproducible without a model call?
- Can its value be measured in a live benchmark?
