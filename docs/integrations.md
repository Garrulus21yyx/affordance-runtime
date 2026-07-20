# Integrations

## 1. Integration Principle

Affordance Runtime should be callable by existing agents without requiring them
to adopt its internal architecture.

The parent agent sends a bounded task. The runtime returns a structured result,
evidence, trace id, and any required follow-up decision.

## 2. Interfaces

Current implemented interface:

```text
TaskRuntimeService
  submit / execute / get_run / approve / cancel
  get_result / get_evidence / get_trace

TaskToolAdapter
  gui_submit_task / gui_execute_task / gui_get_run / gui_approve_task
  gui_cancel_task / gui_get_result / gui_get_evidence / gui_get_trace
```

`LocalScenarioTaskRunner` connects this interface to the real Chromium runtime.
`ExternalTaskProtocol` exposes the same eight operations over newline-delimited
JSON-RPC `affordance-task-rpc/1.0`. The server runs in a separate process and
also owns the local fixture and browser sessions.

Run the real external LangGraph proof with:

```bash
python scripts/langgraph_parent_smoke.py --output evidence/parent
```

The compiled graph completes pricing, retrieves result/evidence/trace, submits
an export, observes `waiting_approval`, supplies a scoped approval, then
retrieves the verified download evidence. `gui_click`, `gui_type`, and
`gui_observe` are not present in external tool discovery.

### 2.1 CLI

```bash
affordance-runtime run \
  --task "Open the pricing page and extract plan limits" \
  --target "https://example.com" \
  --read-only
```

### 2.2 Optional REST Transport

```http
POST /v1/tasks
GET /v1/runs/{run_id}
GET /v1/traces/{trace_id}
POST /v1/evals
```

### 2.3 External Task JSON-RPC and Optional MCP Mapping

Implemented protocol methods:

```text
runtime/info
tools/list
tools/call
shutdown
```

Each request and response uses JSON-RPC 2.0 on one line. This is the current
equivalent external protocol required by M7. MCP can map the same stable tool
schemas later without changing runtime authority.

Optional MCP mapping:

Tools:

```text
gui_run_task
gui_get_run
gui_get_evidence
gui_get_trace
gui_replay_trace
gui_run_eval
```

Production MCP should expose task-level APIs. Low-level primitives such as
`gui_observe`, `gui_click`, and `gui_type` can exist as internal/debug tools,
but they should not be the primary external contract because they bypass the
State Kernel, Affordance Lease, Capability Gate, Action Contract, and Verifier
Ladder.

### 2.4 LangGraph Parent - implemented

The M7 parent is a compiled LangGraph 1.2 graph whose nodes call the external
task protocol:

```text
Agent State
  -> discover task tools
  -> submit / execute pricing
  -> collect result / evidence / trace
  -> submit / execute export
  -> approve export
  -> collect result / evidence / trace
```

LangGraph never receives a browser session or primitive action executor. The
runtime process remains the sole execution authority.

### 2.5 Codex / Claude Tool Adapter

The runtime should expose a simple tool call:

```json
{
  "task": "Find the latest invoice and download it.",
  "constraints": {
    "read_only_until_download": true,
    "no_payment": true
  }
}
```

Return:

```json
{
  "status": "success",
  "result": {},
  "trace_id": "run_001",
  "evidence": [],
  "artifacts": []
}
```

### 2.6 OpenHands / Coding Agent Adapter

Coding agents often need a browser or GUI operator for:

- local app verification
- UI regression checks
- documentation search
- admin panel setup
- browser reproduction

Affordance Runtime can act as a browser/GUI subagent with strict trace and
approval boundaries.

## 3. Parent-Agent Contract

Parent agents should receive only decision-relevant events:

```text
success
failed
blocked
needs_approval
needs_user_login
needs_parent_context
unsafe_action_blocked
```

They should not receive raw low-level event streams unless explicitly requested.

## 4. Safety Constraints

The interface should support constraints:

```json
{
  "read_only": true,
  "no_purchase": true,
  "no_delete": true,
  "no_external_message": true,
  "require_approval_for": ["payment", "delete", "submit_application"]
}
```

## 5. Standalone vs Subagent

### Standalone

The runtime owns the task loop and reports the final result.

### Subagent

The parent agent owns the broader goal. The runtime owns bounded GUI execution.

This separation is important. Affordance Runtime should not pretend to be the
entire agent stack when it is being used as an execution substrate.
