# T3.2 next-layer recovery convergence

Status: completed_locally_non_closed
Branch: `codex/simplify-core-runtime`
Started: 2026-08-20

## Scope

Close the next locally identified gaps without changing World/DeliveryManifest, Auditor, GoalPlan, Binder, or the
CoreAgentLoop execution chain:

1. project `ProtocolFeedback` through the benchmark's closed decision vocabulary and preserve formal reports;
2. remove generation-local E/N/F/R placeholders from model history in favor of semantic operation/target/result data;
3. add one bounded, deterministic, non-authoritative `MissionEnvironmentView` to Manager input;
4. choose native single-tool versus JSON single-command at the provider wire-capability owner, then converge on the
   existing ToolCall/catalog/resolver/admission/Binder/Executor path;
5. retain `multiple_tool_calls -> ProtocolFeedback -> protocol_stall -> Manager` as the exceptional fallback.

## Baseline

- HEAD and origin are `732379b3 refactor: converge T3.2 model-turn contracts`.
- No tracked changes at start of this increment.
- Existing untracked paths are preserved: `.codex-plans/t32-contract-convergence.md`,
  `.codex-plans/t32-probe-v2-zhipu46.md`, and `output/`.
- No reset, checkout, cleanup, live provider call, or live benchmark is authorized.

## Plan

1. [completed] Map benchmark decision projection, semantic history projection, Manager request construction, and
   provider wire selection/compatibility ownership.
2. [completed] Add `ProtocolFeedback` benchmark projection and reporting regressions.
3. [completed] Replace expired-ref placeholders in model history with bounded ref-free semantic target/capability facts.
4. [completed] Add and project bounded `MissionEnvironmentView` from fresh World/current runtime capabilities.
5. [completed] Introduce provider wire-capability selection and route DeepSeek-compatible profiles through the existing
   JSON single-command adapter without model-ID conditionals.
6. [completed] Run focused properties, provider-free reporting diagnostic, full pytest, Ruff, diff-check, cleanup rg,
   and an independent fresh-context audit.
7. [completed] Synchronize only `docs/architecture.md` and `docs/benchmark.md`; report an honest non-closed status.

## Non-goals

- No World compression, DeliveryManifest, Auditor, GoalPlan, Binder, or CoreAgentLoop authority changes.
- No action queue, arbitrary multi-action execution, fill_form, SemanticTargetSelector, VLM fallback, second GUI loop,
  benchmark-specific selector/label, or live/provider witness.
