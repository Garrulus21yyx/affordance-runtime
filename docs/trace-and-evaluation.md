# Evaluation and Turn Recording Contract

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** execution result, effect evaluation, task evaluation, evidence, and telemetry

## 1. Separation rule

```text
ActionResult ≠ ActionEvaluation ≠ TaskEvaluation ≠ benchmark reward
```

Executor/transport success means the backend accepted or completed a call. It
does not prove the intended world change. ActionEvaluator compares before,
BoundActionRequest/batch, result, and fresh after observation. TaskEvaluator checks the full
TaskGoal and optional EvaluationSpec.

## 2. Action evaluation

ActionResult dispatch status is `NOT_SENT`, `SENT`, or `SENT_UNKNOWN`.
`success` only means the adapter did not report an execution error. A
SENT_UNKNOWN result always goes through fresh observation and never direct retry.

Statuses are EFFECT_CONFIRMED, NO_EFFECT, UNKNOWN, CONFLICT, and ERROR. Evidence must be
about the requested target/effect and come from the fresh observation or an
explicit authoritative external check. UNKNOWN never authorizes replay.

Evaluation prefers environment-native/API/WoT state, then DOM/AX structured
state, filesystem/artifact state, visual/VLM evidence, and finally human input.
This is a default strength order, not a ban on cross-source fusion.

## 3. Task evaluation

Statuses are COMPLETE, INCOMPLETE, and BLOCKED. Plan exhaustion, a successful
receipt, a trace event, or model confidence cannot produce COMPLETE.

MilestoneEvaluator uses observation/evidence to judge optional milestones.
Planner output cannot mark a milestone satisfied. Agent `Finish` is only a
proposal and must be confirmed by TaskEvaluator.

TaskEvaluator checks all success criteria, task constraints, forbidden effects,
required outputs/materialization, and any required current final recheck.

When an EvaluationSpec requires an artifact, the artifact must exist and match
the required content/integrity check. Declaration metadata is insufficient.

## 4. Evidence lifetime

- current observation facts are valid for that observation revision;
- recent action evidence binds request ID and before/after observations;
- durable business evidence exists only when an explicit strict profile needs it.

The core does not require a global EvidenceIndex or event-sourced ledger.

## 5. TurnRecorder

Optional records contain before observation ID, LocalObjective, ActionIntent or
Batch, bound request/result lineage, after observation ID, evaluations, route,
latency, and model/visual-call counts.
Recorder failure must not change admission, execution, evaluation, or loop
state. Trace is an offline debugging/benchmark input, never an authority.

## 6. Replay and benchmarks

Replay is offline simulation and cannot fall through to live execution.
Benchmark reward evaluates an exact run/profile and never becomes Runtime task
success. Published claims bind revision and profile.

## 7. Current migration note

Current TraceDag ordering and RuntimeCommitter coupling remain implementation
facts. Their target replacement is best-effort TurnRecorder plus direct loop
state update after domain evaluation.
