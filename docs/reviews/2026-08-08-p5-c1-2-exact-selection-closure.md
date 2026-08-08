# P5-C1.2/B1.2 exact selection and efficient currentness

> **Lifecycle:** IMPLEMENTATION RECORD
> **Semantic authority:** false
> **Start SHA:** `b4f0eef501d343dfe0d94962639b71cc6ff5164e`
> **Date:** 2026-08-08

## Result

This non-default slice closes the remaining gate before the single-surface
Visual vertical. It does not add Visual/WoT execution or change the default
product path beyond the already-admitted baseline bug fix.

- `ActionOption` contains a Runtime effect category, canonical schema digest,
  and opaque eligible-binding group. `AdmittedActionSelection` retains
  option/category/effect/schema/risk/barrier
  identity plus parameters, and `ActionBinder` ranks only within that group.
- Action IDs include observation, target, semantic action, Runtime category,
  normalized effects, schema digest, and eligible binding IDs. Schema variants
  cannot alias.
- `ActionBinding` retains both semantic and source-local target identity.
- DOM bindings use a Runtime-owned coarse category, risk floor, and observation
  barrier. Page-authored effect/risk metadata cannot grant an unlisted TaskGoal
  effect or lower the Runtime risk floor. The Chromium proof no longer requires
  `data-runtime-effect-class`.
- Unsupported DOM primitives retain their semantic target and are reported as
  coverage without aborting observation. Unsupported schema types fail closed.
- World/source identity checks perform no physical acquisition. DOM execution
  owns at most one live DOM target probe, reported separately from observations.
- Reset clears world/source identity before adapters reset. A pre-reset request
  is stale before the next observation.
- A `NOT_SENT` result does not increment execution count. Currentness probes are
  counted from adapter evidence.
- Legacy verified absence releases the progress guard only when settlement and
  recent action outcome carry the same execution attempt ID.

## Remaining boundary

```text
single_DOM_minimum: CLOSED
exact_option_to_binding_fidelity: CLOSED
runtime_owned_coarse_effect_risk: CLOSED
generic_business_effect_classifier: LIMITED
Visual_surface_vertical: NEXT_ADMITTED_SLICE
WoT_surface_vertical: AFTER_VISUAL
semantic_fusion: NOT_STARTED
external_benchmark_status: BLOCKED
default_cutover: NOT_READY
```

## Verification

```text
pytest: 1115 passed
focused selection/currentness/attempt lineage: 46 passed
independent settings recovery --runxfail: passed
real Chromium DOM vertical: passed with one currentness probe
ruff: passed
mypy: passed (232 source files)
target size/import boundaries: passed
docker compose config: passed
git diff --check: passed
```
