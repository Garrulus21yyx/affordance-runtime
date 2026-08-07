# Integrations

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** parent-agent, API, CLI, and UI boundary

## 1. Request boundary

Canonical integrations submit a TaskGoal and may attach an optional
EvaluationSpec or explicit strict-ingestion profile. They do not submit raw
selectors, coordinates, backend bindings/endpoints, file paths, approval tokens,
milestone satisfaction, or completion facts.

During migration, legacy TaskSpec-based endpoints may project one-way into new
contracts. New core code never imports those legacy request types.

## 2. Runtime outcomes

Integrations handle:

```text
Done(result)
WaitingUser(question)
WaitingConfirmation(confirmation_subject_id, semantic_summary, consequences)
Failed(reason)
```

Confirmation UX must display the concrete semantic effect/consequences and
return a decision bound to confirmation-subject identity. Runtime reobserves and
rebinds before execution; binding-only changes do not require another prompt.

## 3. Observation and action privacy

External APIs may expose AgentWorldView and safe turn summaries. They do not
expose credentials, selectors, backend handles, signed URLs, or unrestricted
screenshots/trace by default.

## 4. Cancellation and resume

Cancellation can stop before the next primitive action. A cancel racing with an
effectful dispatch cannot claim the action did not occur; the Runtime returns
SENT_UNKNOWN and requires fresh observation. Current target does not promise process-
crash checkpoint/resume.

## 5. Benchmark integrations

Benchmark adapters translate environments into the same world/action/evaluation
contracts. They cannot pass hidden expected answers or fixture metadata into
the policy or Runtime.
