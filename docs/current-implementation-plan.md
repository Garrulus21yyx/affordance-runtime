# Current Implementation Plan

Implementation status: M0-M8.1, M8.2A, and M8.3 are complete for the
controlled web profile. See
[Implementation Status and Forward Gates](implementation-status.md). The next
required increment is M8.2B public benchmark expansion. M9 is conditional on
measured restart/waiting evidence; production-scale options remain non-blocking.

## 1. Authority

This document is the implementation profile for the current repository. It is
the plan contributors should follow when deciding what to build now.

The [Complete Architecture Blueprint](complete-architecture-blueprint.md)
describes a possible production-scale destination. It does not create current
release requirements. When the two documents differ, this implementation plan
wins until a production feature is explicitly promoted through the decision
gate in the main [Project Plan](project-plan.md).

The governing strategy is:

```text
complete vertical loop
limited horizontal breadth
```

The runtime must demonstrate reliable execution, evaluation, diagnosis, and
controlled evolution end to end. It does not need distributed infrastructure
or many interchangeable implementations of every component.

## 2. Product Definition

Affordance Runtime is a single-process, asynchronous, planner-neutral GUI agent
harness runtime. It converts DOM, visual, accessibility, and WoT observations
into versioned affordances, executes one validated Action Contract at a time,
verifies effects, records evidence, evaluates traces, and regression-gates
harness improvements derived from failures.

The complete product loop is:

```text
UserRequest or parent TaskSpec
  -> Intent Compiler
  -> immutable TaskSpec
  -> Observe
  -> Affordance Snapshot
  -> Generalist Planner Proposal
  -> Grounder / ContractBuilder
  -> Action Contract
  -> Policy + Preflight
  -> Route + Execute
  -> Post-Action Observe
  -> Verify
  -> Recover / Continue / Finish
  -> Trace
  -> Benchmark
  -> Failure Classification
  -> Skill / Policy / Verifier Proposal
  -> Regression Replay
  -> Accept / Quarantine / Reject
```

The implementation is a modular monolith:

```text
User / Parent Agent / Benchmark
                |
                v
       Reference Intake or PlannerPort
                |
                v
          RunCoordinator
     observe / gate / act / verify
        /          |           \
   Adapters     Trace Store   Recovery
        \          |           /
                Evaluator
                    |
              Evolution Gate
```

## 3. What Must Exist

The following capabilities are required to prove the project thesis:

| Capability | Current implementation target |
| --- | --- |
| Task intake | sourced user request, ambiguity-aware compiler, immutable versioned `TaskSpec` |
| Unified Affordance Model | common envelope plus typed DOM, visual, accessibility, and WoT payloads |
| Planner boundary | environment-general `PlannerPort` returning semantic proposals, with scripted, LM, parent-agent, and benchmark adapters |
| Contract building | deterministic proposal-to-`ActionContract` binding; no LM output executes directly |
| Coordinator | one authoritative state writer and action scheduler per run |
| Action Contract | the only object that may enter an executor |
| State validity | snapshot identity, page revision, target fingerprint, and expiration |
| Policy | task constraints, capability checks, and approval for effectful actions |
| Execution routing | Playwright DOM first; visual and WoT as bounded adapter proofs |
| Verification | receipt separated from independent postcondition evidence |
| Recovery | small deterministic matrix with explicit budgets and no blind effectful retry |
| Trace | append-only event log plus artifact references |
| Evaluation | resettable fixtures, baselines, perturbations, ablations, and independent oracles |
| Evolution | failure classification, declarative artifact proposal, replay, and registry decision |

## 4. What Is Intentionally Narrow

Each required capability begins with one useful implementation:

| Area | First implementation |
| --- | --- |
| Planner | scripted diagnosis planner plus one provider-neutral `GeneralistLMPlanner`; framework adapters stay optional |
| Browser backend | Playwright |
| DOM observation | Playwright DOM and accessibility state |
| Visual adapter | Set-of-Marks fixture-level grounding |
| WoT adapter | Thing Description parser plus local device fixture |
| State | in-memory `RunState` for one active run |
| Trace | JSONL and filesystem artifacts |
| Benchmark | three local SaaS scenarios |
| Recovery | stale, locator, modal, timeout, verifier, and capability cases |
| Evolution | declarative skill, policy, verifier, affordance-rule, or fixture patches |
| External interface | CLI first; task-level MCP later |

Completeness comes from connecting these components, not from adding many
providers, frameworks, backends, or services.

## 5. Core Runtime

### 5.1 Coordinator Rule

Each run has one `RunCoordinator` that owns authoritative state transitions and
dispatches every executable contract. Other components return immutable
observations, proposals, decisions, receipts, or reports.

```text
Parent Agent -> task, context, approval
Planner      -> proposal
Policy       -> allow, deny, or approval required
Executor     -> execution receipt
Verifier     -> verification report
Recovery     -> bounded recovery proposal
Coordinator -> only component that advances RunState
```

The planner cannot grant capability or execute actions. The executor cannot
reinterpret a contract. The verifier cannot mutate task state.

### 5.2 Runtime State Machine

The current implementation uses one task-level state machine:

```text
CREATED
OBSERVING
PLANNING
PREFLIGHT
WAITING_APPROVAL
ACTING
VERIFYING
RECOVERING
DONE
FAILED
ABORTED
```

Main path:

```text
CREATED -> OBSERVING -> PLANNING -> PREFLIGHT
        -> ACTING -> VERIFYING -> OBSERVING | PLANNING | DONE
```

Control and failure paths:

```text
PREFLIGHT -> OBSERVING          stale or expired state
PREFLIGHT -> WAITING_APPROVAL   approval required
PREFLIGHT -> ABORTED            policy denied
ACTING -> RECOVERING            execution failed or became uncertain
VERIFYING -> RECOVERING         expected effect not established
RECOVERING -> OBSERVING         bounded recovery is safe
RECOVERING -> FAILED            budget exhausted or risk too high
```

Browser and container availability remain ordinary runtime fields until an
independent worker actually exists.

### 5.3 RunState and Memory

`RunState` stores only information needed for the next safe decision:

```text
run_id, task_spec, phase
current observation, snapshot, contract
constraints, capabilities, pending approval
active subgoal, obligations, evidence refs
step and recovery budgets
latest receipt and verification
final result
```

Memory has three practical layers:

| Layer | Contents |
| --- | --- |
| Working state | current goal, constraints, snapshot, contract, evidence obligations, and budgets |
| Episodic trace | all events and artifact references from this run |
| Accepted harness knowledge | regression-approved skills, policies, verifier rules, and fixtures |

Raw DOM, screenshots, downloads, and complete histories are stored as artifacts,
not accumulated in `RunState`. No vector database is required for the current
runtime.

### 5.4 Task Intake and Generalist Planner

The full current specification is
[Task Intake and Generalist Planner](task-intake-and-planner.md).

The legacy `TaskEnvelope(goal: str)` and scripted planners remain compatibility
scaffolding. M8.2A completed the following boundary:

```text
UserRequest
  -> LLMIntentCompiler
  -> IntentDraft
  -> deterministic ambiguity/policy validation
  -> immutable TaskSpec revision
  -> GeneralistLMPlanner
  -> PlannerProposal
  -> deterministic ContractBuilder
  -> ActionContract
```

The compiler may request clarification but cannot grant capability. The planner
may propose a semantic action but cannot bind authority, select an unchecked
surface payload, or execute it. BrowserGym and AgentLab are benchmark adapters
to this boundary, not the product definition.

## 6. Affordance and Contract Model

### 6.1 Affordance

The shared envelope supports common routing, policy, trace, and evaluation:

```text
id, surface, kind, label, semantic role
state, confidence, risk
backend candidates, evidence refs
snapshot id, target fingerprint
typed payload
```

Typed payloads preserve surface detail:

```text
DOM: locator candidates, role/name, form context, uniqueness
Visual: bbox, mark id, screenshot ref, descriptor
Accessibility: role/name/path, enabled/focused state
WoT: href, operation, method, schemas, security metadata
```

### 6.2 Validity Boundary

The first implementation uses:

```text
snapshot_id
page_revision
target_fingerprint
expires_at
artifact content hash
```

Preflight checks that the snapshot is current, the lease has not expired, the
target fingerprint still matches, preconditions hold, and capability/approval
is valid. More revision dimensions are introduced only if benchmark evidence
shows this representation is insufficient.

### 6.3 Action Contract

An Action Contract binds semantic intent to an executable target and verifier:

```text
schema_version, contract_id, run_id
snapshot_id, page_revision, target affordance, target fingerprint
intent, action, backend, parameters
preconditions, expected effects, verifier plan
required capabilities, risk, approval binding
idempotency key, compensation, timeout
```

Contract data is immutable after approval and must be canonicalizable for
hashing and trace replay.

## 7. Execution, Verification, and Recovery

Execution follows:

```text
pre-observation
  -> policy and preflight
  -> execute contract
  -> ExecutionReceipt
  -> post-observation
  -> VerificationEvidence
  -> VerificationReport
```

An executor receipt proves a technical attempt, not task success. Verification
states are `PASSED`, `FAILED`, `INCONCLUSIVE`, and `ERROR`.

The first verifier set is deliberately small:

- DOM state and URL verifiers
- fixture API or database verifier
- file/download receipt and hash verifier
- screenshot evidence verifier
- model judgment only as weak supporting evidence

Recovery is bounded:

| Failure | Response |
| --- | --- |
| stale snapshot | re-observe and replan |
| locator missing | rebuild affordances, then one backend fallback |
| blocking modal | apply a registered low-risk modal policy or ask/abort |
| execution timeout | observe first, then decide whether retry is safe |
| inconclusive verification | gather one stronger evidence source, then replan/fail |
| capability denied | request approval or abort |

Effectful actions are never blindly retried after timeout or uncertain
execution.

## 8. Async and Docker Boundary

The runtime uses `async` I/O while preserving serial action semantics:

```text
one run
one coordinator
one browser session
one active Action Contract
```

Read-only observation capture, independent verifiers, and artifact hashing may
run concurrently when they refer to the same observation epoch. State mutation,
approval consumption, effectful execution, compensation, and trace sequencing
remain serial.

Docker is used for reproducibility and isolation. M8.1 added a deliberately
small profile:

```text
docker compose
  fixture-web
  runtime-test
  benchmark
  shared artifact volume
```

The fixture keeps canonical state in its in-memory server, so the plan does not
invent a fixture database. The profile pins Playwright/Chromium, runs as a
non-root user, exposes a health check, and writes the same reports/artifacts as
host execution. Official benchmark stacks may join through optional profiles
or an external network.

Docker is not used to create scheduler, coordinator, browser-worker,
event-broker, or memory microservices. M8.1 exits when a clean checkout passes
`docker compose build`, `docker compose run --rm runtime-test`, and
`docker compose run --rm benchmark`.

An optional `wot-proof` profile selectively migrates the old repository's
mature node-wot fixture and the minimum dashboard surface needed for a
cross-surface test. It is not the default product demo and does not copy the old
root Dockerfile or Compose topology wholesale.

The conformance task exposes one reversible state through three surfaces:

```text
DOM dashboard control
real screenshot / SoM control
WoT Thing Description operation
             |
             v
same TaskSpec, capability, expected effect, and independent state oracle
             |
             v
same ActionContract envelope, Coordinator, verifier, trace, and evaluator
```

DOM remains the primary real-browser path; visual remains a controlled
screenshot-grounding path; WoT remains a non-Web adapter proof. The gate proves
shared harness semantics, not equal product maturity across all three.

## 9. Trace, Benchmark, and Evolution

### 9.1 Trace

Canonical run storage is an append-only `events.jsonl` file plus artifacts:

```text
artifacts/<run_id>/
  run.json
  events.jsonl
  observations/
  screenshots/
  dom/
  receipts/
  downloads/
  eval_report.json
```

Events cover observation, snapshot, proposal, contract, policy/preflight,
approval, execution, verification, recovery, and final result. Parent links may
derive causal views without requiring a graph database.

### 9.2 Benchmark

The primary fixtures are:

1. read-only pricing extraction
2. reversible settings update
3. approval-gated report export

The core comparison is Direct Playwright versus Affordance Runtime. Required
ablations are no preflight, no structural verifier, no capability gate, and no
recovery.

Release-facing metrics are limited to:

```text
task_success_rate
stale_detection_recall
verifier_false_accept_rate
constraint_violation_rate
recovery_success_rate
regression_delta
```

Latency, cost, action count, observation count, and fallback count remain
supporting telemetry.

MiniWoB++ is a secondary generalization suite, not a replacement for the local
SaaS fixtures. The M8 adapter pins the official Farama source, owns episode
start/reset, instruction extraction, termination/reward collection, artifact
capture, diagnostics, and report aggregation, and covers click, type, select,
dialog, sequence, and form across three seeds. It is labelled a curated runtime
subset, never a full MiniWoB++ score.

The public benchmark ladder after M8 is:

```text
PR smoke: current 6 MiniWoB++ task families x 3 seeds
Nightly: at least 30 MiniWoB++ task types x 10 seeds
Release: every task supported by the pinned BrowserGym adapter x 5 seeds

External:
  ScreenSpot full offline grounding
  WorkArena L1
  WebArena-Verified stratified subset, then hard subset
  WASP security subset
  VisualWebArena after multimodal action routing is stable
  OSWorld only as a future cross-application boundary
```

BrowserGym is the preferred environment adapter where it already owns reset,
task registration, and benchmark semantics. Affordance Runtime still owns
affordance conversion, contracts, policy/preflight, verification, recovery,
trace, and diagnostics. Unsupported families are reported rather than silently
omitted. Official scores and harness fault-injection scores are separate.

### 9.3 Controlled Harness Evolution

The evolution loop is required, but it operates on declarative artifacts rather
than arbitrary source-code mutation:

```text
failed trace
  -> classify perception / planning / grounding / execution /
     verification / recovery / safety failure
  -> propose Skill, PolicyPatch, VerifierPatch, AffordanceRule,
     or BenchmarkFixture
  -> replay the original failure and related task family
  -> run safety smoke tests
  -> accept, quarantine, reject, or roll back
```

A failure classifier and a report comparing an existing full-runtime variant
against a broken ablation are useful prototype evidence, but do not yet prove
self-evolution. The claim requires a typed artifact with executable payload,
loading it into a fresh candidate runtime, rerunning the suites, persisting the
registry decision, and proving rollback.

M6 first proved the loop for a structural `verifier_patch`. M8.3 extends it to
bounded recovery: attempts are grouped into an incident, repeated signatures
and oscillation are detected, root cause is separated from symptoms, and
declarative recovery skill/policy payloads are executable.

```text
trace events -> RecoveryIncident -> FailureSignature per attempt
  -> repeat / no-progress / A-B oscillation detector
  -> root failure plus symptom chain
  -> declarative RecoveryPolicyPatch or Skill
  -> fresh original/family/global/safety replay
  -> accept, quarantine, reject, or roll back
```

Online behavior only detects and safely aborts a repeated cascade within the
existing recovery budget. Learning remains offline and regression-gated.

## 10. Milestones

### M0: Design Alignment - done

Freeze one state machine, current wire contracts, trace schema, scenario specs,
and declarative evolution artifact schema.

### M1: Web Runtime Core - done

Deliver the pricing fixture, Playwright observer/executor, DOM affordances,
scripted planner, contract/preflight, post-action verification, artifact-backed
trace, CLI, and Direct Playwright baseline.

### M2: Reliability and Cross-Surface Proof - done through M8

The three local scenarios and 3 x 7 matrix run successfully across three
distinct seeded layouts. SoM and WoT prove common contract reuse; M8 adds a
real screenshot-pixel visual grounding path and held-out layout evidence.

### M3: Assisted Evolution Prototype - done through M6

Implemented: classification, proposal types, direction-aware gates,
replay-category accounting, and before/after reporting.

M6 applied a SHA-bound executable verifier proposal to a fresh candidate,
generated new replay traces, persisted the registry decision, and proved
rollback.

### M4: Local Integration Boundary - done through M7

Implemented: in-process task service, bounded parent-agent-shaped tool adapter,
external task JSON-RPC, and a real LangGraph parent in a separate process. The
parent has no access to primitive click/type/observe operations.

### M5: Evidence Freeze - done

- commit the current implementation as a reviewable unit
- add CI for tests, Ruff, mypy, package build, and focused Chromium smoke
- record runtime commit, browser version, fixture version, and seed semantics
- publish reproducible benchmark and evolution summaries
- keep README and status claims aligned with generated evidence

Exit: a clean checkout reproduces the local gold path, 3 x 7 matrix, and
evolution prototype.

Evidence: `./scripts/reproduce_local.sh` passed from a clean clone at commit
`4528f25baab0778a6eec4ce37a9fba82f2a7635e`; see
`evidence/m5-4528f25.md`. That historical M5 report records
`label_only_v1`; M8 supersedes current seed semantics with
`deterministic_distinct_layout_v2`.

### M6: Executable Harness Evolution - done

- add an executable payload for at least one verifier or policy patch
- load it into a fresh candidate runtime
- replay original, task-family, global-smoke, and safety-smoke suites
- persist artifact/registry versions and demonstrate rollback

Exit: one failed trace produces an applied artifact that fixes the failure with
zero safety regression.

Evidence: a clean clone at `4cccc96a0dc14ebdd5c11f03896ff307835ad69c`
loaded `verifier_patch-reversible_settings_update@1.0.0` into a fresh
no-verifier runtime, produced six new Chromium traces across all mandatory
categories, persisted acceptance, and proved runtime plus registry rollback.
See `evidence/m6-4cccc96.md`.

### M7: Real Parent-Agent Integration - done

Expose the bounded API through MCP or an equivalent external protocol. One real
Codex, Claude, OpenHands, or LangGraph parent must complete the pricing flow and
the approval-gated export flow while Runtime remains authoritative.

Evidence: a clean clone at `9a9796e66be882b03a9f8059e89dbb22c9e5b056`
compiled LangGraph 1.2.9 and called a separate runtime process through
`affordance-task-rpc/1.0`. Pricing succeeded; export stopped for scoped
approval and then succeeded with file-hash evidence; only eight task-level
tools were exposed. See `evidence/m7-9a9796e.md`.

### M8: Generalization Evaluation - done

- make seeds produce distinct fixture variants
- add unseen layouts or hidden perturbations
- add a pinned official MiniWoB++ adapter and repeated curated subset
- cover click, type, select, dialog, sequence, and form families
- add a real visual grounding path, not only a static SoM contract proof
- report official MiniWoB success/reward and runtime failure diagnostics

Evidence: `./scripts/reproduce_local.sh` passed from a clean clone at
`e463e160aea9c151667877d5aac40995196075a9`. It produced three distinct
training layout fingerprints and 63 accepted matrix runs; six successful
held-out scenario runs; five successful screenshot-grounded visual runs with
five distinct boxes and no DOM coordinates; and 18/18 raw-reward-successful
episodes over six task families from official Farama commit
`eb59fed60fabe8951350275ba8650633b740013b`. See
`evidence/m8-e463e16.md`.

### M8.1: Reproducible Container Profile - done

- add a pinned Playwright/Chromium Dockerfile, `.dockerignore`, and Compose
- provide fixture, test, and benchmark services with mounted artifacts
- run non-root, add fixture health/reset, and record environment identity
- keep public benchmark stacks as optional profiles or networks
- add an optional `wot-proof` profile from the audited node-wot fixture
- run one reversible cross-surface task through DOM, real screenshot/SoM, and
  WoT without bypassing the Coordinator

Exit: a clean checkout reproduces tests and the local benchmark in containers,
with host/container agreement on outcomes and oracle decisions. The optional
cross-surface run reaches the same oracle state through all three surfaces and
emits contract-compatible, verifier-backed traces for each backend.

Clean commit `40fd93b` passed this exit gate with 58 container tests, a 63-run
benchmark matching the host report on every stable outcome/oracle field, and
DOM, screenshot/SoM, and real node-wot traces against one shared oracle. See
`evidence/m8.1-40fd93b.md`.

### M8.2: Generalist Planning and Public Benchmark Expansion - in progress

#### M8.2A: Task Intake and Generalist Planner - done

Implement the schemas and gates in
[Task Intake and Generalist Planner](task-intake-and-planner.md):

- compile raw requests into sourced, ambiguity-aware, versioned `TaskSpec`;
- keep requested capability distinct from granted authority;
- return semantic `PlannerProposal` rather than a ready contract;
- bind proposals through a deterministic `ContractBuilder`;
- add provider-neutral `ModelPort`, `LLMIntentCompiler`, and
  `GeneralistLMPlanner`;
- retain scripted, parent-agent, and AgentLab benchmark adapters;
- trace prompt/model/schema versions and proposal-to-contract lineage;
- evaluate intent compilation, canonical-task planning, and end-to-end behavior
  separately.

Exit: raw natural language completes read-only, reversible-write,
approval-gated, and cross-surface tasks through the full Coordinator; blocking
ambiguity stops safely; clarification revisions invalidate stale proposals; no
LM output grants authority or bypasses contracts; compiler and planner failures
are attributable separately from runtime failures.

Evidence: `docs/evidence/m8.2a-7edaa97.md` records the controlled 30-request
Mistral compiler suite, verified local SaaS read/write/approval paths, common
DOM/SoM/WoT GeneralistLMPlanner tests, and an official BrowserGym smoke through
the same planner boundary.

#### M8.2B: Public Benchmark Expansion - in progress

Before scaling public suites, complete this bounded consolidation gate:

- align README, implementation status, evidence wording, and executable
  verification commands with the current repository;
- use the committed Web or BrowserGym reproducibility constraints when
  rebuilding evidence, so Pydantic, LangGraph, Pillow, and test tooling cannot
  silently change; the two Playwright profiles remain isolated;
- retain the completed BrowserGym split across action schema, environment
  adapter/episode execution, matrix/checkpoint, and MiniWoB task source;
  public facade imports and runtime behavior remain stable;
- replace the first-sorted-task nightly selection with a versioned,
  action-family-stratified manifest;
- rerun the current generalist-planner PR profile before scaling: the latest
  complete evidence is 18/18 episode coverage and 15/18 official success, with
  the form/slider gap still explicit;
- keep `RunCoordinator` free of benchmark-specific branches. External suites
  provide task sources, environment adapters, artifacts, and official
  evaluators;
- add a screenshot-capable `VisualGrounderPort` before claiming an official
  ScreenSpot prediction result.

This gate is an internal cleanup, not a framework redesign. Do not add a
scheduler, worker pool, second state machine, distributed event bus, or
benchmark-specific Coordinator path.

- use the implemented BrowserGym adapter to route every supported action
  through the full coordinator path and keep the scored policy external
- cover focusable keyboard controls through the semantic `press_key` proposal
  action; it may carry only a key value and is bound to a current affordance
- keep 18 episodes for PR smoke; add 30 task types x 10 seeds nightly
- release-test every supported pinned MiniWoB task x 5 seeds
- retain the implemented coverage, unsupported-action, variance, official
  reward, and runtime-failure report fields while scaling the matrices
- add ScreenSpot, WorkArena L1, a 30-50 task WebArena-Verified subset, and a
  WASP security subset in that order
- defer VisualWebArena and OSWorld until their prerequisite layers are stable

Exit: no scored task-specific regex/selector solver remains, every episode
traverses the full runtime path, official/injected suites are separate, the
environment and model manifests are reproducible, and unsupported action
families remain visible rather than being silently excluded.

Recommended execution order:

```text
generalist PR rerun and form semantics
  -> resumable 30 x 10 MiniWoB nightly
  -> ScreenSpot assets and visual grounding
  -> M8.4 adaptive shallow-planning controlled gate
  -> one real WebArena-Verified task, then the 30-task subset
  -> WASP security subset
  -> WorkArena when authorized access is available
```

### M8.3: Recovery-Cascade Evolution - done

- normalize a `FailureSignature` from phase, error, action/backend, target,
  verifier, and relevant state revision
- group causally related attempts into a `RecoveryIncident`
- detect repeated signatures, no-progress recovery, A-B oscillation, repeated
  stale contracts/verifier failures, and fallback exhaustion
- preserve root failure separately from secondary recovery symptoms
- report cascade depth, repeated-failure rate, loop aborts, duplicate-effect
  risk, and recovery-action effectiveness
- implement narrow executable `RecoveryPolicyPatch` and `Skill` schemas
- replay original, family, global smoke, and safety smoke in a fresh runtime

Exit: one real repeated recovery failure produces a quarantined artifact; the
accepted candidate breaks the loop or reduces cascade depth, adds no unsafe
effect or blind retry, persists its decision, and rolls back.

Clean commit `07e406f` meets this exit. The baseline Coordinator records one
incident and aborts the repeated/no-progress cascade at depth two. A
digest-validated policy patch is first persisted as quarantined, then loaded
into fresh original/family/global/safety candidates; it reduces the matched
cascades to depth one, preserves the successful global path, explicitly
observes uncertain effect before failing safe, persists acceptance, and is
removed by a verified rollback. See `evidence/m8.3-07e406f.md`.

### M8.4: Adaptive Shallow Task Planning - planned

Implement the bounded design in
[Task Intake and Generalist Planner](task-intake-and-planner.md):

- route simple tasks to one synthetic subgoal and exact accepted templates to a
  deterministic `RuleTaskPlanner`;
- use `LLMTaskPlanner` only for open-world, multi-stage, cross-application, or
  data-dependent tasks;
- validate rule, LM, parent, and evolution plans through one deterministic
  `TaskPlanValidator`;
- represent 3-8 outcome-oriented subgoals with optional `depends_on`, while
  executing one ready subgoal at a time;
- keep the existing `GeneralistLMPlanner` as the one-action planner inside each
  subgoal;
- let verifier evidence, never planner self-report, advance plan progress;
- reserve task-level replanning for disproved assumptions, exhausted subgoal
  budgets, TaskSpec revision, missing mandatory stages, or repeated-error
  incidents;
- compare Flat, Always-plan, and Adaptive profiles.

Exit: simple tasks retain the flat path; at least one controlled long-horizon
family improves without regressing short-task safety; traces distinguish task
planning, action planning, local recovery, and task-level replanning.

This milestone does not add recursive hierarchy, parallel effectful subgoals, a
generic DAG scheduler, one agent per node, continuous watching, or a runtime
framework dependency.

### M9: Durable Single-Run Recovery - conditional

Promote only after restart, approval-wait, or uncertain-effect tests expose a
real need. Use a simple durable store for run state, events, idempotent commands,
and effect inspection. Do not add a worker pool or distributed queue.

### PiP Decision Gate

PiP remains optional. It is an observer/human-takeover UI, not browser isolation
or a second runtime. Begin it only if M7 testing shows trace streaming and the
normal run console are insufficient.

## 11. Explicitly Deferred

- durable run queue and scheduler
- browser worker pool and independent browser RPC
- worker lease, heartbeat, and fencing token
- distributed checkpoint and takeover
- multi-tenant authorization and quotas
- Kubernetes, Kafka, or a distributed event bus
- multiple planners competing online for one browser session
- multiple agents controlling the same page
- unrestricted cross-run vector memory
- automatic arbitrary source-code mutation
- continuous watcher until it beats post-action observation
- Picture-in-Picture implementation before the M4 entry conditions and a
  demonstrated standalone or human-takeover use case

These remain available in the complete blueprint. They become current work only
after a measured bottleneck, a scenario requirement, and an explicit project
plan update justify them.
