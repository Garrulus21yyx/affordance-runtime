# Affordance Runtime Project Plan

## 1. Positioning

Affordance Runtime is a GUI agent execution harness. It can run as an
independent agent, or it can be invoked as a subagent by Codex, Claude,
OpenHands, LangGraph, AutoGen, Browser Use, or other open agent frameworks.

The project should not be positioned as a direct replacement for PageAgent,
browser-use, Stagehand, Skyvern, or OpenHands. Those systems are useful
reference points and possible integration targets.

Affordance Runtime defines the lower execution layer:

```text
high-level task
  -> environment observation
  -> affordance modeling
  -> action planning
  -> grounded execution
  -> postcondition verification
  -> recovery / replan
  -> trace / evaluation
  -> harness evolution
```

## 2. Problem

GUI agents fail in predictable ways:

- They click the wrong element because visual grounding or DOM selection is
  unstable.
- They treat a dynamic environment as a frozen screenshot.
- They execute actions without explicit preconditions or expected effects.
- They cannot explain which observation caused an action.
- They cannot replay a failure deterministically.
- They fix a single failure but do not turn it into a reusable skill or policy.
- They are difficult to plug into existing agent frameworks as a bounded,
  auditable subagent.

Affordance Runtime solves this by treating GUI control as a harnessed execution
problem, not only as a prompting problem.

## 3. Core Thesis

Reliable GUI agency requires a typed action substrate.

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
  -> Effect Receipt
  -> Verifier Ladder
  -> State Kernel Update
  -> Recover / Ask / Abort
  -> Trace DAG
  -> Evaluation
  -> Evolution Proposal
  -> Replay + Regression Gate
  -> Versioned Harness Artifact
```

The agent should not only decide what to do. It must know:

- what action space is available
- which backend can execute each action
- what must be true before acting
- what should change after acting
- how to detect environmental drift
- when an affordance snapshot is stale
- which capabilities and approvals are required
- when to recover, replan, ask the parent agent, or abort
- how to learn from the trace after the run

The project is therefore a planner-neutral execution control plane. It can be
used by a local planner, Codex, Claude, LangGraph, AutoGen, OpenHands, browser
agents, or a benchmark harness.

## 4. Modes

### 4.1 Standalone Agent Mode

The runtime receives a natural language task and controls the environment by
itself:

```text
Task:
  Open the pricing page, compare the enterprise and pro plan limits, and save
  screenshots as evidence.
```

The runtime executes:

```text
observe -> model -> plan -> act -> verify -> recover -> report
```

### 4.2 Subagent / Tool Mode

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

### 4.3 Harness Evaluation Mode

The runtime executes benchmark tasks under a controlled harness:

```text
task suite
  -> environment setup
  -> runtime execution
  -> oracle / postcondition check
  -> failure classification
  -> metrics report
  -> regression replay
```

## 5. MVP Scope

The first version should focus on Web GUI Runtime:

- DOM adapter
- screenshot / Set-of-Marks adapter
- Playwright executor
- Page Affordance Model
- State Kernel
- Affordance Lease
- ActionContractV2
- Capability Gate
- Verifier Ladder
- event bus / runtime state transitions
- Trace DAG
- recovery policy
- evaluation runner
- MCP server
- three demos:
  - read-only evidence extraction
  - reversible settings update
  - approval-gated report export

Out of scope for the first version:

- full desktop OS control
- mobile device control
- full RL training
- autonomous unrestricted browsing
- credential handling beyond manual handoff or safe test fixtures

## 6. Success Criteria

The MVP is successful if it can:

1. Build a stable affordance model from a page.
2. Bind each affordance to an environment revision and lease.
3. Reject stale actions before execution.
4. Execute a multi-step task through action contracts.
5. Detect environmental changes during execution.
6. Verify each step with structural receipts when possible.
7. Recover from at least two common failures.
8. Produce a causal trace DAG.
9. Run a small benchmark suite and aggregate runtime-specific metrics.
10. Convert at least one failed trace into a quarantined skill or policy patch.
11. Expose a task-level MCP or REST interface for parent agents.

## 7. Milestones

### M0: Repo Skeleton

- Package layout under `src/affordance_runtime`.
- Migrated DOM, SoM, and WoT adapters from A Modular Action System.
- Core dataclasses for leases, contracts, receipts, state kernel, trace DAG,
  verifier ladder, capability gate, evolution registry, and benchmark metrics.
- Unit tests for contract stale-state checks, DOM extraction, WoT parsing,
  runtime verification, and benchmark metrics.

### M1: Web Gold Path

- Playwright observer and executor.
- Environment revision hashing from URL, DOM hash, screenshot hash, and visible
  loading state.
- Action contract generation from page affordances.
- Structural verifier ladder for DOM text, URL, download receipt, file receipt,
  network receipt, and screenshot reference.
- Trace writer that stores `trace.json`, screenshots, DOM snapshots, and
  receipts.

### M2: Local Benchmark Harness

- Local SaaS fixture app with pricing, settings, reports, modals, async states,
  selector drift, stale snapshots, and download/export receipts.
- Benchmark runner for read-only extraction, reversible write, approval-gated
  side effect, visual grounding, and recovery tasks.
- Metrics report in JSON, Markdown, and CSV.

### M3: Subagent Interface

- MCP task API: submit a bounded task, poll run status, fetch result, fetch
  evidence, fetch trace.
- REST API with the same task-level semantics.
- Thin adapters for Codex/Claude/OpenHands/LangGraph/AutoGen.
- Keep low-level `click/type` tools internal or debug-only so callers cannot
  bypass leases, capability gates, and verifier plans.

### M4: Harness Evolution

- Failure classifier over trace DAGs.
- Evolution proposal generator for skills, policy patches, verifier patches,
  and benchmark fixtures.
- Quarantine registry with applicability, TTL, negative examples, regression
  results, rollback notes, and accepted version.
- Regression gate that replays the original failure, task-family suite, and
  safety smoke suite before accepting an artifact.

## 8. Resume Positioning

Affordance Runtime should be presented as:

> a GUI agent harness runtime for reliable, verifiable, and evolvable
> environment interaction.

The engineering focus is:

- runtime architecture
- action contracts
- event-driven environment feedback
- failure recovery
- trace and evaluation
- skill mining and harness evolution
- integration with existing agent frameworks

## 9. Demo Story

The strongest internship demo is not "it clicks websites." It is:

1. Parent agent gives a bounded task.
2. Runtime observes the page and creates a versioned affordance snapshot.
3. Planner selects an action contract.
4. Capability gate blocks risky unapproved actions.
5. Preflight rejects stale snapshots when the page changes.
6. Executor acts through DOM or visual fallback.
7. Verifier ladder checks a structural receipt.
8. Trace DAG shows why the action happened.
9. Benchmark runner scores success, safety, recovery, and replay.
10. A failed trace becomes a quarantined harness improvement.

