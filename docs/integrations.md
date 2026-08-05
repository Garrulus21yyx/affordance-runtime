# Integrations

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** parent-agent, CLI, service, adapter, and result boundaries

## 1. Integration principle

A caller submits bounded user intent and legal source references. The caller
does not need to adopt Runtime internals and cannot bypass Runtime authority by
supplying accepted TaskSpec identity, concrete selector/coordinate, capability,
approval, verification result, or TaskCompleted state.

## 2. Request boundary

An integration request may provide:

- request/caller/conversation identity and revision;
- request text or stable source ref;
- attachment, target, and profile-context refs;
- caller-granted capability context;
- risk/approval policy refs;
- run budgets and continuation/cancellation handles.

Runtime creates SourceEnvelope and interprets a MinimalIntentProposal. Material
fields use SourceAnchor. Optional SemanticAudit may veto or request
clarification. TaskSpecAuthority alone admits the TaskSpec.

## 3. Runtime operations

A service/tool surface may expose:

```text
submit / execute / get_run
approve / deny / cancel / clarify
get_result / get_evidence / get_trace
```

Approval binds one exact ActionContract hash and state/page revision. Parent
agents cannot approve an action family or stale future action in advance.

## 4. Result boundary

The integration result distinguishes:

- Runtime lifecycle/terminal status;
- TaskCompletionEvaluation and result payload;
- pending approval/clarification/recheck;
- typed failure and recovery state;
- observation, artifact, durable-evidence, and trace refs;
- external evaluator result when applicable.

Receipt success, plan exhaustion, model finish, or benchmark reward is never
reported as Runtime task success by itself.

## 5. Adapter boundary

BrowserGym, Playwright, DOM, visual, AX, API, device, and future desktop/mobile
adapters translate public Runtime contracts. They may capture source data,
route validated concrete actions, and collect external results. They may not
own TaskSpec, full Catalog membership, ActionContract admission, recovery
policy, or completion semantics.

## 6. Streaming and cancellation

Streaming projects committed events. Cancellation and user takeover are typed
Runtime transitions; they do not directly mutate provider/session state behind
the committer. Sensitive source content and artifacts are returned by scoped
refs rather than embedded in every event/result.

The previous integration document is archived at
[maintained-pre-consolidation/integrations.md](archive/superseded-2026-08-05/maintained-pre-consolidation/integrations.md).
