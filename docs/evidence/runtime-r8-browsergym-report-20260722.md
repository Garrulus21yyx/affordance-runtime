# R8 BrowserGym Report and Protocol Containment Evidence

Date: 2026-07-22

## Outcome

Versioned profile metadata and the breadth-first schedule now live in
`browsergym_protocol.py`. FailureEnvelope construction, clustering, and
aggregate report publication live in `browsergym_report.py`.
`browsergym_matrix.py` retains circuit state and atomic checkpoint operations
and re-exports the prior public functions.

Release tasks outside the fixed nightly manifest no longer collapse to the
uninformative `unmapped` family. The report adapter uses the last recognized
executed action as bounded capability evidence (for example,
`observed:text_entry`) and emits `unresolved:no_action_evidence` when no such
evidence exists. Declared protocol families remain authoritative. No task-name
branch or benchmark solver was added.

## Frozen evidence boundary

The completed 625-episode release report is not rewritten. These taxonomy
rules apply to newly generated reports; any new frozen comparison requires a
new clean revision and output directory.

## Verification

Using `/home/yang/.venvs/affordance-browsergym-py312/bin/python`:

```text
ruff check src tests: passed
mypy --ignore-missing-imports src: passed (89 source files)
pytest -q: 519 passed
focused report/adapter/adaptive tests: 66 passed
git diff --check: passed
```

No benchmark episode or GitHub Action was run.
