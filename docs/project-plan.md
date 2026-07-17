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

The repository should be described as an executable skeleton until the Web gold
path, task loop, and benchmark runner exist.

Implemented skeleton:

- typed affordance, contract, receipt, trace, risk, and metric models
- migrated DOM, Set-of-Mark, and WoT adapter code
- single-contract execution path useful for debug and unit testing
- initial capability gate, preflight, verifier, state, trace, and evolution
  structures

Partial:

- State Kernel semantics across multiple contracts
- Affordance lease semantics beyond revision equality
- task constraints and approval token binding
- metric aggregation without full benchmark protocol

Planned before claiming a complete runtime:

- Playwright observer and executor
- task-level run context and explicit state machine
- post-action observation and verification reports
- artifact-backed trace writer
- local SaaS fixture and benchmark runner
- CLI gold path
- bounded recovery policy
- baseline and ablation reports
- task-level MCP interface
- assisted harness evolution after benchmark freeze

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
| v0.2 Reliability | prove runtime differentiators | stale injection, selector drift, modal recovery, approval gate, benchmark report | REST, many framework adapters, desktop/mobile |
| v0.3 Integration | bounded parent-agent use | task-level MCP, run/evidence/trace fetch | public low-level click/type tools |
| v0.4 Assisted Evolution | learn from failed traces | proposal generation, quarantine registry, regression replay | automatic production mutation |

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

The project should not claim complete harness evolution until v0.4 evidence
exists.

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

### M2: Runtime Reliability

Objective: prove the runtime adds value beyond direct browser automation.

Deliverables:

- settings and report-export fixtures
- stale target, selector drift, modal, and delayed receipt perturbations
- capability and approval gate
- bounded recovery policies
- JSON/Markdown/CSV benchmark reports
- ablation runs

Exit criteria:

- all three scenarios run under fixed seeds
- independent oracle checks are used for grading
- unsafe side effects remain zero
- ablation shows which runtime layers matter

### M3: Subagent Interface

Objective: expose the runtime as a bounded task-level tool.

Deliverables:

- MCP task API: submit bounded task, get status, fetch result, fetch evidence,
  fetch trace
- optional REST only if the MCP contract has stabilized
- parent-agent event statuses: success, failed, blocked, needs_approval,
  needs_user_login, needs_parent_context, unsafe_action_blocked

Exit criteria:

- a parent agent can submit a bounded task without access to raw click/type
  primitives
- all returned results include evidence and trace references

### M4: Assisted Harness Evolution

Objective: turn failed traces into reviewed, regression-tested harness artifacts.

Prerequisites:

- stable trace schema
- resettable benchmark environment
- at least N classified failures
- deterministic enough regression runs
- one manually designed patch has passed the gate

Deliverables:

- failure classifier
- proposal generator
- quarantine registry
- regression gate
- before/after report

Exit criteria:

- at least one failed trace becomes a quarantined or accepted fixture, skill,
  policy patch, or verifier patch
- no artifact is accepted without replay and safety checks

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

## 12. Presentation Boundary

Use engineering evidence language in README and interviews:

```text
designed and prototyped a planner-neutral GUI execution runtime skeleton
```

Use stronger implementation claims only after the relevant gold path, benchmark,
trace artifacts, and reports exist.
