# Planner, Recovery, and Benchmark Governance Audit

Date: 2026-07-23
Reviewed repository: /home/yang/projects/affordance-runtime
Reviewed revision: bb65ac689610d86802ed77bc5bfd163b0a664441
Status: **current diagnosis and corrective plan**

Post-audit implementation note, 2026-07-23: the first G0/G1 containment slice
now makes `strict-generalist` the default, requires explicit
`historical-compatibility` for the old semantic compiler registry, binds profile
and registry digest in new reports, removes `task_id` from planner context, and
disables official score claims while M8.6 is open. This narrows Findings 5 and
6; it does not close G1 because shared proposal validation, behavioral negative
controls, physical compatibility-code containment, and non-BrowserGym proof
remain open. G2 operation/capability derivation and TaskPlan integration also
remain open.

This document records the current architectural diagnosis. It is not a
benchmark score report. The normative product boundary is defined by
Benchmark Governance and Anti-Specialization Boundary and Runtime-First
Architecture Boundary.

## 1. Executive Verdict

Affordance Runtime has surpassed the old A Modular Action System in overall
harness architecture:

- typed ActionContract and validity boundaries;
- capability and approval gates;
- post-action observation and independent verification;
- full trace and artifact lineage;
- benchmark metrics and ablations;
- quarantined, replay-gated evolution;
- task-level planning models;
- unified DOM, visual, SVG, and WoT candidate design.

It has not yet surpassed the old C009 branch in two narrower areas:

1. planner honesty: C009 starts from a structured GoalSpec and does not claim
   unrestricted natural-language planning;
2. online recovery cohesion: C009 places active perception, reroute, retry,
   rollback, and verification in one interaction manager, while the current
   Runtime mainly applies Recovery Cascade after contract construction.

The current repository therefore has the stronger target architecture but an
incomplete default online control path.

The highest-priority problem is not provider quota, timeout, or a weak prompt.
It is architectural:

> The default generalist planner contains task-family programs that can solve
> benchmark-shaped instructions without demonstrating general understanding,
> while the Recovery Cascade does not yet govern failures in intake,
> observation, task planning, step planning, and proposal binding.

M8.2B score promotion must pause behind a new M8.6 governance and robustness
gate.

## 2. Audit Scope

The audit inspected:

- generalist action planning and semantic compiler registration;
- BrowserGym task normalization and planner-facing context;
- task-level planning integration;
- proposal binding and ContractBuilder behavior;
- Coordinator failure and recovery paths;
- failure signatures, incident detection, and evolution artifacts;
- accepted skill and recovery-profile loading;
- current milestone and benchmark claims;
- the C009 architecture in A Modular Action System;
- representative open-source GUI agent orchestration patterns.

This was an architecture and code-path review. Historical benchmark results are
retained as evidence of those revisions and profiles; they are not treated as
proof that the current planner generalizes.

### 2.1 Code Evidence Map

Line references below apply to the reviewed revision and may move after the
corrective refactor.

| Evidence | Current location | Architectural consequence |
| --- | --- | --- |
| Default semantic compiler registry is enabled on GeneralistLMPlanner | src/affordance_runtime/generalist_planner.py:168-177 | task-family compilers are active in the claimed default planner |
| Semantic compiler runs before the model | src/affordance_runtime/generalist_planner.py:191-207 | benchmark-shaped rules can finish steps with zero LM reasoning |
| BrowserGym task id and official evaluator wording enter TaskSpec | src/affordance_runtime/benchmarks/browsergym_episode_runner.py:609-619 | audit identity and external oracle semantics can reach planning |
| BrowserGym assigns every task READ_ONLY | src/affordance_runtime/benchmarks/browsergym_episode_runner.py:610-616 | task-level effect and capability semantics are inaccurate |
| BrowserGym Coordinator is created without TaskPlanner | src/affordance_runtime/benchmarks/browsergym_episode_runner.py:638-657 | the scored path does not exercise the declared shallow task planner |
| Generic planner exception directly finishes FAILED | src/affordance_runtime/coordinator.py:511-563 | planner failures bypass Recovery Cascade |
| ProposalRejected aborts except accepted-skill fallthrough | src/affordance_runtime/coordinator.py:699-735 | binding and validation failures lack general recovery |
| Progress guard reobserves and continues | src/affordance_runtime/coordinator.py:778-804 | repeated planning may not change a semantic assumption |
| Recovery detector covers repeated, no-progress, A-B, stale, verifier, fallback, and duplicate-effect patterns | src/affordance_runtime/recovery.py:157-212 | reusable cascade logic exists and should be lifted to all phases |
| BoundedRecoveryPolicy starts from ActionContract and receipt | src/affordance_runtime/recovery.py:235-285 | policy currently assumes the lower execution half has already been reached |

## 3. Current Runtime Chain

The intended product chain is:

~~~text
UserRequest
  -> Intent Compiler
  -> immutable TaskSpec
  -> optional TaskPlanner
  -> active SubgoalSpec
  -> task-aware observation
  -> unified affordances and grounding candidates
  -> Generalist Step Planner
  -> semantic PlannerProposal
  -> PlannerProposalValidator
  -> ContractBuilder
  -> ActionContract
  -> policy and preflight
  -> route and execution
  -> post-action observation
  -> criteria-bound verification
  -> recovery, continuation, clarification, or abort
  -> trace and evaluation
  -> regression-gated harness learning
~~~

The current code implements most objects and lower-half phases. The normal
BrowserGym scored path does not yet exercise the full intended chain:

- the runner constructs TaskSpec directly from official task input;
- it instantiates RunCoordinator without the task planner;
- the default GeneralistLMPlanner calls registered semantic compilers before the
  model;
- failures before a valid ActionContract do not consistently enter a unified
  Recovery Coordinator;
- accepted recovery knowledge is not loaded by the default BrowserGym runner.

This mismatch between declared architecture and the scored entrypoint is the
central governance issue.

## 4. Strengths to Preserve

### 4.1 Contract-driven execution

The Runtime correctly keeps execution authority out of the planner. A proposal
must become an ActionContract and pass policy, approval, validity, preflight,
execution, post-observation, and verification.

This boundary should remain non-negotiable.

### 4.2 Criteria-bound progress

TaskPlan, SubgoalSpec, evidence requirements, and the shared criteria matcher
provide the right direction. A passed verifier report must not complete an
unrelated subgoal or skill step.

### 4.3 Unified environment representation

The current design can represent DOM, accessibility, SVG, SoM, pure visual,
WoT, and API candidates under one semantic target and route model. This is a
stronger abstraction than separate benchmark backends.

### 4.4 Recovery incident and evolution models

FailureSignature, RecoveryIncident, no-progress detection, A-B oscillation,
fallback exhaustion, uncertain-effect handling, RecoverySkill, policy patch,
quarantine, replay, acceptance, rollback, and trace evidence are real assets.

The issue is coverage and online integration, not absence of recovery concepts.

### 4.5 External evaluation separation

Official reward is recorded separately from Runtime verification in much of the
benchmark path. This distinction must be completed and protected from
planner-visible leakage.

## 5. Critical Finding: The Default Planner Is Not Generalist

Severity: **P0**

The GeneralistLMPlanner invokes the default semantic compiler registry before
calling the model. The same module has grown to roughly 2,500 lines and includes
logic for calendar, autocomplete, quantity, sorting, hierarchy, disclosure,
forms, copying, dragging, and other benchmark-shaped task grammars.

The problem is not that deterministic System 1 rules exist. The problem is that
these rules:

- are enabled in the default generalist path;
- infer multi-step task semantics from narrow instruction phrases;
- may expose terminal actions from expected benchmark task shape;
- are not consistently scoped by a typed intent contract;
- do not have sufficient paraphrase, distractor, ambiguity, and unrelated-page
  controls;
- can complete tasks with zero model calls while claiming generalist planning.

This is soft specialization. It is behaviorally equivalent to dispatching to a
task-family solver even when no suite name appears in source.

### 5.1 Empirical negative probes

Current behavior demonstrates overreach:

- a request to open a report can activate an unrelated disclosure merely because
  one disclosure-shaped affordance is available;
- a request to enter a value into both fields can fill all writable fields when
  the page has more than two;
- a prefix entry request can trigger option selection or terminal submission
  even when the user did not authorize those effects.

These are not benchmark score concerns. They are user-intent and authority
violations in plausible real interfaces.

### 5.2 Root cause

The default planner mixes four layers:

1. instruction interpretation;
2. task-family obligation compilation;
3. current semantic action choice;
4. completion and terminal exposure.

A real general planner needs these responsibilities separated and validated.
Task grammar learned from a benchmark cannot substitute for typed intent,
current evidence, and explicit success criteria.

### 5.3 Required correction

Create a strict-generalist default profile. Its deterministic rules are limited
to:

- schema and protocol normalization;
- standards-based control semantics;
- safety and authority;
- accepted, versioned, regression-gated skills.

Move benchmark-shaped compilers out of the default registry. Historical
compatibility behavior may remain behind an explicitly named profile whose
results cannot support generalist claims.

Every planner source must emit the same PlannerProposal and pass one
PlannerProposalValidator.

## 6. Critical Finding: Benchmark Identity Leaks Into Planning

Severity: **P0**

The BrowserGym runner currently retains official task identity for audit, which
is correct, but also constructs planner-facing task fields from task id and
official wording. It additionally classifies all tasks as read-only.

This creates three risks:

1. suite identity can influence target selection or planner behavior;
2. task-level safety semantics are wrong for typing, selection, drag, form
   submission, and other state-changing operations;
3. official evaluator wording is treated as already-authoritative TaskSpec
   without an explicit normalization boundary.

### Required correction

Split runner data into:

- AuditMetadata: suite, task id, seed, evaluator version, reward, termination;
- RuntimeInput: normalized instruction or canonical TaskSpec, constraints,
  capabilities, budgets, and environment observations.

AuditMetadata must never be exposed through planner target, prompt, memory,
skill trigger, or recovery policy.

Operation class and capabilities must be derived from typed intent and action
semantics, not assigned globally by the suite runner.

## 7. Critical Finding: Recovery Covers Only the Lower Half

Severity: **P0**

The Runtime has a meaningful Recovery Cascade, but the normal path does not
route every failure through it.

Observed gaps include:

- planner exceptions terminate the run;
- invalid planner output or proposal-binding failure usually terminates;
- no-affordance and insufficient-context states often become repeated ask-user
  or repeated planning;
- progress guards reobserve and invoke substantially the same planner state;
- task-planning failure, context overflow, provider quota, provider timeout, and
  schema-repair exhaustion lack one coordinated policy;
- varied wrong targets can evade repeated-error matching because exact
  signatures include volatile target/backend details;
- accepted recovery profiles are not consistently loaded by benchmark and
  normal entrypoints.

The current loop can therefore repeatedly try until budget exhaustion without
changing a meaningful assumption. That is bounded retry, not harness recovery.

### 7.1 Recovery must span all phases

The target Recovery Coordinator handles:

- INTAKE;
- OBSERVATION;
- FUSION;
- TASK_PLANNING;
- STEP_PLANNING;
- PROPOSAL_VALIDATION;
- GROUNDING_AND_BINDING;
- PREFLIGHT;
- EXECUTION;
- VERIFICATION;
- PROVIDER_AND_CONTEXT;
- SKILL_ACTIVATION.

Each failure becomes a normalized FailureEnvelope with phase, semantic class,
evidence, state fingerprint, attempted strategy, uncertainty, side-effect
status, and remaining budgets.

### 7.2 Recovery must change something

Another attempt is legal only when the strategy changes at least one of:

- observation source, scope, or freshness;
- task assumption or ambiguity resolution;
- task plan or active subgoal;
- grounding candidate or semantic target;
- executor backend;
- verifier source or strength;
- provider, model, or compacted context;
- accepted skill usage;
- user-provided information.

If no safe change is available, ask the user or abort. Do not repeat the same
planner against the same semantic state.

### 7.3 Semantic cascade detection

Preserve exact signatures for debugging, but add a semantic family key for
cascade control:

~~~text
phase
+ failure class
+ active subgoal
+ expected effect
+ side-effect status
+ normalized observation/progress fingerprint
~~~

This catches repeated planning or grounding failure even when the selected
target id changes on each attempt.

## 8. Finding: Task-Level Planning Is Not the Default Scored Path

Severity: **P1**

TaskPlannerPort, TaskPlan, SubgoalSpec, validation, lineage, and criteria-bound
progress exist. The BrowserGym episode runner currently constructs the
Coordinator without a task planner.

This means benchmark execution primarily evaluates a flat step planner plus
task-family compilers, not the declared optional task-level planner.

### Required correction

Use one task-plan router for all entrypoints:

- simple atomic task: one implicit flat subgoal;
- accepted TaskSkill: validated semantic steps;
- clearly structured deterministic task: standards-based plan;
- open-world, ambiguous, or multi-stage task: LM task planner;
- unsafe ambiguity: clarification rather than plan.

Do not require a DAG for every task. A flat one-subgoal plan is the default.
Dependencies are used only when the objective has real ordering or branching.
Effectful actions remain serial.

## 9. Finding: Planner Registry and Context Contracts Are Too Weak

Severity: **P1**

The compiler registry needs enforceable metadata rather than informal
applicability. Each deterministic compiler must declare:

- typed intent and operation class;
- required observation properties;
- supported action semantics;
- success and evidence requirements;
- confidence and ambiguity behavior;
- positive, paraphrase, distractor, and negative examples;
- source, version, and active profile;
- fallback behavior.

The action planner must receive a bounded PlannerContext containing:

- immutable TaskSpec revision;
- active subgoal and remaining obligations;
- current coherent observation epoch;
- current semantic candidates and conflicts;
- verified progress and evidence summary;
- normalized failure and recovery summary;
- rejected assumptions and attempted routes;
- capabilities, constraints, and remaining budgets.

It must not receive:

- benchmark identity;
- official reward;
- stale raw selectors or coordinates;
- full unbounded trace;
- evaluator hints;
- authority inferred from page content.

## 10. Finding: Large Modules Hide Responsibility Drift

Severity: **P1**

Generalist planner logic has accumulated interpretation, task-family
compilation, context assembly, proposal generation, and schema repair.

RunCoordinator has previously approached the same growth pattern, although
several collaborators have been extracted.

The correction is not microservices. Keep the modular monolith and extract
small internal collaborators at real ownership boundaries:

- IntentCompiler;
- TaskPlanRouter;
- GeneralistStepPlanner;
- PlannerProposalValidator;
- PlannerContextBuilder;
- PerceptionSession;
- ContractBindingService;
- ContractExecutionLoop;
- RecoveryCoordinator;
- TraceWriter.

The Coordinator remains the single authoritative state writer.

## 11. C009 Comparison

The old C009 branch should remain a component source, not be merged wholesale.

### 11.1 Areas where the current Runtime is stronger

- action validity and immutable contracts;
- approval and capability binding;
- independent postcondition verification;
- trace and artifact persistence;
- benchmark metrics and ablations;
- declarative, regression-gated evolution;
- task-level planning data contracts;
- cross-surface route and verifier plans.

### 11.2 Areas where C009 remains stronger

- active perception and multi-source epistemic arbitration are more cohesive;
- the online interaction manager owns retry, reroute, rollback, reobserve, and
  verify as one recovery loop;
- backend confidence and cost selection are integrated into the action loop;
- Thing Directory and node-wot discovery have stronger real-environment assets;
- the structured GoalSpec boundary makes its planning claim more honest.

### 11.3 Selective migration candidates

Worth adapting:

- StateAssertion, fused assertion, and explicit source conflict models;
- rule-first epistemic arbitration and active-perception requests;
- Thing Directory and node-wot discovery;
- verifier-backed backend confidence and cost signals;
- safe reflex or accepted-skill cache concepts;
- fusion calibration, chaos injection, and real WoT fixtures;
- the recovery strategy ordering and reobserve-before-retry discipline.

Do not migrate:

- ContinuousInteractionManager as one large controller;
- C009 smart-room task routing;
- GoalSpec to PrimitiveAction as the new product chain;
- fixed action tuples, selectors, coordinates, or WoT URLs;
- old compatibility planner/router namespaces;
- context isolation mislabeled as Picture-in-Picture;
- evolution artifacts activated without fresh regression acceptance.

## 12. SOTA-Informed Planner Direction

Representative systems support a simple conclusion:

- SeeAct separates textual planning from visual and HTML grounding;
- Agent S2 uses manager-worker planning and dynamic replanning;
- Agent S3 removes hierarchy inside one rollout to reduce inference cost;
- browser-use uses a custom async observe-plan-act loop with planning on demand,
  loop detection, and context compaction;
- OpenHands detects repeated actions, repeated errors, A-B cycles, and context
  problems rather than treating every failure as an isolated retry.

The appropriate design for this Runtime is not a copy of one framework:

> Use a flat generalist loop by default, optional shallow task planning for
> multi-stage work, explicit grounding and contract binding, and a
> phase-spanning Recovery Coordinator.

LangGraph may orchestrate parent workflows or approval waits later. It must not
become the authoritative low-level GUI execution state.

## 13. Target Architecture

~~~text
UserRequest
  -> IntentCompiler
  -> TaskSpec + ambiguity and authority result
  -> TaskPlanRouter
       -> flat subgoal
       -> accepted TaskSkill
       -> validated LM TaskPlan
  -> active SubgoalSpec
  -> PerceptionRequirements
  -> PerceptionSession
       -> DOM / accessibility
       -> SVG
       -> screenshot / OCR / SoM / pure visual
       -> WoT / API
  -> semantic entity resolution
  -> GeneralistStepPlanner
  -> semantic PlannerProposal
  -> PlannerProposalValidator
  -> route and candidate binding
  -> fresh ActionContract
  -> policy and preflight
  -> execute
  -> post-state inspection
  -> criteria-bound verifier
  -> continue / complete
       or
     RecoveryCoordinator
  -> canonical trace
  -> offline evaluation and controlled evolution
~~~

Rules, LM outputs, parent-agent proposals, and accepted skills all enter through
the same validation and execution boundaries.

## 14. Correct Benchmark Operating Model

### 14.1 Diagnostic runs

A bounded nightly or release diagnostic should continue after ordinary episode
failure and produce a complete report.

Collect first, repair second.

Cluster failures by:

- Runtime phase;
- semantic failure family;
- task intent and operation class;
- required perception source;
- grounding and gesture type;
- provider/context outcome;
- verification and side-effect status;
- recovery strategy and cascade depth.

### 14.2 Fail-fast conditions

Stop only when remaining results would be unsafe or invalid:

- policy or authority breach;
- uncertain duplicate side effect;
- corrupt trace or result accounting;
- environment drift;
- provider outage invalidating the profile;
- lost isolation or runaway resources.

Persist the partial report and resume only unobserved cases after repair.

### 14.3 Repair selection

Choose a repair from a cross-task cluster only after identifying a generic
Runtime owner. Implement and prove it outside the suite before targeted replay.

Never repair one failure immediately and restart the full matrix from zero. That
process optimizes for the next visible test rather than the architecture.

## 15. M8.6 Corrective Plan

M8.6 is the new hard gate before M8.2B score promotion.

### G0: Freeze and classify

- freeze current benchmark evidence and immutable revisions;
- stop treating 300/300 or residual release improvement as planner proof;
- enumerate active compilers, prompts, skills, providers, and profiles;
- label each rule as standards, safety, accepted skill, compatibility, or
  suspected task grammar;
- preserve failing and successful traces for audit.

Exit:

- every scored report identifies its active profile and registry digest;
- no new task-family repair enters default generalist code.

### G1: Strict-generalist planner profile

- make strict-generalist the default;
- remove benchmark-shaped compilers from the default registry;
- isolate historical compatibility rules;
- enforce compiler metadata and PlannerProposalValidator for all proposal sources;
- add behavioral anti-cheating tests;
- add real local paraphrase, distractor, ambiguity, and unrelated-interface
  scenarios.

Exit:

- the negative probes in this audit defer, clarify, or act only on explicitly
  authorized targets;
- no compatibility profile result supports a generalist claim;
- strict-generalist works on non-BrowserGym Web, visual, and WoT paths.

### G2: Task planning and intent honesty

- separate IntentCompiler, TaskPlanRouter, and GeneralistStepPlanner;
- derive operation class, constraints, and capabilities from typed intent;
- route simple tasks to one flat subgoal;
- use shallow validated plans only for genuinely multi-stage tasks;
- wire the same router into reference, parent-agent, and benchmark entrypoints;
- keep planner output semantic.

Exit:

- raw natural language reaches a validated TaskSpec;
- simple and multi-stage real local tasks use the declared chain;
- task plan lineage and criteria-bound progress are traceable;
- benchmark identity is absent from planner context.

### G3: Full-phase Recovery Coordinator

- normalize failures from every phase;
- add semantic cascade keys;
- recover planner exceptions, schema failures, no-affordance states, binding
  failures, context exhaustion, provider failures, stale state, execution
  uncertainty, and verification failure;
- require a meaningful strategy change before retry;
- load accepted recovery profiles explicitly in normal entrypoints;
- preserve inspect-before-repeat for effectful actions.

Exit:

- representative failures in every phase enter one traceable recovery path;
- repeated equivalent failure is stopped before budget exhaustion;
- no blind duplicate effect occurs;
- at least one failure recovers by new perception, one by replan, one by route or
  verifier change, and one safely asks or aborts.

### G4: Result audit and nightly protocol

- complete matrices after ordinary failures;
- preserve resumable checkpoints and all unrun status;
- separate infrastructure invalidation from task failure;
- cluster before repair;
- add profile, registry, prompt, model, and budget identity;
- keep external reward separate from Runtime verification.

Exit:

- a diagnostic report can account for every scheduled episode;
- one report shows cross-task failure clusters and architecture ownership;
- a partial invalid run cannot be mistaken for a score.

### G5: Generalization proof

Evaluate four isolated profiles:

1. strict-generalist;
2. strict-generalist plus accepted skills;
3. historical compatibility;
4. ablations.

Required evidence:

- unseen local Web layouts and vocabulary;
- paraphrase and distractor suite;
- ambiguous and under-specified tasks;
- DOM, accessibility, SVG, visual, and WoT routing;
- provider/context stress;
- recovery injection;
- BrowserGym targeted and breadth audits;
- public suites only when their assets and environments are independently
  provisioned.

Exit:

- strict-generalist success is reported independently;
- accepted skills improve cost or success without safety regression;
- compatibility uplift is visible rather than hidden;
- no benchmark score is used as the sole proof of generalization.

## 16. Acceptance Metrics

### Planner

- semantic task success on unseen local tasks;
- clarification precision for blocking ambiguity;
- unrequested-action rate;
- task-scope expansion rate;
- paraphrase consistency;
- distractor false-activation rate;
- valid proposal rate;
- model calls and latency.

### Recovery

- failure detection recall by phase;
- semantic repeated-error stop rate;
- recovery success rate by changed strategy;
- no-progress loop length;
- blind retry count;
- duplicate-effect count;
- safe ask-user and abort precision;
- accepted recovery profile effectiveness.

### Runtime

- task success;
- verifier false-accept rate;
- constraint violation rate;
- stale detection recall;
- route fallback success;
- trace completeness;
- profile reproducibility.

Hard safety requirements:

- unauthorized effect count equals zero;
- unapproved high-risk effect count equals zero;
- known uncertain effects are inspected before repeat;
- benchmark identity leak into planner context equals zero.

## 17. Immediate Work Order

The next implementation sequence is:

1. land governance documents and correct milestone claims;
2. introduce explicit strict-generalist and compatibility profiles;
3. add behavioral probes that currently fail;
4. isolate or disable task-family compilers in the strict profile;
5. remove benchmark identity from planner context;
6. wire TaskPlanRouter into normal and benchmark entrypoints;
7. add phase-spanning FailureEnvelope and RecoveryCoordinator;
8. make nightly collection complete and cluster-first;
9. run non-benchmark conformance;
10. only then resume targeted and breadth benchmark audits.

Do not start by tuning prompts, changing providers, increasing timeout, adding
more task grammar, or chasing a higher release score.

## 18. Deferred Work

The following remain outside this corrective gate:

- distributed worker pools and queues;
- multi-tenant service infrastructure;
- arbitrary source-code self-modification;
- recursive task-plan hierarchies;
- multiple effectful agents controlling one session;
- benchmark-specific planner adapters in the product path;
- full desktop or mobile expansion;
- Picture-in-Picture UI without a measured user need.

## 19. Final Governance Decision

The repository should continue, not be rewritten or merged back into C009.

Its core contracts, unified routing, verification, trace, and controlled
evolution are the correct foundation. The next step is to make the default
planner and online recovery obey that architecture.

M8.2B is therefore subordinate to M8.6:

~~~text
first prove the Runtime is honest, general, and recoverable
then use benchmarks to audit how well it works
~~~
