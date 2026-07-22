# Runtime R5 Planner and Observation De-Specialization Evidence

Date: 2026-07-22

Status: Runtime-first R5 exit complete. BrowserGym runs in this record were
executed from a dirty working tree and have `official_score_claimed=false`.
They are Runtime-path confirmation, not a formal benchmark promotion result.

## Invariant and ownership boundary

The generic Runtime may consume authored interaction metadata only through an
explicit adapter profile. It must not know a benchmark marker, task family,
backend action string, authored answer, selector, coordinate, or reward field.

| Responsibility | Owner after R5 |
| --- | --- |
| Native DOM/ARIA/tabindex/draggable observation | shared DOM adapter |
| Explicit authored-interactive extension schema | shared DOM/SVG adapter API |
| BrowserGym marker, visibility attribute, and `bid` mapping | BrowserGym observation adapter |
| Opaque candidate handle and coherent epoch | shared observation/grounding |
| Semantic rule applicability, required state, evidence, validation, negative examples | `SemanticCompilerRegistry` |
| BrowserGym `bid` and action-schema encoding | BrowserGym contract/execution adapter |
| Terminal reward interpretation | BrowserGym adapter-declared terminal outcome |
| Current-state delta and postcondition verification | shared verifier |

Shared DOM, SVG, session, and grounding code now expose `backend_handle` rather
than a BrowserGym identity. BrowserGym creates the concrete DOM/SVG profiles
and translates normalized bindings to its own action schema. Shared source does
not import or spell benchmark marker attributes, reward fields, or action
syntax.

## Typed semantic compilation

`SemanticCompilerRegistry` makes deterministic semantic help explicit and
auditable. Every compiler or constraint rule declares applicability, required
state, evidence source/version, output validation, and negative examples. A
disabled registry is neutral: model-produced semantic actions such as `DRAG`
remain valid, but no implicit benchmark-shaped compiler or schema constraint is
applied.

The new incremental-control rule is deliberately environment-independent. For
one numeric slider with a known current value and explicit target, it emits one
semantic ArrowLeft/ArrowRight step. Execution then obtains a fresh observation
and independently verifies the postcondition before another step may be
compiled. It does not know a task name, fixture, selector, coordinate, or
BrowserGym action string.

## Conformance and negative controls

Tests prove all of the following without relying on a benchmark task family:

- a neutral `data-runtime-*` authored profile observes custom interactive
  controls and opaque backend handles;
- without that profile, an unknown custom marker is ignored;
- native controls and generic draggable semantics remain available when the
  BrowserGym profile is disabled;
- the BrowserGym adapter recognizes its DOM and SVG authored profiles and
  performs backend-specific encoding;
- generic attribute verification requires an explicitly declared identity
  attribute;
- `official_reward` alone cannot satisfy shared verification;
- adapter-declared terminal success/failure and nonterminal state deltas have
  distinct semantics;
- disabled semantic compilation does not remove model-proposed semantic drag;
- a source-boundary test scans shared Runtime modules and rejects BrowserGym,
  MiniWoB, marker, reward, `bid`, and benchmark action vocabulary outside the
  benchmark adapter and CLI.

The direct boundary scan also returned no matches:

~~~text
rg -n -i "browsergym|miniwob|official_reward|browsergym_set_of_marks|browsergym_visibility_ratio|\bbid\b|click_no_navigation|drag_and_drop" \
  src/affordance_runtime -g '!**/benchmarks/**' -g '!cli.py'
~~~

## Diagnostic sequence and honest failures

All live runs used:

~~~text
/home/yang/.venvs/affordance-browsergym-py312/bin/python
Python 3.12.3
browsergym-miniwob 0.14.3
Playwright 1.44.0
Ollama qwen2.5:7b (local endpoint)
~~~

The first six-episode smoke in
`artifacts/runtime-r5-despecialization-smoke-20260722` passed 5/6. The
`form-sequence:seed-0` failure exposed shared verifier semantics: a
nonterminal `terminal_success=false` field incorrectly suppressed a valid
checkbox state delta. The repair separated terminal adapter evidence from
ordinary nonterminal state verification. The isolated reproduction then
passed 1/1 with ten verified actions.

The first ten-seed affected-family sweep in
`artifacts/runtime-r5-form-sequence-family-20260722` passed 8/10. Seeds 4 and
7 exhausted the 15-call model budget while stepping large numeric slider
distances. There were no provider failures or retries. The repair was the
generic typed incremental-control compiler described above, not a task or
benchmark exception.

After that repair,
`artifacts/runtime-r5-form-sequence-family-v2-20260722` passed 10/10 with mean
official reward 1.0, 108 independently verified actions, and 20 model calls
(two per episode), down from 102 calls in the prior incomplete family run.
Provider failures, 429 retries, transient retries, runtime failures, and
failure clusters were all zero.

The seed-major PR profile in `artifacts/runtime-r5-pr-20260722` then passed
18/18 with mean official reward 1.0 across click, fill, press, and
select-option action families. It recorded 45 DOM routes, 24 model calls, and
zero provider, retry, runtime, acceptance, or failure-cluster errors.

## Static and test gates

Executed in the fixed Python 3.12 environment:

~~~text
python -m pytest -q
452 passed

python -m ruff check src tests
All checks passed!

python -m mypy --ignore-missing-imports src
Success: no issues found in 76 source files

git diff --check
passed
~~~

R5 therefore closes the shared ownership and generality gate. R6 canonical
trace mining and accepted-profile loading remain next. A clean immutable SHA
must be used before any live result is promoted as a formal benchmark score.
