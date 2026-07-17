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
| Preconditions/postconditions | `verification.preflight` and `VerifierLadder` |
| Runtime state machine | `runtime.AffordanceRuntime` plus `StateKernel` |
| Trace logger | causal `trace.TraceDag` |
| Metrics aggregator | `benchmarks.metrics.aggregate` |

## Not Migrated Into The Mainline

- TUM smart-room Docker services.
- Demo cursor animation and presentation-only scripts.
- MiniWoB/WebArena local clones.
- Legacy branch/team workflow notes.
- Course-specific artifacts and screenshots.

Those pieces are still useful as reference demos, but the new repository should
stay focused on a planner-neutral GUI runtime that can be used standalone or as
a subagent by Codex, Claude, OpenHands, LangGraph, AutoGen, or browser agents.

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

