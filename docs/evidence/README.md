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

Milestone summaries name the exact clean commit they reproduce. Generated run
artifacts remain ignored because browser timing fields vary; the committed
summary preserves the stable environment identity, acceptance results, counts,
and thresholds.
