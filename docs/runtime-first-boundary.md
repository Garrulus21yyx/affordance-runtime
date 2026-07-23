# Runtime-First Architecture Boundary

Status: **normative**. This document constrains implementation, review,
milestone claims, and benchmark-driven repair work. When another current-plan
document is ambiguous, this boundary takes precedence. It does not override the
explicitly deferred production blueprint.

The [Benchmark Governance and Anti-Specialization Boundary](benchmark-governance-boundary.md)
is jointly normative. It extends this file from source-level restrictions to
behavioral restrictions on prompts, semantic compilers, skills, planner
profiles, and benchmark-driven repair. A benchmark is an architecture auditor,
not the product objective.

The
[Active Perception and Online Recovery Architecture](active-perception-and-online-recovery.md)
is also normative for M8.6. It defines how missing evidence is repaired before
effects, how phase-general failures become typed recovery commands, and how the
single Coordinator retains authority.

## 1. Decision

Affordance Runtime is the product. BrowserGym, MiniWoB++, WorkArena, ScreenSpot,
WebArena-Verified, WASP, and local fixtures are consumers and evaluation
environments.

~~~text
UserRequest / TaskSpec
  -> task planning
  -> task-aware perception
  -> semantic entity resolution
  -> unified route selection
  -> ActionContract
  -> policy and preflight
  -> execution
  -> post-action observation
  -> criteria-bound verification
  -> recovery / continuation
  -> trace, evaluation, and controlled learning

                              |
                              +-> BrowserGym adapter
                              +-> Playwright live-site adapter
                              +-> visual-only adapter
                              +-> WoT/API adapter
                              +-> parent-agent integration
~~~

Architecture work MUST improve this Runtime path first. A benchmark adapter may
translate an external environment into Runtime contracts, but it must not become
an alternative planner, perception stack, recovery engine, or skill system.

## 2. Non-Negotiable Boundary

The following responsibilities belong to Runtime core or generic Runtime ports:

- task and subgoal semantics;
- perception requirements and observation orchestration;
- source provenance, freshness, conflict, typed evidence gaps, and bounded
  active-perception probes;
- semantic target identity and multi-source candidate alignment;
- typed DOM, accessibility, SVG, SoM, pure-visual, WoT, and API candidates;
- route hard gates, verifier-backed calibration, and safe fallback;
- gesture invariants and candidate-to-contract binding;
- capability, approval, preflight, and uncertain-effect inspection;
- criteria-bound postcondition verification;
- phase-general FailureEnvelope, changed-strategy RecoveryCommand,
  RecoveryReceipt, RecoveryDelta, bounded cascade decisions, and System 1/2
  fallthrough;
- canonical trace, trace-to-skill normalization, replay, and acceptance.

BrowserGym-specific code is limited to:

- environment registration, reset, seed, and episode lifecycle;
- converting BrowserGym observations into generic observation inputs;
- converting a validated Runtime action or gesture into BrowserGym action syntax;
- collecting official reward, termination, and diagnostic metadata;
- resumable matrix execution and report generation.

BrowserGym-specific attributes such as bids or set-of-marks MAY be read by the
BrowserGym observation adapter. They MUST be normalized before entering core.
Core modules must not depend on BrowserGym package types, task names, selectors,
action strings, reward conventions, or fixture-specific DOM classes.

## 3. Prohibited Benchmark Specialization

The following are prohibited in Runtime core, the generalist planner, and shared
DOM/visual/WoT adapters:

- branches keyed by benchmark task id, task family, seed, or official manifest;
- fixed selectors, bids, coordinates, mark ids, labels, answers, or action
  sequences derived from a benchmark;
- benchmark-authored calendar, social-media, shopping, sorting, or tree semantics
  embedded as unconditional generalist logic;
- using official reward as Runtime postcondition evidence;
- bypassing TaskSpec, semantic proposal, ActionContract, policy, preflight,
  post-observation, or verification to improve benchmark success;
- adding a parser or action schema only inside the BrowserGym runner when the
  capability is part of the declared Runtime product;
- declaring an architecture milestone complete from targeted benchmark family
  success alone.

Rule-first behavior is allowed only when it expresses an environment-independent
semantic capability, is registered through a generic rule interface, declares
its applicability and evidence, and passes non-benchmark negative controls.

This prohibition is behavioral. A shared or generalist module still violates
the boundary when it recognizes benchmark-shaped instruction grammar and emits
the task family's expected action sequence. Calendar, autocomplete, quantity,
sorting, hierarchy, disclosure, form, copy, social, or drag programs are not
general merely because they omit suite ids.

Rules must prove typed applicability with paraphrases, distractors, ambiguity,
and unrelated-interface negative controls. They must not expand requested
scope, expose an unrequested terminal, or complete an obligation from task
shape rather than current verifier evidence. Renaming a solver as a semantic
compiler, heuristic, System 1 rule, or skill does not exempt it from this
boundary.

## 4. Benchmark Failure Promotion Protocol

Every benchmark failure must be handled in this order:

~~~text
complete or bounded diagnostic run
  -> normalized failure signature
  -> architecture ownership decision
  -> generic invariant / contract / port / policy change
  -> local non-benchmark conformance test
  -> negative-control and safety tests
  -> BrowserGym adapter conformance test
  -> targeted benchmark replay
  -> breadth/nightly/release replay
~~~

A patch is not architecture work merely because several benchmark tasks share
the same HTML pattern. Review must identify the product-level capability, such
as authored interactive elements, spatial target binding, list-item ownership,
or drag source/destination semantics.

If no environment-independent capability can be stated and tested, the change
belongs in the benchmark adapter or must be rejected.

## 5. Required Evidence for Generic Repairs

An architecture repair discovered through BrowserGym is eligible for promotion
only when all applicable evidence exists:

1. a generic contract or invariant states the corrected behavior;
2. a unit test covers the generic model without importing BrowserGym;
3. a local Playwright, visual, WoT, or synthetic-port scenario proves the path;
4. a negative control proves the rule does not expose unrelated elements or
   actions;
5. the BrowserGym adapter only performs normalization or backend encoding;
6. the same Coordinator, policy, preflight, verifier, recovery, and trace path is
   used;
7. targeted and breadth benchmark runs confirm the external symptom is repaired.

Benchmark-only success is evaluation evidence, not architecture evidence.

## 6. Planner Boundary

The task planner emits outcome-oriented subgoals. The action planner emits
semantic action proposals. Neither may emit or authorize raw selectors,
coordinates, bids, backend action strings, capabilities, or approvals.

Rule-based planning is a System 1 optimization, not a place to accumulate
benchmark solvers. Every rule must implement a typed, independently named
semantic compiler interface and declare:

- supported intent and operation class;
- required observation properties;
- output schema and verifier requirements;
- applicability predicate and confidence;
- negative examples;
- source and version;
- fallback to the general planner.

Rules that mention benchmark families remain in benchmark profiles and do not
count as Runtime capability.

The default product and scored profile is strict-generalist. Its deterministic
registry is limited to protocol/schema normalization, standards-based control
semantics, safety/authority rules, and accepted regression-gated skills.
Benchmark-shaped compilers must be absent.

Historical compatibility behavior may remain only in an explicitly named
compatibility profile. Its results are reported separately and cannot support a
generalist claim. Static source scans are insufficient; behavioral
anti-specialization tests are required.

## 7. Perception and Routing Boundary

TaskSpec or active SubgoalSpec derives PerceptionRequirements. The Coordinator
passes those requirements to one generic PerceptionOrchestrator. The
orchestrator may acquire DOM, accessibility, SVG, screenshot, OCR, SoM,
pure-visual, WoT, or API evidence lazily.

All sources return provenance-preserving candidates in one coherent observation
epoch. Required evidence is evaluated per semantic target and candidate, not as
an unrelated page-global flag.

Route selection chooses the complete path:

~~~text
perception source
  + grounding candidate
  + executor
  + verifier plan
~~~

Route learning uses postcondition-verifier outcomes, never executor receipt
success or official benchmark reward.

## 8. Verification and Learning Boundary

No subgoal or SkillStep completes from an arbitrary passed report. Verification
must match the active success criteria, evidence requirements, semantic target,
expected effect, and freshness boundary.

TaskSkill mining starts from canonical persisted Runtime traces. Manually
constructed semantic traces may be test fixtures but cannot establish an
end-to-end learning claim.

Accepted TaskSkill and RecoverySkill artifacts are loaded through an explicit,
versioned Runtime profile. They still execute step-by-step through fresh
observation, route selection, ActionContract, policy, preflight,
post-observation, and verification.

## 9. Module Ownership

| Module area | Owns | Must not own |
| --- | --- | --- |
| Core contracts | typed invariants and immutable attempt state | benchmark package types or action syntax |
| Generic adapters | standards-based source normalization | MiniWoB task-family solvers |
| Perception | task-aware source acquisition, evidence-gap repair, and provenance | task completion decisions or hidden effectful probes |
| Active perception | cheapest permitted read-only probe and new coherent epoch | action planning, authority changes, or mutation of an old snapshot |
| Planner | semantic intent and outcome proposals | selectors, coordinates, authority, or execution |
| ContractBuilder | candidate binding and fresh attempt contract | free-form task reasoning |
| Coordinator | authoritative serial state transitions | benchmark episode policy |
| Verifier | criteria-bound independent evidence | official reward as sole truth |
| Recovery | phase-general changed-strategy inspect/reobserve/replan/reground/reroute/verify/ask/abort | benchmark-family retries, direct execution, or blind effectful repeat |
| Evolution | trace-derived proposals and regression gate | immediate online self-modification |
| BrowserGym adapter | observation/action/reward translation | replacement Runtime architecture |

## 10. Review and Claim Gate

Every pull request touching benchmark reliability must answer:

1. Which Runtime-level failure class does this repair?
2. Why is the implementation in this module?
3. Which non-BrowserGym test proves generality?
4. Which negative control prevents over-exposure or false matching?
5. Does any benchmark label, selector, coordinate, or action syntax enter core?
6. Does the patch preserve contract, policy, preflight, verification, and trace?
7. Is the benchmark result diagnostic, targeted, nightly, or release evidence?

8. Would the behavior remain correct under paraphrase, distractors, and extra controls?
9. Does the rule encode a task grammar or expose an effect the user did not request?
10. Is the benchmark being used as an auditor rather than the repair objective?
A milestone may be marked done only when its declared generic Runtime path is
wired into a normal entrypoint and has reproducible evidence from the current
immutable revision.
