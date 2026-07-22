# Runtime R7 Clean Public Evaluation Evidence

Date: 2026-07-22

Status: R7 clean-revision reproduction complete; M8.2B release capability and
provisioned external suites remain open.

## Frozen identity

All result-bearing runs use:

- Git SHA: `7e1c7db2672b6258a3c961c2ece51555f420f14e`
- source-tree digest:
  `sha256:4e36fbdef1bfa70d1c8ff387a500e62d3190a41b72f70aa8b020ecca286638a6`
- `working_tree_clean=true`
- Python 3.12, BrowserGym MiniWoB 0.14.3, Playwright 1.44.0
- local Ollama `qwen2.5:7b`
- Prompt `generalist-planner-v59`
- planner context `bounded-current-v1`
- schema digest
  `sha256:e3012bd56ec1d60aaaaa34f78673c8fe87468347e4f5a10c5103b85f5c2e6255`
- fixed 165-second episode, 10-second model-call, 15-call, and 15-second
  execution-reserve budget
- seed-major, single-process `three-layer-breadth-first-v1` protocol

No run used `--resume`, mixed providers, GitHub Actions, a dirty source tree,
or a result-bearing change to code, Prompt, schema, model, or context policy.

## Verification ladder

| Layer | Artifact | Result |
| --- | --- | --- |
| Smoke | `artifacts/runtime-r7-7e1c7db-smoke-20260722` | 6/6, reward 1.0, zero failures |
| PR gate | `artifacts/runtime-r7-7e1c7db-pr-20260722` | seed-major 18/18, reward 1.0, zero failures |
| Diagnostic sweep | `artifacts/runtime-r7-7e1c7db-diagnostic-seed0-20260722` | complete 30/30, reward 1.0, zero failure envelopes |
| Frozen nightly | `artifacts/runtime-r7-7e1c7db-nightly-30x10-20260722` | complete 300/300, reward 1.0, `official_score_claimed=true` |
| Residual release | `artifacts/runtime-r7-7e1c7db-release-125x5-20260722` | complete 625/625 observation, success/reward 0.6432, no batch circuit break |

The nightly selected 30 tasks across ten declared action families. It recorded
785 route selections: 755 DOM and 30 SVG. All 300 episodes succeeded; 455 model
calls had zero provider failures, rate-limit retries, or transient retries.
The two long-distance incremental-control failures from the preceding
`f8001d9` nightly were independently closed in the replacement nightly with 18
and 16 freshly verified actions.

## Complete residual release

The release deliberately expanded to all 125 registered pinned tasks at five
seeds. It observed all 625 planned episodes and did not stop on individual
failures:

- 402/625 official successes, mean reward 0.6432;
- 72 tasks at 5/5, 31 tasks at 0/5, and 22 partially successful tasks;
- 534 episodes ended `done`, 69 `failed`, and 22
  `waiting_clarification`;
- 1,766 selected routes: 1,645 DOM and 121 SVG;
- 1,459 model calls, with zero provider failures, 429 retries, or transient
  retries;
- no missing episode, source drift, schema drift, artifact-write failure, or
  batch circuit break.

The 223 unsuccessful-episode envelopes cluster as follows:

| Root layer | Signature | Episodes |
| --- | --- | ---: |
| EXECUTION | `official_reward_zero` after a nominally completed run | 132 |
| VERIFICATION | `verification_failed` | 23 |
| INTENT / PLANNING | `model_call_budget_exhausted` | 20 |
| EXECUTION | `execution_failed` | 16 |
| OBSERVATION / CONTEXT | `observation_no_affordances` | 15 |
| CONTRACT / FIELD_BINDING | `schema_incompatible` for invalid same-target drag | 10 |
| INTENT / PLANNING | `planner_waiting_clarification` | 7 |

This is a residual capability map, not a passing release score. In particular,
the 132 official-zero episodes must be decomposed by postcondition/effect
semantics before treating them as executor defects. Likewise, the ten invalid
same-target drags demonstrate that a one-object spatial gesture cannot be
forced through the existing source/destination `DRAG` contract.

## Boundary and next decision

The release report correctly preserves root-layer distinctions, but its
expanded tasks all use `family="unmapped"`; action-family attribution is
therefore too coarse for the next cross-task remediation decision. This is an
evaluation-taxonomy gap, not permission to dispatch on task ids.

R7 is complete because clean smoke, PR, nightly, and full residual release
evidence now exist for one immutable revision. M8.2B remains in progress:

1. improve generic semantic/action-family attribution from typed trace data;
2. decide architecture-level work from cross-task evidence, beginning with
   observation, gesture-contract, and semantic postcondition clusters rather
   than task-specific solvers;
3. keep ScreenSpot, WebArena-Verified, WASP, and authorized WorkArena as
   separately provisioned evaluation gates;
4. proceed to R8 module containment without changing runtime semantics or
   adding another state writer.
