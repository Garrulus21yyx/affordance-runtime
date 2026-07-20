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

The controlled web profile is complete through M8, with claims split by
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
| M8.1 Container Reproducibility | pending | pinned Playwright image and Compose test/benchmark profile |
| M8.2 Public Benchmark Expansion | pending | BrowserGym MiniWoB scaling plus selected public suites |
| M8.3 Recovery-Cascade Evolution | pending | repeated-error incidents, root-cause classification, executable recovery artifacts |

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

### M8.1: Container Reproducibility - pending

Add a pinned Playwright/Chromium Dockerfile and a small Compose profile for the
in-memory fixture, tests, and benchmark. Use a non-root runtime, health checks,
deterministic reset, and mounted artifacts. Do not add a scheduler, worker pool,
message broker, or fictional fixture database.

Exit when a clean checkout runs tests and the local benchmark through Compose
and produces oracle-equivalent host/container reports.

### M8.2: Public Benchmark Expansion - pending

Use BrowserGym as the preferred environment adapter. Keep the current 18
MiniWoB++ episodes as PR smoke, add at least 30 task types x 10 seeds nightly,
and run every supported pinned MiniWoB task x 5 seeds for release. No
task-specific regex or hardcoded selector solver may be the scored path.

Then add ScreenSpot, WorkArena L1, a 30-50 task stratified
WebArena-Verified subset followed by its hard subset, and a WASP security
subset. VisualWebArena waits for stable multimodal routing; OSWorld remains a
future boundary. Official and fault-injected reports stay separate.

### M8.3: Recovery-Cascade Evolution - pending

Current recovery is bounded but stateless across attempts beyond counters. M6
can replay a verifier patch, but recovery skills and policy patches are not
executable.

Add a `RecoveryIncident` and normalized `FailureSignature`; detect repeated
failures, unchanged-state recovery, A-B oscillation, repeated stale contracts,
repeated verifier failures, and exhausted fallback. Preserve root failure and
the symptom chain separately. Generate a declarative `RecoveryPolicyPatch` or
`Skill`, replay it in a fresh candidate against original, family, global, and
safety suites, persist the decision, and prove rollback.

Exit when one real repeated-error cascade is safely stopped online, classified
offline, fixed by an accepted artifact, and shown not to introduce duplicate
effects or safety regressions.

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
