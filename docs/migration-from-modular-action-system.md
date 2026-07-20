# Migration From A Modular Action System

The old repository, `Garrulus21yyx/A-Modular-Action-System-Architecture`, is a
smart-room and CUA demo. It proved that a single runtime can perceive DOM,
visual SoM, and WoT device surfaces, route actions across backends, verify
postconditions, and evaluate failures.

Affordance Runtime keeps the reusable core and removes the course/demo-specific
surface area.

## Migrated Concepts

| Modular Action System | Affordance Runtime |
| --- | --- |
| `Affordance` dataclass | `contracts.Affordance` with lease, risk, evidence, and revision |
| DOM Transduction Pattern | `adapters.dom.DomAdapter` |
| Page Affordance Model | `adapters.dom.PageAffordanceModel` |
| Set-of-Marks parser | `adapters.som.SomAdapter` |
| WoT TD parser | `adapters.wot.WotAdapter` |
| Browser session lifecycle | `browser_session.BrowserSession` with an injectable page driver; this is not PiP |
| DOM/visual/WoT executors | `executors.DomExecutor`, `VisualExecutor`, and `WotExecutor` |
| Confidence/cost router | `routing.BackendConfidenceTracker` and `CostAwareRouter` |
| Preconditions/postconditions | safe declarative conditions, `verification.preflight`, and `VerifierLadder` |
| Recovery policy | `recovery.BoundedRecoveryPolicy` with inspect-before-retry semantics |
| Runtime state machine | `runtime.AffordanceRuntime` plus `StateKernel` |
| Trace logger | validated `trace.TraceDag` plus `JsonlTraceWriter` |
| Metrics aggregator | `benchmarks.metrics.aggregate` |

The migration adapts algorithms and tests to the new contracts. It does not
copy the old modules unchanged. Backends now execute an `ActionContract`,
return an `ExecutionReceipt`, and use package-relative public imports under
`affordance_runtime`.

## Picture-in-Picture Clarification

The old repository did not implement Picture-in-Picture. Its
`BrowserSession` created a fresh Playwright browser context and described that
cookie/storage isolation as a "PiP analogue." Session isolation and
Picture-in-Picture are different capabilities.

This migration keeps only the useful session mechanics:

- injectable page driver;
- browser/context ownership and cleanup;
- coherent DOM capture and screenshot access;
- DOM and coordinate action protocols.

It does not migrate the PiP label or claim PiP support. A real PiP capability
would need an independently visible surface or window, content-source updates,
focus and input routing, close/restore lifecycle behavior, and dedicated
evaluation. That feature is outside the current Web gold path until its use
case and acceptance tests are defined.

## Mature Code Migrated in This Pass

- coherent browser-page capture and lifecycle cleanup;
- deterministic DOM action execution with structured receipts;
- visual pointer execution from bounding boxes or centers;
- WoT form execution, minimum-interval gating, and explicit HTTP transport;
- backend confidence decay/recovery and cost-aware selection;
- bounded recovery for stale state, uncertain effects, retries, fallback,
  compensation, approval, and abort;
- safe AST-based condition evaluation instead of `eval`;
- parent-validated JSONL trace persistence;
- the WoT write-surface fix: a read form is no longer silently reused as a
  write form.

These migrated components are now connected by the task-level
observe-plan-preflight-act-observe-verify-recover loop. The migration remains
selective: the legacy demo-specific orchestration listed below is still not
part of the mainline.

## Not Migrated Into The Mainline

- TUM smart-room Docker services.
- Demo cursor animation and presentation-only scripts.
- MiniWoB/WebArena local clones.
- Legacy branch/team workflow notes.
- Course-specific artifacts and screenshots.
- The old `pipeline.py` orchestration and `src.*` import graph.
- Smart-room-specific skill tuples and demo-only action vocabulary.
- Mandatory OpenAI, Anthropic, Playwright, and HTTP client dependencies.
- The old "PiP isolation" label and its incorrect browser-context analogy.

Those pieces are still useful as reference demos, but the new repository should
stay focused on a planner-neutral GUI runtime that can be used standalone or as
a subagent by Codex, Claude, OpenHands, LangGraph, AutoGen, or browser agents.

## Planned Selective Docker Reuse

M8.1 reuses the old environment proof without restoring the old deployment
architecture. The audited node-wot fixture and a minimal dashboard may return
under an optional `wot-proof` Compose profile. The old root Python image, fixed
container names, host-first benchmark flow, presentation scripts, and incorrect
PiP terminology are not migrated.

The acceptance test exposes one reversible state through DOM, real
screenshot/SoM, and WoT. Every path must use the new TaskSpec, Action Contract,
Coordinator, capability gate, postcondition verifier, trace schema, evaluator,
and independent oracle. This turns the old "three backends connect" demo into a
cross-surface harness conformance test.

The maturity claim remains explicit:

| Surface | Required evidence |
| --- | --- |
| DOM | primary real Chromium task loop and public Web benchmark path |
| Visual | real-pixel grounding and controlled cross-surface task |
| WoT | optional containerized adapter/conformance proof |

## New Design Added During Migration

- `StateKernel`: preserves goal, constraints, hidden-state hypotheses,
  evidence, and pending obligations.
- `AffordanceLease`: binds an affordance snapshot to an environment revision and
  TTL.
- `ActionContract`: records backend, preconditions, verifier plan, risk,
  capabilities, idempotency, and compensation.
- `CapabilityGate`: blocks missing permissions and high-risk unapproved actions.
- `VerifierLadder`: prefers structural receipts before weaker observation or
  model-based checks.
- `EvolutionRegistry`: quarantines and regression-gates proposed harness
  improvements.
