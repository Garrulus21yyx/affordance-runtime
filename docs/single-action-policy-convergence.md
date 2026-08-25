# Single-ActionPolicy Convergence

## Status

**C0–C7 single-policy control migration implemented; C8 change-first Observation Delivery and C9 bounded
AgentWorkspace convergence reopened; live closure gates remain blocked.**

This document defines the implemented removal of the mandatory Planner/Milestone/Evidence/Auditor control chain from
the default GUI runtime. It is a convergence redesign, not a patch for Task 7 or run16. Production now uses the single
ActionPolicy path below; prior mission-path tests and run artifacts remain historical scoped evidence, not closure of
this target design.

The separately reopened BrowserGym invariant
`dispatch -> causal stable World -> StepResult` remains required. Simplifying cognitive orchestration does not waive
post-action stability, currentness, binding, receipt, persistence, cleanup, or native-evaluator correctness.

Run evidence after C7 falsified two additional assumptions in the target baseline: a global lexical
`EvidenceCandidates` list does not guarantee that the latest action's public result is salient, and append-oriented
compact history is not a total bounded workspace. C8–C9 replace those mechanisms at their owners; they are not larger
limits, prompt changes, or compatibility layers around the old path.

No live benchmark is authorized by this document alone.

## Decision

The default runtime will be a single continuous `CoreAgentLoop` driven by one `ActionPolicy`. A model-backed
`GoalCompiler` may produce one small static advisory `GoalPlan` at task start or user revision. It is fail-open and is
not called again because a page changes, an action fails, or the agent stalls.

The default path will not contain a mandatory Manager, MilestonePlanner, mutable milestone state, semantic Auditor,
evidence-promotion boundary, or cross-episode MissionState. These components must not remain as hidden compatibility
fallbacks after migration.

The resulting control path is:

```text
User request
-> TaskGoal
-> optional GoalCompiler once
-> static advisory GoalPlan
-> CoreAgentLoop
     TaskGoal
     + GoalPlan
     + fresh change-first WorldDeliveryView
     + current ActionCandidates
     + bounded AgentWorkspace
     + current tools
     -> ActionPolicy: exactly one typed decision
     -> Resolver -> Admission -> Binder -> Executor
     -> dispatch receipt -> causal stable fresh World
     -> StepResult -> RunState
     -> TaskEvaluator
     -> deterministic stall monitor
        normal   -> ordinary ActionPolicy
        recovery -> deliberate ActionPolicy
        repeated -> BLOCKED
-> submit_final_response
-> one STOP
-> fresh acquire
-> official native evaluator
-> durable case result
-> bounded cleanup and fail-open viewer export
```

## Why the current design does not converge

The repeated reopenings have one shared cause: the Runtime tries to convert open-world GUI semantics into a chain of
mechanically admitted intermediate claims.

```text
Planner chooses milestone size
-> ActionPolicy discovers evidence
-> evidence must become scalar WorkingFacts
-> yield must satisfy required_evidence
-> evidence admission chooses a route
-> optional Auditor interprets semantic uncertainty
-> MissionState promotes the result
-> Planner selects another milestone
```

That chain creates more contracts without gaining the authority required to prove them.

### Semantic claims were treated as mechanically decidable

Runtime can determine whether a ref is current and public, whether an action is legal, whether dispatch happened, and
whether an explicit local postcondition holds. Runtime cannot generally determine whether:

- a model-generated milestone has the right semantic size;
- a currently visible fact is sufficient for the user's open-world request;
- all candidates have been found;
- one route is strategically preferable to another;
- a semantic answer is complete merely because selected keys are present.

Adding schemas, keyword admission, required-evidence keys, or state machines around these questions does not make them
mechanical. It moves model uncertainty into brittle boundary failures.

### Evidence recognition and evidence retention were conflated

Current code treats visible evidence, retained evidence, admitted evidence, and completed task state as stages of one
mandatory causal chain. They answer different questions:

| Concept | Question | Correct owner |
|---|---|---|
| current public evidence | what does the current GUI show? | `WorldObservation` |
| optional working note | which exact current value must survive a later view change? | Runtime copy from a current `F*` ref |
| model progress judgment | is there enough information to continue or answer? | `ActionPolicy` |
| official success | did the benchmark task succeed? | native evaluator |

An exact value does not require semantic audit before the same ActionPolicy can use it. A current result does not need
to be pinned before final submission. A pin is not proof that a user requirement is satisfied.

### Planner output became execution authority in practice

Although milestones were described as advisory, `required_evidence`, yield admission, MissionState promotion, and
successor scheduling made them control gates. A poorly sized milestone could therefore prevent a correct visible
result from being used or submitted. No finite schema can guarantee good open-world milestone decomposition.

### Recovery was converted into cross-role workflow

Local action failures, protocol failures, environment failures, semantic stalls, and final-answer delivery were routed
through the same outer orchestration. This caused extra model calls, context loss, schema failures, and provider
failures at points where the ordinary ActionPolicy already had the best current context.

### Verification proved the superseded mechanism, not capability

Provider-free tests successfully proved many properties of the heavy chain. They did not prove that the chain was
necessary, that its milestones were useful, or that successful GUI evidence could flow to a final answer cheaply.
Repeated live failures after correct GUI progress falsified that architecture-level assumption.

## SOTA alignment

The target baseline follows the common thin pattern rather than copying one project wholesale.

- [AgentOccam](https://github.com/amazon-science/AgentOccam) emphasizes observation/action alignment and reports strong
  WebArena results without mandatory new agent roles, online feedback, or search strategies. Its `note`, `stop`, and
  selective observation/history mechanisms keep planning and execution in the Actor.
- [Qwen3-VL OSWorld](https://github.com/xlang-ai/OSWorld/blob/main/mm_agents/qwen3vl_agent.py) uses one
  `computer_use` action envelope, a current screenshot, textual older actions, and four recent detailed turns. The
  model terminates or answers directly.
- [Agent S2](https://github.com/simular-ai/Agent-S/blob/main/gui_agents/s2/memory/procedural_memory.py) is a useful
  heavier comparison: its Worker still sees the current subtask, screenshot, and interaction history, emits one
  function call, and calls `done()` directly. Its reflection layer detects cycles but explicitly does not choose the
  next concrete action. A Manager is an optional higher-level pattern, not evidence that every GUI result needs an
  audited transaction.
- [BrowserGym](https://github.com/ServiceNow/BrowserGym) remains the environment, observation, execution, and native
  evaluation substrate. It does not require a Planner/Auditor state ledger.
- [Agent-E](https://github.com/EmergenceAI/Agent-E/blob/master/ae/utils/dom_mutation_observer.py) treats action-caused
  DOM change as first-class feedback. The target adopts that feedback contract but uses typed before/after public World
  comparison as authority because the released observer does not cover every visibility/style/class transition.
- [WebChallenger](https://github.com/jayoohwang1/webchallenger) supplies the region-cache shape: stable sections,
  unchanged-section reuse, changed-section refresh, and selective expansion. Those algorithms are implemented on the
  existing World/RegionIndex; its Playwright session, PageMem Agent loop, LLM summarizers, offline memory, and action
  workflows are not composed.
- [agent-browser snapshot diff](https://github.com/vercel-labs/agent-browser/blob/main/cli/src/native/diff.rs) is a
  useful independent serialized-snapshot oracle. Its line-level diff and browser session do not become production
  World or execution authorities.
- [LongHorizon-Harness](https://github.com/AMAP-ML/LongHorizon-Harness) remains a reference for explicitly
  high-assurance, cross-round, heterogeneous GUI/CLI work. Its Manager/Auditor protocol is intentionally heavier and
  is not the default WebArena baseline.

The engineering inference is bounded: a single Actor with aligned observation/action interfaces is the default;
reflection or planning is introduced only after benchmark evidence shows a specific failure that the single loop and
bounded recovery cannot handle.

## Authorities after migration

| Authority | Sole owner | What it may decide | What it may not decide |
|---|---|---|---|
| user intent | `TaskGoal` | requested outcome, effects, constraints | GUI state or action legality |
| advisory decomposition | `GoalCompiler` / `GoalPlan` | static semantic hints | mutable progress, permissions, completion |
| current GUI truth | fresh `WorldObservation` | public current facts and provenance | task relevance or success |
| legal semantic actions | complete `ActionSpace` | currently executable operations and targets | physical selectors or task strategy |
| model-visible tools | `PerTurnToolCatalog` | public operation schemas | execution authority |
| next semantic decision | `ActionPolicy` | one action, observation request, note, ask, abort, or final response | private binding or official success |
| physical binding | Binder | current target to private primitive | semantic goal selection |
| dispatch truth | Executor receipts | sent/not-sent/sent-unknown and ordered compound receipts | semantic success |
| committed runtime step | `RunState.apply(StepResult)` | legal state transition | reconstructing missing owner facts |
| operational stall | deterministic Monitor | normal/recovery/terminal stall signal | semantic task completion or a replacement plan |
| official completion | native evaluator after one STOP | benchmark success/failure | modifying the trajectory |
| durable benchmark truth | result store | committed terminal report | controlling the run |
| diagnostics | JSONL/Langfuse | observe owner-produced facts | state, blocking, or retrospective authority |

## Model-facing context

Every ordinary ActionPolicy call receives only:

```text
TaskGoal
+ static GoalPlan, if available
+ LatestEffect, CurrentFindings, and exact ChangedRegions from the causal fresh World
+ automatic ActionCandidates
+ cached PageOutline and typed recovery directory
+ AgentWorkspace:
    latest four detailed steps
    exact bounded SemanticEvents
    aggregated ActivitySummary entries
    optional current-run WorkingFacts
+ current tool catalog
+ typed recovery signal, only when active
```

It does not receive:

- mutable milestone state;
- required-evidence completion status;
- MissionState or Auditor reports;
- previous episode screenshots or Worlds;
- provider reasoning transcripts;
- hidden evaluator state or expected answers;
- stale `E/N/F/R` refs in history.

Context compression remains a delivery concern. It must preserve the latest exact public effect, changed-region
contents, current actions, labels, ancestor closure, and recovery handles. It must not invent a second state authority.
`RequestAdmission` alone allocates and admits the complete request. Neither RunState/history nor the provider Binder
owns an independent byte cap.

## GoalPlan contract

`GoalCompiler` is called only at task start and user revision. It returns `Ready | NotRequired | NeedsInput |
Unsupported | Failed`. `Unsupported` and `Failed` are recorded and the GUI loop continues without a plan.

Each plan contains one to eight static items:

```text
id
objective
done_when
depends_on
final
```

There is no stored item status, frontier, required evidence, milestone admission, automatic recompile, or successor
scheduler. On every turn, ActionPolicy re-evaluates the static hints against the fresh World and may adapt when a hint
is no longer useful. Only a user revision invalidates and recompiles the plan.

## Decision and tool contract

### Exactly one model decision

The provider boundary must yield exactly one typed `RuntimeDecision`. Internally this remains a discriminated union of
the existing semantic decisions. Provider transport may use one PydanticAI output envelope analogous to
`computer_use(action=...)`; this is wire normalization, not a second ToolCatalog or a hand-written compact-JSON agent.

```text
RuntimeDecision
  activate
  type_text
  select_option
  set_form_fields
  scroll
  press_key
  focus
  hover
  drag_to
  read_region
  search_page_content
  find_controls
  remember_fact
  ask_user
  wait
  submit_final_response
  abort
```

The current `PerTurnToolCatalog` still owns which variants and refs are legal. Resolver/Admission/Binder remain the
only execution path.

If a provider emits multiple decisions:

```text
provider response
-> PydanticAI/output boundary validation
-> reject every call before Catalog resolution or dispatch
-> at most one bounded single-action retry in the same policy turn
   input: the identical admitted task + fresh World + tools + SDK history/current ToolReturn + media
   plus a short multiple-call violation
-> exactly one valid decision, or typed policy protocol failure
```

For one rejected call with an invalid representation, the existing narrow repair may only delete invalid
representation fields; it cannot add fields or change the operation, target refs, text, values, keys, options, or any
other leaf. A multi-call retry is instead a fresh choice over the unchanged current context because no prior member was
accepted. Zero-call and wholly unparseable envelopes fail typed without repair because there is no semantic decision
identity to preserve.

The Runtime never silently chooses the first call, executes arbitrary multiple calls, or records each repair as a GUI
step. Repeating the same protocol failure after the bounded repair terminates that policy attempt; the Monitor does
not spend additional GUI turns on it.

### Explicit compound actions only

`set_form_fields` remains one bounded semantic action for two to four independent fields in the same current form. It
does not submit, navigate, or contain arbitrary nested tools. Complete, partial, cancelled, and sent-unknown receipts
remain explicit.

No general multi-action scheduler is introduced. Other GUI effects remain one semantic decision per fresh World.

## Evidence and working memory

### Current evidence

Current public evidence is already usable because it is part of the authoritative fresh World. ActionPolicy may reason
from it immediately and may submit a final answer without first pinning it.

The old global `EvidenceCandidates` lexical Top-k is removed. It could rank generic DOM facts above a newly exposed
result because it had no before/after transition input. Current delivery instead begins with the exact
`PublicWorldDelta` caused by the latest external GUI action and exact pages of every changed region. Result presence
means observable, not complete, verified, or sufficient.

`CurrentFinding` is a bounded exact projection from the current public World/delta. It does not perform business
parsing. If the page exposes one address string, Runtime retains that exact string and does not synthesize state or
postcode fields. A finding may become a `SemanticEvent` for current-run continuity without becoming task-progress or
completion authority.

The misleading `required_evidence: currently_visible` projection is removed.

### Optional exact working notes

`pin_fact` is removed from the mandatory completion chain. If retained, rename the public operation to
`remember_fact(key, evidence_ref, purpose)` and give it one narrow meaning:

```text
current public scalar F-ref
-> Runtime copies the exact value and lineage
-> current-run WorkingFacts
```

It performs zero BrowserGym dispatch. It does not decide relevance, completion, stability, promotion, or official
success. It is useful only when an exact value must survive an upcoming page/search replacement.

There is no Auditor, evidence admission, or MissionState promotion after remembering a fact. Conflicting writes to the
same key remain a typed local error because two different exact values cannot silently replace one another.

## Observation Delivery and AgentWorkspace

The target continuity path is:

```text
causal before/after World
-> one PublicWorldDelta
-> versioned existing regions
-> LatestEffect + exact CurrentFindings + cached unchanged outline + exact changed-region blocks
-> WorkspaceReducer
-> RequestAdmission
-> provider serialization without further fitting
```

`WorkspaceReducer` is deterministic and total for ordinary supported step growth. It retains four detailed steps,
exact bounded semantic events, aggregated observation-only activities, and optional exact WorkingFacts. A repeated
read/search/wait with no World/finding/fact delta updates one `ActivitySummary`; it never appends an unbounded history
item. Every raw step remains in Full Trace.

The following production mechanisms are removed rather than enlarged:

- `EpisodeHistoryCapacityError` for ordinary accumulated history;
- `RunState.can_remember_step()` as a model-capacity authority;
- the fixed model-history byte cap and independent RunState pre-validation cap;
- provider-Binder trimming or reclassification of context overflow;
- collapsing precise public transition values to `fact_change_count` after they leave the recent-four window.

If the irreducible task, current delivery, latest four steps, tools, images, and fitted workspace still exceed the whole
request allocation, `RequestAdmission` returns typed `context_capacity` with zero provider attempts. Only grounded
tool-resolution failures map to `invalid_tool_arguments`.

### Final response

When ActionPolicy believes the user request is complete, it calls `submit_final_response` directly. Runtime validates
only the public response shape, ref currentness where refs are supplied, one-send semantics, and delivery lifecycle.
It does not mechanically prove semantic completeness before sending.

Correctness is determined by:

```text
one STOP/send
-> causal stable fresh acquire
-> official native evaluator
```

Evidence refs may be included for traceability but are not a mandatory proof ledger. A wrong or incomplete answer is a
benchmark failure, not a reason to add another local semantic authority.

## Recovery without a mandatory Manager

Recovery is a bounded mode of the same ActionPolicy, not a cross-role workflow.

### Failure ownership

| Failure | Owner | Response |
|---|---|---|
| malformed output | PydanticAI/provider output boundary | one narrow representation repair when semantics are preserved; then typed protocol failure |
| multiple calls | PydanticAI/provider output boundary | execute none; one same-context single-action retry; then typed protocol failure |
| stale ref or operation mismatch | Resolver/Admission | current typed feedback; no dispatch |
| local postcondition not satisfied | ActionOutcome owner | fresh result and supported alternatives to ActionPolicy |
| `SENT_UNKNOWN` | environment/executor | no blind replay; bounded recapture or typed failure |
| navigation/acquisition pending | BrowserGym transition owner | no next policy turn until stable World or typed failure |
| exact repeated attempt | Monitor plus CoreLoop guard | reject repeat and activate deliberate policy profile |
| route oscillation or repeated no progress | Monitor | deliberate policy profile once; recurrence becomes operational `CONTROL_STALLED` while TaskEvaluation remains `INCOMPLETE|UNKNOWN` |
| missing user-owned fact | ActionPolicy | `ask_user` |
| unavailable capability | Runtime/ActionPolicy | typed `unsupported` or `blocked` |

### Recovery state machine

```text
ORDINARY
  progress                              -> ORDINARY
  first local no-effect                 -> ORDINARY with typed feedback
  second same stall / first route cycle -> RECOVERY
  provider/environment terminal failure -> typed operational terminal outcome

RECOVERY
  progress                              -> ORDINARY
  ask_user                              -> WAITING_USER
  explicit unsupported                 -> typed unsupported terminal outcome
  prohibited exact typed attempt recurs -> CONTROL_STALLED
  materially different attempt          -> ORDINARY

FINALIZING
  response not sent                     -> FAILED
  sent/sent-unknown + fresh post World   -> native evaluation once
  native success                        -> DONE
native non-success                    -> BLOCKED or FAILED by evaluator outcome
```

`RECOVERY` changes only the ActionPolicy call profile and context:

```text
ordinary:   low/off extended thinking, one action
recovery:   one bounded deliberate call, same TaskGoal/GoalPlan/fresh World,
            typed stall and bounded failed-attempt summary, one next decision
repair:     no extended thinking, representation only
```

The Monitor detects operational repetition; it does not infer task semantics, mark the task blocked, or propose a
plan. The deliberate ActionPolicy directly chooses the next action. There is no intermediate advice call.

### Optional future RecoveryAdvisor

No Manager or RecoveryAdvisor is part of this baseline. A one-shot advisory model may be reconsidered only if held-out
benchmark evidence shows that the deliberate ActionPolicy repeatedly fails after receiving accurate fresh World and
typed stall feedback.

If later justified, it may output only a bounded non-authoritative strategy hint. It may not create milestones,
required evidence, MissionState, refs, actions, or completion claims. This is an extension point, not compatibility
code retained during the migration.

## Persistence and observability retained unchanged

Simplifying cognition does not weaken result durability or diagnostics:

```text
terminal case outcome
-> local trace flush
-> durable result commit
-> bounded environment cleanup
-> bounded fail-open viewer/export shutdown
```

Local JSONL remains the complete trace authority. Langfuse remains an isolated lossy viewer. Cleanup, transport retry,
atomic result persistence, and causal BrowserGym transition fixes stay on their current owners and are not folded into
CoreLoop or ActionPolicy.

## Production migration map

The migration switched the default path atomically. No runtime feature flag selects between old and new orchestrators.

### Remove from production composition

| Pre-migration owner/path | Implemented change |
|---|---|
| `mission/supervisor.py` | remove `MissionSupervisor` from default case execution; direct the runner to the existing `CoreAgentLoop` |
| `model/mission_roles.py` | remove MilestonePlanner/Auditor composition and model-facing schemas from the default product path |
| `model/policy/prompts/milestone_planner.yaml` | delete after production and tests no longer consume it |
| `mission/boundary.py` | remove milestone/evidence admission from the default path; retain no semantic completion substitute |
| `mission/contracts.py` | remove `MilestoneRoadmap`, mutable mission progression, admitted outcomes, and MissionState from default runtime contracts |
| `agent/decisions.py` | remove `YieldMilestone`; retain direct final response, ask, abort, local observation, note, and GUI decisions |
| `model/policy/grounded_tool_catalog.py` | remove `yield_milestone`; make working-note and final-response tools follow the thin contracts |
| `agent/context/contracts.py` and `context_builder.py` | remove active milestone, required-evidence status, audit guidance, and MissionState projections |
| `agent/context/evidence_candidate_projection.py` | remove the global lexical EvidenceCandidates authority; latest-effect and changed-region delivery come from the shared typed World transition |
| benchmark runner/contracts/projection | consume `CoreAgentLoop` terminal result directly; delete mission outcome/counter/reflection dependencies |

The useful `mission/monitor.py` behavior moved to `agent/monitor.py` as deterministic operational monitoring independent
of Mission rounds, model-facing recent-step truncation, and milestone state.

### Keep and converge

| Component | Required target |
|---|---|
| `TaskGoal` | sole user-intent authority |
| `GoalCompiler` | optional start/revision-only, fail-open static plan |
| `CoreAgentLoop` | sole cognitive/execution orchestration |
| World/Actor/Delivery | one current public truth, one typed transition, versioned existing regions, and change-first recoverable projection |
| ActionSpace/ToolCatalog | complete internal catalog and one model-visible decision contract |
| Resolver/Admission/Binder/Executor | unchanged single action authority |
| `set_form_fields` | only bounded compound GUI action initially |
| `AgentWorkspace` | latest four detailed steps, bounded exact semantic events, aggregated activity, and optional exact notes |
| `RequestAdmission` | sole authority for the entire model request capacity |
| `WorkingFact` | optional current-run exact note, no promotion workflow |
| `EpisodeMonitor` | fixed-size information-delta stall signals only; never task-semantic BLOCKED authority |
| `TaskEvaluator`/native verifier | only semantic terminal authority |
| JSONL/result store/cleanup/viewer | existing persistence and diagnostics owners |

## Implementation sequence

Implementation status on 2026-08-22: C0–C7 established the single-policy control path, but later live evidence reopened
its observation-delivery and workspace assumptions. C8–C9 below are design-complete and implementation-pending. An
explicitly authorized live W1b witness remains blocked until their provider-free properties, full checks, and a new
fresh-context review pass.

### C0 — freeze the disputed chain

- Mark Planner/Milestone/Evidence/Auditor architecture non-closed.
- Block live W1b while the default control path is changing.
- Preserve prior run evidence as regression input, not closure proof.
- Do not add further milestone-size, evidence-key, Auditor, or Manager prompt patches.

Exit: docs and status agree that the old chain is superseded and no dependent benchmark is presented as closed.

### C1 — establish the direct baseline seam

- Compose `TaskGoal -> optional GoalCompiler -> CoreAgentLoop` directly in the benchmark/application runner.
- Reuse the existing BrowserGym session, World, ActionSpace, Binder, Executor, TaskEvaluator, trace, and result store.
- Return the existing CoreAgentLoop terminal result directly to case projection.
- Add no compatibility fallback to `MissionSupervisor`.

Exit properties:

- exactly one `CoreAgentLoop` and one BrowserGym session;
- zero Planner/Auditor calls;
- ordinary navigation, form fill, result read, and final response complete without outer role transitions;
- current BrowserGym causal-stability gate still applies.

### C2 — remove milestone/evidence control contracts

- Remove milestone fields from ActionPolicy context.
- Remove `required_evidence`, `currently_visible`, audit guidance, and missing-key status.
- Remove `yield_milestone` and its RunStatus/admission branches.
- Change `pin_fact` to optional `remember_fact`, or retain the internal name temporarily while changing the public
  semantics; no compatibility alias remains at migration completion.
- Remove MissionState promotion and semantic Auditor routing.

Exit properties:

- a current visible result can be used by the next action or final response without a pin;
- remembering a current F-ref is zero-dispatch and never changes task status;
- no key-presence check can claim semantic completion;
- repository production search finds no milestone/audit completion dependency.

### C3 — converge one-decision provider output

- Define one Pydantic discriminated `RuntimeDecisionModel` compiled from the current ToolCatalog.
- Use PydanticAI/provider-native structured output rather than a manual compact-JSON parser.
- Enforce exactly one decision at the model boundary.
- Add one same-context single-action retry for multiple output and retain narrow representation repair for one
  parseable malformed call.
- Remove multiple-tool feedback as a repeated GUI turn behavior.

Exit properties:

- a provider response with two valid calls executes neither and performs at most one same-context retry;
- single-action retry receives the same admitted current context, while representation repair stays narrow; neither
  creates a StepResult;
- valid atomic and `set_form_fields` decisions traverse the same Resolver/Binder/Executor path;
- repeated protocol violation terminates with a typed policy failure and bounded cost.

### C4 — converge local recovery

- Make Monitor state independent of model-facing history retention.
- Share one typed attempt signature between producer and CoreLoop guard.
- Classify exact repeat, local no-effect, and route oscillation without interpreting task semantics; repeated provider
  representation failure terminates at the provider boundary and never enters recovery as a GUI step.
- Add ordinary/recovery call profiles to the same ActionPolicy.
- Freeze the bounded rule: first no-effect informs; a bounded no-information family can activate recovery; only the
  recovery signal's exact typed attempt may terminate as `CONTROL_STALLED`. A materially different attempt exits
  recovery and remains bounded by the episode step limit while TaskEvaluation remains unchanged.

Exit properties:

- no Manager/Planner call on any local recovery path;
- successful recovery returns to ordinary mode;
- same failure cannot consume the full turn cap;
- a fresh public result prevents false no-progress classification even when not remembered;
- environment and provider failures retain their own typed owners.

### C5 — simplify finalization

- Expose one stable `submit_final_response` schema owned by the ToolCatalog.
- Validate representation and one-send lifecycle, not semantic completeness.
- Send once, acquire a causal stable post World, and invoke the native evaluator once.
- Derive benchmark terminal status from native evaluation and dispatch truth.

Exit properties:

- no LLM Finalizer or semantic Auditor;
- a correct visible answer can be submitted immediately;
- `SENT_UNKNOWN` is never replayed;
- native evaluator outcome is neither overwritten nor reconstructed by projection.

### C6 — delete superseded code and projections

- Delete old prompts, role composition, schema models, counters, case fields, and tests whose only purpose is the
  superseded mission workflow.
- Remove benchmark reflection over Planner/Auditor/MissionState internals.
- Archive chronological evidence under `docs/history/`; do not mix it into this target design.
- Do not retain import shims, aliases, feature flags, or dual result vocabularies.

Exit: production search and import-graph tests prove one runtime path and no old compatibility consumer.

### C7 — verification and return to benchmark

Run verification in this order:

1. model/schema properties for exactly one decision, representation-pruning repair, and typed zero/unparseable failure;
2. state-machine properties for ordinary/recovery/finalization transitions;
3. action/compound receipt conservation;
4. current evidence usable without pin; optional note retained across view change;
5. generic same-action, no-effect, and `A -> B -> A` recovery witnesses;
6. BrowserGym causal post-action transition gate;
7. six-page W1b-World World/Action/discovery/cost diagnostics;
8. full tests and static checks;
9. independent fresh-context architecture review;
10. one explicitly authorized live W1b witness, followed by a held-out site/task witness.

Closure requires implementation, tests, docs, evidence, and fresh review to agree. One successful Task-7 rerun is not
closure.

### C8 — converge change-first Observation Delivery

- Introduce one typed `PublicWorldDelta` produced from the causal before/after public Worlds and consumed by
  ActionOutcome, Monitor, delivery, continuity, and trace.
- Upgrade the existing RegionIndex with stable region digests/versions and cache unchanged PageOutline blocks.
- Keep the latest external effect across local read/search/control operations; supersede it only after another external
  GUI effect, first retaining its exact public values as a bounded SemanticEvent.
- Render exact latest changes and changed regions before ActionCandidates and the cached outline; page every folded
  change with typed recovery.
- Remove global lexical EvidenceCandidates as the default evidence-delivery authority.
- Use Agent-E as the change-feedback contract, WebChallenger as the changed-section/cache reference, and agent-browser
  serialized diff as a diagnostic oracle. Compose none of their browser sessions, Agent loops, refs, or action paths.

Exit properties:

- every supported public added/modified value is present in the delta or has a typed unsupported outcome;
- after an action exposes a result, the next model delivery contains that exact result before the PageOutline without a
  model search call;
- local reads/searches do not erase the latest GUI effect;
- unchanged regions are reused and changed regions remain completely recoverable;
- all transition consumers agree on one before/after lineage and no rendered-string diff is an authority.

### C9 — converge bounded AgentWorkspace and capacity

- Define `CurrentFinding`, `SemanticEvent`, `ActivitySummary`, `AgentWorkspace`, and one total `WorkspaceReducer`.
- Replace append-oriented model history with latest-four detail, exact semantic events, aggregated no-information
  activity, and optional exact working notes; retain every raw step only in Full Trace.
- Make `RequestAdmission` the sole whole-request capacity authority and have the provider Binder serialize the admitted
  request unchanged.
- Remove `EpisodeHistoryCapacityError`, independent history/RunState byte caps, provider-side trimming, and broad
  exception mapping to invalid tool arguments.
- Make Monitor compare fixed-size World/finding/working-fact digests. Repeated observation-only activity with no
  information gain enters one recovery, then operational `CONTROL_STALLED` without changing TaskEvaluation.
- Put decision/stall thresholds in one generic `AgentLoopProfile`; values are experiment parameters rather than
  benchmark/site branches.

Exit properties:

- 1,000 ordinary steps always reduce to a workspace within its assigned allocation or one typed irreducible
  `context_capacity`; ordinary growth never throws a history exception;
- an exact result leaving the latest-four window remains in a SemanticEvent;
- different queries/regions with no finding delta form one activity/stall family;
- provider attempts are zero on local capacity rejection and only grounded resolution errors become
  `invalid_tool_arguments`;
- Full Trace remains lossless, while no production old-history renderer or second capacity owner remains.

## Acceptance invariants

### Structural

- one `TaskGoal`, World, ActionSpace, ToolCatalog, Binder, Executor, CoreAgentLoop, TaskEvaluator, and native evaluator;
- no production MilestonePlanner, ManagerReview, semantic Auditor, evidence-promotion boundary, or MissionState;
- no second browser session, DOM walker, selector map, action registry, or execution loop;
- no compatibility runtime that can select the old orchestration.

### Decision and execution

- each policy turn produces exactly one typed decision;
- a repair is representation-only and cannot change target/operation through hidden semantic reselection;
- an effectful action is never replayed after `SENT_UNKNOWN`;
- `set_form_fields` is the only initial compound GUI action and conserves all ordered receipts;
- no next policy decision occurs before a causal stable fresh World.

### Context and evidence

- current public World evidence is immediately usable without pin or audit;
- optional remembered facts are exact Runtime copies from current public scalar refs;
- remembering a fact never changes task completion state;
- stale local refs never enter AgentWorkspace or a later context;
- one typed before/after public delta is shared by every transition consumer;
- latest-effect delivery preserves exact changed values before the ordinary outline and survives local reads/searches;
- unchanged regions are cached, changed regions and folded content remain completely recoverable;
- WorkspaceReducer is total for ordinary step growth and RequestAdmission is the only capacity authority;
- exact public results survive the latest-four window as bounded SemanticEvents; no-information activity is aggregated.

### Recovery

- first local no-effect is feedback, a bounded no-information family can enter recovery, and only the prohibited
  exact typed attempt terminates as operational `CONTROL_STALLED` without changing TaskEvaluation to blocked;
- route cycles survive interleaved local reads and rejected calls;
- Monitor does not choose strategy or interpret task completion;
- no Manager/Planner/Auditor model call occurs on ordinary or recovery turns;
- every failure has one typed owner and one terminal projection.

### Finalization and benchmark

- ActionPolicy may submit a supported final response directly;
- Runtime performs no local semantic completion proof;
- STOP is sent at most once and official evaluator runs at most once;
- durable result is committed before cleanup and remote export;
- Langfuse failure cannot delay or change terminal outcome;
- live success, tokens, latency, repeat rate, and recovery cost—not local audit volume—measure capability.

## Benchmark metrics after migration

Every live case reports:

- official success and native-evaluator outcome;
- ordinary, recovery, representation-repair, and provider-transport calls;
- prompt/completion/reasoning tokens by call profile;
- GUI decisions, compound commands, physical receipts, and sent-unknown count;
- exact-repeat, no-effect, route-cycle, recovery-success, and recovery-block counts;
- automatic ActionCandidate rank and explicit discovery usage;
- repeated region/content reads;
- final response send/evaluator counts;
- durable result, cleanup, and viewer status.

Token targets remain benchmark hypotheses, not correctness gates. The primary comparison is task success and cost
against the last stable single-agent baseline under the same model, site, and task cohort.

## Migration risks and trade-offs

### Reduced local assurance

The thin baseline may submit an incomplete or incorrect answer that the old local semantic chain attempted to reject.
This is intentional: the local chain did not possess independent semantic authority and repeatedly rejected correct
progress. The native evaluator remains the authoritative benchmark judge.

### Model-dependent progress judgment

ActionPolicy again owns relevance and completion judgment. Mitigations are aligned current observation, compact
history, automatic candidates, optional exact notes, bounded deliberate recovery, and benchmark evaluation—not a
second semantic state machine.

### Long-horizon limits

Some future W2 tasks may exceed one continuous compact context. Do not retain the current heavy path speculatively.
First measure the thin baseline. If held-out W2 evidence demonstrates a repeated cross-context failure, introduce the
smallest optional offload or recovery port with a new bounded contract and separate ablation.

### Migration churn

Removing contracts affects tests, case schemas, counters, docs, and archived evidence readers. The migration is still
preferable to preserving two control paths. Git history and archived evidence are the rollback mechanism; runtime
feature flags are not.

`target-loop-case.v10` belonged to the removed mission-shaped public case schema. Those JSON artifacts are retained as
raw archival evidence only and are intentionally not accepted by the exact-field current decoder. Decoder compatibility
continues for pre-mission v6-v9 and current v11; archival readability does not imply typed schema compatibility.

## Explicit non-goals

- no task-, site-, label-, selector-, fixed-ref-, or expected-answer-specific logic;
- no attempt to mechanically prove open-world semantic completeness;
- no workflow engine, event ledger, vector database, RAG memory, or cross-case recall;
- no direct composition of Agent-E, WebChallenger, or agent-browser sessions/loops/refs/actions; only their bounded
  observation-delivery algorithms or diagnostic behavior may be adapted at existing owners;
- no arbitrary parallel GUI tools;
- no per-step planner, reflection agent, summarizer, or verifier;
- no weakening of currentness, binding, safety, receipt, stable-observation, persistence, cleanup, or native-evaluator
  boundaries;
- no live benchmark before implementation gates and fresh-context review pass.

## Definition of done

This convergence is complete only when all of the following are true:

1. production composition contains the target single ActionPolicy path and no old mission fallback;
2. all superseded model roles, prompts, state contracts, tool decisions, result projections, and compatibility tests are
   deleted or archived outside production;
3. the supported decision/recovery/finalization algebra is closed and property-tested;
4. current evidence can flow directly to continued action or final response without mandatory pin/audit;
5. optional exact notes work without becoming task-progress authority;
6. multiple provider tool calls are handled within one bounded policy invocation rather than repeated GUI turns;
7. the BrowserGym causal stable-post-state invariant is independently closed;
8. change-first delivery and bounded-workspace properties, W1b-World, full tests, static checks, and independent
   fresh-context review pass;
9. at least one explicitly authorized live witness and one held-out witness demonstrate latest-result salience,
   bounded recovery, and no new
   production specialization;
10. `docs/architecture.md`, `docs/benchmark.md`, this migration document, code, tests, and persisted evidence agree.
