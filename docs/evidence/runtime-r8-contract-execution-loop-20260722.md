# Runtime R8 ContractExecutionLoop Containment Evidence

Date: 2026-07-22

Status: third R8 internal-containment slice complete; R8 remains in progress.

## Boundary

`ContractExecutionLoop` now contains the backend-neutral contract stages that
do not own Runtime state:

- bind run/snapshot/page identity and artifact-scoped download destinations;
- derive the run-scoped capability gate from explicit envelope authority;
- evaluate task policy, capability, and current-observation preflight;
- revalidate a contract after fresh observation or approval;
- delegate one contract to the configured executor;
- produce the configured structural verification report.

The serial Coordinator still sets `current_contract`, changes phases, records
observations and receipts, increments budgets, consumes single-use approval
tokens, writes artifacts and trace nodes, performs current-epoch rebound, and
decides completion or recovery. The collaborator has no `StateKernel` input and
cannot install state, append trace events, retry an effect, or choose a recovery
action. Executor invocation remains exactly once per explicit Coordinator call.

No Prompt, schema, action mapping, verifier rule, budget, task-family branch, or
benchmark adapter changed. The production module contains no BrowserGym or
MiniWoB vocabulary.

## Verification

Using `/home/yang/.venvs/affordance-browsergym-py312/bin/python`:

- focused contract/Coordinator/safety/uncertain-effect/fallback/boundary tests:
  33 passed;
- full repository tests: 479 passed;
- Ruff over `src` and `tests`: passed;
- mypy with `--ignore-missing-imports` over 80 source files: passed;
- `git diff --check`: passed.

Direct generic tests prove successful bind/check/execute/verify staging, an
artifact-scoped download destination, explicit disabled-verifier reporting, and
fail-closed policy, missing-capability, and stale-page paths before execution.
Existing Coordinator tests retain approval single-use, environment drift,
uncertain-effect inspection, no blind duplicate, fallback, trace ordering, and
verifier-backed completion evidence.

## Remaining R8 work

- extract `RecoveryHandler` while preserving Coordinator-owned transitions and
  one authoritative incident record;
- split generalist planner context/LM orchestration from the typed compiler
  registry;
- split BrowserGym observer, encoder, episode runner, and report adapter;
- migrate selected bindings toward tagged payloads with compatibility tests.
