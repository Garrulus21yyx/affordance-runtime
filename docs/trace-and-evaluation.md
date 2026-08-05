# Trace and Evaluation Contract

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** trace events, evidence locations, typed evaluation, external evaluation, and replay

## 1. Trace rule

Trace records committed Runtime facts in causal order. It is an offline
consumer of authoritative transitions, not a completion or recovery owner.

Each event carries run/task identity, relevant revision/epoch/contract refs,
event type, typed payload, causal parent refs, timestamp/sequence, and artifact
refs. Raw user request content is not copied by default; SourceEnvelope refs,
hashes, and lengths preserve identity without broad disclosure.

## 2. Four distinct results

| Layer | Question | Result |
|---|---|---|
| receipt | did backend dispatch report success/failure? | ExecutionReceipt |
| action effect | did this ActionContract's expected local effect occur? | CriterionEvaluation |
| step | does StepSpec.completion hold? | CriterionEvaluation |
| task | does full TaskSpec.success closure hold with required constraints/rechecks? | TaskCompletionEvaluation |

No result substitutes for another. Plan exhaustion and external reward are not
TaskCompleted.

## 3. Criterion policy

Each criterion leaf uses the minimum orthogonal policy:

```text
SatisfactionMode     = STATE_HOLDS | ACTION_CAUSED
EvidenceValidityMode = CURRENT_OBSERVATION | DURABLE | FINAL_RECHECK
AssuranceLevel       = WEAK | STRUCTURAL | AUTHORITATIVE
```

Status is one of `SATISFIED`, `UNSATISFIED`, `UNKNOWN`, `STALE`, `CONFLICT`,
`UNSUPPORTED`, or `ERROR`. No evidence means UNKNOWN; disabled evaluation never
creates synthetic PASSED.

## 4. Evidence locations

1. Current observation evidence stays in canonical UnifiedObservation.
2. Contract-bound causality stays in a bounded RecentActionOutcome index.
3. Artifact hash, resource/version, transaction ID, external final recheck, or
   human confirmation may enter the small DurableEvidenceStore.

Only durable evidence crosses observation epochs. Historical current-state
evidence is admitted only when the criterion validity mode explicitly permits
it.

## 5. Providers and admission

DOM, AX, visual, control-state, API, artifact, network, external, and optional
model/human providers extract evidence with source, freshness, assurance, and
observed value metadata. Typed predicate evaluators own operators.

EvidenceAdmissionPolicy decides whether an evidence record is usable for one
typed criterion ID. It does not own AllOf/AnyOf/root completion semantics.
ModelVerifier provides evidence only; model-only evidence cannot complete
high-risk external effects.

## 6. Task completion

RuntimeCommitter may emit TaskCompleted only when TaskCompletionEvaluator
returns:

```text
TaskSpec.success root == SATISFIED
AND no required constraint violation
AND no unresolved external effect
AND all required FINAL_RECHECK completed
```

Evaluation runs on the initial canonical observation, completed active step,
new durable evidence, returned external recheck, plan exhaustion, Planner Finish
request, and immediately before every TaskCompleted commit.

## 7. External evaluation and claims

Benchmark oracles and rewards are stored separately from Runtime status. Reports
bind repository revision, dirty state, environment/assets, profile, provider,
budgets, seeds, missing/unrun episodes, Runtime result, external result, and
official-claim flag.

Historical evidence remains valid only for its exact identity. Replay may
diagnose or test a proposed generic fix; it cannot rewrite the original trace.

The previous detailed document is archived at
[maintained-pre-consolidation/trace-and-evaluation.md](archive/superseded-2026-08-05/maintained-pre-consolidation/trace-and-evaluation.md).
