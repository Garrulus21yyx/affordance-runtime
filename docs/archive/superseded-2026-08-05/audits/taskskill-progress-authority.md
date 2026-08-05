# TaskSkill Progress Authority Audit

> Baseline: `8445747f0d734b3998b88edb204e099edf58d259`
> Slice: `TPA-1`
> Status: current compatibility authority inventory

## Current state

`TaskSkillRunState` is stored inside StateKernel and currently tracks:

```text
skill_id
version
bindings
next_step_index
active_step_id
completed_step_ids
evidence
fallthrough_reason
```

`AcceptedTaskSkillRuntime` reads and mutates that state through StateKernel's
TaskSkill methods. The executable caller baseline is intentionally restricted to
`task_skills.py`:

```text
activate_task_skill
update_task_skill_bindings
expose_task_skill_step
checkpoint_task_skill_step
fall_through_task_skill
```

RunCoordinator invokes `AcceptedTaskSkillRuntime`; it does not call those five
StateKernel methods directly.

## Current authority finding

TaskSkill is not merely diagnostic today. After verifier-backed checkpointing,
the Coordinator contains a compatibility branch where a completed TaskSkill and
`state.task_plan is None` can set `final_result`, transition to DONE, and append
`TaskCompleted`.

```yaml
current_compatibility_authority:
  skill_step_cursor: true
  verifier_backed_skill_step_checkpoint: true
  no_taskplan_runtime_completion_branch: true
  plan_install_or_replacement: false

target_authority:
  role: current active Runtime step execution strategy
  runtime_task_completion_authority: false
  taskplan_mutation_authority: false
  active_runtime_step_selection_authority: false
```

Literal governance statement: target runtime task completion authority: false.

## Current call chain

```text
RunCoordinator
  -> AcceptedTaskSkillRuntime.expose
  -> StateKernel.activate/update/expose TaskSkill state
  -> normal ActionContract / capability / approval / execution / verification
  -> AcceptedTaskSkillRuntime.verify_active_step
  -> AcceptedTaskSkillRuntime.checkpoint_verified
  -> StateKernel.checkpoint_task_skill_step
  -> compatibility no-TaskPlan completion branch or continue/fallthrough
```

The verification boundary is valuable and must be preserved. The parallel task
completion authority is the debt to remove.

## Owner inventory

| Responsibility | Current owner | Current writes | Target owner |
|---|---|---|---|
| Skill payload admission | accepted profile/registry | accepted payload set | retained policy owner |
| Skill trigger and binding | `AcceptedTaskSkillRuntime` | TaskSkill bindings/state | StepExecutionStrategy selection |
| Skill internal next step | `TaskSkillRunState.next_step_index` | TaskSkill state/version | compatibility continuation only |
| Skill step evidence matching | `AcceptedTaskSkillRuntime.verify_active_step` | none | reusable strategy evidence preparation |
| Skill checkpoint | `checkpoint_verified` -> StateKernel | completed skill IDs/evidence/version | strategy diagnostic/continuation state |
| Runtime active step | legacy TaskPlan/PlanProgress or no plan | separate from skill cursor | StepLifecycle |
| Runtime task completion | Coordinator compatibility branch for no-plan skill | final_result/DONE/trace | TaskSpec completion verifier after TPA-10 |

## Required migration boundary

TaskSkill may:

- propose an action for the Runtime-selected active step;
- impose stricter capability, risk, approval, and evidence requirements;
- retain bounded continuation diagnostics;
- fall through to the standard Step Planner.

TaskSkill may not:

- install, replace, or patch TaskPlan;
- select another Runtime step;
- convert its cursor into Runtime StepProgress;
- complete Runtime task without the normal active-step and task-level verifier;
- bypass ActionContract, approval, preflight, execution, or verification.

## Deletion gate

The no-TaskPlan TaskSkill completion branch can be removed only after:

1. implicit-step/flat-task progress authority is active;
2. TaskSkill proposals bind to the current ActiveStepScope;
3. normal ActiveStepVerifier and TaskSpec completion verification reproduce the
   existing accepted behavior;
4. rollback tests prove the run uses exactly one progress authority;
5. clean PR breadth shows no safety or external-result regression.
