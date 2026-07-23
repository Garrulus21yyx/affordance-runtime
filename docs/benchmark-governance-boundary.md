# Benchmark Governance and Anti-Specialization Boundary

Status: **normative**

This document governs all benchmark-driven work in Affordance Runtime. It is
jointly authoritative with the Runtime-First Architecture Boundary. If a
milestone plan, benchmark checklist, prompt, planner rule, compiler, skill, or
test conflicts with this boundary, this boundary wins.

## 1. Product and Evaluation Boundary

Affordance Runtime is the product. BrowserGym, MiniWoB++, ScreenSpot,
WorkArena, WebArena-Verified, WASP, local fixtures, and future suites are
external consumers and evaluation instruments.

The product objective is:

> Build a general GUI Agent Harness Runtime that can interpret bounded user
> tasks, plan semantic subgoals, observe heterogeneous environments, ground and
> execute current actions, verify effects, recover from failures, trace every
> decision, and improve only through regression-gated harness learning.

A benchmark has one role:

> Audit the robustness, safety, efficiency, and generalization of the Runtime
> architecture.

A benchmark score is not the product objective, roadmap owner, planner design
input, or definition of general intelligence.

## 2. Non-Negotiable Rule

A benchmark failure may reveal a Runtime capability gap. It may not authorize a
benchmark solver.

Every accepted repair must be expressible as all of the following:

1. an environment-independent capability, invariant, contract, or policy;
2. a generic implementation outside suite-specific orchestration;
3. a non-benchmark conformance test;
4. at least one negative control or distractor test;
5. the normal Runtime path from TaskSpec through verification and trace;
6. a benchmark replay used only as confirmation.

If a proposed repair cannot satisfy these conditions, it belongs in an external
adapter, a compatibility profile, or the rejected-change log. It does not belong
in Runtime core or the default generalist planner.

## 3. Prohibited Specialization

### 3.1 Hard specialization

The following are prohibited in Runtime core, shared adapters, the default
planner, and accepted skills:

- dispatch by task id, task family, seed, suite, manifest, URL, title, or reward;
- fixed benchmark selectors, bids, coordinates, mark ids, labels, answers, or
  action sequences;
- reading official evaluator state as planning or Runtime success evidence;
- bypassing TaskSpec, PlannerProposalValidator, ActionContract, policy, preflight,
  post-observation, verification, recovery, or trace;
- moving benchmark logic into a shared filename merely to pass source scans;
- increasing timeout, retry, or model budget to hide a semantic loop.

### 3.2 Soft or disguised specialization

The prohibition is behavioral, not lexical. A change is still specialization
when it avoids suite names but implements a benchmark task grammar.

Examples include:

- a default compiler that recognizes calendar wording and emits the exact
  sequence needed by the benchmark family;
- a sorting, tree, disclosure, autocomplete, quantity, social, or drag solver
  that activates from narrow instruction phrases learned from a suite;
- a rule that treats quoted strings, both fields, starts with, or similar
  benchmark wording as sufficient authority without a general typed intent
  contract;
- terminal exposure based on the expected shape of a benchmark task rather than
  verified TaskSpec obligations;
- planner branches whose positive examples come from one suite and whose
  negative controls do not cover paraphrases, distractors, or unrelated real
  interfaces;
- a compatibility rule enabled in the default generalist profile.

Renaming such logic as semantic compiler, generalist rule, skill, heuristic, or
System 1 does not make it general.

## 4. What Generic Capability Work Looks Like

Allowed work improves a declared Runtime abstraction rather than a task answer.
Examples include:

- standards-based actionability for native controls, authored interactive
  elements, ARIA widgets, SVG geometry, canvas or screenshot regions, WoT
  operations, and API affordances;
- provenance-preserving multi-source observation and conflict handling;
- semantic target identity, source and destination gesture invariants, and
  typed candidate binding;
- task-derived PerceptionRequirements and lazy source escalation;
- verifier-backed route reliability and inspect-before-repeat safety;
- criteria-bound subgoal progress and ambiguity detection;
- bounded provider context, typed provider failure, and safe user clarification;
- general recovery from stale state, missing grounding, execution uncertainty,
  verification failure, planning failure, and context degradation;
- trace-derived TaskSkill or RecoverySkill artifacts that pass held-out replay.

A generic capability may improve a benchmark. The benchmark improvement is
external confirmation, not the reason the capability is valid.

## 5. Planner Boundary

The planner stack has three distinct responsibilities:

~~~text
UserRequest
  -> Intent Compiler
  -> immutable TaskSpec
  -> optional TaskPlanner
  -> active SubgoalSpec
  -> Generalist Step Planner
  -> semantic PlannerProposal
  -> PlannerProposalValidator
~~~

The Intent Compiler may infer a typed draft and identify ambiguity. It may not
grant authority or emit GUI actions.

The TaskPlanner may decompose a genuinely multi-stage objective into
outcome-oriented subgoals. It may not encode selectors, coordinates, backend
actions, benchmark labels, or authority. Simple tasks remain flat.

The Generalist Step Planner selects one semantic next action from the current
TaskSpec, active subgoal, bounded history, current observation, and available
affordances. It may not be a registry of benchmark task-family programs.

PlannerProposalValidator is mandatory for rule, LM, parent-agent,
accepted-skill, and recovery-produced proposals. It runs before completion,
clarification, contract binding, approval, or execution handling.

Each proposal carries separate runtime-authored `PlannerProposalProvenance`.
The semantic proposal producer cannot author authority through this field. The
provenance names the typed source, producer identity, profile/version, and
evidence references; it is validated, traced, and persisted with proposal
history. Missing provenance is a proposal rejection. A planner-authored
subgoal never expands TaskSpec target scope.

### 5.1 Default and compatibility profiles

The strict-generalist profile is the default scored and product profile.

Its rule set may contain only:

- protocol and schema normalization;
- standards-based deterministic semantics;
- safety and authority rules;
- accepted, versioned skills whose applicability and replay evidence are
  explicit.

Benchmark-family compilers must be absent from this profile.

Historical or suite compatibility logic may exist only in an explicitly named
compatibility profile. Compatibility results cannot support a generalist claim
and must be reported separately.

## 6. Benchmark Identity Isolation

The planner-facing task and context must not contain suite identity unless the
user's real task explicitly requires it.

External runners may retain task id, seed, official evaluator wording, suite
version, and reward in audit metadata. They must not place these values in
planner-visible targets, goals, hints, memory, skill triggers, or recovery
policies.

The Runtime receives only the normalized user instruction or canonical
TaskSpec, current observations, capabilities, constraints, budgets, and
evidence. Official reward is stored after the run as an external evaluator
result.

## 7. Benchmark Failure Promotion Protocol

Benchmark execution and architecture repair are separate phases.

~~~text
run a bounded diagnostic matrix to completion
  -> retain every episode result
  -> normalize and cluster failure signatures
  -> identify the owning Runtime phase
  -> state a generic invariant or missing contract
  -> reproduce outside the benchmark
  -> add negative controls and distractors
  -> implement the generic repair
  -> run focused conformance and safety tests
  -> replay the targeted benchmark cluster
  -> replay breadth, nightly, or release profiles
~~~

Ordinary task failures do not stop the diagnostic matrix. The matrix must
continue so error clusters, cross-task frequency, and architecture ownership can
be assessed together.

Fail-fast is reserved for:

- safety or authority violation;
- trace, schema, or artifact corruption;
- invalid official result accounting;
- environment drift that makes remaining runs non-comparable;
- provider or infrastructure failure that invalidates the whole matrix;
- runaway resource use or loss of isolation.

After a fail-fast event, preserve the partial report and mark all unrun cases as
not observed. Never restart from zero without retaining the previous evidence.

## 8. Required Evidence for a Generic Repair

Every promoted repair must include:

1. a Runtime-level failure statement;
2. the owning port, contract, invariant, or policy;
3. a benchmark-independent reproduction;
4. paraphrase or equivalent-intent coverage where language is involved;
5. distractor, ambiguity, and unrelated-task negative controls;
6. proof that the same Coordinator and ActionContract path is used;
7. safety, uncertain-effect, and duplicate-effect checks where applicable;
8. targeted benchmark confirmation;
9. breadth regression evidence;
10. an honest claim describing what remains unsupported.

A targeted family pass is never sufficient by itself.

## 9. Behavioral Anti-Cheating Tests

Static scans for suite names are necessary but insufficient. Governance tests
must also exercise behavior.

The strict-generalist planner must be tested with:

- paraphrases not present in benchmark instructions;
- unrelated controls that resemble task-family patterns;
- extra writable fields and extra terminals;
- ambiguous labels and multiple valid candidates;
- contradictory DOM, accessibility, SVG, visual, and WoT evidence;
- requests that mention a prefix but do not authorize selection or submission;
- disclosure controls that exist but were not requested;
- real local interfaces with different layout and vocabulary;
- missing evidence that must cause clarification or safe deferral;
- accepted skill disabled, enabled, stale, and applicability-mismatch profiles.

A rule fails governance when it takes an unrequested action, completes an
unverified obligation, expands scope, or activates from a task-shaped phrase
without sufficient current evidence.

## 10. Recovery and Evolution Boundary

Same-run recovery may use only bounded, predefined or accepted strategies. It
must change at least one meaningful variable before another attempt:

- observation coverage or freshness;
- task or subgoal assumption;
- grounding candidate or source;
- executor route;
- verifier strength;
- provider or compacted context;
- requested user information.

Repeating the same planner with the same semantic state is not recovery.

Cross-run learning remains offline and controlled:

~~~text
verified traces
  -> failure or success mining
  -> declarative candidate
  -> quarantine
  -> held-out and safety replay
  -> accept, reject, remain quarantined, or roll back
~~~

No benchmark failure may immediately mutate the default planner, prompt, policy,
or skill registry.

## 11. Reporting Profiles

Reports must identify the active profile:

- strict-generalist;
- strict-generalist plus accepted skills;
- historical compatibility;
- ablation;
- infrastructure diagnostic.

Scores from different profiles must not be merged.

Every report records:

- immutable source revision;
- planner and model identity;
- active compiler and skill registry digests;
- prompts and budgets;
- environment and suite versions;
- observed, completed, failed, and unrun counts;
- Runtime failure taxonomy;
- external evaluator result;
- safety and duplicate-effect outcomes.

## 12. Review Checklist

Every benchmark-related pull request must answer:

1. What user-facing Runtime capability is missing?
2. Can the behavior be described without naming a benchmark?
3. Which generic contract or invariant owns it?
4. Which non-benchmark test proves it?
5. Which paraphrase and distractor tests prevent task-grammar overfitting?
6. Could this rule take an action the user did not request?
7. Does planner-visible context contain benchmark identity?
8. Does the change preserve PlannerProposalValidator, ActionContract, policy, preflight,
   post-observation, verification, recovery, and trace?
9. Is an accepted skill involved, and is applicability regression-gated?
10. Is the benchmark result being used as audit evidence rather than product
    completion?

A missing or weak answer blocks merge.

## 13. Violation Response

When specialization is found:

1. stop benchmark score promotion;
2. preserve traces and current evidence;
3. disable the rule in strict-generalist profiles;
4. move historical compatibility behavior behind an explicit profile if needed;
5. add a behavioral regression that demonstrates the leak;
6. redesign the capability at the correct Runtime boundary;
7. rerun local conformance before benchmark confirmation;
8. correct README, status, and milestone claims.

Passing scores obtained through a violating path remain historical diagnostics
and cannot support current architecture claims.

## 14. Final Principle

The repository is successful when unseen, real environments benefit from the
same contracts, observation, planning, routing, verification, recovery, trace,
and learning architecture.

It is not successful merely because a fixed benchmark matrix reaches a high
score.
