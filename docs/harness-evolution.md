# Harness Evolution

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** offline policy, observation, route, and evaluator improvement

## 1. Boundary

The harness consumes immutable run/turn records and benchmark outcomes. It may
propose changes to observation policy, route policy, prompts, or evaluators, but
it never changes a live run or grants execution authority.

## 2. Candidate types

- targeted-observation policy;
- semantic entity fusion or conflict resolution;
- route ranking and cost model;
- AgentWorldView compression;
- AgentPolicy prompt/model configuration;
- ActionEvaluator/TaskEvaluator logic;
- benchmark task and adapter coverage;
- currentness-checked BindingCache candidates;
- verified milestone/Skill templates.

Event schema, commit protocol, ledger, or recovery-transaction tuning is not a
primary product-evolution axis.

## 3. Promotion evidence

Candidates require focused correctness checks plus positive cross-surface
comparison. Report task success, observation/model/visual cost, latency, route
mistakes, fallback, confirmation, and unknown-effect behavior. No candidate may
weaken stale zero-call, semantic confirmation identity, fresh observation, no blind
retry, or output integrity.

The promotion chain is Turn records → failure attribution → candidate memory,
Skill or route hint → offline replay/cross-surface evaluation → publish/reject.
The live Runtime never mutates or automatically publishes its own core policy.

BindingCache hits are hints only: target identity and fingerprint/currentness
must be resolved against the current observation, and execution still requires
fresh post-action observation.

## 4. Isolation

Offline replay cannot call live drivers, networks, credentials, accounts, or
effectful adapters. Benchmark reward and harness suggestions never become
online TaskEvaluation.
