# Affordance Runtime Project Plan

> **Lifecycle:** CURRENT PRODUCT ROADMAP
> **Updated:** 2026-08-08
> **Target:** [Unified World Interface and E2E AgentLoop Architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)
> **Migration authority:** [Evolution Plan](superpowers/plans/2026-08-05-task-contract-centered-runtime-architecture-evolution-plan.md)

## 1. Product position

Affordance Runtime is the common world interface between an agent policy and
heterogeneous GUI/device environments. Its value is measured by whether the
same policy can efficiently observe, act, and verify across DOM, Accessibility,
Visual, SVG, WoT, API, and Device surfaces.

The durable product shape is a lightweight modular monolith with a short loop,
not an event-sourced workflow engine or authorization platform.

Its organizing principle is:

```text
responsibility-thin, semantics-strong intake
+ capability-thick, infrastructure-thin execution loop
```

Intake protects stable meaning and boundaries. Execution intelligence is
concentrated in observation, grounding, action-space generation, route
selection, post-action evaluation, and fact-driven replanning.

## 2. Product contracts

The stable target vocabulary is:

```text
semantically strong TaskGoal + risk-proportionate MaterialBindings
optional EvaluationSpec / strict source lineage
optional TaskPlan<Milestone> + LocalObjective
WorldObservation + Internal ActionSpace
disposable AgentContext + opaque ContextIdentity
bounded IntentContext + progress/world/history/pending/budget views
AgentActionPageView + typed AgentDecision
SemanticTarget + ActionBinding
ActionSpace + ActionIntent
BoundActionRequest + ActionResult
ActionEvaluation + TaskEvaluation
AgentLoopState + Turn
HumanConfirmation + optional TurnRecorder
bounded ActionBatch + evaluated memory/Skill sidecars
```

Surface-specific payloads remain below the world interface. Strict source
provenance and structured completion rules are opt-in profiles, not mandatory
core contracts for every GUI task.

## 3. Delivery phases

| Phase | Outcome | Status |
|---|---|---|
| P4 baseline | Existing serial path preserves final-request identity, stale zero-call, receipt/effect separation, output integrity, and unknown no-retry | retained baseline |
| P5-A | Documentation reset; strong TaskGoal/risk profiles and minimal world/action contracts | target contracts integrated non-default |
| P5-B | Symmetric SurfaceAdapter interface across DOM/AX/Visual/SVG/WoT/API/Device/CLI | DOM, Visual-only, and WoT local-simulation minimums integrated non-default; other surfaces pending |
| P5-C | Positive DOM, Visual, and WoT vertical loops using the same policy/evaluator | shared-state adapter-only matrix proven for DOM, Visual, and WoT; no fusion claim |
| P5-D | Semantic human confirmation, current rebind, unknown-effect and evaluator cutover | complete, non-default |
| P5-D6.1 | General semantic confirmation and evidence-bound evaluation contracts | complete, non-default |
| P5-M0 | Model-safe policy views and evidence-validated evaluator boundary | complete, non-default |
| P5-M0.1 | Unified disposable AgentContext, ContextIdentity, bounded intent/world/history, relevance, paging, source assurance and typed decisions | complete, non-default |
| P5-M0.1.1 | One-shot context epochs, fresh observation identity, traversable cursor paging and coherent bounded projections/history | complete, non-default |
| P5-M1 | Model-backed target AgentPolicy using deterministic evaluators | complete |
| P5-M1.1 | Existing ModelPort bridge and invocation hardening | complete for strict boundary and local HTTP transport; live provider unavailable |
| P5-M2 | Production evaluator composition and criterion adjudicators | complete for declared minimum profiles; general entailment partial |
| P5-M3 | New-loop benchmark harness | not started; next admitted slice |
| P5-M3 | New-AgentLoop harness and fixed BrowserGym/MiniWoB smoke | not started; external admission blocked |
| P5-E | Milestone planning, LocalObjective, bounded context and long-horizon evaluation | not started |
| P5-F | Strictly bounded no-observation-barrier ActionBatch | isolated helper prototype exists; AgentLoop integration not started |
| P5-G | Currentness-checked memory/Skill with offline promotion | BindingCache prototype exists; target integration not started |
| P5-H | Surface breadth, default cutover, telemetry downgrade and old-core deletion | not started |

The detailed order and exit/deletion gates live only in the evolution plan.

## 4. Product success measures

Primary measures:

- cross-surface task success;
- steps and observations to completion;
- targeted-observation rate and information gain;
- model calls and visual calls;
- latency and execution failures;
- wrong-route and fallback counts;
- human-confirmation count and correctness;
- unknown-effect handling without duplicate action;
- long-horizon constraint retention, milestone verification, and ask-user correctness;
- batch utilization and cache-currentness hit/rejection rates.

Secondary engineering measures include contract size, default-path imports,
adapter conformance, and deletion of legacy owners. Delta/event/commit counts
are not product measures.

## 5. Correctness requirements

Every phase preserves observation-bound request identity, stale zero-call,
semantic confirmation identity with current rebinding, model/binding separation, result/effect/completion
separation, fresh post-action observation, unknown no-retry, required-output
integrity, and benchmark neutrality.
AgentContext remains a one-way disposable projection; every decision binds the
current context ID, LocalObjective changes relevance only, and source assurance
never grants execution authority.
Each policy call receives a new one-shot generation even when its public
projection is otherwise identical. Runtime-issued paging cursors bind filters,
objective identity and exact membership; they are not durable state.

## 6. Non-goals

- durable ledger, checkpoint/resume, or event sourcing without an admitted fault model;
- distributed/multi-writer transaction protocol;
- global authorization-proof or capability-token platform;
- prompt-injection classification as the Runtime architecture center;
- mandatory full TaskPlan or strict source graph for ordinary GUI tasks;
- trace or external reward as online execution/completion authority.

## 7. Program completion

The program reaches this target when the default product path uses the unified
world contracts and short AgentLoop, the DOM/AX/Visual/SVG/WoT positive matrix
succeeds with only adapter variation, the local correctness invariants remain
verified, a long-horizon task and bounded Batch/Skill gates pass, and the old StateKernel/delta/committer/recovery-transaction chain no
longer appears in the default import or call path.
