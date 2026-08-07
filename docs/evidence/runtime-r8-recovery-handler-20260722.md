# Runtime R8 RecoveryHandler Containment Evidence

Date: 2026-07-22

Status: fourth R8 internal-containment slice complete; R8 remains in progress.

## Boundary

`RecoveryHandler` now computes one typed `RecoveryEvaluation` from an immutable
`RecoveryRequest`. It owns failure-signature construction, uncertain-effect
classification, cascade assessment, bounded recovery context, and policy
selection.

The handler never mutates the supplied `RecoveryIncident` or `StateKernel`. For
an open incident it evaluates a deep copy after simulating completion of the
previous pending attempt, preserving the existing loop/no-progress semantics.
`RunCoordinator` remains responsible for the only authoritative application:

- transition into and out of recovery;
- create or continue the single incident;
- complete pending attempts and append symptoms/findings/context;
- record grounding reroute or reobservation lineage;
- append the selected attempt and terminal outcome;
- update diagnostics and the recovery budget.

No recovery policy, threshold, Prompt, action mapping, budget, trace event, or
benchmark adapter changed. The production module contains no BrowserGym or
MiniWoB vocabulary.

## Verification

Using `/home/yang/.venvs/affordance-browsergym-py312/bin/python`:

- focused handler/policy/Coordinator/uncertain-effect/fallback/TaskSkill and
  boundary tests: 44 passed;
- full repository tests: 482 passed;
- Ruff over `src` and `tests`: passed;
- mypy with `--ignore-missing-imports` over 81 source files: passed;
- `git diff --check`: passed.

Direct generic tests prove stale-state reobservation, uncertain-effect
inspect-before-retry, and repeated-signature abort. The key negative control
asserts that evaluation leaves the authoritative incident's pending outcome,
state-after value, symptom chain, and findings unchanged. Existing integration
tests retain one-shot effect inspection, no blind duplicate, safe reroute,
loop abort, recovery trace order, and verified-progress preservation.

## Remaining R8 work

- split generalist planner context/LM orchestration from the typed compiler
  registry;
- split BrowserGym observer, encoder, episode runner, and report adapter;
- migrate selected bindings toward tagged payloads with compatibility tests;
- complete the module-ownership/trace-schema audit after all extractions.
