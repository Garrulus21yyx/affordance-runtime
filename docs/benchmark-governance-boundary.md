# Benchmark Governance and Anti-Specialization Boundary

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** benchmark use, repair admission, evidence claims, and specialization controls
> **Runtime boundary:** [Runtime-First Architecture Boundary](runtime-first-boundary.md)

## 1. Decision

Benchmarks audit Affordance Runtime; they do not own it. Every benchmark-driven
change must improve a generic Runtime contract, invariant, or capability and
must have at least one non-benchmark or metamorphic control.

## 2. Prohibited production dependencies

Runtime core, shared planners, prompts, semantic owners, adapters, recovery,
and verification may not depend on:

- benchmark task ID, seed, family, site, expected answer, or authored solution;
- fixture selectors, coordinates, exact labels, URLs, or DOM layouts;
- task-template branches disguised as “generalist” helpers;
- benchmark reward as progress/completion authority;
- evaluation-only metadata in planner context.

Moving a special case to a shared module does not make it general.

## 3. Admissible repair form

A benchmark failure may justify a change only when the repair packet contains:

1. typed generic failure cause;
2. owner and contract boundary;
3. non-benchmark reproduction or metamorphic negative control;
4. protected-family/breadth regression plan;
5. safety and uncertain-effect analysis;
6. immutable revision/profile identity;
7. explicit non-claims.

## 4. Evaluation separation

| Result | Meaning |
|---|---|
| Runtime `TaskCompleted` | TaskSpec.success closure committed by RuntimeCommitter |
| external reward/oracle | evaluator judgment for one episode |
| harness diagnostic | injected/internal path evidence |
| benchmark profile result | aggregate for one immutable revision and profile |

These values are reported separately. A passed evaluator cannot retroactively
make an unsafe or unverified Runtime transition valid.

## 5. Profiles and claims

At minimum, reports identify planner profile, provider/model, environment and
asset version, source revision, dirty state, seed set, budgets, missing/unrun
episodes, Runtime result, external result, and official-score claim flag.

Targeted smoke supports diagnosis. Breadth supports regression confidence.
Promotion additionally requires architecture admission, safety, cross-surface
or non-benchmark evidence, and all required checks at the same revision.

## 6. Data and prompt isolation

Task instructions and page content remain untrusted inputs. Evaluation labels,
expected values, hidden state, and oracle code cannot enter Runtime planning or
verification context unless the public integration contract would provide the
same data in production.

## 7. Historical evidence

Old reports remain valid only for their recorded revision/profile. They are not
rewritten when architecture changes and do not define current behavior.

The previous detailed policy is archived at
[maintained-pre-consolidation/benchmark-governance-boundary.md](archive/superseded-2026-08-05/maintained-pre-consolidation/benchmark-governance-boundary.md).
