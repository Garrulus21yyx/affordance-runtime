# Run11 observability authority convergence

Status: complete

## Goal

Make local JSONL/SQLite the only synchronous authority path and isolate every Langfuse SDK call behind a bounded,
non-blocking queue consumed by a per-case daemon viewer worker.

## Frozen invariants

- Runtime event -> local JSONL -> put_nowait -> immediate return.
- Runtime, Supervisor, runner, and PydanticAI provider call stacks never invoke Langfuse/OTel SDK methods.
- Queue capacity is bounded; overflow and viewer failure are fail-open local metrics only.
- Worker is daemon, owns the client, and may be abandoned after bounded flush/join.
- ModelInvocationResult typed attempts are the sole generation projection; no Agent.instrument_all path.
- Viewer failure cannot change MissionRunResult, SQLite result, case acceptance, or JSON report truth.
- Preserve dirty worktree; no live provider, BrowserGym/WebArena witness, task-specific witness, or W2 cohort.

## Steps

1. [completed] Map current recorder/sink/client/flush/instrumentation owners, consumers, lifecycle, and tests.
2. [completed] Introduce bounded non-blocking viewer queue and daemon worker with per-case circuit breaker.
3. [completed] Remove synchronous sink calls, main-thread client flush, and PydanticAI direct instrumentation.
4. [completed] Project typed model attempts as generation observations without duplicate paths.
5. [completed] Add hang/full-queue/unreachable/flush-timeout/healthy-viewer fault tests.
6. [completed] Update architecture and benchmark contracts plus removal evidence.
7. [completed] Run focused tests, full pytest, Ruff, diff-check, and bounded fresh-context audit; no live.
