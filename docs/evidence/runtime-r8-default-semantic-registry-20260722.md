# Runtime R8 Default SemanticCompiler Registry Containment Evidence

Date: 2026-07-22

Status: default registry assembly slice complete; R8 remains in progress.

## Boundary

The Runtime's ordered default semantic compiler profile now lives in
`default_semantic_compilers.py`. It owns only declarative assembly:

- compiler and constraint identifiers and precedence;
- supported intents and operation-class scopes;
- typed applicability predicates;
- required state keys, declared output kinds, verifier requirements, negative
  examples, and evidence source/version metadata;
- a typed callback bundle for the semantic algorithms.

`generalist_planner.py` retains the semantic compilation and constraint
algorithms. Its existing `default_semantic_compiler_registry()` entrypoint now
injects those functions into the factory, so downstream callers and the
`GeneralistLMPlanner` default remain compatible. The planner still owns model
invocation, Prompt/schema validation and repair, proposal binding, and compiler
execution order relative to the model fallback.

This slice changed no Prompt, schema, model budget, context-policy version,
provider behavior, compiler identifier, rule precedence, applicability rule,
evidence declaration, or semantic output. It introduced no service, state
writer, backend syntax, selector, coordinate, or benchmark/task-family branch.
The Generalist planner fell from 2,617 to 2,481 lines; the 193-line profile
module is provider- and adapter-neutral.

## Runtime-first evidence

Direct factory tests freeze the four-rule precedence:

```text
authored calendar range
  -> bounded text transform
  -> typed incremental control
  -> general typed affordance semantics
```

They also prove that a context eligible for every rule selects only the first
rule, all evidence sources and operation classes remain declared, and empty or
unsupported contexts call no compiler and produce no constraint. Existing
generic DOM tests continue to prove incremental-control compilation and
semantic drag behavior without importing or running BrowserGym. The shared
source boundary test rejects BrowserGym/MiniWoB vocabulary.

No benchmark was run for this internal containment slice: the required claim is
behavioral equivalence and ownership improvement, covered by the full Runtime
suite and generic integration tests. Benchmark evaluation remains a later
external gate and is not used as architecture evidence here.

## Verification

Using `/home/yang/.venvs/affordance-browsergym-py312/bin/python`:

- focused registry, generic DOM, and source-boundary tests: 12 passed;
- full repository tests: 488 passed;
- Ruff over `src` and `tests`: passed;
- mypy with `--ignore-missing-imports` over 83 source files: passed;
- `git diff --check`: passed.

## Remaining R8 work

- extract Generalist model invocation and schema-repair orchestration while
  keeping Prompt/schema/budget behavior stable;
- decide whether semantic algorithms need a further cohesive module boundary,
  based on ownership rather than file-size reduction;
- split BrowserGym observer, encoder, episode runner, and report adapter;
- migrate selected bindings toward tagged payloads and finish the ownership and
  trace-schema audit.
