# Architecture

## Goal

Affordance Runtime is a small research runtime for a general GUI agent. It combines adaptive multi-source observation
with bounded task planning: expose one current semantic world, let a model propose a small semantic plan, and let the
single ActionPolicy interpret that plan against fresh evidence on every turn.

The design retains one project-owned GUI loop, one mutable `RunState`, one `StepResult` per turn, and one model-context
projection. It does not turn task structure into an authoritative workflow engine.

### Implementation status

Goal semantics is reopened after repeated Ready-path failures exposed an internally inconsistent model-facing
contract and two competing interpretations of progress. The production guidance path now uses a bounded five-field
`GoalPlan`, directly projected without symbolic lowering or a Runtime-owned progress snapshot. Compiler failure is
advisory, only user revision recompiles, and plan guidance never gates actions or termination. Implementation and local
gates are complete. A bounded compiler retry records both calls when a transient rate limit occurs. In the second
formal Like run, the compiler succeeded on its initial call and a Ready three-item plan reached every ActionPolicy
turn. The policy activated three different Like controls, then repeatedly reversed already-active Likes and exhausted
ten steps without Submit. Ready delivery is witnessed, but behavioral success and independent fresh-context review
remain required, so this work is explicitly non-closed.

## One loop

```text
observe selected sources -> fuse one current WorldObservation
  -> at task start/revision call GoalCompiler once
       Ready -> directly project immutable GoalPlan
       NotRequired / Failed / Unsupported -> ordinary loop with explicit absent/unavailable guidance
       NeedsInput -> existing waiting-user path for a missing user-owned task fact
  -> compile current ToolCatalog
  -> project Task + fresh World + GoalPlan + bounded recent steps + current tools
  -> ActionPolicy chooses exactly one offered tool
  -> validate, bind, and execute at most one GUI action
  -> acquire fresh World -> evaluate local effect and formal task completion
  -> update RunState or terminate
```

Compiler availability never decides run failure, action permission, or completion. Runtime does not maintain item
status, frontier, per-subject progress, a persistent world delta, or another control loop.

## Goal semantics target

### Reopened causal model

The former model contract allowed relation paths whose deterministic expansion could exceed the internal recursive
program depth. A schema-valid, semantically plausible response could therefore fail Runtime lowering, while harmless
surplus description fields could reject the entire proposal. More fundamentally, the derived symbolic snapshot and
ActionPolicy's open-world reading were competing interpretations of current progress. This is a contract and
acceptance-gate defect, not evidence that the configured model cannot produce useful semantic plans.

Strictness remains where Runtime owns truth: action admission, current binding, risk, confirmation, dispatch, effect
lineage, and formal completion. Model planning becomes a bounded advisory hint.

### Simple GoalPlan contract

Each model-facing item contains only:

```text
id | objective | done_when | depends_on | final
```

A Ready plan has 1..8 items, unique IDs, existing acyclic dependencies, bounded nonblank text, and at most one final
item. Unknown descriptive surplus is ignored. `GoalPlanBoundary` repeats mechanical validation and assigns task
revision, plan version, and digest. It does not inspect entity kinds, predicates, relations, selectors, World paths,
or current status and performs no lowering.

`GoalPlan` is not a mutable milestone list, workflow, binding, permission, completion proof, or progress state. There
is no Runtime-owned item status, frontier, per-subject result, or snapshot derived from World.

### Lifecycle and policy interpretation

At task start and each user revision, GoalCompiler is attempted once. No layout change, repetition, ambiguity, stall,
or provider failure causes automatic recompilation. ActionPolicy re-evaluates the static plan against fresh World on
every turn. Its prompt requires preservation of visibly satisfied toggles, advancement of the earliest dependency-ready
unsatisfied outcome, final-action deferral until prerequisites visibly hold, and exactly one action. These are reasoning
instructions, never action bans. `ActionEffect` proves only a local transition; TaskEvaluator/native verifier alone
owns formal completion.

### Trace and failure semantics

Every initial, schema-repair, and contract-repair provider attempt is captured before the next call can overwrite its
transcript. `goal_compiler_completed` later projects disposition/version, public reason/question fields, prompt/model
identity, initial observation lineage, and attempts. Compiler metrics remain separate from ActionPolicy metrics and
are retained by external-breadth evidence. Trace remains observational and never enters RunState or model context.

### Explicit non-goals

No Manager/Worker, per-step compiler, separate LLM progress evaluator, mutable todo, memory, RAG, achievement record,
ArgMin, VLM fallback, objective refs, second Binder, or second loop is added by this increment.

## SOTA alignment as of 2026-08-17

| Official source | Architecture signal | Decision here |
|---|---|---|
| [Agent S2 Manager prompt](https://github.com/simular-ai/Agent-S/blob/main/gui_agents/s2/memory/procedural_memory.py) and [Manager](https://github.com/simular-ai/Agent-S/blob/main/gui_agents/s2/agents/manager.py) | concise natural-language subtask nodes and DAG edges, not a world-query AST | use only a minimal semantic skeleton; do not adopt its hierarchy |
| [UI-TARS prompt](https://github.com/bytedance/UI-TARS/blob/main/codes/ui_tars/prompt.py) | task, screenshot, and history drive rolling thought/next action | keep progress interpretation inside ActionPolicy |
| [GUI-Owl source](https://github.com/X-PLUG/MobileAgent/blob/main/Mobile-Agent-v3/android_world_v3/android_world/agents/gui_owl.py) | goal, screenshot, and history drive the next JSON action/status | keep one rolling GUI loop and native verifier authority |

The inference for this no-training project is one ActionPolicy loop plus an optional start/revision semantic skeleton.
These sources are research architecture signals, not production-assurance or benchmark-parity claims.

## Runtime responsibilities

### WorldEnvironment

`WorldEnvironment` coordinates `SurfaceAdapter` instances, observation selection, acquisition, and fusion. DOM, AX,
visual, WoT, HTTP, BrowserGym, and later sources all enter through this boundary. An adapter owns source-specific
capture, private bindings, currentness, and execution routes; it does not choose task semantics or completion.

BrowserGym and Playwright are private execution backends, not model-visible tools. BrowserGym may use Playwright
internally while publishing the same public world and semantic-action protocol as any other adapter.

BrowserGym capture is one aligned source snapshot containing raw DOM, AXTree, rendering properties, and a screenshot.
Its SurfaceAdapter performs the source-local canonical fusion exactly once, keyed by BrowserGym's stable private BID:
AX role/name/state remain the higher-assurance accessible semantics, while bounded salient DOM attributes
(`class`, `id`, `name`, `type`, `role`, `title`, `alt`, `placeholder`, `aria-label`, and `aria-description`) remain parallel public evidence
under `semantic.dom.*` predicates. DOM evidence never overwrites an AX name and never becomes execution authority;
the BID itself and BrowserGym rendering attributes remain private. Missing accessible names are represented as
unknown rather than causing the DOM evidence or executable capability to disappear. Viewport visibility is a
presentation fact, not authority over the action inventory. A malformed DOMSnapshot or conflicting semantic evidence
for one BID fails with a typed adapter error instead of silently dropping that modality.

### SemanticActionRegistry

The semantic capability registry defines the stable action algebra: verb, supported subject kinds, public parameters,
effect class, destination semantics, and verification family. It contains reusable operations such as `activate`,
`type_text`, `select_option`, and `drag_to`, never selectors, coordinates, benchmark cases, or backend APIs.

BrowserGym publishes `drag_to(source, destination)` only when one current snapshot contains an executable draggable
source and a finite compatible endpoint domain. Both private endpoints are checked together immediately before one
official BrowserGym dispatch. Directional pointer gestures, text selection, and drawing gestures are not silently
treated as element-to-element drag; they remain unoffered until they have their own honest semantic contract.

### PerTurnToolCatalog

The per-turn catalog is the single model-visible Tool Registry. It compiles currently executable semantic actions,
local deterministic utilities such as `count_children`, and the closed control set `request_evidence`, `next_actions`,
`ask_user`, `wait`, and `abort`. `propose_done` is not published by the grounded product catalog and is not part of
the target control algebra. Each registered entry pairs one name, description, and strict input schema with one
opaque Runtime binding whose uniform `resolve` contract performs private binding or its local deterministic handler.
The semantic registry defines what a GUI action means; the per-turn registry defines what is callable now. Neither is
a backend plugin registry.

The public catalog has one stable tool name per semantic operation. Names come directly from
`SemanticActionRegistry` (`activate`, `type_text`, `select_option`, and so on); they never contain a digest, target
identity, selector, or snapshot-dependent suffix. A single-target action uses `target`, whose enum contains only the
current public entity references. A two-endpoint action uses `source` and `destination`. Runtime privately maps the
chosen operation and current reference tuple to one exact action binding. Refreshing or reordering the world may
change the enum values, but never the tool name or parameter shape.

Public references are opaque current-snapshot handles, not values the model derives or copies from hidden Runtime
state. Unknown, invalid, ambiguous, or stale references fail without dispatch and receive the exact current schema
for at most one repair. Hashes remain private integrity data and must never be model input.

Presence in the observation means only that a reference is available as evidence. A reference is actionable for one
operation only when that operation's current parameter schema lists it. The stable model instruction states this
rule, and each generated action-tool description repeats it next to the exact current enum; neither the world adapter
nor the execution adapter guesses actionability from a node's mere presence.

### Model and tool protocol

PydanticAI owns provider clients, provider messages, native tool-call parsing, call IDs, and basic schema repair. The
current `PerTurnToolCatalog` is exposed as a PydanticAI `ExternalToolset`, so a model proposes one deferred semantic
tool call but never executes Python or GUI code inside the framework. Runtime resolves that call against the opaque
current binding and remains the final validation authority.

The temporary `PydanticAIGroundedDecisionPort` reuses the existing policy seam during migration. It is not a second
permanent model abstraction. There is no global retry orchestrator: each provider adapter owns its explicit bounded
recovery so every physical call remains traceable. The PydanticAI action adapter disables SDK retries and reserves the
overall deadline for at most two transport attempts plus bounded `Retry-After`/exponential backoff. Provider categories
remain distinct in attempt evidence even though the public Agent failure is deliberately safe and compact. A watchdog
cancellation projects attempts already captured by the adapter before cancellation propagates. The remaining custom
HTTP and structured-response code is reduced to the bounded compact path plus historical conformance callers before
superseded pieces are removed. The compact exception currently applies to `glm-4.1v-thinking-flashx`, whose
OpenAI-compatible response envelope is not a standard chat-completion/tool-call response;
`LLM_MODEL_ADAPTER=compact-json` selects it.

Standard text models such as `glm-4.6` use the PydanticAI native-tool path. Provider cohort composition accepts either
grounded transport and derives identity from its owning adapter; the frozen same-model Mistral A/B path retains its
stricter compact-adapter identity gate. `LLM_GOAL_COMPILER_MODEL` applies independently in both branches so an action
model cohort does not silently change the compiler role.

The GLM-4.6 action role uses bounded single-step settings: thinking disabled, `max_tokens=512`, and
`temperature=0.0`. These are provider-call settings, not prompt advice. Every successful semantic call reports elapsed
attempt/repair/backoff time in `ModelMetadata`; a cancellation received during an active network call records a
`cancelled` attempt with elapsed latency before cancellation continues to the owning watchdog.

### CoreAgentLoop

`CoreAgentLoop` owns temporal order and termination. It never interprets page semantics, creates backend selectors,
implements a named tool such as counting, or accumulates another control history. It records a generic Registry-owned
local result, or for a dispatched GUI action performs at most one execution followed by a fresh observation, action
evaluation, and task evaluation. Runtime owns `max_steps` and stops at zero.

### RunState and StepResult

`RunState` is the only mutable run-control value. It contains the current world, current task evaluation, latest step,
terminal status, private counters, and at most eight public recent-step summaries. Counters and limits never enter the
model context.

`StepResult` is the complete fact for one turn: decision, optional local tool result or GUI execution, before/after
observation identities, action evaluation, task evaluation, and resulting status. A local result is stored once on
its resolved call and exposed through `StepResult`, not copied into a second state field. `StepResult` is not a log,
aggregate root, or reconstruction format.

### Complete trace without a second state

Observability consumes the existing model-turn result and `StepResult` at the two Core Loop boundaries. A local
append-only `trace.jsonl` stores the exact public `AgentContext`, current tool schemas, typed decision, provider
diagnostics, action/result/evaluation facts, and the complete call-ID/request-ID/observation-ID lineage. Each world
observation is written once; steps reference its identity, and binary media is content-addressed under `artifacts/`.
Every provider attempt is recorded at the provider boundary as an OpenInference-shaped LLM transcript containing its
input messages, exact current tool schema, output message or typed error, token usage, response ID, and semantic phase
(`initial`, `structured_output_repair`, `argument_repair`, or `tool_intent_repair`). Screenshot data URLs are replaced
by content-addressed artifacts. Trace data never enters `RunState` or `AgentContext` and cannot affect control.
Langfuse renders the same agent root, model-turn chain, LLM generations, and Runtime tool spans; it is an exporter,
not an authority, queue, transcript owner, or second loop. The separate private capture remains an optional isolated
copy for deployments that do not enable a local Runtime trace.

## Mechanical action/result identity

The accepted identity chain is:

```text
provider call_id
  -> typed decision
  -> BoundActionRequest.request_id
  -> ActionResult.request_id
  -> ActionEvaluation.request_id
  -> StepResult
```

`StepResult` rejects mismatched request, backend, before-observation, or after-observation identities. Provider IDs
remain internal telemetry; the model receives each action and its result nested in one `StepView`, so a result cannot
be associated with another action by position or prose inference.

## Model context

Each model turn contains exactly five kinds of information:

```text
Task
  original instruction, constraints, permitted effects, formal task evaluation, requested outputs
Current Observation
  one latest fused public world and current screenshot when selected
Current Goal Plan
  ready(plan version + ordered semantic items), not_required, or unavailable(reason category)
Recent Steps
  latest complete action/result pair plus up to seven compact pairs
Current Tools
  exact tools and schemas callable in this turn
```

The latest observation overrides history. ActionPolicy interprets each plan item against that fresh world; Runtime
neither computes nor persists item status or a frontier. Formal completion remains in TaskEvaluator. No model summary
or separate progress-evaluator call is made per step.

```text
WorldObservation -> ActorWorldSnapshot
GoalPlan -> AgentGoalPlanView
ActorWorldSnapshot + AgentGoalPlanView -> GroundedPolicyContextBinder
```

`GroundedPolicyContextBinder` is the only provider-message assembler. The model never receives budgets, backend
routes, selectors, coordinates, private bindings, provider transcripts, old worlds/screenshots, benchmark rewards,
or hidden state. Under `structure-first.v1`, images require admitted evidence need; under `screenshot-ax.v1`, the
current screenshot accompanies the same AX-backed world. Old images are never retained in recent steps.

### GUI capability exposure and visual profiles

The model-facing GUI contract is one high-level, snapshot-scoped action set such as `activate(target)`,
`type_text(target, text)`, `select_option(target, options)`, and `drag_to(source, destination)`. BrowserGym BIDs,
Playwright selectors, native events, and coordinates remain private execution details. DOM-clickable fallbacks are
lower authority than native AX controls: a wrapper owning exactly one native executable control remains structural
context but is not exposed as a second action. Prompt bounding happens only after the complete canonical inventory is
built; paging or retrieval may limit one turn's projection, but the union of pages must conserve every current action.

`structure-first.v1` and `screenshot-ax.v1` are perception profiles over this same world and action catalog, not
separate execution paths. Screenshot+AX may help the main multimodal model interpret layout or open-world content,
but it never creates coordinate authority; every dispatched GUI action still resolves through the current semantic
binding. A model-backed visual grounder or disambiguator is an optional evidence provider. Failure of an
automatically inferred visual enhancement does not invalidate an otherwise complete structured observation, while
an explicit model request for visual evidence remains required and fails with its typed provider reason.

Visual acquisition has four bounded admission conditions. A perception profile may attach the current raw screenshot
to every main-model turn; an explicit `request_evidence` may require entity discovery, target disambiguation, or
verification; Runtime may add optional entity discovery when the structural inventory reports typed truncation; and
an unresolved declared postcondition may require visual diagnosis. The mere presence of multiple controls, duplicate
labels, or a configured provider is not evidence and never triggers a specialist. Target disambiguation therefore
starts only after the policy states a semantic intent. Its E-ref candidates are derived once from current executable
bindings, restricted and clipped to the same screenshot coordinate space, and remain snapshot-scoped. Fewer than two
visible candidates is a typed local capability-unavailable outcome, not a visual-provider failure and not a provider
call.

Action evaluation is projected once through the latest `StepResult`. Confirmed effect and confirmed no-effect map to
`action_effect_confirmed` and `action_no_effect_change_strategy`; the latter tells the model to change target or
strategy without adding a second progress ledger. Runtime does not infer page-specific task semantics when a model
continues to make poor choices despite current state, screenshot, and effect feedback.

A native-tool provider receives tools through PydanticAI rather than a duplicate menu in the context. A retained
compact-JSON compatibility model may receive the same current catalog in the public context because it has no native
tool field. Its provider-envelope normalizer projects only the operation and arguments (including their admitted
aliases); provider commentary is discarded as non-authoritative metadata and can never become an action argument.
Missing or conflicting action-bearing fields still fail closed, and Runtime validates the projected arguments against
the selected current `ToolSpec` before dispatch.

## Current model prompt

The product has one stable system prompt. Schema details belong to `ToolSpec`; current facts belong to context;
validation errors belong to the matching tool result. Its stable decision rules are:

```text
- Task is the user-objective authority; fresh Observation is current UI authority.
- Treat GoalPlan as an advisory semantic skeleton, never as proof or permission.
- Before each choice, reassess plan outcomes from fresh World and recent effects.
- Do not click an already active toggle unless the task requests undo.
- Prefer the earliest visibly unsatisfied item whose dependencies visibly hold.
- Attempt a final item only after all prerequisites visibly hold.
- Choose exactly one currently offered tool; never invent targets or backend details.
- Runtime owns validation, binding, safety, execution, effects, and formal completion.
```

Control decisions such as `request_evidence`, `ask_user`, and `abort` use the same current tool-call protocol.
`ask_user` is reserved for required user-owned task information unavailable from the interface; Runtime confirmation
remains separate. Ordinary GUI-effect tasks terminate when TaskEvaluator confirms completion, while tasks requesting a
textual answer use the model's native final output only after requested outputs are verified.

## Validation and repair

Tool handling is deterministic and bounded:

1. Use strict provider schemas when supported.
2. Validate every call again in Runtime.
3. Normalize only representation-equivalent calls; never infer and execute a changed intent.
4. For a known tool with invalid arguments, return public field violations and its exact schema, then allow one repair.
5. For an ambiguous tool intent, return at most three exact current `did_you_mean` candidates and allow one repair.
6. For an unknown tool, return current names without pretending semantic equivalence.
7. If the repaired call is still invalid, return a typed policy failure and execute nothing.
8. If an admitted action becomes stale, acquire a fresh observation and let the next ordinary model turn replan; do
   not replay automatically.

Repair results retain the provider `call_id`. They are dynamic tool results, not permanent prompt instructions.

## Counting and arithmetic boundary

The public world preserves observed structure and does not inject task-derived counts or answers. When the current
public structural document is complete, the per-turn Registry exposes the deterministic
`count_children(containers=[...])` entry. Its binding owns the schema, eligible current references, validation, and
mechanical direct-child handler. The model chooses every relevant repeated group; the binding returns each count and
their total as the result of that explicit turn.
Runtime never parses the task to select operands or infer which groups matter. Further arithmetic remains model
reasoning until benchmark evidence demonstrates a different shared failure after explicit totals are available.

## Authority

| Question | Owner |
|---|---|
| What did a source observe? | SurfaceAdapter |
| Which evidence should be acquired? | ObservationPolicy |
| What is the current unified world? | WorldFusion / WorldObservation |
| What did the user request? | caller / revisioned TaskGoal |
| What semantic skeleton may help? | GoalCompiler proposes; GoalPlanBoundary validates and versions |
| Which plan item is satisfied or next now? | ActionPolicy interprets GoalPlan + fresh World; no Runtime progress state |
| What semantic action should be attempted? | Model policy |
| Which tools are callable now? | PerTurnToolCatalog |
| Is the call legal, current, and bound? | Runtime admission and Binder |
| What was physically dispatched? | executing adapter |
| Did it have a local effect? | ActionEvaluator |
| Is the task complete? | TaskEvaluator/native verifier |
| Continue, wait, ask, finish, or fail? | CoreAgentLoop from typed execution/user/safety/task outcomes—not plan guidance |

## Closed status algebra

Run status is `running`, `waiting_user`, `waiting_confirmation`, `done`, `blocked`, `cancelled`, or `failed`.
Terminal states are absorbing for the current run. Unsupported states fail with a typed reason. Durable replay,
cross-process idempotency, and distributed recovery are outside the supported scope.

## Migration status

The control-core migration is complete. Model/provider plumbing is now being reduced before empirical benchmark
validation:

| Phase | Status | Exit condition |
|---|---|---|
| 1. Freeze architecture, prompt, context, non-goals, and migration order in the five maintained documents | done | documents agree and historical plan files are removed |
| 2. Preserve `call_id` and use strict provider tool schemas where supported | done | call/result lineage and provider tests pass; current admitted native providers rely on Runtime strict validation because their documented wire schemas do not expose a strict-tool flag |
| 3. Introduce the thin model workspace and eight nested `StepView` records | done | no budget, duplicate world, transition, event, or feedback channels reach the grounded model boundary |
| 4. Migrate observation, action paging, wait, ask/resume, done, confirmation, abort, and error paths | done | supported decisions have typed core-loop integration tests; confirmation continuations preserve one model-step count |
| 5. Connect benchmark runners to the core loop | done | target benchmark exclusively executes `CoreAgentLoop`; reports persist `runtime=core` and raw per-case evidence |
| 6. Cut over and delete the legacy cluster | done | public Runtime, CLI, and target benchmark use the core; old control state and projections are deleted |
| 7. Validate PydanticAI against the current dynamic catalog and Runtime | done | Zhipu text and vision tool calls, `call_id`, bounded repair, `ask_user`, and Runtime auto-completion pass |
| 8. Select model transport by actual wire capability | done | native tools use `pydantic-ai`; 4.1V uses `compact-json`; both pass the same real click-button Runtime witness and `propose_done` is not model-visible |
| 9. Converge the model/tool/context boundary and delete superseded paths | done | one typed AgentContext, one Actor world projection, one provider binder, stable registry-owned tools, and no legacy structured decision/parser/serialization path |
| 10. Replace symbolic goal guidance with Simple GoalPlan | implementation complete; Ready delivered / policy behavior failed / non-closed | five-field plan is directly projected and compiler attempts are traced; Ready reached all ten turns, but policy reversed satisfied Likes and never submitted; held-out success plus independent audit remain required |
| 11. Run paired structured-only/adaptive cohorts | pending | the first 15-case pair completed 13/15 in both arms but acquired zero visual sources, so it is valid Runtime evidence but not evidence for the adaptive-observation claim |

Phase 9 ends with the full test gate plus the frozen five-case visual witness (`miniwob-60-05`, `34`, `42`, `49`,
and `60`) running through 4.1V and `CoreAgentLoop`; that witness precedes the paired cohort and cannot change product
semantics.

Any follow-up fixes must preserve this boundary and be justified by a shared invariant or benchmark evidence.

## Removed at cutover

The legacy `AgentLoop`, `AgentLoopState`, `ControlTransition`, `ControlContinuation`, `ControlFeedback`,
`ControlOutcome`, `ControlReducer`, progress-event control projections, transition digests, model-visible budget views,
and summaries that existed only to support the old ledger-shaped context are no longer production modules.

## Complexity guardrails

- Keep `GoalPlan` immutable, bounded, and advisory; never add current status, refs, selectors, World queries, bindings,
  or a mutable progress store.
- Reuse the single ActionPolicy, `SelectAction -> BoundActionRequest`, Binder, Executor, and TaskEvaluator path.
- Keep action legality, currentness, risk, confirmation, dispatch, effects, and formal verification strict.
- Do not add Manager/Worker, a second evaluator loop, per-step planning calls, or benchmark-specific product branches.
- Add a type only when it owns one non-duplicated invariant required by the loop.

## Exit criteria

- `TaskGoal` and fresh `WorldObservation` remain the user-intent and environment authorities.
- A Ready GoalPlan is bounded, acyclic, versioned, projected once, and never treated as progress or proof.
- Every dispatched action has one matching result, fresh observation, and evaluation; stale calls never execute.
- Tests cover tolerant response parsing, plan/DAG invariants, revision invalidation, advisory failures, transcript
  preservation, five-section context, current-world precedence, and private-field non-leakage.
- The second 2026-08-17 formal Like run reports Ready-plan delivery, all policy actions, official failure, and separate
  compiler breadth metrics without a case-specific branch; it witnesses delivery but falsifies the behavioral claim.
- Held-out cases and an independent fresh-context audit remain required before any closed claim.
- Code, tests, maintained documents, and benchmark reports describe the same single-loop architecture.
