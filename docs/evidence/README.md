# Reproducible Evidence

M5 freezes the controlled-local evidence protocol. Generated benchmark and
evolution reports must identify the runtime commit, Python, Playwright,
Chromium, fixture version, suite version, worktree state, and seed semantics.

From a clean checkout:

```bash
./scripts/reproduce_local.sh
```

The script installs an isolated environment, runs tests and static checks,
builds the package, executes a focused real-Chromium smoke, runs the 3 x 7 local
matrix, generates the evolution report, and validates both release gates.

Until M8, `seed_semantics=label_only_v1` is expected and must not be presented
as randomized evidence. M8 replaces it with deterministic, distinct fixture
variants and adds unseen layouts plus a pinned MiniWoB++ subset.
