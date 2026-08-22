# Architecture

## Status

Current status: **Planner/Auditor provider-free convergence verified / G0–G6 passed / live benchmark requires separate
authorization**.

This file is the sole normative architecture contract. Chronological run evidence, superseded designs, and prior
reopenings are preserved in
[`history/architecture-pre-milestone-convergence-2026-08-22.md`](history/architecture-pre-milestone-convergence-2026-08-22.md).
They do not override this document.

The convergence goal is a small, continuous GUI runtime with one execution authority. Long-horizon support adds a
low-frequency outcome roadmap and verified cross-milestone state; it does not turn ordinary page transitions into
Manager assignments.

## End-to-end data flow

```text
User request
→ TaskGoal
→ [short task] optional GoalCompiler → advisory GoalPlan
  [long task]  MilestonePlanner → advisory MilestoneRoadmap
→ Supervisor selects one dependency-ready outcome milestone
→ one continuous CoreAgentLoop episode
    TaskGoal + current milestone + selected accepted facts
    + fresh WorldDeliveryView + ActionCandidates + EvidenceCandidates
    + episode working facts + compact history
    → ActionPolicy
    → one semantic decision or bounded set_form_fields
    → Resolver → Admission → Binder → BrowserGym Executor
    → ExecutionReceiptBatch → fresh WorldObservation
    → StepResult → RunState.apply
→ observable milestone outcome | typed needs_replan | hard cap | terminal failure
→ deterministic evidence admission
→ continue same milestone | admit formal result | optional Auditor only for semantic UNKNOWN
→ MissionState
→ mechanically select the next dependency-ready milestone
→ MilestonePlanner only at START, typed NEEDS_REPLAN, or ROADMAP_EXHAUSTED_NOT_FINALIZABLE
→ mechanical final-response admission
→ one STOP → fresh acquire → native evaluator
→ durable case result
→ bounded cleanup and optional observability export
```

There is one BrowserGym session, one current World authority, one ActionSpace, one Binder, one executor, one
TaskEvaluator/native-verifier authority, and one mutable episode transition point. Projections are read models, not
alternative control paths.

## Authority and owners

| Fact or transition | Sole owner | Non-owner rule |
|---|---|---|
| user intent | `TaskGoal` | plans may describe but never replace it |
| current GUI truth | fresh `WorldObservation` | no downstream DOM/AX re-interpretation |
| currently legal semantic actions | complete `ActionSpace` | rendered text and model output cannot authorize actions |
| model-visible action contract | `PerTurnToolCatalog` | provider wire adapters only transport it |
| private physical binding | Binder | model never submits selector, BID, or coordinates |
| physical dispatch truth | `ExecutionReceiptBatch` | projection cannot reconstruct or overwrite receipts |
| episode transition | validated `StepResult` through `RunState.apply` | history, monitor, trace, and benchmark only consume committed state |
| milestone proposal | `MilestonePlanner` plus schema admission | advisory outcome description only |
| verified cross-milestone state | `MissionState` through evidence admission | planner/executor claims cannot write it directly |
| mission benchmark completion | native `TaskEvaluator` after one delivered STOP | planner, policy, auditor, and final response cannot self-certify |
| local trace | synchronous JSONL recorder | remote viewers are lossy and fail-open |
| benchmark result | durable result store | cleanup/export cannot erase or revise it |

## World delivery and discovery

The complete current World remains authoritative. Model delivery is a reversible projection, not destructive memory:

```text
BrowserGym raw observation
→ SurfaceAdapter
→ full WorldObservation
→ lossless supported-public ActorWorldSnapshot + complete ActionSpace
→ WorldDeliveryIndex
→ PageMap + ActiveView/SearchResults + DeliveryManifest
→ ActionCandidates and EvidenceCandidates
```

The default first view contains:

- a compact page identity and functional-region map;
- task-relevant navigation, dialog, form, result, and status structure with ancestor/label/header closure;
- automatically retrieved top-k executable candidates;
- newly exposed exact result facts and state evidence;
- summaries plus typed recovery handles for folded regions.

Large repeated siblings, boilerplate, duplicate parent/child text, decorative state, and inactive content are folded.
Offered targets, decision-relevant state, labels, table headers, dialog ownership, and exact evidence required by the
current milestone are never silently dropped. The PageMap remains the scoped delivery contract; a separately rendered
full view is a non-authoritative cost baseline, not a fallback that may expand the executable set or remove recovery
handles. Acceptance requires the compact view to beat that baseline while its manifest proves recoverability.

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

## Tool and action path

Tools express stable operations; current refs express operands. Executable targets use `E*`, public scalar evidence
uses `F*`, read-only structural nodes use `N*`, and expandable regions use `R*`. Generation-local refs are valid only
for the current context and are removed from compact history.

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
by choosing a different semantic target or operation. Grounding rejection returns typed feedback to the normal policy
loop.

`set_form_fields` is one optional compound semantic action for two to four already visible, independent form fields.
The Binder resolves every field against the same current catalog, the executor dispatches in order, and the receipt
batch retains complete/partial/unknown truth. It never includes submit, navigation, menu exploration, or arbitrary
multi-tool execution. Those remain explicit policy decisions.

## Milestone planning

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

Migration impact is bounded: new cases use `target-loop-case.v10` because the four former terminal Auditor failure
labels collapse to `audit_unavailable`. Older evidence remains historical/read-only; production does not expose aliases
that could recreate the removed control outcomes. No benchmark task data or MissionState migration is required.

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

## Episode context, working facts, and mission state

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

`EpisodeMonitor` is deterministic and owns an episode-local route trail independent of model-facing history. Every
committed step contributes a sample, including local reads/searches, protocol rejection, and no-dispatch outcomes.

Progress distinguishes authoritative/structural result change from focus, hover, cursor, appearance, or screenshot-only
change. Route regression compares page identity, formal task progress, newly visible public result evidence, and working
facts. The first repeated route without new evidence produces RECOVER; the repeated cycle produces YIELD. A useful
unpinned public result prevents a false no-progress decision.

Machine repeat prevention uses one shared typed `AttemptSignature`; human recovery text is a separate field. Resolver
or Admission produces typed operation/target rejection, Monitor accumulates it, and CoreLoop compares the same
signature helper before dispatch.

Runtime owns budgets:

- ordinary long-horizon episode target: enough turns to finish one milestone;
- hard episode cap: 15 ActionPolicy turns;
- a compound form action counts as one policy decision and multiple conserved dispatch receipts;
- recovery does not automatically expand the cap;
- Planner cannot submit or rewrite the cap.

The hard cap is a safety boundary, not a reason to split coherent work into eight-turn assignments.

## Provider, schema, and reasoning boundary

PydanticAI owns supported provider message/tool transport and Pydantic validation. A mature local JSON parser/repair
may repair only representation defects such as fences, brackets, commas, and quoting. Semantic repair is a single
bounded model call. Unsupported or still-invalid output becomes a typed role failure.

Role reasoning is explicit rather than globally disabled:

- ordinary ActionPolicy: low/off extended thinking with a small tool-call output budget;
- genuine ambiguity or typed recovery: one bounded deliberate policy call;
- MilestonePlanner: low-frequency deliberate reasoning, with structured answer budget protected from reasoning where
  the provider shares one token pool;
- syntactic/schema repair: thinking off and narrow output;
- mechanical boundaries: no model call.

Read-only Planner and Auditor transport failures receive one bounded retry with no GUI replay. Every physical attempt
records its actual reasoning mode, output limit, origin, duration, and typed result. Exhausted schema repair exposes at
most four `{field_path, code, attempt, phase}` diagnostics; raw rejected values are not copied into public diagnostics.

### Current SOTA alignment (reviewed 2026-08-22)

- [Plan-and-Act (ICML 2025)](https://proceedings.mlr.press/v267/erdogan25a.html) separates a structured high-level
  Planner from an environment-specific Executor. This supports keeping roadmap outcomes separate from continuous GUI
  action selection. Its dynamic replanning after HTML changes is a research design, not a production assurance
  requirement; the project’s lower-frequency trigger set is an engineering inference chosen to preserve one action
  authority and reduce provider cost.
- [WorkArena / BrowserGym (ICML 2024)](https://proceedings.mlr.press/v235/drouin24a.html) evaluates realistic knowledge
  work through rich actions and multimodal observations, supporting validation on actual browser tasks rather than
  planner-shaped fixtures.
- [WebArena (ICLR 2024)](https://openreview.net/forum?id=Jjn5IFp3qP) evaluates functional correctness of resulting site
  state and permits multiple valid action paths. This supports keeping native evaluation authoritative and forbids
  Auditor/Planner claims or reference action sequences from becoming completion truth.

## Results, persistence, cleanup, and observability

Task completion does not require an LLM Finalizer. When admitted public evidence supports the requested answer, a
`FinalResponse` cites current public evidence refs; the Resolver privately maps them to canonical evidence and the
mechanical final-response boundary validates current lineage and output shape. Public output schemas use one finite
closed subset (`type`, object properties/required/additionalProperties, arrays/items/bounds, scalar constraints, and
bounded `oneOf`/`anyOf`); unknown keywords or malformed combinations fail closed before value validation. Core yields this proposal without
writing `DONE`, then Supervisor sends STOP once, acquires one post-STOP World, and invokes the native evaluator once.
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

## Implementation migration

The provider-free implementation migration is complete. The active contract map is:

| Superseded contract | Current owner and contract |
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

## Closure criteria

Implementation is not closure. The milestone architecture can close only when:

1. production search finds no old assignment contract or compatibility alias;
2. provider-free replay proves successful continuous routes are not split at ordinary page/state changes;
3. state-machine/property tests cover every decision, receipt, yield, cancellation, retry, partial, persistence, and
   projection boundary;
4. held-out route regression and form workflows pass without site-specific branches;
5. six real-page World/Action/Evidence recoverability gates pass;
6. full tests, lint, diff check, docs, and durable evidence agree;
7. an independent fresh-context architecture review passes;
8. a later explicit live W1b witness improves or preserves success and cost without reopening the same authority gap.
