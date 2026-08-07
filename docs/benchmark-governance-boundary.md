# Benchmark Governance Boundary

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** separation between product behavior and offline evaluation

## 1. Rule

Benchmarks measure Affordance Runtime; they do not define Runtime semantics.
Production code, prompts, planners, adapters, route policy, and evaluators may
not branch on benchmark task ID, seed, family, expected result, selector,
coordinate, or hidden fixture metadata.

## 2. Core matrix

The primary target benchmark is positive and cross-surface:

```text
same TaskGoal
same AgentPolicy
same semantic action vocabulary
same ActionEvaluator and TaskEvaluator
different SurfaceAdapter only
→ completed task
```

Required initial surfaces are DOM, AX, Visual, SVG, and WoT. API/Device/CLI extend
the matrix after their adapters are symmetric.

## 3. Metrics

- task success and failure class;
- steps and observation count;
- targeted observations and coverage gaps;
- model and visual calls;
- latency;
- route choice, fallback, and wrong-route count;
- human confirmations;
- stale rejections and unknown-effect duplicate attempts;
- long-horizon constraint/milestone/ask-user behavior;
- batch-barrier and cache-currentness behavior.

Hash equality, event order, delta atomicity, and owner count may protect the
legacy baseline but are not product-level generalization metrics.

## 4. Evidence identity

Every report binds revision, dirty-state status, configuration/profile, model,
adapter versions, task manifest, and denominators. A historical report does not
roll forward. External reward remains offline evidence and never enters
TaskEvaluation.

## 5. Ablations

Benchmark-only ablations use separate composition and are impossible to select
from product inputs. A benchmark failure becomes product work only after being
expressed as a general contract/invariant with non-benchmark evidence.
