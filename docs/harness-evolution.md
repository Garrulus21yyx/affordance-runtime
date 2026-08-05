# Harness Evolution

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** offline, regression-gated learning from traces and failures

## 1. Boundary

Harness evolution is offline and advisory. It consumes committed trace,
artifacts, typed failures, evaluations, and immutable benchmark evidence. It
never participates in synchronous TaskSpec admission, Catalog construction,
ActionContract gating, recovery ownership, task completion, or state commit.

## 2. Controlled loop

```text
immutable failed trace/evidence
→ typed failure analysis
→ generic evolution proposal
→ quarantined candidate
→ replay original failure
→ metamorphic/non-benchmark controls
→ protected breadth and safety replay
→ accept / reject
→ versioned registry entry
```

Accepted candidates enter production only through a separate reviewed change
with architecture admission and explicit owner/deletion gates.

## 3. Candidate types

Permitted proposals include:

- adapter/source acquisition improvements;
- typed predicate/evidence-provider improvements;
- generic grounding/binding or recovery policy changes;
- prompt/context projection changes that cannot alter Runtime authority;
- new regression fixtures or benchmark profiles;
- reusable skills that remain subordinate to TaskSpec and Runtime gates.

Proposals cannot embed task IDs, answers, selectors, coordinates, site-specific
templates, or expand user authorization.

## 4. Evidence requirements

Every proposal binds source revision/profile, failure cause, changed owner,
expected generic invariant, replay set, safety/uncertain-effect analysis,
before/after metrics, and rollback identity.

No-op diagnostic changes do not count as behavior improvement. Targeted success
without breadth/metamorphic controls cannot be promoted.

## 5. Safety constraints

- never mutate production code directly from a live trace;
- never learn capability/approval grants from observed page content;
- never make model evidence authoritative for high-risk external effects;
- never auto-retry an uncertain external transaction during replay;
- never rewrite immutable source traces or evaluator outputs.

## 6. Deferred scale

Queues, worker pools, cross-task evidence reuse, multi-agent parallel evolution,
and automatic source-code mutation remain deferred until measured needs justify
their operational and evidence-lineage cost.

The previous detailed evolution document is archived at
[maintained-pre-consolidation/harness-evolution.md](archive/superseded-2026-08-05/maintained-pre-consolidation/harness-evolution.md).
