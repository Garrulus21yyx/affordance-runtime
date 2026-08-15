# Benchmark

## Purpose

Benchmarks are the final evidence for task capability, generalization, robustness, and adaptive-observation value.
Unit, property, and architecture tests protect contracts; they do not substitute for live GUI execution.

## Primary questions

1. Does the agent complete supported GUI tasks?
2. Does adaptive observation preserve or improve success relative to structured-only observation?
3. Does it reduce visual calls, model tokens, latency, or unnecessary acquisition?
4. Can it recover when structured evidence is insufficient or an action has an unknown effect?

## Required report

Every live run records, per case:

- task and seed from a predeclared manifest;
- terminal status and official environment success;
- action, observation, and model-call counts;
- source selections by modality;
- visual supplementation and recovery counts;
- tokens and elapsed time;
- typed environment, provider, Runtime, and task failures.

Reports must not contain prompts, model responses, selectors, coordinates, credentials, hidden state, oracle values,
expected answers, or benchmark reward payloads exposed to the model.

## Current evidence

The retained R2-era MiniWoB-60 runs are negative baselines, not performance claims:

| Frozen run | Task success |
|---|---:|
| historical breadth | 6 / 60 |
| post-attribution rerun | 4 / 60 |
| later diagnostic | 8 / 60 |

Those runs used different exact source revisions and must not be merged into a trend. They show that architecture
verification was ahead of demonstrated task capability. The simplification branch must establish a new live baseline
before adding another architecture layer.

## Simplification acceptance

Run the same predeclared supported cohort against the R2 checkpoint and the simplified core with identical provider,
model, seed, step budget, and pacing. Accept the simplified core when:

- every case produces a valid terminal result and cleanup succeeds;
- no benchmark identifier or oracle data enters product context;
- success does not regress beyond the predeclared tolerance;
- failures are attributable without a control ledger;
- the report contains source, cost, and recovery metrics needed for the adaptive-observation claim.

Then run a paired experiment:

```text
A: structured source only
B: structured source first, visual supplement on typed need
```

The portfolio claim should report task success together with visual-call, token, and latency deltas. A useful result
may be either higher success at similar cost or similar success at lower observation cost.

## Local MiniWoB runtime

Use the pinned project configuration and interpreter:

```bash
set -a
source .env
set +a
export MINIWOB_URL=http://127.0.0.1:18888/miniwob/
export PYTHONPATH=src:tests
/home/yang/.venvs/affordance-browsergym-py312/bin/python -m pytest <focused-tests>
```

Before a live run, verify `http://127.0.0.1:18888/miniwob/click-button.html`. Reuse the existing project server when
it returns 200. Raw run output belongs under an artifact directory, not in maintained documentation.

The current frozen selection manifest remains at `docs/benchmarks/miniwob-60-seed7-v1-manifest.json` until benchmark
runner cleanup moves manifests and artifacts out of the documentation tree.

## Current executable gate

The simplified core is not yet connected to the live MiniWoB runner, so this branch makes no new performance claim.
Its current executable gate is:

```bash
pytest -q tests/unit tests/integration tests/conformance
```

Before the first paired live run, step four must add an explicit `core` versus `legacy` engine selection to benchmark
composition and persist that choice in every report. Do not infer the engine from a branch name. The run must use the
frozen JSON manifest above, write raw per-case JSON under an artifact directory, then aggregate only after all case
records exist. The paired tolerance and A/B observation profiles must be recorded alongside that run rather than
embedded in product code.
