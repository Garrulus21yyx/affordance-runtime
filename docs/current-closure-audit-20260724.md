# M8.6 Closure Audit - 2026-07-24

## 1. Scope

This audit reviews remote branch `agent/migrate-runtime-components` at:

~~~text
f4c3308e7b4fcb945425a7d79b4d1e27588befde
docs: record m8.6 implementation freeze
~~~

The worktree was clean before and after verification. The review traced the
normal Runtime entrypoints rather than accepting milestone prose or unit-test
counts as behavioral proof. It covered strict planning, intent and TaskPlan
routing, active perception, phase-general recovery, complete-run evaluation,
generalization evidence, and responsibility containment.

## 2. Executive Decision

M8.6 contains substantial real implementation. It is not a documentation-only
milestone. However, the claim that all G0-G5 exit criteria are closed is broader
than the current behavior and evidence support.

The correct status is:

> **M8.6 implementation substantially complete; closure reopened for G2.5 and
> G3 semantic defects and G5 empirical evidence.**

The repository may not promote the milestone back to `done` until the closure
work in Section 7 is complete. Historical benchmark results remain compatibility
or diagnostic evidence and must not be promoted.

## 3. Verification

Using `/home/yang/.venvs/affordance-browsergym-py312/bin/python`:

~~~text
pytest -p no:cacheprovider -q
665 passed in 11.13s

ruff check src tests scripts
All checks passed

mypy --ignore-missing-imports src
Success: no issues found in 96 source files
~~~

These results prove that the checked-in test and static-analysis gates are
healthy. They do not remove the semantic findings below because the missing
integration assertions are not represented in the current test suite.

No remote model, real browser benchmark matrix, external suite, credential, or
score-producing evaluation was run during this audit.

## 4. Gate Assessment

| Gate | Audit decision | What is actually established |
| --- | --- | --- |
| G0 evidence/profile freeze | complete | historical and current profile identities are separated; score promotion is disabled |
| G1 strict generalist | substantially complete | strict is default; compatibility grammar is physically isolated; proposal provenance and validation are shared |
| G2 intent and TaskPlan | complete for internal entrypoints | raw request compilation, typed TaskSpec, flat/shallow planning, and criteria-bound subgoal progress are wired |
| G2.5 active perception | reopened | typed protocol and call sites exist, but task model/cost budgets can be expanded and source presence can masquerade as semantic evidence |
| G3 full-phase recovery | reopened | failure normalization, cascade control, and uncertain-effect inspection are real; several advertised commands have no owning-port effect |
| G4 complete-run audit | complete | ordinary failures continue, batch stops are allowlisted, partial results and resume accounting are typed |
| G5 generalization evidence | schema/conformance complete; empirical proof incomplete | four-profile report validation is real, but the comparison ledger is authored test data rather than fresh profile-separated Runtime rollout evidence |

## 5. Blocking Findings

### F-01 - Active perception expands authority budgets

Severity: closure blocker.

`RunCoordinator._fulfill_targeted_perception` builds `ProbeBudget` with `max`
between task requirements and capability cost. A task declaring zero model calls
or zero cost can therefore receive a visual or SoM probe that requires a model
call and cost. `BrowserSession.capture_targeted` independently promotes the
model-call budget to at least one for visual/SOM sources.

This violates the M8.6 exit requirement that every targeted probe is budgeted.
The Controller's own `budget.includes` check is correct, but it receives an
already-expanded budget.

Required repair:

- treat TaskSpec/SubgoalSpec and remaining RunBudget values as upper bounds;
- filter capabilities that do not fit those bounds;
- return typed `BUDGET_EXHAUSTED` or safe limitation when no probe fits;
- add Coordinator-level zero-model-call, zero-cost, and latency-limit tests;
- prohibit adapters from increasing authority budgets.

### F-02 - Screenshot transport is accepted as visual evidence

Severity: closure blocker.

`BrowserSession` emits a visual `SourceObservation` whenever a screenshot file
exists. `_snapshot_has_evidence` then treats the presence of a preferred source
as satisfying the required evidence kind. It does not require a relevant visual
assertion, grounded candidate, target relation, or accepted arbitration result.

This permits a visual-property task to skip active grounding merely because a
screenshot was captured.

Required repair:

- separate artifact/source availability from semantic evidence;
- require target- and property-relevant `GroundingCandidate` or accepted
  `StateAssertion` evidence;
- retain screenshots as transport artifacts until a grounder or verifier
  produces typed evidence;
- add negative tests for screenshot-only, unrelated-region, stale, and
  conflicting visual evidence.

### F-03 - Some recovery commands report synthetic success

Severity: closure blocker.

`COMPACT_CONTEXT`, `REPAIR_MODEL_SCHEMA`, and `SWITCH_PROVIDER` currently update
counters and transition back to observation, then synthesize a changed progress
fingerprint and successful `RecoveryCommandReceipt`. They do not prove that an
owning context, schema, or provider port performed the declared change.

`SWITCH_PROVIDER` additionally requires `configured_provider_id`, but the normal
Coordinator recovery context does not populate it. The command is therefore not
reachable through the advertised path.

Required repair:

- introduce typed owning-port handlers for each enabled command;
- emit success only from a handler result with before/after evidence;
- remove unimplemented commands from `available_commands`;
- populate provider identity only when a configured fallback really exists;
- test failed/no-op handlers and ensure they produce no `RecoveryDelta`;
- preserve inspect-before-repeat for all uncertain effects.

### F-04 - G5 validates a ledger, not broad Runtime generalization

Severity: claim blocker.

The four-profile test portfolio directly authors success, model-call, planner-
call, effect, and `pytest:*` evidence fields. This is appropriate for report
schema and tamper-resistance tests, but it is not profile-separated Runtime
execution evidence. The G5 evidence document correctly says no browser, remote
model, or benchmark episode was run; the milestone title and `complete` status
must not imply otherwise.

Required repair:

- generate fresh immutable runs for strict, strict plus accepted skills,
  compatibility, and declared ablations;
- use non-BrowserGym unseen layouts, paraphrases, distractors, ambiguity,
  cross-surface routes, provider/context faults, and recovery injection;
- bind every case to real run events, contracts, receipts, verification reports,
  environment identity, and artifact hashes;
- compute profile comparisons from those run artifacts;
- keep external suites `unprovisioned` until independently available.

### F-05 - RunCoordinator is again a responsibility concentration point

Severity: architecture containment blocker for new features.

`coordinator.py` is 3813 lines and now contains task-plan lifecycle, active-
perception execution, contract control, phase recovery dispatch, and trace
coordination. Single-writer authority is correct, but it does not require the
Coordinator to implement every phase algorithm.

No new feature behavior may be added to this module until the containment work
in the normative
[Responsibility Containment Boundary](responsibility-containment-boundary.md)
is complete.

## 6. Substantive Completed Work

The following implementation should be retained:

- explicit strict-generalist and historical-compatibility profiles;
- physical compatibility algorithm isolation and lazy loading;
- mandatory proposal provenance and one shared `PlannerProposalValidator`;
- typed intent compilation, TaskSpec, flat/shallow TaskPlan routing, and plan
  lineage;
- typed evidence gaps, probe plans/receipts, coherent targeted epochs, and
  active-perception call sites;
- phase-general `FailureEnvelope`, semantic cascade detection, typed recovery
  plans, uncertain-effect inspection, and bounded stop behavior;
- complete-run evaluation identity, ordinary-failure continuation, exact resume,
  and post-collection clustering;
- four-profile report schema, metric recomputation, tamper rejection, and
  explicit external-evidence gaps.

The closure work must correct the semantics without reintroducing task-family
planning or building a second Runtime.

## 7. Ordered Closure Plan

### R1 - Budget and evidence truth

1. fix ProbeBudget derivation and adapter authority escalation;
2. distinguish artifact availability from semantic evidence;
3. add generic non-BrowserGym integration and negative controls;
4. rerun the full local quality gate.

### R2 - Real recovery command effects

1. add a typed `RecoveryCommandDispatcher` that invokes existing owning ports;
2. enable only commands with real handlers;
3. bind receipts and deltas to handler evidence;
4. prove no-op, repeated, unsafe, and unavailable changes fail closed.

### R3 - Responsibility containment

1. extract active-perception flow from Coordinator;
2. extract recovery command dispatch and completion;
3. extract TaskPlan flow if it still adds an independent reason to change;
4. keep Coordinator as the sole state-transition committer;
5. add ownership and import-boundary tests.

### R4 - Fresh empirical evidence

1. run the four isolated profiles through real non-BrowserGym Runtime paths;
2. publish immutable case/run/artifact manifests;
3. run a new strict frozen M8.2B diagnostic only after R1-R3 pass;
4. collect the bounded matrix before cluster-level repair;
5. do not stop at the first ordinary failure or add benchmark-shaped solvers.

## 8. Reclosure Criteria

M8.6 may return to `done` only when:

- zero-budget probes are rejected without hidden escalation;
- evidence requirements are satisfied by relevant semantic evidence, not source
  or artifact presence;
- every enabled recovery command produces a real owning-port result before a
  successful receipt and delta;
- no-op recovery cannot be credited as progress;
- the Coordinator passes the containment gate and gains no new domain role;
- profile comparisons are derived from immutable Runtime runs;
- the full quality gate passes on the exact reviewed revision;
- status, plans, README, and evidence documents identify the same revision and
  do not promote historical benchmark scores.

M9 and distributed/service work remain deferred. They are not valid substitutes
for closing these Runtime semantics.

## 9. Reclosure Progress After This Audit

The findings above remain the immutable decision for audited revision `f4c3308`.
Subsequent working-tree repairs on 2026-07-24 have locally closed the code-level
parts of F-01, F-02, F-03, and the first containment ratchet of F-05:

- `ProbeBudgetPolicy` intersects declared and remaining authority; neither the
  Coordinator nor BrowserSession promotes model-call, cost, or latency limits;
- source/screenshot presence no longer satisfies semantic evidence; a relevant,
  current, linked, conflict-free candidate is required;
- `ActivePerceptionFlow` owns typed probe preparation/execution without state or
  trace authority;
- `RecoveryCommandDispatcher` exposes only configured owning-port commands and
  requires matching before/after evidence; failed, unavailable, or no-op work
  produces no `RecoveryDelta`;
- the normal provider-failure path invokes a configured switch owner;
- the Coordinator remains the only state/trace committer and its executable
  ratchet decreased from 3813/29 to 3732 lines / 26 methods.

Local verification in the fixed Python 3.12 environment is 680 tests passed,
Ruff passed, mypy passed over 100 source files, and `git diff --check` passed.
This is working-tree repair evidence, not an immutable reviewed release.

F-04 was subsequently closed by the fresh provider-free rollout at
`docs/evidence/runs/m8.6-g5-c939051`, bound to implementation revision
`c9390517624eaf28a84aee9e77d0ba83ff533106`. Its 11 real Runtime cases cover all
four isolated profiles, recompute to `passed`, retain 100% safe outcomes, and
carry an independently revalidated 82-file artifact hash index. No benchmark
score or external-suite claim is included. M8.6 may therefore return to `done`;
M8.2B is unblocked for a new strict frozen diagnostic collection under its own
identity.
