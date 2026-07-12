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
Environment Surface
  -> Affordances
  -> Action Contracts
  -> Executions
  -> Postconditions
  -> Trace
  -> Evaluation
  -> Evolution
```

The agent should not only decide what to do. It must know:

- what action space is available
- which backend can execute each action
- what must be true before acting
- what should change after acting
- how to detect environmental drift
- when to recover, replan, ask the parent agent, or abort
- how to learn from the trace after the run

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
- action contracts
- postcondition checker
- event bus
- trace logger
- recovery policy
- evaluation runner
- MCP server
- three demos:
  - MiniWoB++ atomic tasks
  - WebArena-style mock task
  - SaaS pricing or invoice extraction task

Out of scope for the first version:

- full desktop OS control
- mobile device control
- full RL training
- autonomous unrestricted browsing
- credential handling beyond manual handoff or safe test fixtures

## 6. Success Criteria

The MVP is successful if it can:

1. Build a stable affordance model from a page.
2. Execute a multi-step task through action contracts.
3. Detect environmental changes during execution.
4. Verify each step with postconditions.
5. Recover from at least two common failures.
6. Produce a replayable trace.
7. Run a small benchmark suite and aggregate metrics.
8. Convert at least one failed trace into a reusable skill or policy patch.
9. Expose an MCP or REST interface for parent agents.

## 7. Resume Positioning

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

