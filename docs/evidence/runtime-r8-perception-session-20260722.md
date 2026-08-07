# Runtime R8 PerceptionSession Containment Evidence

Date: 2026-07-22

Status: second R8 internal-containment slice complete; R8 remains in progress.

## Boundary

`PerceptionSession` now owns observation-port interaction and coherent capture
profile construction:

- derive task/subgoal-specific `PerceptionRequirements` and bounded task terms;
- widen requirements from prior failed grounding sources;
- capture ordinary generic sources without changing their port contract;
- configure BrowserSession screenshot paths and artifact registration;
- resolve synchronous or asynchronous targeted-observation ports and require a
  complete `BrowserSnapshot` result.

The collaborator is stateless with respect to the run. It does not call
`remember_observation`, increment observation or active-perception counters,
enforce run budgets, alter the active task plan, append trace nodes, or select a
route. Those operations remain serial in `RunCoordinator` and `StateKernel`.
Artifact file creation is scoped to the existing `ArtifactStore` and does not
create another run-state writer.

No Prompt, schema, action, verifier, provider, budget, task-family rule, or
benchmark adapter changed. The module contains no BrowserGym/MiniWoB protocol
vocabulary and its direct tests use only generic observation fixtures.

## Verification

Using `/home/yang/.venvs/affordance-browsergym-py312/bin/python`:

- focused PerceptionSession, BrowserSession, generic Coordinator, Coordinator,
  and boundary tests: 47 passed;
- full repository tests: 476 passed;
- Ruff over `src` and `tests`: passed;
- mypy with `--ignore-missing-imports` over 79 source files: passed;
- shared-runtime benchmark-vocabulary boundary: passed;
- `git diff --check`: passed.

Direct negative controls prove that a plain observation source leaves
authoritative state untouched, a missing targeted port fails closed, and an
unknown failed-source label cannot widen perception. Existing generic
integration tests continue to prove task-derived visual-primary observation,
DOM-to-visual escalation, one coherent epoch across sources, bounded repeated
targeted perception, preserved trace event names/order, and no action during an
unresolved material source conflict.

## Remaining R8 work

- extract `ContractExecutionLoop` and `RecoveryHandler` without transferring
  state or trace authority;
- split generalist planner context/LM orchestration from the typed compiler
  registry;
- split BrowserGym observer, encoder, episode runner, and report adapter;
- migrate selected bindings toward tagged payloads with compatibility tests.
