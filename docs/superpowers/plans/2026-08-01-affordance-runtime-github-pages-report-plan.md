# Affordance Runtime GitHub Pages Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a source-anchored Chinese GitHub Pages report that explains Affordance Runtime from natural-language intake through planning, execution, recovery, verification, and final evidence.

**Architecture:** Use one dependency-free static report page with an E2E architecture map, continuous execution narrative, expandable deep dives, glossary, and source index. Treat current code and tests as implementation truth, label SAR-0 target design separately, and use Agent Atlas only as a depth checklist.

**Tech Stack:** Static HTML5, CSS, minimal vanilla JavaScript, Python repository inspection scripts, pytest/ruff/mypy metadata, local HTTP preview.

---

### Task 1: Establish the immutable evidence baseline

**Files:**
- Modify: `docs/superpowers/plans/2026-08-01-affordance-runtime-github-pages-report-plan.md`

- [x] **Step 1: Record branch and revision**

Run: `git fetch --prune && git rev-parse --abbrev-ref HEAD && git rev-parse HEAD && git rev-parse '@{upstream}'`

Expected: branch `agent/migrate-runtime-components`; local and upstream SHA both `786857f8fb61aa99f2c7e6a23eb8225957e1438b`.

- [x] **Step 2: Capture the repository surface**

Run: `rg --files src/affordance_runtime tests scripts docs | sort > /tmp/affordance-runtime-report-files.txt`

Expected: a deterministic inventory covering runtime source, tests, scripts, and documentation.

- [x] **Step 3: Record baseline completion in this plan**

Edit this task to mark completed steps and add any revision drift discovered before writing.

### Task 2: Trace the public entrypoints and top-level lifecycle

**Files:**
- Read: `src/affordance_runtime/__main__.py`
- Read: `src/affordance_runtime/cli.py`
- Read: `src/affordance_runtime/runtime.py`
- Read: `src/affordance_runtime/runtime_client.py`
- Read: `src/affordance_runtime/integrations/task_api.py`
- Read: `src/affordance_runtime/integrations/external_protocol.py`
- Read: `src/affordance_runtime/integrations/langgraph_parent.py`
- Modify: `docs/superpowers/plans/2026-08-01-affordance-runtime-github-pages-report-plan.md`

- [x] **Step 1: Enumerate callable entrypoints and ownership transitions**

Run: `rg -n '^(class|def|async def) ' src/affordance_runtime/{__main__,cli,runtime,runtime_client}.py src/affordance_runtime/integrations/{task_api,external_protocol,langgraph_parent}.py`

Expected: a symbol list from CLI/service/parent-agent intake to Runtime methods.

- [x] **Step 2: Trace one submit-to-result path**

Read callers and callees until the path reaches `RunCoordinator`, terminal state, and returned result/evidence.

Expected: every edge has a concrete symbol and return type; no edge is inferred only from naming.

- [x] **Step 3: Record findings and unresolved branches in this plan**

### Task 3: Trace natural language into canonical task semantics

**Files:**
- Read: `src/affordance_runtime/task_intake.py`
- Read: `src/affordance_runtime/intent_compiler.py`
- Read: `src/affordance_runtime/source_ledger.py`
- Read: `src/affordance_runtime/canonical_obligation_compiler.py`
- Read: `src/affordance_runtime/task_source_references.py`
- Read: `src/affordance_runtime/task_obligation_coverage.py`
- Read: `src/affordance_runtime/decision_constraints.py`
- Read: `tests/test_canonical_obligation_compiler.py`

- [x] **Step 1: Extract all intake and canonical semantic dataclasses/enums**

Run: `rg -n '^(class|def) ' src/affordance_runtime/{task_intake,intent_compiler,source_ledger,canonical_obligation_compiler,task_source_references,task_obligation_coverage,decision_constraints}.py`

Expected: accepted request, source facts, obligations, coverage, and constraints are mapped to their code owners.

- [x] **Step 2: Verify authority boundaries from tests**

Run: `python -m pytest -q tests/test_canonical_obligation_compiler.py`

Expected: PASS; failures block claims about canonical obligation behavior.

- [x] **Step 3: Build a field-accurate natural-language-to-typed-object example for the report**

Expected: example fields match current constructors and enum values.

### Task 4: Trace planner request, structured output, plan admission, and repair

**Files:**
- Read: `src/affordance_runtime/planning_request.py`
- Read: `src/affordance_runtime/planning_request_builder.py`
- Read: `src/affordance_runtime/planning_request_serializer.py`
- Read: `src/affordance_runtime/planner_context.py`
- Read: `src/affordance_runtime/planner_model_orchestrator.py`
- Read: `src/affordance_runtime/generalist_planner.py`
- Read: `src/affordance_runtime/planner_adapters.py`
- Read: `src/affordance_runtime/planner_admission_projection.py`
- Read: `src/affordance_runtime/planner_schema_recovery.py`
- Read: `src/affordance_runtime/planner_context_recovery.py`
- Read: `src/affordance_runtime/model_recovery.py`
- Read: `tests/test_generalist_planner.py`
- Read: `tests/test_planner_response_contracts.py`

- [x] **Step 1: Map request serialization and model boundaries**

Run: `rg -n '^(class|def|async def) ' src/affordance_runtime/{planning_request,planning_request_builder,planning_request_serializer,planner_context,planner_model_orchestrator,generalist_planner,planner_adapters,planner_admission_projection,planner_schema_recovery,planner_context_recovery,model_recovery}.py`

Expected: prompt input, structured response, schema parse, retry/recovery, and admission are separate mapped stages.

- [x] **Step 2: Verify planner contracts**

Run: `python -m pytest -q tests/test_generalist_planner.py tests/test_planner_response_contracts.py`

Expected: PASS.

- [x] **Step 3: Explicitly classify context behavior**

Expected: report distinguishes planner projection/recovery from full conversation-history compaction and states whether the latter exists in current code.

### Task 5: Trace TaskPlan, StepSpec, TaskSkill, progress, and replanning

**Files:**
- Read: `src/affordance_runtime/task_plan_contracts.py`
- Read: `src/affordance_runtime/task_planning.py`
- Read: `src/affordance_runtime/task_plan_generators.py`
- Read: `src/affordance_runtime/task_plan_flow.py`
- Read: `src/affordance_runtime/task_plan_lifecycle.py`
- Read: `src/affordance_runtime/task_plan_progress.py`
- Read: `src/affordance_runtime/task_plan_progress_flow.py`
- Read: `src/affordance_runtime/task_skills.py`
- Read: `src/affordance_runtime/task_skill_progress.py`
- Read: `src/affordance_runtime/active_step_scope.py`
- Read: `tests/test_task_plan_contracts.py`
- Read: `tests/test_task_skills.py`
- Read: `tests/test_active_step_scope.py`

- [x] **Step 1: Map task/step lifecycle and all state transitions**

Expected: report shows plan creation, admission, active-step selection, criterion binding, credit, completion, and replan triggers.

- [x] **Step 2: Verify focused plan/skill tests**

Run: `python -m pytest -q tests/test_task_plan_contracts.py tests/test_task_skills.py tests/test_active_step_scope.py`

Expected: PASS.

### Task 6: Trace the five-stage agent loop and single-writer state commits

**Files:**
- Read: `src/affordance_runtime/coordinator.py`
- Read: `src/affordance_runtime/contract_execution_loop.py`
- Read: `src/affordance_runtime/runtime_loop_phase.py`
- Read: `src/affordance_runtime/perception_phase.py`
- Read: `src/affordance_runtime/planning_phase.py`
- Read: `src/affordance_runtime/execution_phase.py`
- Read: `src/affordance_runtime/progress_phase.py`
- Read: `src/affordance_runtime/recovery_phase.py`
- Read: `src/affordance_runtime/runtime_result_phase.py`
- Read: `src/affordance_runtime/runtime_committer.py`
- Read: `src/affordance_runtime/state_kernel.py`
- Read: `tests/test_horizontal_architecture_governance.py`

- [x] **Step 1: Trace the actual loop condition and directive routing**

Expected: each iteration branch identifies its StageInput, StageResult/directive, budgets, terminal check, and next owner.

- [x] **Step 2: Verify architecture ownership checks**

Run: `python -m pytest -q tests/test_horizontal_architecture_governance.py`

Expected: PASS.

- [x] **Step 3: Reconcile code with SAR-0 target loop**

Expected: report labels implemented phase extraction, remaining Coordinator logic, compatibility imports, and target-only claims.

### Task 7: Trace perception, grounding, action choice, contract execution, and verification

**Files:**
- Read: `src/affordance_runtime/unified_observation.py`
- Read: `src/affordance_runtime/perception.py`
- Read: `src/affordance_runtime/perception_session.py`
- Read: `src/affordance_runtime/active_perception.py`
- Read: `src/affordance_runtime/unified_grounding.py`
- Read: `src/affordance_runtime/interaction_grounding.py`
- Read: `src/affordance_runtime/action_choice.py`
- Read: `src/affordance_runtime/contracts.py`
- Read: `src/affordance_runtime/executors.py`
- Read: `src/affordance_runtime/verification.py`
- Read: `src/affordance_runtime/action_outcome_flow.py`
- Read: `tests/test_unified_observation.py`
- Read: `tests/test_perception.py`
- Read: `tests/test_contracts.py`

- [x] **Step 1: Map observation-to-action binding and stale-state defenses**

Expected: target identity, environment revision, preconditions, expected effects, receipt, post-observation, and verifier evidence are connected field-by-field.

- [x] **Step 2: Verify focused perception/contract tests**

Run: `python -m pytest -q tests/test_unified_observation.py tests/test_perception.py tests/test_contracts.py`

Expected: PASS.

### Task 8: Trace recovery, authorization, approval, liveness, and terminal behavior

**Files:**
- Read: `src/affordance_runtime/recovery_protocol.py`
- Read: `src/affordance_runtime/recovery_coordinator.py`
- Read: `src/affordance_runtime/recovery_owner_dispatcher.py`
- Read: `src/affordance_runtime/proposal_recovery_policy.py`
- Read: `src/affordance_runtime/failure_envelope.py`
- Read: `src/affordance_runtime/scope_authorization.py`
- Read: `src/affordance_runtime/approval_contracts.py`
- Read: `src/affordance_runtime/safety.py`
- Read: `src/affordance_runtime/terminal_readiness.py`
- Read: `src/affordance_runtime/runtime_terminal.py`
- Read: `src/affordance_runtime/obligation_progress.py`
- Read: `src/affordance_runtime/obligation_attribution_flow.py`
- Read: `tests/test_model_recovery.py`
- Read: `tests/test_uncertain_effect_coordinator.py`

- [x] **Step 1: Build the typed failure-to-owner routing table**

Expected: runtime mechanical recovery, planner/schema/context recovery, replan, user handoff, terminal failure, and uncertain effect are distinct.

- [x] **Step 2: Verify recovery and uncertain-effect tests**

Run: `python -m pytest -q tests/test_model_recovery.py tests/test_uncertain_effect_coordinator.py`

Expected: PASS.

### Task 9: Trace evidence, trace, evaluation, evolution, and external E2E harnesses

**Files:**
- Read: `src/affordance_runtime/trace.py`
- Read: `src/affordance_runtime/runtime_evidence.py`
- Read: `src/affordance_runtime/artifacts.py`
- Read: `src/affordance_runtime/evaluation_audit.py`
- Read: `src/affordance_runtime/evolution.py`
- Read: `src/affordance_runtime/harness_learning.py`
- Read: `scripts/run_generalist_local_e2e.py`
- Read: `scripts/run_g5_runtime_rollout.py`
- Read: `scripts/langgraph_parent_smoke.py`
- Read: `scripts/reproduce_local.sh`

- [x] **Step 1: Map emitted evidence to consumers and promotion gates**

Expected: runtime correctness evidence is separated from benchmark scoring and evolution acceptance.

- [x] **Step 2: Select one generic E2E path and one external parent path for narrative examples**

Expected: examples remain Runtime-first and do not imply BrowserGym is the product.

### Task 10: Calibrate deep-dive coverage against Agent Atlas

**Files:**
- Read: `/home/yang/agent-systems-atlas/pages/interview-agent.html`
- Read: `/home/yang/agent-systems-atlas/pages/interview-project.html`
- Read: `/home/yang/agent-systems-atlas/pages/interview-memory-context.html`
- Read: `/home/yang/agent-systems-atlas/pages/loopx-state-kernel.html`
- Read: `/home/yang/agent-systems-atlas/pages/browsergym-web-runtime.html`
- Modify: `docs/superpowers/plans/2026-08-01-affordance-runtime-github-pages-report-plan.md`

- [x] **Step 1: Extract architecture depth dimensions, not canned answers**

Expected: coverage checklist includes state ownership, authority, structured output, context cost, idempotency, liveness, recovery, evaluation leakage, and trade-offs.

- [x] **Step 2: Record missing report angles**

Expected: missing angles are added to the report outline without turning it into a Q&A page.

### Task 11: Build the static report site

**Files:**
- Create: `docs/affordance-runtime-deep-dive/index.html`
- Create: `docs/affordance-runtime-deep-dive/styles.css`
- Create: `docs/affordance-runtime-deep-dive/site.js`
- Create: `docs/affordance-runtime-deep-dive/README.md`
- Modify: `docs/README.md`

- [x] **Step 1: Create semantic HTML shell and complete content**

Expected: all twelve approved information-architecture sections are present with no placeholder text.

- [x] **Step 2: Add responsive, print-safe visual design**

Expected: layout works at 320px and desktop widths; diagrams have text alternatives.

- [x] **Step 3: Add progressive navigation without making JavaScript mandatory**

Expected: anchors and details work without JavaScript; JavaScript only enhances active navigation and menu behavior.

- [x] **Step 4: Add publication and maintenance instructions**

Expected: README explains local preview and GitHub Pages configuration without claiming remote deployment.

### Task 12: Validate facts, markup, links, and reader comprehension

**Files:**
- Verify: `docs/affordance-runtime-deep-dive/index.html`
- Verify: `docs/affordance-runtime-deep-dive/styles.css`
- Verify: `docs/affordance-runtime-deep-dive/site.js`
- Verify: `docs/affordance-runtime-deep-dive/README.md`
- Verify: `docs/README.md`

- [x] **Step 1: Scan for placeholders and unqualified architecture claims**

Run: `rg -n 'TBD|TODO|待补充|占位|已经完全|全面完成' docs/affordance-runtime-deep-dive docs/README.md`

Expected: no placeholders; absolute completion claims are absent or evidence-qualified.

- [x] **Step 2: Check local source anchors**

Run: a Python link checker that resolves every `../` repository link from the report directory.

Expected: zero missing local targets.

- [x] **Step 3: Parse HTML and validate required sections**

Run: Python `html.parser` check for duplicate IDs, missing fragment targets, missing image/SVG accessibility labels, and the twelve required section IDs.

Expected: zero errors.

- [x] **Step 4: Preview in a real browser at desktop and mobile widths**

Run: local HTTP server plus Playwright screenshots/console checks.

Expected: no console errors, no horizontal overflow at 320px, all primary navigation links work.

- [x] **Step 5: Run focused repository tests and style checks**

Run: the focused pytest commands from Tasks 3–8 and `ruff check src tests`.

Expected: PASS; report-only changes introduce no Runtime regressions.

- [x] **Step 6: Perform reader testing**

Expected: a fresh-context reader can explain the E2E path, authority boundaries, planner-to-task conversion, context semantics, recovery routing, and implemented-vs-target distinction without external context.
