# Agent Orchestration and Live Feedback

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** serial Runtime loop, phase results, feedback, continuation, and commit ordering

## 1. Main loop

```text
capture canonical observation
→ trigger task-completion precheck when required
→ plan/replan current TaskPlan
→ activate StepSpec
→ build full Runtime ActionChoiceCatalog
→ select directly or through bounded ChoicePage
→ build ActionContract
→ task authority / capability / approval / preflight
→ execute
→ capture canonical post-action observation
→ LoopEvaluator(effect, step, triggered task, continuation)
→ RuntimeCommitter
→ continue / perceive / recover / replan / ask / finish
```

The loop is serial by default. Parallel observation providers may run inside a
capture only when their results join into one explicit canonical epoch before a
semantic consumer proceeds.

## 2. Physical sequence and logical authority

Verification is physically inside the loop so each action receives immediate
feedback. It remains logically separated:

- Executor reports dispatch receipt;
- EvidenceProviders extract observations;
- LoopEvaluator returns typed evaluations;
- TaskCompletionEvaluator computes full TaskSpec.success closure;
- RuntimeCommitter applies progress/terminal transitions.

No phase may bypass another by writing StateKernel directly.

## 3. Planning horizons

Task Planner changes milestone structure under current facts. Step Choice
Planner selects among displayed members of a Runtime-built Catalog. Zero/one/N
choice handling is Runtime-owned. A model request never creates the candidate
space it is asked to reason over.

## 4. Live feedback

Feedback consists of committed typed facts:

- observation/coverage/conflict changes;
- selection, contract, gate, and receipt results;
- effect/step/task evaluations;
- bounded progress and recent action outcomes;
- recovery owner/command/outcome;
- approval/clarification requests;
- terminal result and evidence/trace refs.

Streaming UI may project these events but cannot mutate their meaning.

## 5. Continuation safety

- new observation epoch invalidates stale Catalog/contract/approval bindings;
- plan replacement does not revise TaskSpec;
- plan exhaustion triggers final evaluation, not completion;
- uncertain external effects route to inspect/recheck/block, not automatic retry;
- post-action observation is reused when the typed Perception disposition permits.

## 6. Coordinator boundary

Coordinator invokes owners, receives typed results, commits transitions/events,
and chooses the next phase. Algorithms remain in their domain owners. Generic
exception text may be logged but cannot select a recovery owner or synthesize a
command.

The previous detailed orchestration document is archived at
[maintained-pre-consolidation/orchestration-and-feedback.md](archive/superseded-2026-08-05/maintained-pre-consolidation/orchestration-and-feedback.md).
