# Current Implementation Plan

> **Lifecycle:** CURRENT ACTIVE QUEUE
> **Updated:** 2026-08-08
> **Start baseline:** `codex/migrate-world-interaction-capabilities@792d327112cd72f3cb5c9bd02c273c80f626f349`
> **Implementation truth:** [Implementation Status](implementation-status.md)

## Current decision

The transaction-platform queue remains stopped. P5-A/B1/C1 has established the
target contracts, minimum Unified World Interface, and real DOM plus
Visual-only and WoT local-simulation short loops without changing the default product path.

## Slice status

| Slice | Status | Current result / debt |
|---|---|---|
| R0 | complete | facts reconciled; smart-room atomic mismatch fix; lockfiles/npm ci; WoT metadata/security/event boundary |
| A1 | complete, non-default | strong TaskGoal and optional EvaluationSpec; legacy projection is one-way edge |
| A2 | complete, contracts only | optional replaceable TaskPlan/Milestone/LocalObjective; no model planner |
| A3 | complete, non-default | immutable WorldObservation, private bindings, policy view, runtime ActionSpace |
| A4 | complete, non-default | ActionIntent/request/result, evaluations, decisions, bounded turns |
| B1 | complete for DOM minimum | SurfaceAdapter, UnifiedWorldEnvironment, DOM adapter, binder |
| C1 | complete, non-default | real Chromium positive loop plus negative matrix |
| C1.1/B1.1 | complete | task-aware ActionSpace, source/world/fingerprint currentness, lineage, schema, budget, Finish/unknown closure |
| C1.2/B1.2 | complete | exact option/binding groups, Runtime-owned coarse effect/risk, single-probe currentness, reset/schema/attempt lineage |
| C2/B3 Visual | complete, non-default | screenshot-only proposer, private coordinates, one-probe pointer execution, real Chromium loop |
| C3/B4 WoT | complete, non-default | real local HTTP TD/read/invoke, private transport binding, deployment scope, one-probe execution |
| DOM/Visual/WoT matrix | proven for shared-state task | same TaskGoal/policy/evaluators; adapter-only variation, no fusion |
| P5-D | complete, non-default | semantic confirmation, fresh rebind, single-send consumption, explicit effect certainty |
| P5-D6.1 | complete, non-default | effective risk, destination, presentation, terminal immutability, policy reselection, evaluation lineage/evidence, task-evaluation control |
| P5-M0 | complete, non-default | model-safe policy projections, evidence-resolved evaluations, target output integrity |
| P5-M0.1 AgentContext architecture | `COMPLETE_NON_DEFAULT` | disposable unified context, bounded intent/world/history, current context identity, relevance, paging, source assurance, typed decisions |
| P5-M0.1.1 operational closure | `COMPLETE_NON_DEFAULT` | one-shot epochs, fresh acquisition identity, cursor paging, projection coherence, recurrent decision history |
| P5-M1 model-backed AgentPolicy | `CLOSED` | canonical structured decision contract and deterministic evaluators retained |
| P5-M1.1 ModelPort bridge/hardening | `CLOSED` | hostile JSON, deadline, typed failures/metadata, zero retry/fallback, local HTTP proof; live unavailable |
| P5-M2 production evaluator composition | `CLOSED_FOR_DECLARED_MINIMUM` | Runtime-composed mechanical/semantic/user/hybrid criteria and output binding |
| P5-M2.1 evidence semantics closure | `CLOSED_FOR_DECLARED_PROFILES` | relevance-bound effects, strong no-effect scope, presented evidence only, dynamic readiness |
| P5-M3 new-loop benchmark harness | `CLOSED_FOR_INTERNAL_FIXED_MANIFEST` | internal core/safety/evaluation accepted; external suites not run |
| P5-M3.1 measurement/real adapters | `CLOSED_LOCALLY` | typed expectations, actual safety counters, real DOM/Visual/WoT suite, exact-head attestation command |
| P5-M3.2 admission package | `CLOSED_FOR_PINNED_MECHANICAL_PROFILE` | full-CI/live/adapter evidence and fixed manifest feed a protected manual workflow |
| P5-E | `NOT_STARTED` | long-horizon plan execution |
| ActionBatch integration | `NOT_STARTED` | isolated legacy-contract helper remains only |
| default cutover/deletion | `NOT_STARTED` | old baseline retained and frozen |

## Next admitted slice

The three-surface single-adapter matrix, P5-D current profile, and P5-D6.1 are
complete. P5-M0, P5-M0.1, P5-M0.1.1, P5-M1 and the P5-M1.1 existing-transport bridge are
complete on the non-default path. P5-M2 criterion-specific composition is also
complete for its declared minimum, and M2.1 closes its evidence-semantic entry
gates. P5-M3 now closes the internal fixed-manifest harness. External benchmark
admission remains blocked until final-head full CI, exact live policy evidence,
and the target-loop BrowserGym environment wrapper all close. The reviewed
mechanical manifest is not itself execution authority; default cutover and
old-core deletion remain unauthorized.

## Frozen work

- new RuntimeDelta/RuntimeCommitter/StateKernel capability;
- ledger, checkpoint/resume, event sourcing, generic recovery transaction;
- global approval/capability/token registry or worker fencing;
- ActionBatch integration and long-horizon plan mutation;
- default cutover or deletion before the positive cross-surface gates.
- any AgentContext ownership of Runtime state, private route projection, or
  LocalObjective-based legality/risk change.

## Verification policy

Every target slice runs focused pytest, Ruff, mypy on affected modules,
`git diff --check`, then the full suite. Evidence is exact-revision/profile
scoped; benchmark oracles never drive product behavior.

## P5-M3.3 closure

Exact model input/schema complexity is measured and installed Ollama failures
are stage-attributed. A canonical 1,024-character completion-summary budget
closes the observed full-union grammar-initialization blocker: exact Qwen and
Llama diagnostic reruns each pass Level 2, then fail current-page destination
admission at Levels 3/4 under format-only. D0–D4 destination diagnostics isolate the
next boundary: Qwen fails only when the complete context makes `target_id`
salient, while Llama first fails on the real nested action-page and also copies
`target_id` in the complete context. No destination auto-repair is admitted.
The post-repair compact-contract gate then passed L0–L4 at 20/20 for each exact
profile on clean HEAD, producing accepted per-profile action-selection
attestations. Mistral also passed one fresh Level-4 no-regression call for each
grounding. The production default stays format-only; adopting compact grounding
is a separate provider-neutral product decision.
External execution remains blocked by
the optional BrowserGym dependency, target-loop external environment adapter
and admission package; M3.3 does not authorize that run or a default cutover.

## P5-M3.4 closure

Compact grounding is production-supported as an explicit configuration, with
`compact-contract.v1` and actual canonical schema digest in secret-free model
metadata and exact-profile identity. Format-only remains the current default
and explicit rollback configuration. The pure cutover checker is currently
blocked by incomplete seven-decision live-local behavior, failed compact
strong-provider no-regression and unavailable exact-head CI. The next action is
review/remediation of those measured blockers, not a default flip.

## P5-M3.5 closure

The v1 guide is frozen and its evidence is scoped to action selection. The new
decision-neutral v2 profile, complete Runtime replay matrix, recurrent CLI and
secret-free attestation are implemented. Scripted candidate closure is 75/75.
Exact Qwen and Llama GPU candidates failed their 5/5 recurrent gates, so their
20/20 support gates were not run. The next admitted work is evidence review or
a separately authorized design change; this slice does not tune prompts,
switch defaults, run external benchmarks, or add repair/retry/fallback.

## P5-M3.6 closure

The two-stage decomposition diagnostic is implemented entirely under
`benchmarks/model_conformance/two_stage`. It measures routing, fixed-route
payload filling, end-to-end Runtime outcomes, and the original single-stage
compact-v2 baseline with atomic per-stage progress. Qwen and Llama both failed
candidate admission because routing remained incomplete despite 35/35 payload
isolation. No support gate, remote Mistral run, production adoption, external
benchmark, or default change is admitted. A future adoption review would still
need 20/20 exact evidence plus call-budget, latency, token, rate-limit,
strong-provider, rollback, and exact-head CI evidence.

## P5-M4 closure

The current mainline owner is the existing target loop. The pinned BrowserGym
adapter now owns lifecycle/projection/private binding/execution/mechanical
verification under `benchmarks/external_smoke`, while AgentLoop, parser,
Runtime admission, target core, and default Coordinator remain unchanged. Real
fixed-task adapter conformance is closed at 3/3. The remaining activity is
operational only: generate clean-head attestations, push, and verify exact-head
CI. A live fixed smoke may run only after exact-head internal/full-CI/live-policy
evidence admits it and the caller already supplied both explicit execution
gates. Its current result is determined only by the exact-head protected
workflow and artifact, not by a durable status literal in this plan.

## P5-M4.2 local verified-progress closure

The local target-loop correction is complete: fresh structural fill/select
postconditions produce current action evidence; already-satisfied selections
are zero-call; an unchanged exact repeat terminates with a typed no-progress
code; bounded progress enters the next AgentContext; and watchdog timeout
retains partial counts/evaluation status. The fixed manifest now uses 10 turns
per simple case so `(max_turns - 1) * 7.5s` remains below its 120s watchdog
after a fixed 5s scheduling margin. No live provider, protected workflow, or
external smoke belongs to this slice. The historical `cd49b8e` timeout remains
the formal result until a separately authorized exact-head run occurs.

## P5-M4.3 seeded breadth queue

The next bounded activity is the frozen MiniWoB-60 seed-7 in-family campaign,
not P5-E implementation. Registry census, primitive inventory, deterministic
selection, typed attribution, atomic non-resumable progress, privacy-safe case
reports, and exact-head attestation are repository-owned. Dynamic success
counts and run identity remain outside source control. After one complete
campaign, failure distribution selects the next review among primitive breadth,
projection, policy relevance, progress/evaluation, seed robustness, or P5-E.
No campaign result may tune the production prompt during the run.
