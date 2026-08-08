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

Target statuses are `EFFECT_CONFIRMED`, `NO_EFFECT_CONFIRMED`, `UNKNOWN`, and
`REJECTED`. `NO_EFFECT_CONFIRMED` requires fresh identity-bound authoritative
evidence that the effect did not occur and permits a new policy turn, never an
automatic replay. `UNKNOWN` means coverage/evidence cannot determine whether
the effect occurred; the loop stores the pending unknown request, waits for the
user, and never enters ordinary execution for that intent. `REJECTED` fails or
stops according to loop policy. Evidence must concern the requested target and
effect and come from the fresh observation or an authoritative external check.

Every target-path `ActionEvaluation` binds a non-empty request ID and distinct,
non-empty before/after observation IDs. `EFFECT_CONFIRMED` and
`NO_EFFECT_CONFIRMED` additionally require at least one authoritative evidence
reference; explanatory text is not evidence. AgentLoop rejects any request or
observation lineage mismatch before TaskEvaluator can treat the evaluation as
trusted.

Evaluation prefers environment-native/API/WoT state, then DOM/AX structured
state, filesystem/artifact state, visual/VLM evidence, and finally human input.
This is a default strength order, not a ban on cross-source fusion.

## 3. Task evaluation

Statuses are COMPLETE, INCOMPLETE, UNKNOWN, and BLOCKED. Plan exhaustion, a successful
receipt, a trace event, or model confidence cannot produce COMPLETE.

`UNKNOWN` waits for user direction with zero execution. `BLOCKED` terminates
the run as BLOCKED with zero further execution. Neither status is treated as
ordinary INCOMPLETE.

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
