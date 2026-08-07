# R8 BrowserGym Episode Runner Containment Evidence

Date: 2026-07-22

## Outcome

The BrowserGym bridge no longer owns single-episode execution. Adapter-owned
`browsergym_episode_runner.py` now contains planner adapters, backend execution,
Coordinator setup/traversal, external JSON-line policy lifecycle, local source
serving, and killable child-process isolation. The public bridge preserves its
previous imports.

The batch layer remains separate: breadth-first scheduling, frozen identity,
resume/checkpoint rules, circuit breaking, FailureEnvelope aggregation, and
report publication remain in `browsergym.py` pending the reporting split.

## Preserved boundaries

- `RunCoordinator` and `StateKernel` remain the only Runtime authority.
- Prompt version, candidate schema, context policy, call/step budgets, typed
  results, and trace projection are unchanged.
- Process timeout terminates the child and closes its result queue.
- A child that exits without a result produces `worker_exit:<code>` rather than
  a false success.
- No task/family dispatch, benchmark-specific Core branch, service, or durable
  queue was added.

## Verification

Using `/home/yang/.venvs/affordance-browsergym-py312/bin/python`:

```text
ruff check src tests: passed
mypy --ignore-missing-imports src: passed (87 source files)
pytest -q: 515 passed
focused runner/adapter/adaptive/visual tests: 69 passed
git diff --check: passed
```

No benchmark episode or GitHub Action was run for this structural slice.
