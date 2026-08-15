# Target Runtime topology cutover and legacy deletion plan

Date: 2026-08-15

Status: `DESIGNED / T0_COMPLETE / T1_READY / WAVE_A_ADMITTED /
BLOCKS_WORLD_GRAPH_A.1_AND_NEW_CAPABILITIES`

## Goal

Make the physical repository structure express the already-selected target
authority chain. A maintainer should be able to enter through one product
composition root, read one `AgentLoop`, follow one current world/action/effect
chain, and distinguish production adapters from benchmark harnesses without
knowing the repository's migration history.

This is a cutover and deletion plan, not a compatibility program. Every slice
migrates all active consumers and their tests, then deletes the displaced code,
tests, exports and fixtures in the same coherent change.

## Why this is required

The target logical chain exists, but the filesystem still exposes several
generations as peers:

```text
legacy product path
cli.py -> composition.py -> RunCoordinator
       -> RuntimeLoopPhase -> ContractExecutionLoop -> legacy phase modules

target product path
target composition/client -> TargetRuntime
                          -> AgentEpisodeRunner -> AgentLoop
```

The root public package exports both generations, and the installed console
script still enters the mixed legacy CLI. Production BrowserGym surface code is
also located below benchmark packages. These shapes make old APIs and test
fixtures de facto owners even after semantic authority has moved.

Current-worktree inventory is diagnostic rather than deletion authority:

| Inventory | Count | Meaning |
|---|---:|---|
| production Python files | 505 | total `src/affordance_runtime/**/*.py` |
| package-root Python files | 150 | excessive unowned/legacy physical surface |
| benchmark package Python files | 153 | includes harnesses plus some reusable surface implementation |
| test Python files | 342 | entire current test source set |
| tests directly under `tests/` | 337 | tests do not mirror production ownership |
| architecture test files | 5 | current explicit import/redline boundary |
| tests importing selected legacy runtime/planning/recovery families | 49 | candidate migration/deletion consumers |
| tests importing target agent/world/model/surface families | 151 | target-owned candidates |

The import counts come from a bounded static prefix scan. They establish the
size and separation problem; the required consumer inventory in Phase T0 owns
each final keep/rewrite/delete decision.

## Target public runtime

Only three lifecycle concepts remain on the product path:

```text
TargetRuntime
  product façade: intake, composition, start/run and continuation admission
        |
        v
AgentLoop
  sole observe -> context -> decide -> admit -> bind -> execute
       -> reobserve -> evaluate -> transition loop
        |
        v
AgentRunSession
  sole pause/resume/confirmation/user-input session handle
```

`TargetRuntimeClient` and `AgentEpisodeRunner` are presumed redundant
pass-through layers. Phase T0 must confirm their consumers and any unique
contract. If none exists, their methods move to `TargetRuntime` or
`AgentRunSession` and both classes are deleted. They may be retained only if
the inventory identifies a distinct lifecycle authority that cannot be owned by
those three concepts; convenience wrapping is not sufficient.

There is one product composition function and one installed product command.
Benchmark commands use a separate benchmark entrypoint and consume the public
target runtime instead of enlarging the product CLI.

## Target package topology

The exact `git mv` sequence follows deletion, but the remaining code has these
homes:

```text
src/affordance_runtime/
├── app/
│   ├── runtime.py             # TargetRuntime public façade
│   ├── composition.py         # sole product composition root
│   ├── cli.py                 # target product command only
│   └── result.py
├── agent/
│   ├── loop.py                # sole AgentLoop
│   ├── session.py
│   ├── state.py
│   ├── control_transition.py
│   ├── decisions.py
│   ├── policy.py              # cognitive ports
│   ├── context/               # AgentContext and ActorWorldSnapshot projections
│   └── control/               # bounded observe/select/execute/evaluate helpers
├── world/
│   ├── observation contracts, acquisition, fusion, identity, relations, delta
├── actions/
│   ├── capabilities, ActionSpace, admission, binding, verification contracts
├── model/
│   ├── tools/                 # compiler, normalizer, exact resolver
│   └── providers/             # provider transport/serialization
├── execution/
├── evaluation/
├── task/
├── risk/
├── confirmation/
├── surfaces/
│   ├── dom/
│   ├── browsergym/
│   ├── visual/
│   ├── wot/
│   └── http_json/
└── benchmarks/
    ├── target/
    ├── browsergym/
    └── reporting/
```

Names may be adjusted where an existing package already has the correct owner.
The plan does not authorize a wholesale rename. The required result is no
ambiguous root-level owner and no production adapter hidden inside a benchmark
runner. `world/`, `agent/`, `evaluation/`, `execution/`, `task/`, `risk/`,
`confirmation/` and `surfaces/` are reused where already coherent.

## Import direction

Architecture tests enforce this direction:

```text
app -> agent -> world/actions/execution/evaluation/task
app composition -> model providers + surfaces
agent/context -> public world/actions/evaluation/task contracts
surfaces -> public world/actions/execution contracts
model/tools -> agent public context/policy ports + public action projections
model/providers -> provider transport contracts only
benchmarks -> app public API + admitted surface APIs
```

`AgentContext`, `ActorWorldSnapshot`, decision requests and cognitive policy
ports belong to `agent/`; they define what the loop asks for. `model/` is an
outbound adapter that compiles and transports those public requests. The loop
therefore never imports a provider, tool compiler or provider serialization
type, and the model layer never owns Runtime state.

Forbidden dependencies:

- world, actions, agent, execution or evaluation importing `benchmarks`;
- core code importing `testing` or benchmark fixtures;
- surfaces importing AgentLoop or product composition;
- provider binders importing private surface routes;
- benchmarks constructing a second loop or bypassing target admission;
- new package-root `*_phase.py`, `*_flow.py`, `*_coordinator.py` or parallel
  runtime modules;
- re-export shims that keep a deleted legacy module importable.

## Migration phases

### T0 — authoritative consumer and test inventory

Status: `COMPLETE`

The authoritative inventory and disposition evidence is
[Target Runtime topology T0 consumer and test inventory](../evidence/2026-08-15-target-runtime-topology-t0-inventory.md).

Create one reviewable inventory containing every candidate legacy production
module, public export, CLI command, script, benchmark consumer, test file and
fixture. Each row has:

```text
owner cluster
current path
active product consumers
active benchmark consumers
test consumers
target replacement
disposition: KEEP_MOVE | REWRITE | DELETE_WITH_OWNER
replacement invariant/test
deletion commit
```

`git grep`/AST import reachability, public exports, script entrypoints and
runtime registrations are all checked. Filename age, low line count and low
coverage alone never authorize deletion.

Exit:

- every candidate file and test has one disposition;
- active versus historical benchmarks are explicitly named;
- no “temporarily keep everything” bucket exists;
- the inventory and architecture tests agree on the target public spine.

### T1 — public façade and command cutover

Status: `PENDING_T0`

- make `TargetRuntime` the sole public runtime façade;
- make `AgentLoop` the sole product loop and `AgentRunSession` the sole
  continuation handle;
- collapse and delete `TargetRuntimeClient` and `AgentEpisodeRunner` unless T0
  proves a unique owner;
- make the installed `affordance-runtime` command enter the target product CLI;
- move benchmark commands to a separate entrypoint or explicit scripts;
- remove legacy `RunRequest`, `RunResult`, `RuntimeClient`,
  `LegacyRuntimeClient`, `UnifiedObservation` and related exports from the root
  public API after their active consumers migrate;
- update README/current docs in the same slice.

No import-compatible alias or fallback command remains after cutover.

Exit:

- one installed product entrypoint;
- one public composition root;
- one public runtime façade;
- one `AgentLoop` implementation;
- product tests exercise no legacy public API.

### T2 — active benchmark and surface migration

Status: `PENDING_T1`

- move reusable BrowserGym environment, observation, binding, currentness,
  execution and verifier adapters out of `benchmarks/external_smoke` into
  `surfaces/browsergym` or the relevant product owner;
- keep case manifests, campaign runners, reporting and benchmark evaluation in
  `benchmarks`;
- migrate every active benchmark to compose the public target runtime and
  inject only environment/model/evaluator ports;
- delete compatibility runners and case projections when no active profile
  consumes them;
- retain historical result/evidence documents without retaining the obsolete
  runtime that produced them.

Exit:

- no production surface implementation is owned by a benchmark namespace;
- active benchmarks do not import legacy coordinator/runtime modules;
- benchmark code cannot construct an alternate admission/execution/evaluation
  chain.

### T3 — delete legacy orchestration clusters

Status: `PENDING_T1_T2`

Delete owner-by-owner, with all imports/tests/fixtures removed or migrated in
the same commit. Candidate clusters include:

- top-level `runtime.py`, `runtime_client.py`, `coordinator.py`,
  `composition.py`, `contract_execution_loop.py`, `runtime_*_phase.py` and
  their phase helpers;
- superseded planning, recovery, progress, action-choice and perception paths
  that are not part of the declared target product or a retained higher-level
  planning port;
- root `adapters/` implementations displaced by `surfaces/`;
- compatibility semantic compilers and compatibility-only projections;
- tests whose sole purpose is preserving a deleted legacy API or dual path.

This list is an inventory seed, not blanket deletion authorization. T0 must
show the exact consumers and target replacement for every file.

Exit for each cluster:

- zero production imports and zero active benchmark imports;
- no root public export or CLI reference;
- target-owned contract/invariant tests exist where the behavior remains
  supported;
- compatibility/shadow tests are deleted with their path;
- architecture redlines prevent reintroduction;
- no shim, fallback-old, dual-write or archived executable source remains.

### T4 — move the remaining live code into owner packages

Status: `PENDING_T3`

Only live files move. Each `git mv` slice updates every production import, test,
fixture, package export and documentation reference atomically. Avoid a
repository-wide move commit that obscures semantic review.

Recommended slices:

1. product façade/composition/CLI;
2. loop/session/transition spine;
3. action capability/ActionSpace/admission/binding owners;
4. model context/tool/provider boundaries;
5. BrowserGym surface ownership;
6. residual shared utilities with a demonstrated owner.

Exit:

- package-root modules are limited to the stable public façade and genuinely
  cross-cutting primitives;
- a new maintainer can follow `app/runtime.py -> agent/loop.py` without entering
  legacy or benchmark code;
- import-boundary tests reflect the physical directory layout.

### T5 — topology closure

Status: `PENDING_T4`

Run the complete verification below, perform a fresh-context reader/architecture
review and update implementation status. World-graph A.1 may begin when the
minimum topology gate is satisfied; full historical benchmark-report cleanup
may continue separately only if it is isolated and imports no legacy product
runtime.

## Test migration plan

Tests migrate with their production owner. The existing large flat suite is not
kept as a compatibility blanket and is not reorganized in one mechanical move.

### Target test topology

```text
tests/
├── architecture/             # import direction, banned paths, sole-owner redlines
├── unit/
│   ├── agent/
│   ├── world/
│   ├── actions/
│   ├── model/
│   ├── evaluation/
│   ├── execution/
│   └── task/
├── integration/
│   ├── runtime/
│   ├── surfaces/
│   └── providers/
├── conformance/              # cross-adapter contract/property suites
├── benchmarks/               # runner/reporting/manifest tests only
└── support/                  # non-test builders/fakes shared by named owners
```

### Per-test disposition

Every test is classified with its production owner:

| Disposition | Use |
|---|---|
| `KEEP_MOVE` | already verifies the target owner/invariant; move with imports updated |
| `REWRITE` | valid invariant expressed through a legacy API; rewrite against the target public contract, then delete the old test |
| `DELETE_WITH_OWNER` | verifies only deleted compatibility behavior, old orchestration order or removed API shape |

Tests are not retained merely to keep the historical pass count high. A lower
test count is acceptable when the inventory records which tests were deleted,
which target invariant replaces them, and why no supported behavior was lost.
Conversely, moving a legacy test unchanged does not prove migration if it keeps
the old owner importable.

### Test rules

1. Production code and its tests move or delete in the same coherent slice.
2. Contract, property and state-machine coverage survives; obsolete call-order
   and compatibility-shape assertions do not.
3. One invariant has one primary owner suite. Adapter conformance may reuse that
   suite with different fixtures rather than copying assertions per adapter.
4. Benchmark case tests verify runner/reporting contracts and never authorize a
   product branch or old Runtime path.
5. Fakes/builders move to `tests/support/<owner>` and may not expose a deleted
   legacy API.
6. Temporary shadow/equivalence tests are deleted in the same commit that
   removes the shadow path.
7. Test collection must not import deleted modules incidentally through root
   package re-exports.
8. Each slice reports tests moved, rewritten, deleted and added; raw total count
   is evidence, not an acceptance threshold.

### Required architecture tests

- root public API exports only target contracts;
- installed product CLI resolves only to the target application entrypoint;
- exactly one production `AgentLoop` and one product composition root exist;
- banned legacy runtime/coordinator/phase modules are physically absent;
- core packages do not import benchmarks/testing/provider implementations;
- active benchmarks import the public target runtime, not internal loop or
  legacy composition;
- BrowserGym reusable implementation lives under `surfaces/browsergym`;
- no compatibility module, re-export shim or fallback-old branch is reachable;
- test modules mirror declared owner packages and no test imports a deleted
  owner.

## Minimum gate before world-graph A.1

World-graph A.1 and new interaction capabilities remain blocked until:

1. Wave A closure implementation is committed and proportionally verified;
2. target product CLI/public API/composition are the default path;
3. old product coordinator/runtime/contract-execution loop is unreachable and
   deleted;
4. the sole `AgentLoop`/session/transition spine is physically obvious;
5. reusable BrowserGym source code needed by A.1 has a product surface owner;
6. tests for the touched owners have migrated and architecture redlines prevent
   restoration of the old path.

Moving every historical benchmark report test is not a prerequisite if the
remaining benchmark-only tail is isolated, has an explicit disposition and
cannot import or expose the deleted product runtime.

## Verification

Each deletion/move slice runs:

1. changed-owner unit and property tests;
2. target Runtime integration and continuation tests;
3. adapter conformance where a surface moves;
4. architecture/import redlines;
5. active benchmark runner/reporting tests affected by the slice;
6. full pytest;
7. Ruff, mypy and `git diff --check`;
8. package build/import and installed console-script checks.

A deterministic local target CLI/end-to-end witness is required for the root
entrypoint switch. Pure moves/deletions do not require an external provider or
live benchmark run; any later benchmark/generalization claim still requires its
separately declared clean-SHA evidence.

## Falsifiable exit criteria

Topology cutover is complete only when:

- the installed product command and root public API expose the target path only;
- exactly one Runtime façade, AgentLoop and session continuation path exist;
- old coordinator/phase/contract-execution modules and their tests are deleted;
- every retained file has one package owner and allowed import direction;
- active benchmarks consume the target public API and reusable adapters live
  outside benchmark namespaces;
- the consumer/test inventory has no unresolved rows;
- no legacy/compatibility import, shim, fallback or dual path is reachable;
- source, tests, documentation, package exports and implementation status agree;
- focused, architecture, full, static and package checks pass from the same
  reviewed worktree.

## Non-goals

- no redesign of world/action/effect authority during topology-only commits;
- no new plugin framework, dependency injection container or generic phase
  engine;
- no event store, graph database or test-management platform;
- no preservation of old APIs solely for hypothetical external consumers;
- no mass rename whose only benefit is aesthetic consistency;
- no deletion of historical evidence documents;
- no benchmark-specific production branches to preserve an old score.
