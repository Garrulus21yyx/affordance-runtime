# T3.3 action candidate cutover plan

Goal: implement and verify the complete provider-free T3.3 breaking cutover from DirectActions and legacy discovery tools to one deterministic ActionCandidate ranker and separated read/action discovery contracts.

Constraints: start at `8af7b714`; preserve and do not commit `.codex-plans/` or `output/`; do not run live/provider/W2; do not change environment/model configuration; do not add site/case-specific behavior.

## Steps

1. **done** — Read required architecture/benchmark sections and inventory current owners, public tools, DirectActions code, tests, and provider-free diagnostic.
2. **done** — Define the bounded typed candidate/ranker and discovery-result contracts at the existing paging/search owners.
3. **done** — Implement shared ranker, automatic Top-5 projection, structural closure, manifest closure, and `find_actions` pagination/search reuse.
4. **done** — Perform the public breaking cutover to `open_region`, `find_content`, `find_actions`; remove old names, aliases, branches, fixtures, and DirectActions production path.
5. **done** — Add/update invariant and regression tests, including read/action separation and native/JSON convergence.
6. **done** — Run focused and existing related tests; repair shared causes only.
7. **done** — Run full pytest, Ruff, and diff check.
8. **done** — Run and persist the six-page provider-free diagnostic with T3.3 metrics.
9. **done** — Conduct an independent limited fresh-context audit; repair and rerun gates if P0/P1 is found.
10. **done** — Update only `docs/architecture.md` and `docs/benchmark.md` with honest non-closed status and evidence.
11. **done** — Verify staged scope excludes user artifacts, commit, and push to `origin/codex/simplify-core-runtime` only if all gates pass.

## Files produced or modified

- `.codex-plans/t33-action-candidate-cutover.md` (execution-only, never commit)
- `src/affordance_runtime/actions/paging.py`
- `src/affordance_runtime/agent/context/action_candidate_projection.py`
- `src/affordance_runtime/agent/context/{compact_world_renderer,context,context_builder,episode_history,model_turn_delivery,step_projection,world_region_index}.py`
- `src/affordance_runtime/model/policy/{grounded_tool_catalog,prompts/grounded_agent.yaml}`
- `src/affordance_runtime/mission/monitor.py`
- `src/affordance_runtime/benchmarks/webarena_verified.py`
- `tests/unit/agent/test_action_candidate_delivery.py` plus migrated semantic/tool/paging/integration contracts
