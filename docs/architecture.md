# Architecture

## Status

Current status: **single-ActionPolicy control path plus C8 stages 1–6 implemented provider-free /
generated diagnostics, fresh audit, and live closure gates blocked**. The mandatory
Planner/Milestone/Evidence/Auditor production path has been removed. Prior Planner/Auditor G0–G6 evidence remains
historical scoped evidence, not whole-runtime closure.

The accepted root-cause design and concrete removal plan are in
[`single-action-policy-convergence.md`](single-action-policy-convergence.md). This file and that convergence contract
describe the current single-policy production path and its pending C8–C9 convergence; milestone-path sections below
are historical analysis, not a selectable path.
Chronological run evidence, superseded designs, and prior reopenings are preserved in
[`history/architecture-pre-milestone-convergence-2026-08-22.md`](history/architecture-pre-milestone-convergence-2026-08-22.md).
They do not override this document.

The target runtime is a small, continuous GUI runtime with one execution authority: optional start/revision-only
GoalCompiler, one static advisory GoalPlan, and one ActionPolicy loop. Long-horizon behavior in the baseline comes from
a bounded `AgentWorkspace` and optional exact working notes, not mandatory roadmap, milestone, Auditor, or MissionState
transitions. The current code implements change-first delivery, bounded workspace, sole whole-request admission, and
the information-increment Monitor; remaining generated diagnostics and a fresh audit still prevent verified closure.

Stages 1–6 of the C8–C9 migration are now implemented provider-free. The seven named contracts are frozen, and
`WorldTransitionProjector` is the sole producer of `PublicWorldDelta`. `StepResult`, `ActionOutcome`, evaluation
delivery, the existing `WorldDeliveryIndex`, `EpisodeMonitor`, compact continuity, and trace consume that delta object
or its exact serialization. The existing index now owns document lineage, content/structure digests, monotonic region
versions, exact current membership, and unchanged-outline reuse. Production model delivery is ordered
`LatestEffect → CurrentFindings → ChangedRegions → ActionCandidates → PageOutline → RecoveryDirectory`; local
read/search/find operations preserve the latest external GUI effect, and default production requests no longer produce
global lexical `EvidenceCandidates`. `RunState` now stores one bounded `AgentWorkspace`: the latest four committed
steps remain detailed, exact GUI results/effects/working facts/failures/recovery become bounded `SemanticEvent`s, and
ordinary read/search/find/wait/no-effect activity collapses by family. Full Trace still receives every original step.
The append-only `recent_steps`, old history renderer, history-capacity exception, RunState pre-cap, and
`fact_change_count` precision loss are removed. `RequestAdmission` is the sole complete-request capacity owner and the
provider Binder only serializes an admitted request. `EpisodeMonitor` stores only the World, CurrentFindings, and
WorkingFacts digests plus observation-only/recovery counters; query and region variation cannot disguise a
zero-information loop. Its `30/8/1` profile caps, but never raises, the prior task turn budget. Remaining C8 diagnostics
and later C9 gates stay open; this stage status does not authorize a live run.

## Current end-to-end data flow

```text
User request
→ TaskGoal
→ optional GoalCompiler once → static advisory GoalPlan
→ one continuous CoreAgentLoop
    TaskGoal + GoalPlan
    + fresh change-first WorldDeliveryView + ActionCandidates
    + bounded AgentWorkspace
    → ActionPolicy
    → exactly one typed decision or bounded set_form_fields
    → Resolver → Admission → Binder → BrowserGym Executor
    → ExecutionReceiptBatch → causal stable fresh WorldObservation
    → WorldTransitionProjector → StepResult
    → RunState.apply + total WorkspaceReducer + fixed-size EpisodeMonitor update
    → TaskEvaluator + deterministic ordinary/recovery control
→ representation-only final-response admission
→ one STOP → fresh acquire → native evaluator
→ durable case result
→ bounded cleanup and optional observability export
```

There is one BrowserGym session, one current World authority, one ActionSpace, one Binder, one executor, one
TaskEvaluator/native-verifier authority, and one mutable episode transition point. Projections are read models, not
alternative control paths.

## Causal post-action observation boundary

`WorldObservation` freshness has two independent dimensions: it must be newly acquired, and it must belong to the
stable causal post-state of the dispatched action. BrowserGym returning from a click and producing an observation does
not by itself establish the second fact. Playwright distinguishes navigation request/start, main-frame commit, and
DOMContentLoaded; actionability and action completion do not close an arbitrary delayed navigation.

The BrowserGym/Playwright owner thread therefore owns this closed transition:

```text
STABLE_NO_NAVIGATION
STABLE_NAVIGATION
NAVIGATION_PENDING
ACQUISITION_UNSTABLE
```

Before dispatch it installs main-frame navigation and document-mutation observers and records URL/document epoch.
Browser-native link and form-submit controls receive a bounded navigation-start lease. A mechanically non-navigation
control skips that lease. When navigation starts, the same step waits boundedly for main-frame commit,
DOMContentLoaded, and a short DOM-quiet predicate before a fresh `_get_obs` capture. No fixed long sleep is an
authority. `NAVIGATION_PENDING` and `ACQUISITION_UNSTABLE` carry no post observation, fail post-action acquisition, and
therefore cannot start another ActionPolicy turn.

The owner emits, and trace only forwards, `dispatch_started`, `dispatch_returned`, `navigation_started`,
`navigation_committed`, `post_capture_started`, `post_capture_completed`, before/after URL, before/after document
epoch, and stability status. Neither CoreLoop, Monitor, nor trace may reconstruct these facts from adjacent steps.

This contract follows the current Playwright navigation lifecycle and event-waiting model; Playwright explicitly
separates commit/load states and warns that time-based waits can observe stale state. BrowserGym's upstream fixed
`pre_observation_delay` remains a compatibility delay, not causal proof.

## Authority and owners

| Fact or transition | Sole owner | Non-owner rule |
|---|---|---|
| user intent | `TaskGoal` | plans may describe but never replace it |
| current GUI truth | fresh `WorldObservation` | no downstream DOM/AX re-interpretation |
| public transition between two Worlds | `WorldTransitionProjector` | ActionOutcome, Monitor, delivery, history, and trace consume one delta rather than rebuilding it |
| currently legal semantic actions | complete `ActionSpace` | rendered text and model output cannot authorize actions |
| current model delivery | `ObservationDeliveryStore` + deterministic `DeliveryPlanner` | delivery is a reversible read model and cannot alter World or ActionSpace |
| model-facing current-run continuity | total `WorkspaceReducer` producing `AgentWorkspace` | raw history, provider messages, and trace cannot become a second workspace |
| whole-request capacity | `RequestAdmission` | RunState, history projection, renderer, and provider Binder cannot own independent caps |
| model-visible action contract | `PerTurnToolCatalog` | provider wire adapters only transport it |
| private physical binding | Binder | model never submits selector, BID, or coordinates |
| physical dispatch truth | `ExecutionReceiptBatch` | projection cannot reconstruct or overwrite receipts |
| episode transition | validated `StepResult` through `RunState.apply` | history, monitor, trace, and benchmark only consume committed state |
| advisory goal decomposition | start/revision-only `GoalCompiler` | `GoalPlan` is static guidance and has no progress state |
| operational recovery | deterministic `EpisodeMonitor` + same `ActionPolicy` | monitor signals cannot claim task semantics |
| benchmark completion | native `TaskEvaluator` after one delivered STOP | policy and final response cannot self-certify |
| local trace | synchronous JSONL recorder | remote viewers are lossy and fail-open |
| benchmark result | durable result store | cleanup/export cannot erase or revise it |

## World delivery and discovery

The complete current World remains authoritative. Model delivery is a reversible, change-first projection, not
destructive memory. This replaces the prior design in which every turn rebuilt a page projection and ranked a global
pool of public scalar facts using task/plan lexical similarity.

```text
BrowserGym raw observation
→ SurfaceAdapter
→ full WorldObservation
→ lossless supported-public ActorWorldSnapshot + complete ActionSpace
→ WorldTransitionProjector(before World, after World)
→ PublicWorldDelta
→ versioned WorldDeliveryIndex
→ ObservationDeliveryStore
   - latest external GUI effect
   - current exact findings
   - current region versions
   - cached page outline
→ DeliveryPlanner
→ LatestEffect + CurrentFindings + ChangedRegions + ActionCandidates + PageOutline + RecoveryDirectory
→ DeliveryManifest
```

`PublicWorldDelta` is the one typed account of public change. It records added, removed, and modified public targets and
facts, their stable region membership, and before/after World lineage. `ActionOutcome`, `EpisodeMonitor`, model
delivery, compact continuity, and trace consume this object. They may select fields for their own views, but may not
compute competing definitions of what changed.

`RegionVersion` state upgrades the existing `WorldDeliveryIndex`; it is not a second region system. Each stable region
key has structural/content digests, a monotonically increasing version within the current document lineage, exact
target/fact membership, and public delivery cost. Unchanged regions reuse their cached outline. Changed regions alone
are rebuilt. Navigation creates a new document lineage and invalidates generation-local refs and the old region cache.

`ObservationDeliveryStore` owns the lifecycle of the latest external GUI effect. Local operations such as
`read_region`, `search_page_content`, and `find_controls` do not clear or replace it. A later external GUI effect
supersedes it; before replacement, its exact public additions/modifications are input to `WorkspaceReducer`, the sole
owner that may retain them as a bounded ref-free `SemanticEvent`. The delivery store is not a memory framework,
task-progress authority, or completion proof.

`CurrentFindings` is derived only from exact current public World values and the current delta. Result/status/table
cells, selected values, identifiers, amounts, dates, and full address strings rank ahead of generic DOM metadata;
newly added or modified values receive the highest delivery priority. Fields such as `semantic.dom.attribute.*`,
decorative class/color tokens, and generic inactive-state facts are folded by default but remain recoverable through
their region. This is a delivery ordering rule, not semantic completion logic. Source-provided structure may identify a
table cell or status; Runtime may not infer new business fields from unstructured text.

The default delivery order is fixed:

1. exact public additions/modifications caused by the latest GUI effect;
2. current exact findings, with changed values first;
3. exact contents or a bounded first page of changed regions;
4. automatically retrieved current executable candidates;
5. a cached functional PageOutline;
6. a typed directory and cursors for every folded current or changed region.

For example, after activating `Go`, the next request must put this before the ordinary page outline:

```yaml
LatestEffect:
  caused_by: activate button "Go"
  dispatch: sent
  changed_regions: [Directions]
  added_public_content:
    - "Distance: 33km. Time: 0:32."
    - "Pittsburgh International Airport, Findlay Township, Allegheny County, 15231"
```

This block preserves exact page text. Runtime does not infer that `33km` satisfies the task, split an address into
state/postcode fields, or claim completeness. Those remain ActionPolicy judgments. If a changed region exceeds its
delivery allocation, the first page plus `omitted_count` and a lossless cursor are mandatory; omission without a
recovery handle is invalid.

The default new-document view contains:

- a compact page identity and functional-region map;
- task-relevant navigation, dialog, form, result, and status structure with ancestor/label/header closure;
- automatically retrieved top-k executable candidates;
- summaries plus typed recovery handles for folded regions.

Large repeated siblings, boilerplate, duplicate parent/child text, decorative state, and inactive content are folded.
Offered targets, changed public contents, decision-relevant state, labels, table headers, dialog ownership, and recovery
handles are never silently dropped. A separately rendered full view remains a non-authoritative cost baseline, not a
fallback that may expand the executable set.

The old global `EvidenceCandidates` ranking path is absent from default production delivery. Its compatibility type is
temporarily retained for direct legacy callers and is scheduled for deletion with the remaining old delivery paths.
Task-aware ranking remains useful
for `ActionCandidates` and for ordering pages inside an already identified changed region, but it cannot decide whether
a post-action public change is visible at all.

Discovery has three distinct contracts:

| Public operation | Answers | Does not do |
|---|---|---|
| `find_controls` | which current executable controls match an intent | search readable page facts or future controls |
| `search_page_content` | which current public text/value/fact matches a query | authorize or execute GUI actions |
| `read_region` | what content/status/table is inside a known region | serve as a low-precision action registry |

The old names `find_actions`, `find_content`, and `open_region` are removed at migration completion; they are not kept
as parallel compatibility tools. Empty results return typed scope and a mechanically correct next-operation hint.

Action candidates are generated automatically after every fresh World. A model should not have to read regions merely
to discover a currently executable control. `find_controls` remains an explicit full-inventory fallback.

### Open-source reuse boundary

The target adopts three public designs without importing their competing browser and Agent authorities:

| Reference implementation | Adopted contract or algorithm | Integration boundary |
|---|---|---|
| [Agent-E Change Observation](https://github.com/EmergenceAI/Agent-E/blob/master/ae/utils/dom_mutation_observer.py) | every external action returns a first-class account of newly appearing/changing page content | its MutationObserver may be an optional non-authoritative BrowserGym settle hint; the authoritative delta is still the full before/after World diff because Agent-E's observer does not cover every style/class/visibility transition |
| [WebChallenger PageMem](https://github.com/jayoohwang1/webchallenger) | stable page sections, unchanged-section reuse, changed-section refresh, and selective exact expansion | implement on the existing `WorldDeliveryIndex`; do not import its Playwright session, Agent loop, LLM section summarizer, offline site memory, or compound-action authority |
| [agent-browser snapshot diff](https://github.com/vercel-labs/agent-browser/blob/main/cli/src/native/diff.rs) | independent added/removed/changed snapshot comparison | use as a diagnostic/conformance oracle over serialized public snapshots; its line-level diff is not the production typed World authority and its browser session is never composed |

BrowserGym remains the only capture/execution dependency. No second DOM walker, selector map, browser session, ref
registry, action registry, or Agent loop is introduced. If external source code is copied rather than reimplemented
against typed World objects, its MIT/Apache attribution and exact pinned revision must be recorded; the initial baseline
requires no vendored external runtime code.

## AgentWorkspace and request capacity

The repeated history-capacity and post-result wandering failures shared one cause: model continuity was an
append-oriented rendering of `recent_steps`, while result salience, repetition folding, request fitting, and provider
serialization were split across different owners. The production state now uses the reducer below; whole-request
fitting remains the next migration stage.

Each committed `StepResult` therefore has three independent consumers:

```text
StepResult
├── Full Trace: complete and lossless
├── WorkspaceReducer: total update of bounded model workspace
└── EpisodeMonitor: fixed-size operational-stall state
```

The model-facing contract is:

```text
fresh public World + PublicWorldDelta
→ CurrentFindings
→ WorkspaceReducer(previous workspace, committed StepResult)
→ AgentWorkspace within the allocation supplied by RequestAdmission
```

```python
@dataclass(frozen=True)
class CurrentFinding:
    evidence_ref: str
    predicate: str
    exact_value: PublicScalar
    source_context: str
    coverage: CoverageState

@dataclass(frozen=True)
class SemanticEvent:
    step_index: int
    kind: Literal[
        "gui_effect", "public_result", "working_fact", "typed_failure", "recovery"
    ]
    summary: str
    exact_public_values: tuple[PublicValue, ...]

@dataclass(frozen=True)
class ActivitySummary:
    family: Literal[
        "read_region", "search_page_content", "find_controls", "wait", "no_effect"
    ]
    world_digest: str
    attempt_count: int
    new_finding_count: int
    last_outcome: str

@dataclass(frozen=True)
class AgentWorkspace:
    recent_steps: tuple[DetailedStep, ...]       # at most four
    semantic_events: tuple[SemanticEvent, ...]  # fitted within allocation
    activities: tuple[ActivitySummary, ...]     # aggregated
    working_facts: tuple[WorkingFact, ...]
```

`CurrentFinding` accepts only values explicitly present in the public World or current public delta. A whole address
remains a whole address unless the page separately exposes structured state/postcode values. Runtime never parses or
guesses new business facts from a string. `SemanticEvent.summary` is a deterministic template over the committed
operation/effect/failure; no per-step LLM summarizer is introduced.

`WorkspaceReducer.reduce(previous, step, detailed_step, step_index, current_findings)` is a total deterministic function for every
ordinary supported step. Its rules are:

- keep the latest four steps in detailed form;
- retain an exact bounded `SemanticEvent` for a real GUI effect, newly exposed public result, working-note change,
  typed failure, or recovery transition;
- aggregate ordinary reads/searches/waits with no new finding into `ActivitySummary` instead of appending history;
- deterministically deduplicate repeated exact public values and fold older low-priority events within the supplied
  fixed workspace bounds;
- write every original step to Full Trace regardless of workspace retention.

Forty searches with no information gain therefore occupy one activity record, not forty model-history entries.
`WorkspaceReducer` does not throw an episode-history-capacity exception for ordinary growth. Allocation-aware
`WorkspaceReducer.fit()` and conversion of irreducible overflow to `context_capacity` with `provider_attempts=0` remain
owned by the next `RequestAdmission` stage.

`RequestAdmission` is the sole capacity authority:

```text
model/provider window and configured request target
→ allocate task/plan, current delivery, tools, images, recent detail, workspace
→ WorkspaceReducer.fit(workspace allocation)
→ estimate the complete request
→ admit or typed context_capacity
→ Provider Binder serializes the admitted request unchanged
```

The old independent model-history byte cap, RunState pre-validation cap, `EpisodeHistoryCapacityError`, and any provider
Binder pruning/capacity decision are removed. The provider Binder does not summarize, trim, reinterpret, or retry a
locally rejected request.

`EpisodeMonitor` holds fixed-size digests and counters rather than reading retained model history:

```text
world digest
current-findings digest
working-facts digest
observation-only stall family/count
recovery count
```

Different read/search queries or regions are still one stall family when there is no World, finding, working-fact, or
GUI-dispatch delta. The configured profile determines when feedback becomes RECOVERY and when recurrence becomes
`CONTROL_STALLED`. Monitor terminates a control loop; it does not change `TaskEvaluation` to `BLOCKED` or claim that the
user task is impossible. A recovery call receives current findings, the aggregated activity, fresh delivery, and the
same `submit_final_response` option through the same ActionPolicy.

Budget values are carried by one generic profile:

```python
@dataclass(frozen=True)
class AgentLoopProfile:
    max_policy_decisions: int
    max_consecutive_observation_only: int
    max_recoveries_per_stall: int
```

Values such as `30/8/1` are experiment-profile defaults. A larger number such as 100 may remain an abnormal global
safety ceiling, but cannot authorize dozens of zero-information reads/searches. Profile values are not site/task
branches and do not change the fixed contracts above.

## Tool and action path

Tools express stable operations; current refs express operands. Executable targets use `E*`, public scalar evidence
uses `F*`, read-only structural nodes use `N*`, and expandable regions use `R*`. Generation-local refs are valid only
for the current context and are removed before any StepResult is retained in AgentWorkspace.

```text
Semantic Capability Registry
→ BrowserGym InteractionProfile with complete translator/executor support
→ complete current ActionSpace
→ ActionCandidate retrieval/paging
→ stable PerTurnToolCatalog
→ provider-native tool call
→ catalog-aware representation normalization
→ Resolver / Admission / Binder / Executor
```

The provider layer may normalize wire representation and validate Pydantic models. It cannot repair an invalid target
by choosing a different semantic target or operation. A representation violation receives at most one same-turn,
schema-only repair; a repeated violation becomes a typed policy failure and never creates a GUI step.

`set_form_fields` is one optional compound semantic action for two to four already visible, independent form fields.
The Binder resolves every field against the same current catalog, the executor dispatches in order, and the receipt
batch retains complete/partial/unknown truth. It never includes submit, navigation, menu exploration, or arbitrary
multi-tool execution. Those remain explicit policy decisions.

## Superseded milestone planning

### Reopening causal model

The repeated Planner/Auditor reopenings shared one cause: model roles were constrained and scheduled through semantic
guessing in the Runtime instead of closed typed boundaries. Planner authority was policed by free-text keywords, while
Auditor routing collapsed mechanically incomplete evidence and genuinely semantic uncertainty into the same
`UNKNOWN`. This produced both false Planner rejection (for example, business uses of “coordinates” or “selector”)
and near-unconditional Auditor cost.

The defects are classified as follows:

| Class | Shared mechanism | Converged owner change |
|---|---|---|
| architecture | semantic and mechanical uncertainty shared one route | `EvidenceBoundary` owns a closed admission route algebra |
| contract ambiguity | Planner text was treated as latent GUI authority | Pydantic schema is the complete authority boundary; text remains advisory |
| duplicated truth | Auditor failure could terminate despite retained World/WorkingFacts | Supervisor retains the same milestone and pending facts without writing MissionState |
| verification | example keyword tests and “Auditor called on UNKNOWN” tests preserved the defect | vocabulary generation, state-machine route, call-frequency, and exceptional-path properties |
| diagnostics/governance | schema failure erased field-level cause; old passing gates remained displayed | bounded field-path/code diagnostics and reopened gate attestation |

This is not an event-sourcing or workflow-platform change. It closes only the Planner schema/frequency and milestone
admission/Auditor contract within the existing Supervisor and single CoreAgentLoop.

Historical migration impact was bounded; current cases use `target-loop-case.v11`. Pre-mission v6-v9 cases remain
accepted by the legacy decoder. Mission-shaped v10 JSON is retained only as raw archival evidence and is intentionally
not accepted by the exact-field decoder; “read-only” does not mean schema-compatible. Production exposes no aliases
that can recreate the removed control outcomes.

### Contract

The old public `Manager → execute_subtask` assignment model is superseded. `MilestonePlanner` proposes a bounded
outcome roadmap:

```text
MilestoneRoadmap
  version
  milestones: 1..5 Milestone

Milestone
  id
  outcome                 # one user-relevant result
  done_when               # one fresh observable state or evidence packet
  required_evidence       # business evidence requirements, not GUI refs
  depends_on              # milestone ids only
  final                    # at most one
```

The roadmap Pydantic schema is strict, frozen, and `extra="forbid"`. Its six milestone fields are the complete supported
algebra, so `tool`, `action`, `selector`, `target_ref`, `coordinates`, `field_commands`, episode budgets, mutable
completion, and any unknown field fail structurally. Free text is checked only for type and length. Natural-language
business concepts such as geographic coordinates, product selectors, selected values, and click-through rates are
valid and have no execution authority. `MissionState` is the completion authority. The Supervisor mechanically
selects a milestone whose dependencies have accepted outcomes.

One milestone may require many tightly coupled GUI actions. Opening menus, navigating pages, filling fields, reading
results, and pinning facts normally stay in the same continuous episode. A milestone ends only when its declared
outcome is observable, a typed strategic failure requires replanning, the user is required, or the Runtime hard cap is
reached.

Planner calls are allowed only:

1. `START` at long-task start;
2. `NEEDS_REPLAN` after a typed strategic infeasibility;
3. `ROADMAP_EXHAUSTED_NOT_FINALIZABLE` when no dependency-ready unresolved milestone remains and final response is not
   yet possible.

An admitted milestone with another ready milestone never invokes Planner. A revised version must increase; every
milestone already accepted by `MissionState` must remain byte-for-byte equal, while only the unresolved tail may be
replaced. Runtime performs no natural-language “materially different” comparison.

Ordinary state changes, reads, searches, action paging, first stalls, and fact pins do not call the Planner.

### Planner visibility

The Planner sees `TaskGoal`, accepted `MissionState`, current/remaining roadmap, last typed milestone result or failure,
remaining mission budget, and an optional bounded ref-free functional-region summary. It does not see screenshots,
the full World, ActionSpace, ToolCatalog, E/N/F/R refs, selectors, provider reasoning, or executor trajectory.

The functional-region summary prevents planning from an empty generic capability list, but remains non-authoritative:

```yaml
- label: Directions
  purpose: route planning form
  control_families: [text_input, submit]
  coverage: complete
```

It does not claim that an open-world deliverable is reachable. Actual feasibility is discovered by ActionPolicy, which
may return typed `needs_replan(delivery_not_observable|subtask_task_mismatch|capability_unavailable)`.

### Example granularity

For a filtered report retrieval, the milestone is the visible filtered result and requested row—not separate
assignments for opening Reports, selecting a report, filling dates, submitting, and reading.

For a multi-airport distance task:

```text
M1 obtain an evidence-backed candidate-airport set
M2 obtain one complete route packet for one unverified candidate (repeatable)
M3 establish candidate coverage and retain candidates satisfying the distance condition
M4 produce the requested final list from accepted evidence
```

Within one M2 episode the policy may open Directions, call one `set_form_fields(From, To)`, submit, read distance and
address fields, pin exact evidence, and yield the milestone. Planner invocation between those steps is prohibited.

## Superseded episode/milestone state path

Three stores remain separate:

| Store | Scope | Contents | Writer |
|---|---|---|---|
| Full Trace | case | complete inputs, outputs, receipts, failures, lineage | trace recorder |
| Episode Context | current episode | older compact steps, latest four detailed steps, working facts, fresh World | Runtime projections |
| MissionState | cross-episode | admitted outcomes, carry facts, failed strategies, last milestone result | evidence boundary |

`CompactStep` is a deterministic projection of `StepResult`; it contains semantic action, target semantics, public
arguments, dispatch/effect, public deltas, progress deltas, and typed failure. It excludes local refs, BIDs, selectors,
coordinates, screenshots, reasoning, and provider transcripts. The latest four turns remain detailed; older steps are
compact and deterministically fold exact repetition when byte limits require it.

`pin_fact(key, evidence_ref, purpose)` is an episode-local evidence bookmark. The model cannot submit a value. Runtime
resolves the current public scalar `F-ref`, stores its lineage, and exposes the resulting `WorkingFact`. State-changing
milestones do not require pins unless an exact value is needed later. Evidence-packet milestones may require named
facts before `yield_milestone(outcome_proposed)` is admitted. Natural-language answers may be returned directly when
the current evidence packet is complete; pinning is not a universal prerequisite for final response.

Only `EvidenceBoundary.accept` may promote a working fact or outcome into `MissionState`. Its pre-Auditor route algebra
is closed and ordered:

| Deterministic result | Supervisor route | Auditor |
|---|---|---|
| required evidence missing, non-public/non-scalar, or invalid lineage | same milestone with bounded evidence guidance | never |
| final milestone and task-global formal evaluation is COMPLETE | construct a proved proposal for boundary admission | never |
| final milestone, evaluation is INCOMPLETE, and an explicit criterion is UNSATISFIED | same milestone with typed unsatisfied guidance | never |
| no public semantic change and no newly retained evidence | same milestone with `outcome_unproven` | never |
| evidence shape/currentness/lineage complete, but business meaning unresolved | `SEMANTIC_AUDIT` | once |

Task-global evaluation is never projected onto a non-final milestone. `BLOCKED` remains a terminal TaskEvaluator result
owned by Supervisor rather than a recoverable milestone assessment. Within the final milestone, formal evaluation
precedes the no-change test because it is authoritative even when the public semantic digest is stable.

The Auditor receives only a bounded TaskGoal projection, current Milestone, pre-milestone MissionState, fresh public
evidence packet, WorkingFacts, before/after public outcome summary, and yield reason. It receives no World object,
screenshot, full trajectory, ActionSpace, ToolCatalog, model reasoning, provider transcript, expected answer, or
reward. Its result is only `satisfied|unsatisfied|unknown`, cited evidence refs, missing evidence keys, and bounded
guidance. It cannot mutate state, plan, act, or certify official success.

`unsatisfied`/`unknown` retain the current World and pending WorkingFacts, do not write MissionState, and project
guidance back into the same ActionPolicy milestone. Exhausted Auditor transport/schema repair returns typed
`AUDIT_UNAVAILABLE` with those GUI results intact and performs no GUI replay. Planner is invoked only if ActionPolicy
later emits typed `needs_replan`. There is no separate post-roadmap or post-response “Final Auditor” stage; an ordinary
semantic audit may still resolve a genuinely unknown final milestone before `FinalResponse` is proposed.

WorkingFact keys may alias the same exact EvidenceRecord. One canonical evidence ref may not identify conflicting
observation versions in a single working set: the second pin is rejected as typed invalid arguments before RunState or
EvidenceBundle admission, while the Bundle independently fails closed if a producer bypasses that invariant.

## Progress, recovery, and budgets

`EpisodeMonitor` is deterministic and owns a current-run route trail independent of model-facing history. Every
committed GUI or local-tool step contributes a sample; provider representation failures remain at the provider
boundary and do not become monitor-visible GUI steps.

Progress distinguishes authoritative/structural result change from focus, hover, cursor, appearance, or screenshot-only
change. Route regression compares page identity, current findings, newly visible public result evidence, and working
facts. The first repeated route without new evidence produces RECOVER; recurrence after recovery produces the typed
control termination `CONTROL_STALLED`. Task evaluation remains `INCOMPLETE|UNKNOWN`; Monitor does not claim that the
task is semantically blocked. A useful unremembered public result prevents a false no-progress decision.

Machine repeat prevention uses one shared typed `AttemptSignature`; human recovery text is a separate field. Resolver
or Admission produces typed operation/target rejection, Monitor accumulates it, and CoreLoop compares the same
signature helper before dispatch.

Runtime owns bounded execution budgets:

- one `AgentLoopProfile` with maximum policy decisions, maximum consecutive observation-only activity, and maximum
  recoveries per stall;
- one bounded hard ActionPolicy safety cap;
- a compound form action counts as one policy decision and multiple conserved dispatch receipts;
- recovery does not automatically expand the cap;
- model output cannot submit or rewrite the cap.

The hard cap is a safety boundary, not a second planning authority.

## Provider, schema, and reasoning boundary

PydanticAI owns supported provider message/tool transport and Pydantic validation. The current ToolCatalog closes the
available output schemas. One parseable invalid call admits at most one same-turn representation-pruning repair that
may delete invalid fields but cannot add or change any effect-bearing leaf. A multiple-call envelope may repair only
to one exactly unchanged parseable member of the rejected set. Zero-call and wholly unparseable envelopes fail typed without
repair because no semantic identity exists to preserve. Unsupported or still-invalid output becomes a typed policy
failure.

Role reasoning is explicit rather than globally disabled:

- ordinary ActionPolicy: low/off extended thinking with a small tool-call output budget;
- genuine ambiguity or typed recovery: one bounded deliberate policy call;
- representation repair: thinking off and narrow output;
- mechanical boundaries: no model call.

Provider transport retry remains separate from semantic policy calls and never replays GUI effects. Every physical
attempt records its actual reasoning mode, output limit, origin, duration, phase, and typed result. Exhausted repair
exposes bounded field-path/code diagnostics; raw rejected values are not copied into public diagnostics.

Exception classification is closed at the provider boundary:

| Owner failure | Public policy failure |
|---|---|
| `GroundedToolResolutionError` | `invalid_tool_arguments` |
| `ModelRequestCapacityError` / RequestAdmission rejection | `context_capacity` |
| provider transport failure | `provider_unavailable` |
| unexpected Runtime failure | `internal_error` |

A broad `except (ValueError, TypeError) -> invalid_tool_arguments` mapping is unsupported because it hides workspace,
serialization, and internal defects as model mistakes.

### Current SOTA alignment (reviewed 2026-08-22)

- [Playwright navigation lifecycle](https://playwright.dev/python/docs/navigations) and
  [Page API](https://playwright.dev/python/docs/api/class-page) distinguish navigation start, commit,
  DOMContentLoaded, and later load states, and provide event/predicate waits around actions. This is the direct
  execution-boundary reference for causal post-action capture; Playwright actionability alone does not certify an
  arbitrary timer-delayed navigation.
- [Playwright library guidance](https://playwright.dev/python/docs/library) warns that time-based sleeps can leave code
  observing outdated state. The Runtime therefore uses bounded navigation events and DOM-quiet predicates rather than
  a fixed long sleep.
- [BrowserGym's current environment implementation](https://github.com/ServiceNow/BrowserGym/blob/main/browsergym/core/src/browsergym/core/env.py)
  applies `pre_observation_delay` before extracting an observation. That is useful compatibility pacing but, by
  inference, cannot identify which dispatch owns a later navigation and is not accepted as causal proof here.
- [WorkArena / BrowserGym (ICML 2024)](https://proceedings.mlr.press/v235/drouin24a.html) evaluates realistic knowledge
  work through rich actions and multimodal observations, supporting validation on actual browser tasks rather than
  planner-shaped fixtures.
- [WebArena (ICLR 2024)](https://openreview.net/forum?id=Jjn5IFp3qP) evaluates functional correctness of resulting site
  state and permits multiple valid action paths. This supports keeping native evaluation authoritative and forbids
  Auditor/Planner claims or reference action sequences from becoming completion truth.
- [Agent-E](https://arxiv.org/abs/2407.13032) makes action-caused DOM changes first-class model feedback. Its released
  observer is a useful change-notification reference but is not complete enough to replace typed before/after World
  comparison.
- [WebChallenger](https://arxiv.org/abs/2606.10423) uses stable page sections, cached summaries, and changed-section
  refresh. The target adopts this incremental-delivery shape on the existing RegionIndex without its separate
  Playwright/Agent/memory stack or additional per-step summarizer calls.
- [agent-browser diffing](https://agent-browser.dev/diffing) provides compact structural snapshot comparisons. It is
  used as an independent diagnostic reference rather than a second browser or production World authority.

## Results, persistence, cleanup, and observability

Task completion does not require an LLM Finalizer. `submit_final_response` may optionally cite current or explicitly
remembered public evidence refs; the mechanical final-response boundary validates lineage and output shape without
claiming semantic completeness. Public output schemas use one finite
closed subset (`type`, object properties/required/additionalProperties, arrays/items/bounds, scalar constraints, and
bounded `oneOf`/`anyOf`); unknown keywords or malformed combinations fail closed before value validation. Core sends
STOP once, acquires one post-STOP World, invokes the native evaluator once, and does not resume ActionPolicy afterward.
`SENT_UNKNOWN` is evaluated from the acquired post-state without replaying STOP. `NOT_SENT` admits neither a
post-STOP capture nor native evaluation, even if an inconsistent adapter returns an acquisition. Standalone atomic
tasks may still terminate directly from their native evaluator; the STOP gate is the mission benchmark protocol.

The preliminary case result is durably committed before cleanup or remote export. The supported order is:

```text
case body terminal outcome
→ local trace flush
→ fsync temp result + atomic replace + parent-directory fsync
→ durable case-result acknowledgement
→ bounded environment cleanup
→ bounded viewer/export close
→ optional report materialization from durable store
```

Persistence failure becomes typed `HARNESS_PERSISTENCE`; display text is not sufficient. Environment cleanup has a
deadline, and already-closed conditions such as Playwright `TargetClosedError` are idempotent cleanup success. Other
cleanup failures are secondary harness facts and cannot replace a previously durable task outcome.

Langfuse is a viewer, not part of the control path. Local JSONL is synchronous and authoritative. Remote projection is
bounded before `put_nowait` to an isolated child process. Queue full/closed/broken, child death/hang, network failure,
flush, close, and repeated close are total fail-open conditions. No Langfuse future, socket, or shutdown may block the
Supervisor or result commit.

## Superseded mission-path implementation inventory

The provider-free implementation of the mission path was completed before the single-ActionPolicy redesign reopened
the architecture. This map records the contracts C1–C6 removed or replaced; none is a current production owner:

| Superseded contract | Historical owner and contract |
|---|---|
| Manager page/control assignment | `MilestonePlanner` proposes one bounded `MilestoneRoadmap` |
| mutable subtask status | admitted `MissionState` outcomes; roadmap remains advisory |
| `entry_scope_key` execution authority | ref-free `FunctionalRegionSummary`, used only as Planner situation context |
| eight-turn page cutover | one continuous milestone episode with Runtime-owned hard cap 15 |
| `yield_subtask` | typed `yield_milestone(outcome_proposed|needs_replan)` |
| `find_actions` / `find_content` / `open_region` | `find_controls` / `search_page_content` / `read_region` |
| compact-JSON product bridge | provider-native `ToolCall` through the single catalog/resolver path |
| Planner/Manager state-change review | deterministic evidence admission, with Auditor only for `UNKNOWN` |
| LLM finalization review | mechanical response admission, one STOP, one post-world acquire, one native evaluation |

Lifecycle isolation, durable-result ordering, bounded cleanup, side-effect-free role retry, automatic candidates,
typed route recovery, and compound receipt conservation remain on their existing owners. No compatibility alias or
fallback production path is retained. Live capability evidence remains a separate, explicitly authorized benchmark
stage and is not implied by provider-free implementation completion.

## Non-goals

- no second GUI loop, Binder, browser session, evaluator, DOM walker, selector map, or action registry;
- no per-step Manager, Auditor, summarizer, reflection agent, embedding retrieval, or vector database;
- no benchmark-case, site-label, fixed-ref, selector, or expected-answer specialization;
- no attempt to prove an open-world objective is reachable from a functional-region summary;
- no long-term cross-case recall during W1b/W2;
- no production-grade workflow platform, event-sourcing system, or generalized ledger.

## Superseded mission-path closure criteria (historical)

The milestone architecture is no longer a closure target. The following criteria are retained as historical evidence
and regression input; active closure is defined by C0–C9 in the linked convergence document, including change-first
delivery and bounded workspace convergence:

1. production search finds no old assignment contract or compatibility alias;
2. provider-free replay proves successful continuous routes are not split at ordinary page/state changes;
3. state-machine/property tests cover every decision, receipt, yield, cancellation, retry, partial, persistence, and
   projection boundary;
4. held-out route regression and form workflows pass without site-specific branches;
5. six real-page World/Action/Evidence recoverability gates pass;
6. full tests, lint, diff check, docs, and durable evidence agree;
7. an independent fresh-context architecture review passes;
8. a later explicit live W1b witness improves or preserves success and cost without reopening the same authority gap.

The reopened BrowserGym transition additionally requires a generic delayed-link witness, typed navigation timeout,
typed acquisition-instability witness, a non-navigation fast-path bound, trace-order assertions, and proof that no
next policy decision is admitted before stable capture. Task-7 replay is not closure evidence and remains blocked until
those properties, the full provider-free suite, docs, and a fresh-context review agree.
