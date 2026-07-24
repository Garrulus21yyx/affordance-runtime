# Reproducible Evidence

M5 freezes the controlled-local evidence protocol. Generated benchmark and
evolution reports must identify the runtime commit, Python, Playwright,
Chromium, fixture version, suite version, worktree state, and seed semantics.

From a clean checkout:

```bash
./scripts/reproduce_local.sh
```

The script installs an isolated environment, runs tests and static checks,
builds the package, executes focused Chromium and external LangGraph smokes,
runs the three-seed 3 x 7 local matrix, generates executable-evolution and M8
generalization reports, and validates all evidence gates.

Historical M5 evidence records `seed_semantics=label_only_v1` and must not be
presented as randomized evidence. Current M8 evidence records
`deterministic_distinct_layout_v2`, plus held-out layouts, screenshot grounding,
and a repeated pinned official MiniWoB++ subset.

M8.1 adds a digest-pinned non-root container profile, exact host/container
outcome comparison, and an optional real node-wot cross-surface conformance
gate. See `m8.1-40fd93b.md`.

Milestone summaries name the exact clean commit they reproduce. Generated run
artifacts remain ignored because browser timing fields vary; the committed
summary preserves the stable environment identity, acceptance results, counts,
and thresholds.

Historical score interpretation is governed by
`m8.6-g0-profile-and-report-inventory-20260724.md`. In particular, reports that
predate explicit strict/compatibility profile and registry identity are legacy
diagnostics or reconstructed historical-compatibility evidence, not current
strict-generalist scores. New generalization evidence uses the four-profile G5
contract and cannot promote a benchmark score as sole proof.
