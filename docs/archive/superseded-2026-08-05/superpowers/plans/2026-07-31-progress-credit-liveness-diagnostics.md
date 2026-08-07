# Progress Credit, Liveness, and Diagnostic Truth Implementation Plan

> **For Codex:** Execute this plan task by task. Do not start the later InteractionIntent or ActionChoice-coverage program in this unit.

**Goal:** Close the three proven post-action progress-credit loops, make those failures terminate with a typed root cause instead of exhausting the runtime budget, and make BrowserGym reports describe the actual planning and terminal boundary.

**Architecture constraint:** This is an S0/S1 behavioral repair on the current five-stage architecture. It may replace or delete stale diagnostics, but must not add a top-level phase/stage, compatibility adapter, facade, or parallel result protocol. State and trace commits remain owned by `RuntimeCommitter`.

**Validated starting evidence:** `click-checkboxes` seeds 0 and 1 and `click-scroll-list` seed 1 dispatch a successful first action, record a verified effect, then reject mandatory active-step evidence. Repeated proposals are blocked as `effect_already_satisfied` until the runtime budget is exhausted. This is a progress-evidence binding/liveness fault, not a proven executor fault.

**Master-plan relationship:** This executes M0/M1 of `2026-07-31-agent-loop-semantic-closure-master-plan.md`. Named episodes are external evidence only; production behavior must be task-agnostic and must pass generic/metamorphic invariants before those replays.

---

## Task 1: Emit one canonical planning-turn diagnostic event

**Files:**

- Modify: `src/affordance_runtime/planning_contracts.py`
- Modify: `src/affordance_runtime/generalist_planner.py`
- Modify: `src/affordance_runtime/planning_phase.py`
- Test: planning contract and planning-stage focused tests under `tests/`

**Implementation:**

1. Add an immutable planning diagnostic payload containing the actual model boundary and Runtime choice facts: `model_stage`, grounded target count, action choice count, and selection source.
2. Populate it where the strict planner response is constructed; do not infer these fields later from legacy `PlannerContextBuilt` events.
3. Have `PlanningStage` return one `PlanningTurnEvaluated` `RuntimeEvent` per planning turn through the existing `StageResult.events` path.
4. Delete or stop emitting any superseded default-path diagnostic fields in the same unit.

**Tests:**

- Zero, one, and many-choice paths report the correct counts.
- Model stage distinguishes Intent, TaskPlan, and ActionChoice selection.
- Runtime auto-selection is not mislabeled as a model selection.

## Task 2: Bind active-step verification to the resolved progress target

**Files:**

- Modify: `src/affordance_runtime/execution_phase.py`
- Reuse: `resolve_task_plan_progress_target` and `TaskPlanProgressTarget` from the existing planning domain code
- Test: execution/contract binding focused tests

**Implementation:**

1. In `ActionStage._bind`, resolve the current proposal's task-plan progress target from proposal, immutable state view, and snapshot.
2. Pass that explicit target into `bind_active_subgoal_verifiers(..., progress_target=...)`.
3. Preserve fail-closed behavior for stale, missing, or ambiguous targets; do not fall back to a guessed active step.
4. Do not add an ActionStage-to-PlanningStage dependency: import the domain resolver/service only.

**Tests:**

- A current unambiguous target materializes active-step criterion and requirement IDs.
- A stale or ambiguous target remains uncredited.
- The three affected BrowserGym tasks no longer lose active-step IDs after a verified first action.

## Task 3: Emit one canonical post-action evaluation

**Files:**

- Modify: `src/affordance_runtime/progress_phase.py`
- Modify only the existing progress result/status type; do not add a second protocol
- Test: progress-stage focused tests

**Implementation:**

1. Represent action effect, active-step progress, and task completion as independent typed statuses.
2. Emit one `PostActionEvaluated` event containing those three statuses plus credited criterion/requirement IDs and the active progress target.
3. Keep completion authority unchanged: verified effect alone must not imply step or task completion.
4. Route the event through `StageResult.events`; the stage must not write TraceDag directly.

**Tests:**

- Verified effect plus credited step evidence advances the step.
- Verified effect without credit reports an explicit uncredited status.
- Task completion remains independently verified.

## Task 4: Replace budget exhaustion with a typed progress-liveness failure

**Files:**

- Modify: `src/affordance_runtime/contracts.py`
- Modify: `src/affordance_runtime/failure_envelope.py`
- Modify: `src/affordance_runtime/execution_phase.py`
- Modify: `src/affordance_runtime/stage_protocol.py` and the single owner handoff in `src/affordance_runtime/runtime_committer.py` only if the existing Progress handoff cannot carry the typed reason
- Test: failure ownership and loop-liveness focused tests

**Implementation:**

1. Add `RuntimeErrorCode.PROGRESS_CREDIT_INVARIANT` and `FailurePhase.PROGRESS`.
2. At the existing ActionStage progress guard, first attempt typed active-step reconciliation. Detect the invariant only when effect is already satisfied, the same progress target/action context cannot receive required credit, and relevant state did not change.
3. Return a typed failure owned by `FailureOwner.PROGRESS`; do not repeat observation until the global runtime budget expires.
4. Keep non-runtime owners out of `RecoveryDecision` and do not increment runtime recovery count for this failure.

**Tests:**

- The cycle terminates at the first proven invariant violation.
- Root failure phase is `PROGRESS`, terminal status is failure, and the report does not call it executor failure.
- Existing legitimate re-observation/recovery paths remain available when the invariant has not been proven.

## Task 5: Make BrowserGym metrics and failure classification event-derived

**Files:**

- Modify: `src/affordance_runtime/benchmarks/browsergym_episode_runner.py`
- Modify: `src/affordance_runtime/benchmarks/browsergym_report.py`
- Test: BrowserGym report/unit tests

**Implementation:**

1. Derive `model_stage`, grounded target count, action choice count, and selection source from `PlanningTurnEvaluated`.
2. Derive effect/step/task statuses and progress-credit failures from `PostActionEvaluated`.
3. Report `root_failure_phase` separately from `terminal_status`.
4. Remove the fallback that maps the terminal string `execution_failed` to executor ownership when no runtime failure object is present.
5. Delete stale default-path metrics based only on absent `PlannerContextBuilt` events in the same unit.

**Tests:**

- Pre-dispatch Intent, TaskPlan, and ActionChoice failures are classified at their true model stage.
- Progress-credit invariant failures are not classified as executor failures.
- Reports contain no zero-valued placeholder metrics when a canonical event is available.

## Task 6: Verification ladder and evidence update

**Files:**

- Modify: `docs/change-admission/sar-9-phase-architecture-closure.yaml` only with measured evidence; do not create a new micro-slice YAML
- Modify: the existing PR-breadth/fresh-run result document if one exists

**Commands and order:**

1. Run focused tests for planning diagnostics, target binding, progress evaluation, failure ownership, and BrowserGym reports.
2. Run affected architecture gates, Ruff on changed files, core mypy, and `git diff --check`.
3. Run the three targeted episodes and preserve full timelines:
   - `click-checkboxes`, seed 0
   - `click-checkboxes`, seed 1
   - `click-scroll-list`, seed 1
4. Run complete clean 6x2. Stop if it is not 12/12.
5. After clean 12/12, run fresh 30x2 and record every failure by root phase and terminal status.

**Acceptance:**

- Targeted progress-credit/liveness loops: 0.
- Targeted episodes pass, or any remaining failure occurs after the repaired boundary with a new typed root cause and complete timeline.
- Clean 6x2: 12/12.
- Fresh 30x2: all 60 episodes observed, provider failures 0, unclustered failures 0.
- No claim that fresh 30x2 is fully clean until the later InteractionIntent/choice-coverage work is complete.
- No new top-level stage, compatibility adapter, facade, or micro-admission YAML.
- No production branch contains a BrowserGym task id, seed, task title, or family-specific literal; generic and renamed/reordered fixtures prove the behavior independently.

---

## Deferred program boundary

After this unit is verified, plan InteractionIntent and choice coverage in this order: Element, Collection/Dynamic, Data/Read, Relation, Spatial, followed by TaskPlan/Intent repair. That work must not be mixed into the progress-credit repair because it changes planning semantics and has a different behavioral gate.

## Self-review checklist

- Every new canonical field replaces a stale default-path source in the same unit.
- Stage modules communicate through the existing `StageResult`; no second result protocol appears.
- No stage imports another stage or mutates StateKernel/TraceDag directly.
- Progress ownership remains distinct from runtime recovery.
- Failure reports distinguish root cause from terminal envelope.
- The protected clean 6x2 corridor remains 12/12 before fresh 30x2 is attempted.
