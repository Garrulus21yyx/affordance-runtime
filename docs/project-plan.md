# Affordance Runtime Project Plan

> **Lifecycle:** CURRENT PRODUCT ROADMAP
> **Updated:** 2026-08-10
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
ObservationCapabilities + ObservationAcquisition + ExecutionOutcome
disposable AgentContext + opaque ContextIdentity
bounded IntentContext + progress/world/history/pending/budget views
AgentActionPageView + typed AgentDecision
SemanticTarget + ActionBinding
ActionSpace + ActionIntent
BoundActionRequest + ActionResult
ActionEvaluation + TaskEvaluation
AgentLoopState + bounded ControlTransition
optional VerifiedTaskState + TaskProgressAuditor
HumanConfirmation + optional TurnRecorder telemetry
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
| P5-M1.1 | Existing ModelPort bridge and invocation hardening | complete for strict boundary/local HTTP transport; later exact Mistral profile separately attested |
| P5-M2 | Production evaluator composition and criterion adjudicators | complete for declared minimum profiles; general entailment partial |
| P5-M2.1 | Evidence semantics and dynamic evaluation closure | complete for Runtime-derived obligation and presented-evidence profiles |
| P5-M3 | New-AgentLoop internal fixed-manifest harness | complete for fixed internal manifest |
| P5-M3.1 | Harness measurement and real-adapter attestation | complete; reviewed exact-head internal artifact available, live profile separately gated |
| P5-M3.2–M4 | Exact-head gates and pinned BrowserGym/MiniWoB adapter/profile | complete for declared profiles; no generalization/default-cutover claim |
| P5-M4.2–M4.4 | Local fill/select containment, historical MiniWoB-60 breadth and typed attribution/capability evidence | valid clean `b3b64a2` negative run at 6/60; short-loop gaps remain |
| post-M4.4 separately authorized rerun-v3 | Re-execute the frozen profile with expanded typed evidence | valid clean `83dc4fa` negative run at 4/60; separate from M4.3 |
| P5-M4.5-A | Typed observation acquisition lifecycle and real active-capture closure | complete, non-default |
| P5-M4.5-B | Bounded control/failure contract | integrated non-default; reopened convergence review; implemented, not verified |
| P5-M4.5-C | Same-profile MiniWoB-60 diagnostic | complete diagnostic; valid clean `4924ce6` evidence at 8/60; formal exit, performance and generalization not claimed |
| P5-M4.6 | Evidence-directed short-loop remediation | IN_PROGRESS; M4.6-A COMPLETE_NON_DEFAULT_FOR_DECLARED_CURRENTNESS_SCOPE; M4.6-B COMPLETE_NON_DEFAULT_FOR_DECLARED_VERIFIER_SCOPE; M4.6-C COMPLETE_NON_DEFAULT_FOR_DECLARED_INVENTORY_SCOPE; M4.6-D COMPLETE_NON_DEFAULT_FOR_DECLARED_CONTROL_FEEDBACK_SCOPE at `ccb682a8ef4acb00973e5c6a14c7c69c91d073fc` with accepted run `miniwob-control-feedback-25:ca6cfffdf3334844958b38210a5043bd`; M4.6-E NOT_STARTED |
| P5-M4.7 | Supported-subset multi-seed | not started; blocked by M4.6 targeted/full-run gates |
| P5-E | VerifiedTaskState, task-level progress auditing, milestone/frontier planning and replanning | not started; blocked by M4.6/M4.7 breadth gates |
| P5-F | Strictly bounded no-observation-barrier ActionBatch | isolated helper prototype exists; AgentLoop integration not started |
| P5-G | Currentness-checked memory/Skill with offline promotion | BindingCache prototype exists; target integration not started |
| P5-H | Surface breadth, default cutover, telemetry downgrade and old-core deletion | not started |

The detailed order and exit/deletion gates live only in the evolution plan.
Current status tokens are M4.5-B `INTEGRATED_NON_DEFAULT /
REOPENED_CONVERGENCE_REVIEW / IMPLEMENTED_NOT_VERIFIED`, M4.5-C
`COMPLETE_DIAGNOSTIC / EVIDENCE_VALID_AT_4924CE6 /
FORMAL_EXIT_NOT_ATTESTED / PERFORMANCE_NOT_CLAIMED /
GENERALIZATION_NOT_CLAIMED`, and M4.6 `IN_PROGRESS / M4.6-A
COMPLETE_NON_DEFAULT_FOR_DECLARED_CURRENTNESS_SCOPE / M4.6-B
COMPLETE_NON_DEFAULT_FOR_DECLARED_VERIFIER_SCOPE / M4.6-C COMPLETE_NON_DEFAULT_FOR_DECLARED_INVENTORY_SCOPE / M4.6-D COMPLETE_NON_DEFAULT_FOR_DECLARED_CONTROL_FEEDBACK_SCOPE / M4.6-E NOT_STARTED`; Implementation
Status owns current code truth.

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
separation, capability-aware fresh post-action acquisition, unknown no-retry, required-output
integrity, and benchmark neutrality.
AgentContext remains a one-way disposable projection; every decision binds the
current context ID, LocalObjective changes relevance only, and source assurance
never grants execution authority.
Each policy call receives a new one-shot generation even when its public
projection is otherwise identical. Runtime-issued paging cursors bind filters,
objective identity and exact membership; they are not durable state.
Expected unsupported/failed acquisition is typed. Dispatch truth is independent
of acquisition failure. One accepted policy decision has exactly one bounded
root ControlTransition, while AgentLoopState remains the current-state authority.
VerifiedTaskState accepts only validated evidence; TaskPlan remains a hypothesis.

## 6. Non-goals

- durable ledger, checkpoint/resume, or event sourcing without an admitted fault model;
- distributed/multi-writer transaction protocol;
- global authorization-proof or capability-token platform;
- prompt-injection classification as the Runtime architecture center;
- mandatory full TaskPlan or strict source graph for ordinary GUI tasks;
- trace or external reward as online execution/completion authority;
- ControlTransition as a durable ledger, replay source, global event taxonomy,
  state reconstruction mechanism, or second execution truth;
- a Runtime progress guard used as a substitute for policy/planner competence.

## 7. Program completion

The program reaches this target when the default product path uses the unified
world contracts and short AgentLoop, the DOM/AX/Visual/SVG/WoT positive matrix
succeeds with only adapter variation, the local correctness invariants remain
verified, a long-horizon task and bounded Batch/Skill gates pass, and the old StateKernel/delta/committer/recovery-transaction chain no
longer appears in the default import or call path.

## 8. Exact model-profile conformance

P5-M3.3 is complete for the tested exact profiles. Input complexity is measured
rather than inferred from budget limits, and structured-output failures are
located before policy/runtime compatibility conclusions are drawn. Weak-model
compatibility is not a core requirement: an exact profile may be explicitly
unsupported without adding parser repair, retry, fallback or model-specific
Runtime behavior. This phase did not itself authorize an external run; the
later M4 adapter and breadth records are separate profile-scoped evidence.

The exact installed Qwen 2.5 7B and Llama 3.1 8B digests now pass the complete
L0–L4 compact-contract support gate at 20/20 per level. This closes their tested
local action-selection profile, not full recurrent AgentPolicy, without changing the format-only production default.
It did not by itself close the later external adapter, live-profile or
default-cutover gates.

## 9. Compact grounding production profile

P5-M3.4 makes compact grounding explicitly configurable without provider/model
routing, retry, fallback or Runtime repair. Exact identity includes grounding
version and schema digest. The default-cutover checker is evidence-only and has
no Runtime dependency. Global compact-default readiness remains blocked by the
decision matrix/provider evidence; format-only remains default. Later M4
external runs are independently gated and do not promote compact grounding.

## 10. Decision-neutral recurrent qualification

P5-M3.5 is complete as an implementation/measurement slice. V1 remains the
explicit action-selection profile. V2 is explicit but experimental and not admitted,
but both exact local profiles failed candidate admission and Mistral v2
availability is unmeasured. Global default cutover therefore remains blocked;
any future default change must be a separate minimal commit after all hard
gates pass.

## 11. Two-stage diagnostic decomposition

P5-M3.6 is complete as a diagnostic implementation and measurement slice.
The benchmark-only harness reuses canonical payload branches, strict parsing,
and production Runtime control while keeping route proposals outside Runtime
state. Exact Qwen and Llama candidates both failed with a routing bottleneck;
payload-only was 35/35 for each only when the harness fixed the correct route.
Two-stage production admission remains explicitly out of scope.

## 12. BrowserGym pinned mechanical profile

P5-M4 closes a narrow external-world adapter, not a benchmark campaign. The
reviewed MiniWoB trio is projected into existing WorldObservation and
ActionSpace contracts, executed via Runtime-private BrowserGym bindings, and
evaluated only from current official mechanical status. Adapter conformance is
3/3 and admits `target_loop_adapter_ready` only from a clean exact-head
attestation. Live Mistral smoke remains an independently gated deployment
profile with fixed 7.5-second pacing. Its exact-head internal DOM attestation
was accepted and external preflight admitted the subsequently authorized run;
the formal `cd49b8e` run then failed by case timeout. No local diagnostic or
correctness test backfills that result. No generalization or default
Coordinator cutover follows from this milestone.

P5-M4.2 adds only run-scoped verified-progress containment to that profile.
It does not plan the next action or remove fill/select from ActionSpace:
different requested values remain executable, while a mechanically satisfied
exact value is zero-call and an unchanged repeat is bounded. Timeout evidence
now preserves partial episode counts. The `cd49b8e` formal smoke remains a
recorded case-timeout failure; this local closure does not change its status.

P5-M4.3 is one frozen 60-task, single-seed MiniWoB breadth profile before the
P5-E decision. It is a diagnostic gate inside one synthetic benchmark family.
It neither changes product authority nor satisfies long-horizon, multi-surface,
seed-robustness, generalization, or default-cutover completion gates.

P5-M4.4 interprets the valid 6/60 result without changing its historical
denominator or files. It adds future failure-origin observability, full-registry
multi-axis capability requirements, and local no-model coverage diagnostics.
That slice's rerun-blocked decision remains historical. A later separately
authorized rerun-v3 completed at clean `83dc4fa` with valid 4/60 evidence,
including 7 post-observation failures and 9 still-unclassified typed failures.
It remains separate from 6/60 and does not establish a trend. A third,
separately authorized clean diagnostic at `4924ce6` completed 60/60 at 8/60;
it is also independent and claims neither performance acceptance nor trend.

P5-M4.5 now precedes P5-E. M4.5-A has separated reset/independent capture from
execute-returned post-action acquisition and closed origin/fallback/counting
semantics with real pinned active-capture evidence. M4.5-B is an integrated
candidate whose reducer legality, ordered physical attempts, confirmation,
evaluation epochs, current snapshot authority and typed benchmark fact owners
remain under convergence review. M4.5-C diagnostic execution is complete; its
run patterns plus exact-source review support AX currentness, verifier,
semantic-inventory and bounded control-feedback/repair/no-gain gaps without
closing B. M4.6 repairs those gaps in independently
measurable slices; its targeted gates and a new immutable full run precede the
M4.7 supported-subset multi-seed gate, whose immutable manifest, exact seed set,
numeric provider-availability/capacity floor, success floor and maximum seed
variance are frozen before execution. P5-E then reuses the existing TaskPlan
contracts while adding validated VerifiedTaskState frontier promotion and a
task-level auditor separate from the local fill/select ProgressController.
