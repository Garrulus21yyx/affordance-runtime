# Responsibility Containment Boundary

Status: **normative**. This document prevents responsibility inflation in the
current modular monolith. It governs production code, architecture reviews,
milestone claims, and benchmark-driven repair. When convenience conflicts with
this boundary, containment wins.

It is jointly normative with the
[Runtime-First Architecture Boundary](runtime-first-boundary.md) and the
[Benchmark Governance and Anti-Specialization Boundary](benchmark-governance-boundary.md).

## 1. Core Decision

The Runtime uses one authoritative `RunCoordinator`, but the Coordinator is a
single **state-transition committer**, not a universal implementation module.

~~~text
typed request/result collaborators
              |
              v
RunCoordinator
  validate current state/version
  invoke one owning port
  commit the returned typed result
  append the authoritative trace event
  choose the next phase
~~~

Single-writer means only the Coordinator commits authoritative `RunState`. It
does not authorize the Coordinator to implement planning algorithms, source
parsers, probe selection policy, provider repair, executor behavior, verifier
logic, benchmark scheduling, report generation, or learning algorithms.

No module may gain a new responsibility merely because it already has access to
the required data.

## 2. Dependency Direction

The allowed control direction is:

~~~text
entrypoints and adapters
  -> task-level Runtime API
  -> RunCoordinator
  -> typed domain collaborators and ports
  -> environment/provider implementations

domain contracts <- all layers
benchmark adapters -/-> core policy or planning ownership
collaborators -/-> authoritative RunState mutation
~~~

Collaborators receive immutable context views and return immutable decisions,
receipts, deltas, or reports. The Coordinator validates version and provenance,
then applies the state transition.

Circular ownership, shared mutable blackboards, hidden state writers, and
adapter-to-core callbacks that bypass contracts are prohibited.

## 3. Ownership Matrix

| Area | Owns | Must not own |
| --- | --- | --- |
| `RunCoordinator` | phase sequencing, state-version checks, authoritative commit, budget accounting, trace ordering | parser algorithms, Prompt/model policy, provider repair, probe ranking, backend encoding, verifier implementation, report aggregation |
| Intent compiler | raw request to sourced intent draft | capability grant, GUI target choice, execution |
| Task-plan flow | flat/skill/shallow-plan selection, plan lineage, subgoal activation | grounding, backend choice, state mutation |
| Step planner | semantic proposal from bounded context | selectors, coordinates, capabilities, execution, success authority |
| Proposal validator | provenance, scope, action/target and current-context validity | repairing proposals or inventing replacement actions |
| Perception session | coherent source capture and normalization | deciding task completion or granting extra budget |
| Active-perception controller | evidence-gap extraction and cheapest permitted read-only probe decision | increasing authority budgets, executing effects, mutating old snapshots |
| Active-perception flow | invoke targeted capture and return typed resolution | planner behavior, state mutation, hidden source-specific retry |
| Contract builder | bind one current candidate into one immutable contract | free-form task reasoning or capability grant |
| Contract execution loop | preflight, route invocation, post-observation handoff | task replanning or benchmark reward handling |
| Verifier | criteria-bound evidence report | treating executor acknowledgement or reward as sole task truth |
| Recovery coordinator | select one validated changed strategy | perform provider/context/schema work or mutate Runtime state |
| Recovery command dispatcher | invoke the existing owning port and return evidence-backed receipt/delta | select arbitrary strategy, mark no-op work successful, bypass policy |
| Trace/artifact store | append and persist canonical evidence | decide task success or evolution acceptance |
| Evaluation runner | schedule, account, resume, cluster after collection | repair tasks during collection or modify planner behavior |
| Evolution | trace-derived proposal, quarantine, replay, accept/reject/rollback | immediate online code mutation |
| BrowserGym/public-suite adapter | normalize observation, encode validated action, collect external result | planner, recovery, verifier, skill, or Runtime policy ownership |

## 4. Hard Prohibitions

The following changes are rejected:

1. adding an independent reason to change to `RunCoordinator`;
2. implementing an owning-port effect inline in recovery dispatch;
3. increasing task capability, cost, model-call, latency, or observation budget
   inside an adapter or helper;
4. treating source, screenshot, DOM, receipt, or reward presence as semantic
   evidence without target- and criterion-bound interpretation;
5. generating a successful receipt or delta from an intended change rather
   than an observed owning-port result;
6. placing benchmark family behavior in a generalist or shared module;
7. duplicating state, plan, recovery, or trace authority in a second manager;
8. adding a new framework, service, queue, event bus, registry, or abstraction
   when an existing typed port can own the behavior;
9. splitting files without establishing a real ownership boundary;
10. using line-count reduction to hide circular dependencies or pass mutable
    state through an untyped dictionary.

## 5. Mechanical Containment Gates

Line count is not the architecture, but it is an escalation signal.

- A Runtime control module above 1,500 lines requires an accepted containment
  plan before new feature logic is added.
- A Runtime control module above 2,000 lines is feature-frozen. Only correctness,
  security, evidence, or net-reduction changes are permitted.
- A method above 250 lines requires extraction or an explicit review explaining
  why one cohesive transaction cannot be separated.
- A pull request that adds a new reason to change to a feature-frozen module
  fails review even when its net line count decreases.
- An extraction is accepted only when the new collaborator has a typed input,
  typed output, no authoritative state mutation, and focused tests.

`coordinator.py` is currently feature-frozen. Its remediation target is below
2,000 lines first and below 1,500 lines after the current active-perception,
recovery-dispatch, and TaskPlan ownership extraction. The ratchet in
`tests/test_responsibility_containment.py` prevents growth beyond the audited
3813-line and 29-method surface; both ceilings must only decrease. These numbers
are gates, not a reason to create one-file-per-class packages.

`compatibility_planner_algorithms.py` is historical compatibility containment,
not an acceptable model for current Runtime control modules. It may not receive
new strict-generalist behavior.

## 6. Required Extraction Pattern

Use this pattern:

~~~text
Coordinator builds immutable ContextView
  -> collaborator decides or invokes its owning port
  -> collaborator returns TypedResult
  -> Coordinator validates state/version/provenance
  -> Coordinator commits state and canonical trace
~~~

Do not use this pattern:

~~~text
Coordinator calls helper
  -> helper mutates RunState
  -> helper writes trace
  -> helper executes a fallback
  -> Coordinator infers what happened
~~~

The first required extractions are:

1. `ActivePerceptionFlow`: requirements/gaps plus remaining authority budget to
   probe decision, targeted capture, and typed resolution;
2. `RecoveryCommandDispatcher`: validated command to real owning-port result,
   receipt, and delta;
3. `TaskPlanFlow`: planning context, plan/replan invocation, lineage, and typed
   acceptance result when this remains an independent change axis;
4. `ProbeBudgetPolicy`: strict intersection of task, run, and capability limits,
   never capability-driven budget expansion.

The Coordinator remains the sole state writer after all extraction.

## 7. Change Admission Contract

Every production change must state in its pull request or evidence record:

1. the single responsibility being changed;
2. the current owning module or port;
3. why no other module must change for the same reason;
4. the typed input and output boundary;
5. the authority and budget source;
6. the state writer and trace writer;
7. the generic positive, negative, stale, no-op, and failure tests;
8. the non-BrowserGym evidence when benchmark work discovered the need;
9. whether any module crosses a mechanical containment gate;
10. which old responsibility or duplicated path is removed.

Missing answers block merge. A vague answer such as "Coordinator owns the run"
does not justify adding phase-specific algorithms to Coordinator.

## 8. Completion and Evidence Semantics

The following three levels must remain separate:

| Level | Meaning | Valid claim |
| --- | --- | --- |
| protocol | schema, validator, and unit behavior exist | component implemented |
| integration | normal entrypoint invokes the owning port and returns a real typed result | Runtime path integrated |
| empirical evidence | immutable runs and artifacts demonstrate the behavior under declared controls | gate or capability proven |

Protocol tests cannot close an empirical gate. A synthetic ledger may test
report calculation but cannot establish task success, generalization, recovery,
or efficiency. A transport artifact may prove capture but cannot establish
semantic evidence. A planned change may not produce a successful recovery
receipt until the owning port proves it occurred.

## 9. Scope Control

Containment must not turn into infrastructure expansion. The current target
remains an asynchronous modular monolith with one run, one Coordinator, one
effectful action lane, typed ports, filesystem/JSONL evidence, and bounded
offline evolution.

The following remain deferred unless a measured failure promotes them:

- worker pools and distributed queues;
- separate agent containers or microservices;
- distributed event buses;
- multiple authoritative coordinators;
- multi-tenant control planes;
- unrestricted cross-run memory;
- generic workflow frameworks inside the low-level GUI execution loop.

## 10. Review Outcome

A change passes responsibility governance only when:

- it improves one declared Runtime responsibility;
- it does not create a second owner;
- it does not add a new reason to change to a feature-frozen module;
- authority and budgets can only stay equal or become narrower downstream;
- success is backed by the owning port and criteria-bound evidence;
- the same behavior is testable without a benchmark adapter;
- the repository remains simpler to explain after the change.

If these conditions cannot be met, the change must be redesigned, deferred, or
rejected.
