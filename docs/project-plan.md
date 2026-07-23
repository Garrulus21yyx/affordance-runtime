# Affordance Runtime Project Plan

## 1. Positioning

Affordance Runtime is a planner-neutral GUI execution runtime. It can be used by
a parent agent, a local reference planner, or a benchmark harness, but its core
responsibility is the execution layer rather than general task intelligence.

Primary product:

```text
planner-neutral GUI execution runtime
```

Reference application:

```text
a minimal standalone planner used for local demos and benchmarks
```

External usage:

```text
parent agents submit bounded GUI tasks and receive result, evidence, trace, and
approval/blocking decisions
```

The project should not be positioned as a direct replacement for PageAgent,
browser-use, Stagehand, Skyvern, OpenHands, or OSWorld. Those systems are useful
reference points, baselines, or integration targets.

### 1.1 Plan Authority and Two Horizons

The project uses two compatible planning horizons:

- [Current Implementation Plan](current-implementation-plan.md): the
  authoritative plan for current code, milestones, and release claims.
- [Complete Architecture Blueprint](complete-architecture-blueprint.md): a
  non-blocking reference for a future durable, multi-run, service-grade system.

Repository governance, current correctness work, selective C009 reuse, and
claim/evidence gates are maintained in the Governance and Correctness Gates
section of the current implementation plan. Two documents are jointly
normative:

- [Runtime-First Architecture Boundary](runtime-first-boundary.md);
- [Benchmark Governance and Anti-Specialization Boundary](benchmark-governance-boundary.md).

They prohibit hard and behaviorally equivalent soft specialization. Every
benchmark-discovered repair requires non-benchmark conformance, paraphrase or
distractor controls when applicable, safety evidence, and only then benchmark
confirmation. Benchmark score is audit evidence, not the product objective.

They are not competing designs. The complete blueprint preserves production
reasoning; the current plan deliberately implements a smaller topology while
retaining the complete domain loop.

```text
Current implementation:
  complete vertical harness loop
  limited horizontal infrastructure

Complete blueprint:
  future operational scaling options
  no current release obligation
```

If the documents differ, the current implementation plan wins. A blueprint
feature becomes current work only when:

1. a benchmark, integration, or operational failure requires it
2. the current simpler design has been measured and shown insufficient
3. the feature has explicit ownership, persistence, and safety semantics
4. this project plan is updated with entry criteria and exit evidence

Affordance Runtime defines the lower execution layer:

```text
high-level task
  -> environment observation
  -> affordance modeling
  -> action contract
  -> capability / safety gate
  -> preflight revalidation
  -> grounded execution
  -> post-action observation
  -> postcondition verification
  -> bounded recovery / replan / ask / abort
  -> trace / evaluation
  -> assisted harness evolution
```

## 2. Problem

GUI agents fail in predictable ways:

- They click the wrong element because visual grounding or DOM selection is
  unstable.
- They treat a dynamic environment as a frozen screenshot.
- They execute actions without explicit preconditions or expected effects.
- They cannot explain which observation caused an action.
- They report success from a click receipt instead of independent verification.
- They lose constraints such as read-only or approval-required across long
  tasks.
- They cannot replay a failure deterministically.
- They fix one failure without turning it into a reusable regression case.
- They are difficult to plug into existing agent frameworks as a bounded,
  auditable subagent.

Affordance Runtime solves this by treating GUI control as a harnessed execution
problem, not only as a prompting problem.

## 3. Core Thesis

Reliable GUI agency requires a typed, versioned, and verifiable action
substrate.

The central abstraction is:

```text
Task Envelope
  -> State Kernel
  -> Budgeted Observation
  -> Versioned Affordance Snapshot
  -> Planner Port
  -> Action Contract
  -> Capability / Safety Gate
  -> Preflight Revalidation
  -> Execute
  -> Execution Receipt
  -> Post-Action Observation
  -> Verification Report
  -> State Kernel Update
  -> Recover / Ask / Abort
  -> Trace Events
  -> Evaluation
  -> Assisted Evolution Proposal
  -> Replay + Regression Gate
  -> Versioned Harness Artifact
```

The agent should not only decide what to do. The runtime must know:

- what action space is available
- which backend can execute each action
- what must be true before acting
- what should change after acting
- how to detect relevant environmental drift
- when an affordance snapshot or target is stale
- which capabilities and approvals are required
- when to recover, replan, ask the parent agent, or abort
- how to evaluate a trace after the run

## 4. Current Status

The controlled web profile is complete through M8.1, with claims split by
evidence level. See
[Implementation Status and Forward Gates](implementation-status.md).

| Area | Status | Evidence boundary |
| --- | --- | --- |
| M0 Design Freeze | done | contracts, state machine, trace schema, scenarios, and gates are tested |
| M1 Web Gold Path | done | real Chromium pricing path, artifacts, verification, and baseline |
| M2 Local Reliability | done | three local scenarios and 3 x 7 comparison matrix pass |
| M3/M6 Assisted Evolution | done | SHA-bound executable verifier artifact passes fresh mandatory replay and persisted rollback |
| M4/M7 Integration Boundary | done | external task RPC and real LangGraph parent complete pricing and gated export |
| M5 Evidence Freeze | done | CI, package build, manifests, versioned reports, and clean-checkout reproduction |
| M8 Generalization | done | distinct and held-out layouts, real screenshot grounding, and 18 pinned official MiniWoB++ episodes |
| M8.1 Container Reproducibility | done | digest-pinned non-root Compose profile, 63-run host/container agreement, real DOM/visual/WoT conformance at `40fd93b` |
| M8.2A Task Intake and Planner Contracts | partial / reopened | typed intake, TaskSpec revision, semantic proposal binding, and provider-neutral ports exist; default planner behavior is not yet strict-generalist |
| M8.2B Public Benchmark Audit | paused | historical smoke, PR, nightly, and release reports remain revision/profile evidence; score promotion waits for M8.6 |
| M8.3 Recovery-Cascade Components | partial / reopened | incident detection, lower-half recovery, executable artifacts, replay, and rollback exist; full-phase online recovery waits for M8.6 |
| M8.4 Adaptive Shallow Task Planning | component done | TaskPlan, validation, criteria-bound progress, lineage, and reference evidence exist; normal benchmark entrypoint integration waits for M8.6 |
| M8.5 Unified Adaptive Routing and Skill Internalization | component done | unified candidates, routes, gestures, visual/WoT paths, trace mining, accepted profiles, fallthrough, and rollback exist |
| M8.6 Generalist Planner, Active Perception, and Full-Phase Recovery Governance | in progress | strict-generalist separation, benchmark identity isolation, bounded evidence-gap repair, full-phase Recovery Coordinator, complete-run audit, and generalization proof are the current hard gate |

M9 durable single-run recovery remains conditional on a measured restart or waiting
failure.

Current seeds create deterministic distinct local variants, and M8 adds unseen
layouts and screenshot grounding. SoM and WoT also prove common contract reuse
in controlled tests. Distributed service infrastructure, desktop/mobile
expansion, arbitrary source mutation, and PiP remain future options.

## 5. Modes

### 5.1 Reference Standalone Mode

The runtime ships with a minimal reference planner so local demos can run without
an external agent:

```text
Task:
  Open the pricing page, compare the enterprise and pro plan limits, and return
  screenshots as evidence.
```

The reference application executes:

```text
observe -> model -> propose contract -> act -> verify -> recover -> report
```

This mode is for demonstration and benchmarks. It does not make the runtime a
complete general-purpose agent.

### 5.2 Subagent / Tool Mode

A parent agent calls the runtime with a bounded task:

```json
{
  "task": "Find the pricing page and extract plan limits.",
  "target": "https://example.com",
  "constraints": {
    "read_only": true,
    "no_purchase": true
  }
}
```

The runtime returns:

```json
{
  "status": "success",
  "result": {
    "plans": []
  },
  "evidence": ["artifacts/run_001/step_008.png"],
  "trace_id": "run_001",
  "actions": [],
  "postconditions": []
}
```

### 5.3 Harness Evaluation Mode

The runtime executes benchmark tasks under a controlled harness:

```text
task suite
  -> environment setup
  -> runtime execution
  -> independent oracle / postcondition check
  -> failure classification
  -> metrics report
  -> regression replay
```

## 6. MVP Boundaries

The first project line is realistic Web/SaaS GUI work. Smart-room/WoT remains a
secondary non-web adapter proof, not the main story.

| Release | Purpose | Required | Deferred |
| --- | --- | --- | --- |
| v0.1 Core | one read-only Web gold path | DOM observation, Playwright execution, Action Contract, preflight, post-action verification, trace writer, CLI | SoM, event bus, MCP, WoT, evolution |
| v0.2 Reliability and surface proof | prove runtime differentiators and contract reuse | stale injection, selector drift, modal recovery, approval gate, benchmark report, bounded SoM and WoT proofs | REST, many framework adapters, desktop/mobile |
| v0.3 Assisted Evolution | learn from failed traces | classification, declarative proposal, quarantine registry, regression replay | automatic production mutation |
| v0.4 Optional Integration | bounded parent-agent use | task-level MCP, run/evidence/trace fetch, optional LLM or LangGraph adapter | public low-level click/type tools |

## 7. Scenario Specs

The MVP is anchored by three local SaaS scenarios:

- [Pricing Extraction](scenarios/pricing-extraction.md): read-only evidence
  extraction.
- [Reversible Settings Update](scenarios/settings-update.md): controlled write
  with persisted-state verification.
- [Approval-Gated Report Export](scenarios/approval-gated-report-export.md):
  side effect only after explicit approval and file/audit receipt.

Each scenario defines initial state, constraints, capabilities, perturbations,
oracle, budgets, trace expectations, pass criteria, and failure conditions.

## 8. Success Criteria

The v0.1 Core succeeds only if it can:

1. Run the pricing extraction scenario from one command.
2. Produce result, evidence artifacts, and trace artifacts.
3. Bind each action contract to observation, snapshot, and revision identity.
4. Reject stale or expired actions before execution.
5. Execute through Playwright with post-action observation.
6. Verify success using structural evidence rather than click receipt alone.
7. Preserve read-only constraints across the task.
8. Compare against a direct Playwright baseline.

The v0.2 Reliability release succeeds only if it can additionally:

1. Run all three local SaaS scenarios.
2. Pass injected stale target, selector drift, modal, and delayed receipt cases.
3. Enforce capability and approval policy.
4. Produce a benchmark report with defined denominators and independent oracles.
5. Show ablations for no lease, no verifier, no capability gate, and no recovery.
6. Show that visual and WoT affordances can enter the same contract, trace, and
   evaluation path without becoming separate product lines.

The v0.3 Assisted Evolution release succeeds only if one real failed trace is
classified, converted into a declarative skill, policy, verifier, affordance,
or fixture proposal, replayed against the original and related scenarios, and
accepted or quarantined with a reproducible report.

The project should not claim complete harness evolution until this v0.3
evidence exists. MCP, LangGraph, and additional framework adapters do not block
that claim.

## 9. Milestones

### M0: Design Freeze and Status Alignment

Objective: make the plan precise enough to constrain implementation.

Deliverables:

- `docs/design-freeze.md`
- scenario specs for the three Web/SaaS tasks
- status matrix separating implemented, partial, planned, and deferred
- system invariants
- revision model
- recovery decision matrix
- baseline and ablation plan

Exit criteria:

- README and docs no longer imply planned features are already implemented.
- Every MVP demo has an oracle and pass/fail criteria.
- Every core abstraction maps to a hypothesis or invariant.

### M1: Web Gold Path

Objective: complete one read-only Web task end to end.

Entry criteria:

- contract schema frozen for v0.1
- pricing fixture spec frozen
- trace minimum schema frozen

Deliverables:

- local pricing fixture
- Playwright observer and executor
- DOM affordance builder
- reference planner or scripted planner
- post-action verifier
- trace writer
- CLI command
- direct Playwright baseline

Exit criteria:

- one command completes pricing extraction repeatedly in a fixed environment
- result, screenshots, DOM/artifact refs, and trace are emitted
- read-only constraint has zero violations
- stale perturbation is blocked or re-observed before action

Explicitly deferred:

- visual fallback
- event bus / continuous watcher
- MCP
- WoT
- evolution

### M2: Runtime Reliability and Cross-Surface Proof

Objective: prove the runtime adds value beyond direct browser automation.

Deliverables:

- settings and report-export fixtures
- stale target, selector drift, modal, and delayed receipt perturbations
- capability and approval gate
- bounded recovery policies
- bounded visual SoM adapter proof using the shared affordance and contract path
- bounded local WoT fixture proof using the shared policy, trace, and evaluation
  path
- JSON/Markdown/CSV benchmark reports
- ablation runs

Exit criteria:

- all three scenarios run under fixed seeds
- independent oracle checks are used for grading
- unsafe side effects remain zero
- ablation shows which runtime layers matter
- DOM, visual, and WoT payloads preserve surface-specific data while reusing
  common contract, trace, and evaluation semantics

### M3: Assisted Harness Evolution - done through M6

Current evidence: typed classification/proposals, direction-aware gates,
replay-category accounting, and a before/after report.

Completed exit criteria:

- proposal contains an executable declarative payload
- a fresh candidate runtime loads that payload
- original, family, global-smoke, and safety-smoke suites rerun
- registry decision persists and rollback is demonstrated

### M4: Local Integration Boundary - done through M7

The in-process task service, bounded tool adapter, external JSON-RPC, and real
LangGraph parent are implemented. The parent submits, approves, and retrieves
result/evidence/trace without primitive GUI tools.

### M5: Evidence Freeze - done

Deliver CI, package-build checks, an environment manifest, clean-checkout
reproduction, and versioned benchmark/evolution summaries. Exit when the local
gold path, 3 x 7 matrix, and evolution prototype reproduce from a documented
revision.

### M6: Executable Harness Evolution - done

Materialize a verifier or policy artifact, apply it to a fresh candidate runtime,
persist the decision, replay all mandatory categories, and prove rollback. This
closes the M3 claim gap.

### M7: Real Parent-Agent Integration - done

Expose the bounded task API through MCP or an equivalent protocol and connect
one real Codex, Claude, OpenHands, or LangGraph parent. Complete pricing and
approval-gated export with evidence and trace retrieval. This closes M4.

### M8: Generalization Evaluation - done

Deliver distinct seeded variants, unseen layouts/hidden perturbations, a pinned
official MiniWoB++ adapter, and a real visual grounding path.

The MiniWoB++ work is a curated runtime-diagnostics subset:

- official source is pinned and unmodified
- adapter owns episode start/reset, instruction, termination, reward, and trace
- repeated tasks cover click, type, select, dialog, sequence, and form families
- reports contain official success/reward plus runtime diagnostics
- results are never presented as a full MiniWoB++ leaderboard score

At clean commit `e463e16`, the three-seed 63-run local matrix, six held-out
scenario runs, five screenshot-grounded visual runs, and 18 official episodes
across all six curated families passed. The official source is pinned at Farama
commit `eb59fed60fabe8951350275ba8650633b740013b`; the result remains a curated
runtime subset rather than a full-suite leaderboard claim.

### M8.1: Container Reproducibility - done

Add a pinned Playwright/Chromium Dockerfile and a small Compose profile for the
in-memory fixture, tests, and benchmark. Use a non-root runtime, health checks,
deterministic reset, and mounted artifacts. Do not add a scheduler, worker pool,
message broker, or fictional fixture database.

Add an optional `wot-proof` profile by selectively migrating the audited
node-wot fixture and only the dashboard surface needed for conformance. A single
reversible task must run through DOM, real screenshot/SoM, and WoT while sharing
TaskSpec, capability policy, Action Contract envelope, Coordinator, verifier,
trace schema, evaluator, and an independent state oracle. Direct executor
shortcuts do not count.

Exit when a clean checkout runs tests and the local benchmark through Compose,
produces oracle-equivalent host/container reports, and records successful
verifier-backed traces for all three surfaces. This proves shared harness
semantics, not equal backend maturity.

Clean commit `40fd93b` satisfies the exit gate: 58 container tests and build,
63 accepted benchmark runs with exact stable host/container agreement, and
three verifier-backed traces against the same node-wot oracle. See
`evidence/m8.1-40fd93b.md`.

### M8.2: Generalist Planning and Public Benchmark Expansion - in progress

#### M8.2A: Task Intake and Planner Contracts - component done; behavior reopened under M8.6

The authoritative
[Task Intake and Generalist Planner](task-intake-and-planner.md) specification
is implemented. Raw `goal: str` authority is replaced by a sourced,
ambiguity-aware, immutable
`TaskSpec`; add `LLMIntentCompiler`, provider-neutral `ModelPort`, and
`GeneralistLMPlanner`; change planner output from executable contract to
semantic `PlannerProposal`; and bind it through deterministic
`ContractBuilder`.

The reference path is environment-general and must complete real local Web and
DOM/visual/WoT tasks. Parent agents may submit a validated `TaskSpec`.
AgentLab remains a BrowserGym planner/baseline adapter rather than the product
planner.

Exit when natural language reaches verified results for read-only,
reversible-write, approval-gated, and cross-surface cases; blocking ambiguity
and policy conflict stop safely; TaskSpec revisions invalidate stale proposals;
and all model/proposal/contract lineage is traceable.

#### M8.2B: Public Benchmark Expansion - paused behind M8.6

First complete a bounded consolidation pass:

- reconcile README/status claims and verification commands with the current
  test count and M8.2A completion;
- lock result-bearing Python dependencies;
- split BrowserGym benchmark responsibilities without changing runtime
  semantics;
- freeze a versioned, action-family-stratified nightly task manifest;
- rerun the current generalist PR profile and retain the form/slider failure as
  an explicit gap until it is solved semantically;
- retain the implemented screenshot-to-point `VisualGrounderPort` before
  ScreenSpot predictions;
- keep suite-specific reset, task, trace, and evaluator code outside
  `RunCoordinator`.

The core architecture remains a single-process modular monolith with one
authoritative Coordinator and one Action Contract at a time. The consolidation
pass must not introduce production-service infrastructure.

The isolated BrowserGym 0.14.3 full-Coordinator bridge, typed action whitelist,
external-policy boundary, and real one-task smoke are implemented. Existing
18-episode, PR, nightly, and release reports remain historical profile evidence.
Do not expand or promote scores until M8.6 closes.

No task-specific regex, selector solver, or behaviorally equivalent task-family
semantic compiler may be the strict-generalist scored path. Calendar,
autocomplete, quantity, sorting, hierarchy, disclosure, form, copy, social, and
drag programs do not become general merely by living in a shared planner module
or omitting benchmark ids.

#### M8.2B Reliability Blocker

The current gate is not resolved by increasing the 150-second episode timeout.
Diagnostics separate three blockers: Gemini free-tier quota exhaustion before
action, an Ollama container whose exposed GPU cannot initialize NVML and
therefore loads with zero VRAM residency, and a Runtime semantic gap that can
treat transport success as effect success and repeat an already-satisfied
action.

Before another scored matrix, complete the detailed
`M8.2B.1 Provider and Runtime Reliability Gate` in
`current-implementation-plan.md`: action-specific postcondition verification,
deterministic no-progress blocking, bounded planner context and deadlines,
typed quota handling, and either a repaired GPU-local path or one
quota-sufficient pinned remote provider. Re-run one task, six tasks, and 18
episodes before nightly and release expansion. Diagnostic 300-second runs and
operational provider fallback are not score-equivalent to the fixed
single-provider benchmark profile.

Then add ScreenSpot, WorkArena L1, a 30-50 task stratified
WebArena-Verified subset followed by its hard subset, and a WASP security
subset. VisualWebArena waits for stable multimodal routing; OSWorld remains a
future boundary. Official and fault-injected reports stay separate.

### M8.3: Recovery-Cascade Evolution - component and artifact path done

Recovery is now stateful across attempts through normalized signatures and a
single causal incident. Recovery skills and policy patches are executable only
through narrow declarative, digest-validated payloads.

`RecoveryIncident` and normalized `FailureSignature` detect repeated
failures, unchanged-state recovery, A-B oscillation, repeated stale contracts,
repeated verifier failures, and exhausted fallback. Preserve root failure and
the symptom chain separately. Generate a declarative `RecoveryPolicyPatch` or
`Skill`, replay it in a fresh candidate against original, family, global, and
safety suites, persist the decision, and prove rollback.

Clean commit `07e406f` satisfies the exit: one real repeated-error cascade is
safely stopped online, classified offline, reduced from depth two to one by an
accepted policy artifact, and shown through fresh replays, persisted registries,
uncertain-effect inspection, and rollback not to introduce duplicate effects,
blind retries, or safety regressions. See `evidence/m8.3-07e406f.md`.
The evidence above closes the lower-half incident, policy-artifact, and replay
path only. It does not prove that intake, observation, task planning, step
planning, proposal validation, binding, provider/context, and accepted-skill
failures enter one online Recovery Coordinator. That full-phase integration is
reopened under M8.6.

### M8.4: Adaptive Shallow Task Planning - component done

Add an optional task-level layer above the implemented action planner. A
deterministic router keeps simple tasks flat, uses accepted rule/skill templates
for exact cases, and calls an LM task planner only for open-world or multi-stage
work.

Every source produces the same immutable, versioned `TaskPlan` with 3-8
outcome-oriented `SubgoalSpec` items and optional `depends_on`. A
deterministic validator rejects cycles, stale revisions, unbounded plans,
unverifiable outcomes, constraint loss, authority grants, selectors,
coordinates, and executable actions. The Coordinator executes one ready
subgoal at a time through the existing observe/propose/contract/preflight/act/
post-observe/verify loop; only verifier evidence advances progress.

The controlled Flat/Always-plan/Adaptive experiment proves sequencing. R1 binds
fresh strong evidence explicitly to every mandatory Subgoal and SkillStep
obligation. R2 supplies bounded planning context, evidence-aware replanning,
monotonic plan lineage, verified-progress preservation, and a real
non-BrowserGym Chromium multi-stage path. See
`evidence/runtime-r2-task-planning-context-20260722.md`. Do not add a generic DAG scheduler,
recursive hierarchy, parallel effectful nodes, per-node agents, or continuous
watching.

### M8.5: Unified Adaptive Routing and Skill Internalization - component done

M8.5 implements the project's intended unified behavior rather than treating
DOM, SVG, visual, and WoT as unrelated demos. One semantic target may expose
multiple typed GroundingCandidates from DOM, accessibility, SVG geometry, SoM,
pure visual, WoT, or API evidence. A task-aware PerceptionOrchestrator acquires
sources lazily; a SemanticEntityResolver preserves provenance and conflicts;
an Adaptive Route Planner applies capability, freshness, confidence, verifier,
and risk gates before ranking viable perception/grounding/executor/verifier
routes.

The planner and accepted skills specify semantic target queries and desired
effects, never selectors, coordinates, backends, or authority. RoutePlan owns
ordered alternatives; each ActionContract binds exactly one fresh candidate.
Fallback after missing/stale grounding creates a new observation, route, and
contract. Timeout or uncertain effect requires post-state inspection before
retry or cross-surface reroute, and policy denial can never be bypassed through
another backend.

Complete the SVG/visual route with a selective SvgGeometryObserverPort,
VisualRegionProposerPort, VisualGrounderPort, and deterministic
VisualContractBinder. A subgoal requiring `visual + spatial` captures
DOM/accessibility, SVG geometry when present, and screenshot artifacts in one
coherent observation epoch, then creates visual/SVG GroundingCandidates under
the relevant UnifiedAffordance.

The planner proposes semantic POINT_ACTIVATE or DRAG over target/source ids and
never emits raw coordinates. The binder maps the selected current candidate to
`click`/`drag_and_drop` when reliable bids exist, `mouse_click` for a grounded
point, or a bounded visual drag gesture. Every route creates a fresh
ActionContract and traverses preflight, execution, post-observation, independent
verification, trace, and recovery. Visual evidence may be primary for
appearance, layout, vibe, SVG/canvas spatial tasks, or remote-rendered controls
rather than only a last fallback.

Add two separate regression-gated learning streams:

~~~text
repeated independently verified success
  -> parameterized semantic TaskSkill candidate

repeated FailureSignature / RecoveryIncident
  -> RecoverySkill or RecoveryPolicyPatch candidate

candidate
  -> quarantine
  -> original, family, held-out, global, and safety replay
  -> accept, reject, remain quarantined, or roll back
~~~

TaskSkill stores typed parameters, ordered semantic SkillSteps, preconditions,
postconditions, evidence requirements, capabilities, risk, applicability, and
negative examples. It never stores raw selector, coordinate, mark id, WoT URL,
browser handle, or approval token. An accepted skill executes one verified step
at a time and asks Unified Routing to ground each step in the current
environment. A failed step retains prior verified progress, enters the existing
Recovery Cascade, and may fall through to System 2 planning.

Accepted TaskSkill and calibrated route hints form the System 1 normal fast
path; accepted RecoverySkill/Policy forms the known-failure fast path;
Generalist task/action planning, stronger perception, VLM grounding, and
ask-user handling form System 2. Every path still creates fresh contracts and
passes policy, preflight, execution, and verification.

Entry retains the implemented M8.3 cascade and existing M8.4 planning
components, but M8.4 criteria-bound progression is now a shared completion
gate. Exit requires a cheap
structured primary route, a task-driven visual-primary case, verified
DOM-to-visual fallback, an authoritative WoT/API selection, zero blind
duplicate effects, one accepted held-out TaskSkill that reduces model calls or
latency without safety regression, and skill failure that safely resumes System
2 or Recovery Cascade.

The detailed contracts, fallback matrix, phased implementation, baselines,
metrics, and acceptance criteria are authoritative in
`current-implementation-plan.md`.

The prior `evidence/m8.5-completion-audit-20260722.md` remains component and
perturbation evidence rather than the closure proof. Runtime-first R1-R8 are
complete; R8 module containment closed with TaskPlanLifecycle,
PerceptionSession, ContractExecutionLoop, and read-only RecoveryHandler
collaborators plus a separated generalist PlannerContextBuilder, typed default
SemanticCompiler registry factory, and stateless model/schema repair
orchestrator, plus adapter-owned BrowserGym observer, encoder, episode runner,
versioned protocol, and report/taxonomy modules, in
`current-implementation-plan.md`, with findings in
`current-architecture-audit-20260722.md` and closure evidence in
`evidence/runtime-r8-closure-20260722.md`. BrowserGym nightly and public suites
remain evaluation gates under M8.2B, not substitutes for Runtime completion.

### M8.6: Generalist Planner, Active Perception, and Full-Phase Recovery Governance - in progress

M8.6 is the current hard gate. M8.2B score promotion and new task-family repair
are paused until it closes. The authoritative diagnosis is
[Planner, Recovery, and Benchmark Governance Audit](planner-recovery-governance-audit-20260723.md);
the normative control design is
[Active Perception and Online Recovery Architecture](active-perception-and-online-recovery.md).

#### Objective

Make the declared Runtime chain true in normal, parent-agent, and benchmark
entrypoints:

~~~text
UserRequest
  -> IntentCompiler
  -> TaskSpec
  -> optional shallow TaskPlan
  -> active SubgoalSpec
  -> PerceptionRequirements
  -> coherent multi-source observation and assertion arbitration
  -> bounded active perception when evidence is insufficient
  -> generalist semantic proposal
  -> PlannerProposalValidator
  -> unified candidate binding
  -> ActionContract
  -> policy / preflight / execute / post-observe / verify
  -> on any failure: FailureEnvelope
  -> full-phase Recovery Coordinator
  -> validated command + receipt + non-empty RecoveryDelta
  -> normal-loop re-entry / ask / abort
  -> trace and controlled learning
~~~

The default path must generalize to unseen real interfaces. BrowserGym and
public suites audit this path; they do not define it.

#### Entry diagnosis

- default semantic compilers can implement behaviorally task-specific calendar,
  autocomplete, quantity, sorting, hierarchy, disclosure, form, copy, social,
  and drag programs before an LM is called;
- negative probes show unrequested disclosure activation, over-broad field
  filling, and prefix-to-submit scope expansion;
- BrowserGym audit identity and incorrect blanket read-only classification can
  enter planner-facing TaskSpec fields;
- the BrowserGym Coordinator is created without the optional TaskPlanner;
- planner exceptions and proposal-binding failures usually terminate rather
  than entering Recovery Cascade;
- no-progress handling can reobserve and call the same planner without changing
  a semantic assumption;
- existing recovery signatures and artifacts are strong but mainly cover the
  contract/execution/verification half of the chain.

#### G0: Freeze and classify

Freeze current scores as historical revision/profile evidence. Inventory every
active compiler, prompt, skill, provider, and registry digest. Classify rules as
standards, safety, accepted skill, compatibility, or suspected task grammar.

Exit when every report identifies its profile and registry, and no new
task-family repair enters the default planner.

Current evidence: the R10 clean nightly is frozen as historical compatibility
evidence, and new runs bind planner profile plus compiler registry digest.
Legacy report inventory remains open.

#### G1: Strict-generalist profile

Make strict-generalist the default product and scored profile. Permit only
protocol/schema normalization, standards-based control semantics, safety and
authority rules, and accepted regression-gated skills.

Move historical task-family compilers behind an explicit compatibility profile.
Add behavioral tests for paraphrases, distractors, extra controls, ambiguity,
unrelated interfaces, unrequested terminals, and scope expansion.

Exit when known negative probes defer, clarify, or act only on authorized
targets, and strict-generalist passes non-BrowserGym Web, visual, and WoT
conformance.

Current implementation: strict-generalist is the default and cannot load the
non-empty historical compatibility registry. Compatibility is explicit and
cannot claim a generalist score. One shared PlannerProposalValidator now gates
all proposal sources, initial task-shape controls pass, and the same strict
planner passes non-BrowserGym DOM/visual/WoT conformance. Strict uses a separate
Prompt and protocol/current-state-only candidate policy; task-shaped rewrites
remain compatibility-only. Historical objective parsers, terminal exposure,
repair recipes, semantic rewrites, and registry callbacks are now physically
isolated in `compatibility_planner_algorithms.py`; strict import/construction
does not load that module. The complete behavioral control matrix and explicit
proposal-source provenance remain open.

#### G2: Intent and task-planning integration

Separate IntentCompiler, TaskPlanRouter, and GeneralistStepPlanner. Derive
operation class, constraints, and capabilities from typed intent rather than
suite defaults.

Use one flat subgoal for simple tasks, accepted semantic skills when applicable,
and a validated shallow LM TaskPlan only for genuinely multi-stage work.
PlannerProposalValidator applies to deterministic, LM, parent-agent, skill, and recovery
proposals. Effectful actions remain serial.

Wire the same task-plan router into reference, parent-agent, and benchmark
entrypoints. Remove suite identity and official reward from planner context.

Exit when raw natural language reaches a validated TaskSpec, simple and
multi-stage local tasks use the declared chain, plan lineage and evidence-bound
progress are traceable, and planner context has zero benchmark identity leakage.

#### G2.5: Active perception and evidence repair

Active perception is shared Runtime infrastructure, not a planner trick and not
a benchmark adapter fallback. It turns a typed EvidenceGap into the cheapest
permitted read-only ProbePlan, executes it through PerceptionSession, creates a
new coherent observation epoch, and re-runs source arbitration.

It serves four call sites in this order:

1. normal observation for task-required visual, spatial, device, or structural
   evidence;
2. high-risk preflight when freshness, uniqueness, or target state is weak;
3. verification when the current evidence is inconclusive;
4. RecoveryCoordinator when a failure is caused by missing or conflicting
   facts.

The controller must enforce probe capability, observation/time/model budgets,
task relevance, source freshness, and no hidden effectful interaction. A
surviving safety-relevant conflict blocks execution.

Exit when cheap structural paths remain cheap, visual/spatial tasks acquire the
right evidence proactively, bounded probes resolve injected stale/conflicting
sources, and irreducible conflicts end as safe inconclusive results.

#### G3: Full-phase Recovery Coordinator

G3 follows G2.5. Recovery first determines effect status and evidence gaps; it
does not retry, reroute, or replan while the relevant world state is unknown.

Normalize failures from intake, observation, fusion, task planning, step
planning, proposal validation, grounding/binding, preflight, execution,
verification, provider/context, and skill activation.

Another attempt is allowed only when recovery changes observation coverage,
assumption, subgoal plan, grounding candidate, route, verifier, provider/context,
accepted skill use, or user information. Preserve inspect-before-repeat for
effectful actions.

Add semantic cascade keys so equivalent failures are detected even when target
or backend identifiers vary. Explicitly load accepted recovery profiles in
normal entrypoints.

Exit when representative failures in every phase enter one traceable recovery
path, equivalent loops stop before budget exhaustion, no blind duplicate effect
occurs, and recovery proves reobserve, replan, reroute or stronger verify, and
safe ask/abort outcomes.

#### G4: Complete-run result audit

Ordinary episode failures do not stop a diagnostic matrix. Preserve every result,
cluster failures after collection, and resume only unobserved cases.

Fail fast only for safety/authority violations, trace or result corruption,
non-comparable environment drift, profile-wide provider/infrastructure failure,
loss of isolation, or runaway resources.

Reports separate Runtime verification from external reward and record observed,
failed, unrun, invalidated, and resumed counts.

Exit when every scheduled case is accounted for and one complete report groups
cross-task failure clusters by Runtime ownership before any repair is selected.

#### G5: Generalization proof

Evaluate four isolated profiles:

1. strict-generalist;
2. strict-generalist plus accepted skills;
3. historical compatibility;
4. declared ablations.

Use unseen local layouts and vocabulary, paraphrases, distractors, ambiguous and
under-specified tasks, DOM/accessibility/SVG/visual/WoT routes, provider/context
stress, recovery injection, then targeted and breadth external audits.

Exit when strict-generalist results stand alone, accepted skills improve cost or
success without safety regression, compatibility uplift is visible rather than
hidden, and no benchmark score is the sole evidence for a generalization claim.

#### Hard acceptance gates

- benchmark identity leak into planner context: zero;
- unauthorized or unapproved high-risk effects: zero;
- unrequested-action and task-scope-expansion regressions: zero on governance
  controls;
- uncertain effects inspected before repeat: 100 percent;
- every proposal source passes PlannerProposalValidator;
- all active-perception probes are read-only, budgeted, task-relevant, and
  create a new coherent observation epoch;
- unresolved safety-relevant evidence conflict cannot reach an effectful
  ActionContract;
- repeated semantic failure stops or changes strategy before budget exhaustion;
- non-benchmark conformance precedes benchmark replay;
- current status and README claims name the exact active profile and revision.

### M9: Durable Single-Run Recovery - conditional

Promote only after a restart, approval-wait, or uncertain-effect test proves
in-memory state insufficient. Add a simple durable run/event store, idempotent
commands, and post-restart effect inspection. Worker pools, distributed queues,
and multi-tenancy remain in the complete blueprint.

## 10. Non-Goals

Out of scope for the first web releases:

- full desktop OS control
- mobile device control
- unrestricted browsing
- real credential automation beyond safe test fixtures or manual handoff
- real payment, deletion, or external messaging without explicit approval
- autonomous RL training
- production self-modification
- public low-level click/type tools that bypass contracts
- durable queues, worker pools, worker leases, and distributed checkpoints
- multiple planners or agents controlling the same browser session
- multi-tenant infrastructure, Kubernetes, Kafka, or a distributed event bus

## 11. Decision Gates

The plan is allowed to delete ideas when evidence is weak:

- If revision-bound contracts do not improve stale handling over target
  revalidation, simplify the lease model.
- If continuous event watching does not beat post-action observation on selected
  tasks, defer the event bus.
- If visual fallback does not improve task success enough to justify latency,
  move it out of MVP.
- If common affordance fields erase surface-specific information, keep a common
  envelope but split typed payloads.
- If evolution proposals cannot be evaluated reproducibly, keep only manual
  failure analysis and regression fixture generation.
- If a production-blueprint feature has no measured current bottleneck, keep it
  in `complete-architecture-blueprint.md` rather than implementing it.
- If trace streaming and the normal run console provide sufficient observation
  and takeover ergonomics, defer PiP instead of maintaining a second UI surface.

## 12. Presentation Boundary

The required gold path, benchmark, trace artifacts, and reports now exist. Use
engineering evidence language in README and interviews:

```text
implemented and evaluated a planner-neutral GUI execution runtime
```

Keep production-scale claims bounded to the modular-monolith profile; the
complete blueprint remains a future architecture reference.
