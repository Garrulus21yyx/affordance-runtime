# Integrations

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** parent-agent, CLI, service, adapter, and result boundaries

## 1. Integration principle

The current MVP is single-process and single-session. Principal/tenant/account
rules in this document apply only when an integration explicitly admits a
multi-principal or multi-tenant deployment claim; they are not P4/P5 blockers.

A caller submits bounded user intent and legal source references. The caller
does not need to adopt Runtime internals and cannot bypass Runtime authority by
supplying accepted TaskSpec identity, concrete selector/coordinate, capability,
approval, verification result, or TaskCompleted state.

## 2. Request boundary

An integration request may provide:

- request/caller/conversation identity and revision;
- request text or stable source ref;
- attachment, target, and profile-context refs;
- caller-asserted capability/delegation refs plus issuer/subject/audience metadata;
- risk/approval policy refs;
- run budgets and continuation/cancellation handles.

Runtime creates SourceEnvelope and interprets a MinimalIntentProposal. Material
fields use SourceAnchor. Optional SemanticAudit may veto or request
clarification. TaskSpecAuthority alone admits the TaskSpec.

`caller_identity` and every identity field supplied in request JSON are
untrusted claims; the effective principal comes only from the authenticated
transport/session. Before dereferencing any inbound source, attachment, target,
profile-context, capability/delegation, policy, continuation, or cancellation
ref, Runtime authorizes that exact ref against principal, tenant/account,
audience, resource kind/identity/version, and run/task scope. Cross-tenant or
cross-account substitution fails closed even when the opaque ref is syntactically
valid. Risk/approval policy refs resolve only in a trusted, versioned
Runtime/tenant policy namespace: a caller may request a stricter/narrower policy,
but cannot replace, weaken, or shadow mandatory product/tenant policy.

Caller capability material is untrusted context until an independent capability
authority verifies a signed/opaque grant by exact issuer, subject, audience,
tenant/account, resource scope, run/task binding, revision, expiry and
revocation state. An unverified ref may only narrow the requested ceiling; it
never enters `granted_capabilities`. A caller cannot self-issue a grant merely
because it is authenticated to submit requests.

## 3. Runtime operations

A service/tool surface may expose:

```text
submit / execute / get_run
approve / deny / cancel / clarify
get_result / get_evidence / get_trace
```

Every operation is authorized against an authenticated principal and the exact
run owner/tenant/account/audience; possession or guessability of a run/ref ID is
not authorization. `approve` additionally requires an authenticated approver
whose role/scope is allowed by approval policy, and binds issuer/subject/run/
session-generation/contract hash/nonce/expiry/revocation. Service-to-service
delegation is verified by the same rules rather than trusted from request JSON.

Approval is requested only for an exact `SealedActionContract` built from a
committed fresh observation. It binds run/session generation, contract hash,
state/page/document revision, context/surface/coordinate/capability/proof
digests, material parameters and expiry. It does not grant capability or amend
TaskSpec. Parent agents cannot approve a Draft, action family, stale future
action, or third-party page/tool instruction in advance; late grants are
tombstoned after interrupt, cancel, restart or contract staleness.

## 4. Result boundary

The integration result distinguishes:

- Runtime lifecycle/terminal status;
- TaskCompletionEvaluation and actual typed `OutputMaterialization` refs;
- pending approval/clarification/recheck;
- typed failure and recovery state;
- observation, artifact, durable-evidence, and trace refs;
- external evaluator result when applicable.

Transport receipt success, plan exhaustion, model finish, or benchmark reward is never
reported as Runtime task success by itself.

## 5. Adapter boundary

BrowserGym, Playwright, DOM, visual, AX, API, device, and future desktop/mobile
adapters translate public Runtime contracts. They may capture source data and
adapter-owned truthful SourceCoverage/context/coordinate/capability descriptors,
route permit-authorized concrete actions, and collect external results. They may not
own TaskSpec, full Catalog membership, ActionContract admission, recovery
policy, or completion semantics.

## 6. Streaming and cancellation

Streaming projects committed events. Cancellation and user takeover are typed
Runtime transitions; they do not directly mutate provider/session state behind
the committer or prove an in-flight effect did not occur. Restart uses a new
session generation and fresh observation; `runtime_resume.py` only validates
and routes. Sensitive source content and artifacts are returned by scoped
refs rather than embedded in every event/result. Dereferencing result, evidence,
artifact, approval, or trace refs repeats principal/run/tenant/account policy,
revocation and retention checks and applies field redaction; opaque identifiers
alone are not an anti-IDOR boundary. Cross-run listing and ref substitution fail
closed and are audit events.

The previous integration document is archived at
[maintained-pre-consolidation/integrations.md](archive/superseded-2026-08-05/maintained-pre-consolidation/integrations.md).
