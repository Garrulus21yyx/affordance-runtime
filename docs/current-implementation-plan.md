# Current Implementation Plan

Derived status summary (`implementation-status.md` remains authoritative): the
controlled harness components through M8.6 exist,
but only the scoped internal governance gate is closed. The 2026-07-24 closure
audit reopened G2.5 budget/evidence semantics, G3 owning-port recovery effects,
G5 empirical profile evidence, and responsibility containment. The scoped
G2.5/G3/first-containment slices and fresh four-profile rollout pass for
immutable implementation revision `c939051`. The strict M8.2B diagnostic has
since completed at 24/60 and is not promotable; historical scores remain
unpromoted. See
[Implementation Status and Forward Gates](implementation-status.md),
[Horizontal Architecture Governance Track](architecture-governance-track.md),
[Responsibility Containment Boundary](responsibility-containment-boundary.md),
[Benchmark Governance and Anti-Specialization Boundary](benchmark-governance-boundary.md),
[Active Perception and Online Recovery Architecture](active-perception-and-online-recovery.md),
the [M8.6 Closure Audit](current-closure-audit-20260724.md), and the
[Current Governance Critical Audit](current-governance-critical-audit-20260725.md).
The intake remediation is governed by
[Intent Schema and Obligation Authority Governance](intent-schema-authority-governance-20260726.md).

Runtime-first R1-R8 remains valid component and containment evidence.
TaskPlanFlow/TaskPlanLifecycle, PerceptionSession, ContractExecutionLoop, RecoveryHandler,
PlannerContextBuilder, and BrowserGym adapter splits are retained. They do not
prove that the default planner is strict-generalist or that all pre-contract
failures enter Recovery Cascade.

The historical R9 and post-R9 slices below are preserved as diagnosis and
revision evidence only. Their task-family repair instructions are superseded by
M8.6 and must not authorize additional default semantic compilers. M9 remains
conditional on measured restart/waiting evidence; production-scale options
remain non-blocking.

Governance interpretation: M8.6 is complete only as the scoped internal
budget/evidence/injectable-dispatch/G5 gate. Normal BrowserGym and
`GeneralistTaskPipeline` entrypoints now configure concrete planner-context and
planner-schema owners, and configured multi-profile paths retain provider
switching. This is component/integration evidence, not level-4 empirical
recovery effectiveness. It does not claim that every entrypoint has every
recovery owner, that the strict planner is robust, or that Coordinator
responsibility reduction has reached its stated target.

The horizontal architecture-governance track is active immediately and applies
as a synchronous admission gate to every step below. It is not another
milestone in the sequence: existing architecture debt does not block unrelated
work, while a proposed change that grows a frozen control surface, introduces a
reverse dependency, or duplicates authority fails admission. Named debt is
reduced incrementally when the active feature/correctness slice touches it.

## Active Double-track Queue

The current scheduler allows one active vertical slice and one active
horizontal slice. Both pass the same architecture change-admission gate and
each has one production writer. Read-only investigation and final diff review
may be delegated, but interface decisions and final acceptance remain with the
integrator.

| Lane | Current slice | Entry condition | Exit condition | Not a prerequisite for |
| --- | --- | --- | --- | --- |
| Vertical | V-PRB-5A clean PR breadth rerun | SG7 targeted `text-transform` / `enter-date` confirmation passed cleanly at `3d44a9d`; after V-PRB-2, PR breadth at `c24b277` remains 12/12 observed, 8/12 passed, 4/12 failed, 0 provider failure, with invalid provider graph closed and remaining official failures now in downstream planning/admission; V-PRB-5A is implemented locally as a compiler-local requested-effect sequence repair; remote CI is disabled for this iteration | same 6-task x 2-seed PR breadth matrix rerun on the clean V-PRB-5A commit; classify impact before selecting V-PRB-5B, V-PRB-6, H2, fresh diagnostic, or promotion | unrelated horizontal debt retirement and immutable Planner input |
| Horizontal | introduce immutable Planner input | active-subgoal read/activation split is locally closed; mutable Planner `StateKernel` boundary remains baselined | standard Planner contract no longer receives mutable `StateKernel`; planner context derives from frozen request/view data | SG7 unless SG7 would expand or depend on that debt |

Promotion remains held until the relevant vertical evidence is bound to the
same committed revision and the required validation channel is available. When
remote CI is enabled, that means remote-green required checks; when remote CI
is intentionally disabled, local equivalent gates may support development
continuation but cannot be promoted as remote-green evidence. “When authorized”
means the named entry conditions above are satisfied and no safety, authority,
architecture, or validation gate is being bypassed; it does not mean waiting
for a repository-wide refactor.

### Review-driven remediation sequence

The latest architecture review is incorporated as an ordered, non-monolithic
sequence. These items are not retroactively marked complete and must not be
batched into a single mixed patch:

0. **P0 governance and validation baseline** — keep current revision identity
   split between current HEAD, latest production repair, latest PR-breadth
   evidence, and the last full local-equivalent gate. New authority-free
   collaborators must enter the executable manifest in the same change. Remote
   CI is disabled for this iteration, so local equivalent gates support
   development but not remote-green or promotion claims.
1. **V-PRB-5A button-sequence effect semantics** — implemented locally as a
   compiler-local requested-effect sequence repair after a non-BrowserGym RED
   test. Flat default behavior remains unchanged; multi-stage requested-effect
   fallback now explicitly preserves intermediate/final terminal boundaries and
   sequential dependency. Do not judge impact until the same clean PR breadth
   matrix is rerun.
2. **V-PRB-5B entry action-family resolution** — keep this as a separate child
   slice for slider-like reversible-write action-family selection. Execute it
   after 5A, or earlier only if 5A RED proves a public semantic/schema ADR is
   required before implementation.
3. **V-PRB-6 terminal completion guard classification** — track
   `enter-text:seed-1` separately because BrowserGym official reward is 1.0
   while Runtime still records a terminal guard. External reward is not Runtime
   completion authority.
4. **H2 immutable Planner input** — after the current vertical evidence is
   frozen, or earlier only if 5A/5B evidence proves mutable `StateKernel` input
   is the root cause, introduce frozen `PlannerStateView` / `PlanningRequest`
   so the standard Planner contract no longer receives mutable `StateKernel`.
5. **P2 semantic fallback owner extraction** — continue extracting the
   remaining SG7-triggered exact-value, page-observed-text, and terminal-submit
   fallbacks out of `GeneralistLMPlanner`; V-PRB-3's
   `semantic_action_resolver.py` is only one extracted cluster and still has
   deep-immutability/input-typing debt.
6. **P3 intent semantic normalizer** — isolate source-bound value-entry lexical
   normalization from `LLMIntentCompiler`; the normalizer may propose typed
   semantics but may not create READY authority or bypass canonical graph
   construction.
7. **Fresh diagnostic / promotion decision** — only after PR breadth reaches
   its defined acceptance with all guard observations classified, run a
   current-revision fresh diagnostic. Keep `official_score_claimed=false`
   unless promotion is explicitly authorized.

P4 is currently negative: protected cross-family / PR breadth failed at
`d66760f` with 12/12 observed, 0/12 passed, and no provider/runtime
provisioning failure. The next vertical action is not PR/nightly/release
promotion; it is root-owner classification and a bounded generic INTENT /
PLANNING repair candidate, with the single CONTRACT / FIELD_BINDING
`schema_incompatible` case tracked separately. The task packet is
`docs/change-admission/v-pr-breadth-intent-planning-repair.yaml`.

The umbrella packet is diagnostic only and may not become a production patch.
V-PRB-0 failure-attribution fidelity is complete: 12/12 episodes now have an
exact mechanism owner in
`docs/evidence/runs/m8.2a-pr-breadth-d66760f/episode-attribution.yaml`.
The resulting child lanes are:

1. **V-PRB-1 invalid coverage audit handling** — `click-dialog:seed-0` and
   `enter-text:seed-0`; candidate owner is the coverage audit validator.
2. **V-PRB-2 provider graph proposal normalization** —
   `click-button-sequence` and `form-sequence`; candidate owner is the
   source-bound multi-effect proposal normalizer/canonical compiler boundary.
3. **V-PRB-3 typed semantic action constraints** — `choose-list`,
   `click-button`, `click-dialog`, and `enter-text` clarification cases;
   candidate owner is a semantic action resolver, not new task-name fallback in
   `GeneralistLMPlanner`.
4. **V-PRB-4 structured decoding / attribution projection** —
   `click-button:seed-1`; TaskSpec was not created, so the current
   `CONTRACT / FIELD_BINDING` report layer is projection debt until proven
   otherwise.

V-PRB-1 invalid coverage audit handling has been selected as the first
production slice after non-BrowserGym reproduction proved deterministic READY
was blocked only by an invalid optional coverage audit. The repair is scoped to
intent coverage audit admission: the invalid quote audit is recorded but cannot
veto deterministic READY. It does not modify Coordinator, StateKernel,
PlannerPort, prompt, budget, task grammar, or benchmark-specific logic. After
the local gates and commit, rerun the same PR breadth 6-task x 2-seed matrix on
the clean committed revision. Do not batch V-PRB-2 through V-PRB-4 into this
patch.

The clean V-PRB-1 PR breadth rerun at `d40f8f1`
(`docs/evidence/runs/m8.2a-pr-breadth-d40f8f1/`) remains negative: 12/12
episodes were observed, 0/12 passed, with no provider failure,
missing/unrun/invalidated case, or promotion claim. V-PRB-1 did close the
invalid coverage-audit mechanism: the prior `click-dialog:seed-0` and
`enter-text:seed-0` invalid quote failures now advance to
`planner_waiting_clarification`. The largest remaining cluster is therefore
V-PRB-3 typed semantic action constraints with 7 episodes; V-PRB-2 provider
graph proposal normalization remains the alternative next child slice with 4
episodes. Select exactly one of these next; do not batch.

V-PRB-3 typed semantic action constraints is selected next as the largest
remaining mechanism. The child slice adds a strict semantic action resolver:
when the strict model returns an empty `ask_user`, the resolver may choose one
current typed action from immutable `PlannerContext` only if TaskSpec fields and
current affordance summaries identify a unique safe activation, selected-option
terminal submit, or target-derived text-entry value. This is not a task-name
fallback and does not modify Coordinator, StateKernel, PlannerPort, Prompt,
budget, benchmark-specific logic, provider graph normalization, or structured
decoding. After local gates and commit, rerun the same PR breadth 6-task x
2-seed matrix on the clean committed revision.

The clean V-PRB-3 PR breadth rerun at `9b951ed`
(`docs/evidence/runs/m8.2a-pr-breadth-9b951ed/`) improved the matrix to 12/12
observed, 8/12 official success, 4/12 official failure, with no provider
failure, missing/unrun/invalidated case, or promotion claim. The typed semantic
action constraint cluster is closed for this matrix. The remaining
official-failed mechanism is V-PRB-2 provider graph proposal normalization:
`click-button-sequence` and `form-sequence`, seeds 0 and 1, still fail before
TaskSpec creation with invalid provider obligation graphs. `enter-text:seed-1`
also records a runtime terminal-completion guard observation while receiving
`official_reward=1.0`; classify it separately and do not count it as an
official failed episode. Select exactly one next production slice: V-PRB-2
provider graph proposal normalization, with non-BrowserGym reproduction first.
Do not batch it with PlanningRequest migration, terminal completion guards,
fresh diagnostic, PR/nightly/release promotion, or benchmark-family patches.

V-PRB-2 provider graph proposal normalization is now selected as the next
single production slice. Its packet is
`docs/change-admission/v-prb-2-provider-graph-proposal-normalization.yaml`.
The first required non-BrowserGym reproduction is
`tests/test_intent_compiler.py::test_llm_compiler_canonicalizes_multistage_requested_effects_when_provider_graph_is_incomplete`.
The intended owner is the canonical obligation compiler boundary: preserve
valid provider proposal graph normalization, but when a multi-stage draft has
source-bound `requested_effects` and an incomplete provider graph, generate
Runtime-owned canonical claims and obligations from `requested_effects` instead
of making provider graph completeness the READY authority.

V-PRB-2 has now been implemented locally with a non-BrowserGym red/green test.
The repair is intentionally narrow: flat tasks remain canonicalized as before;
multi-stage drafts only fall back to requested-effect canonicalization when
they contain multiple source-bound requested effects and the provider proposal
graph is incomplete. Single-effect multi-stage repair-failure tracing and valid
provider proposal graph normalization remain unchanged. After local gates and
commit, rerun the same PR breadth matrix on the clean committed revision before
judging matrix impact.

The clean V-PRB-2 PR breadth rerun at `c24b277`
(`docs/evidence/runs/m8.2a-pr-breadth-c24b277/`) remains negative: 12/12
observed, 8/12 official success, 4/12 official failure, no provider failure,
no missing/unrun/invalidated case, and no promotion claim. V-PRB-2 closed the
invalid provider graph mechanism: the four previously pre-TaskSpec failures now
advance to downstream planning/admission. The remaining official-failed
clusters are two `click-button-sequence` planner clarification cases and two
`form-sequence` task-planning `entry_action_family_unavailable` cases.
`enter-text:seed-1` still records a runtime terminal-completion guard
observation with `official_reward=1.0`; keep it separate from official failed
episodes. The next selectable slice is a new V-PRB-5 downstream
task-planning/planner constraint follow-up, starting with exact owner
classification and non-BrowserGym reproduction. Do not batch it with
PlanningRequest migration, fresh diagnostic, or promotion.

V-PRB-5 has been opened as diagnostic-only packet
`docs/change-admission/v-prb-5-downstream-planning-follow-up.yaml`. It splits
the remaining official failures into two candidate mechanisms and forbids a
mixed production patch:

- **V-PRB-5A button sequence progress / next-subgoal gating** —
  `click-button-sequence` seeds 0 and 1 create a TaskSpec and accepted
  two-subgoal TaskPlan, execute the first `ONE` activation, then still present
  `button ONE is available` as active subgoal and return `ask_user` /
  `waiting_clarification` instead of progressing to `button TWO`.
- **V-PRB-5B form sequence entry action family availability** —
  `form-sequence` seeds 0 and 1 create a TaskSpec and proposed three-subgoal
  plan, but TaskPlan validation requires `type_text` for the slider
  reversible-write obligation while the environment offers slider `press_key`;
  context/schema/task-plan recovery attempts do not clear the rejection.

Latest review refinement:

- V-PRB-5A is now tracked by
  `docs/change-admission/v-prb-5a-button-sequence-effect-semantics.yaml`.
  Its non-BrowserGym RED showed a compiler-local gap: the requested-effect
  fallback preserved Runtime graph authority but made every generated effect
  terminal and omitted ordered dependencies. The local repair keeps flat
  requested effects independent by default and enables ordered dependency /
  intermediate-terminal semantics only for multi-stage requested-effect
  fallback. Rerun PR breadth on the clean commit before judging matrix impact.
- V-PRB-5B is tracked by
  `docs/change-admission/v-prb-5b-entry-action-family-resolution.yaml` and
  remains independent. Its likely owner is typed TaskPlan action-family
  resolution from obligation plus current affordance, not Prompt repair,
  context compaction, or lexical subject matching alone.
- V-PRB-6 is tracked by
  `docs/change-admission/v-prb-6-terminal-completion-guard.yaml` and must not
  be mixed into either 5A or 5B. Runtime success, verifier success, and
  BrowserGym reward stay separate.
- Immutable PlanningRequest / PlannerStateView remains the next horizontal
  lane, but it is not a prerequisite for 5A/5B unless the new RED evidence
  directly implicates mutable planner input or hidden state mutation.

Current M8.2B diagnostic position (2026-07-25): after the typed ownership,
proposal, TaskPlan, and provider-arity repair slices, clean SHA `df5b820`
completed a new seed-major 30 x 2 diagnostic at 24/60 official success/reward
(`0.4`). All 60 cases were accounted with zero provider failure/retry,
unrun/missing/invalidated case, or batch stop. The 36 ordinary envelopes are
12 intent/planning, 11 contract/field binding, 8 verification, 3 execution,
and 2 observation/context. `official_score_claimed=false`; frozen nightly is
held. The remainder of this paragraph is a historical revision-by-revision
snapshot, not the current capability inventory. Clean evidence-only SHA `6d1703c` then preserved verifier reason,
artifact lineage, and failed verifier kind in the canonical FailureEnvelope.
The provider-neutral terminal-readiness protocol, typed TaskPlan validation,
current grounding resolver, and strict-Planner candidate narrowing are
implemented through clean `3447795`. The provider-neutral sourced claim and
TaskObligationSpec input contract is implemented at `a6233ac`, but provider
completeness and typed repair before READY are not. Clean `fe28a76` rejects a
wholly missing raw-language ledger/graph as typed `UNSUPPORTED`; clean
`aca0b5d` adds an independently decoded, fixed-budget coverage review; clean
`f3c4a6f` projects graph-level malformed input to typed rejection. Deterministic
non-BrowserGym raw-intake conformance closes at `d860c2c`; TaskPlan outcome
compilation closes at `0b294f8`; verifier-evidence identity binding is now the
completed at `6861e98`; deterministic cross-scenario conformance is now the
completed at `766f598`. Clean `c6c19d1` extracts typed-text and ordinal
admission; terminal narrowing joins the same owner at `482a3c5`; and clean
`ca71819` completes verifier-backed current-target exclusion, active-subgoal
scope, and strict finish-evidence admission in the same stateless owner. The
full local gate is 890 tests, Ruff, and governed mypy over 107 source files.
At that historical snapshot, clean `befa319` wires an evidence-backed provider-switch owner into the
BrowserGym generalist normal entrypoint only when a configured multi-profile
fallback exists; it remains fail-closed for a single provider. Context/schema
owners were still absent, so normal-entrypoint recovery wiring remained open
at that revision. Current BrowserGym and `GeneralistTaskPipeline`
context/schema integration is stated above.
Clean `b48bf02` separately moves immutable model-invocation assembly to
`PlannerModelRequest`/`PlannerModelOrchestrator`, reducing
`GeneralistLMPlanner.propose()` to 222 lines without changing semantic
admission or model budgets. Clean first-case validation at
`1bef687` proves the diagnostic residual does not yet enter that path:
`scroll-text:seed-0` remains 0/1 because IntentDraft v5 omits the requested
terminal effect/data dependency and the flat RuleTaskPlan has no typed outcome
or action family. Treat this as an incomplete diagnostic and move the next
owner upstream to sourced intake-to-obligation completeness. Do not weaken the
verifier or `UNREQUESTED_EFFECT`, add task-specific solvers, expand budgets, or
run family/PR/nightly before the typed input path exists. Evidence:
`evidence/m8.2b-strict-reevaluation-plan-20260724.md`.

Clean `03a0d32` moves TaskPlan commit intent, commit-failure normalization, and
TaskPlan trace projections to `TaskPlanCommitPreparation`. The Coordinator now
only invokes `install_task_plan`/`replace_task_plan` and appends the returned
typed projections; its source decreases from 3643 to 3584 lines. This is a
containment reduction, not an M8.2B behavior or benchmark claim.

Clean `50ae956` moves recovery protocol event payload construction to pure
`RecoveryTraceProjection`; Coordinator only appends those typed projections and
decreases to 3567 lines. At that historical revision, recovery command execution
and state completion remained separate open ownership work; the later typed
dispatcher/owner integration supersedes that status.

Clean `7669090`/`5538f4d` add one bounded raw-intake repair path for missing
success criteria, sourced claims, obligations, or malformed obligation graphs.
Initial draft, repair, and independent coverage share a three-call intake
ceiling; BrowserGym reserves that third slot by reducing planner allowance.
Unsourced/stale, policy, and ambiguity failures remain single-call fail-closed.
The follow-up repair-audit correction records every reserved intake call rather
than inferring a fixed two-call path: `IntentDraftRepairProduced` now carries
its real model-call record and a distinct `intent-draft-repair-v2` decoding
identity. That identity and schema are part of immutable BrowserGym checkpoint
metadata, while provider/context/schema recovery ownership remained separately
open at those historical revisions. The targeted gates cover successful repair, a failed repair's typed,
redacted trace event, unsafe repair fail-closed, budget exhaustion, single-call
policy/ambiguity stops, and BrowserGym's successful-repair call accounting.
This is a local correctness repair, not
benchmark evidence or authorization to run a protected family.

Protected-family recheck after that local repair was deliberately bounded to
`enter-date` and `text-transform`. At immutable `f2f689a`, the first breadth
wave was invalidated as `schema_incompatible` before seed-1 because raw provider
obligation nodes failed strict decoding. Clean `05bd94c` changed that boundary
so malformed nodes become typed `invalid_provider_obligation` repair input; its
complete 2-task x 2-seed recheck accounted for all four episodes with zero
provider/retry failure, but all four remained fail-closed after the one repair.
The required-field provider envelope at clean `58f01ff` reproduced the same
two seed-0 failures. The stable root layer is `INTENT / PLANNING`: the local
provider did not produce a valid sourced obligation graph. These are negative
local evidence, not scores. Hold PR breadth and diagnostic; do not repair this
by task-name logic, more retries, a larger budget, or a Prompt-only patch.
The sole BrowserGym launcher now exposes explicit immutable `--llm-profile`
selection instead of overriding a configured profile to local; local retains
its GPU preflight, while a selected remote profile is recorded separately by
the existing run identity and is never merged with local evidence.
Schema-authority re-audit at clean `bba582c`: recent commits correctly preserve
provider obligation fields during bounded repair, distinguish repair Prompt
identity, count reserved model calls, preserve the selected provider profile,
and trace failed repairs. `TaskSpec`, graph vocabulary, structural validation,
policy, and fail-closed admission are code-owned. However,
`LLMIntentCompiler` still accepts provider-authored claim and obligation
instances, `_compile_decoded_draft()` can copy them into TaskSpec after
validation, and the default `ModelBackedTaskObligationCoverageChecker` gives a
model COMPLETE result a role in READY admission. No code-owned source-unit
ledger or generic canonical graph compiler exists. This is bounded model
authority, not model-independent compilation.

At that historical audit revision, the fixed Python 3.12 local gate passed 907
tests, Ruff, and repository-governed mypy over 110 source files. No benchmark or
provider episode was run for that audit.

SG1 is now complete at the succeeding source-ledger revision: a deterministic
bounded `SourceLedgerBuilder` emits hash-bound whole-request/clause/reference
units before model intake, records redacted lineage in trace, maps the legacy
`raw_text` alias to the canonical whole-request unit, and rejects an over-bound
request without a model call. Prompt identities advance to
`intent-compiler-v7` and `intent-draft-repair-v2`; this is a new immutable
intake identity, not comparable benchmark evidence. SG2-SG6 are now complete
at the current local revision; this does not authorize a benchmark, provider,
or release score.

The governing remediation is
[Intent Schema and Obligation Authority Governance](intent-schema-authority-governance-20260726.md).
Do not continue repairing provider graph shape through Prompt changes. Preserve
the current three-call maximum while moving authority into:

~~~text
SourceLedgerBuilder
  -> HybridIntentInterpreter proposal
  -> CanonicalObligationCompiler
  -> deterministic coverage and policy
  -> optional model audit with veto-only authority
~~~

Mandatory feature/evidence sequence (all steps are independently subject to the
horizontal architecture gates):

~~~text
freeze benchmark-family repair
  -> SG0 complete: freeze schema/graph authority and anti-specialization boundary
  -> SG1 complete: code-owned bounded SourceLedger and exact request lineage
  -> SG2-SG5 complete: canonical graph construction, source/graph coverage, veto-only audit, and no direct candidate graph copying
  -> full local quality gates
  -> SG6 complete: non-BrowserGym held-out intake conformance and adversarial omissions
  -> context/schema normal-entrypoint owners complete at maturity level 3
  -> retain partial configured provider switch without claiming full recovery
  -> SG7 targeted protected families
  -> PR breadth and fresh diagnostic only after SG1-SG6 pass
  -> nightly/release only after promotion criteria and explicit authorization
  -> publish immutable local evidence
  -> synchronize origin or remote CI only with explicit user authorization
~~~

The existing `TaskObligationOutcomeCompiler`, `DecisionConstraintSet`, task
planner, contract, verification, recovery, trace, and evolution path remain
downstream consumers. They must not absorb raw-language or benchmark-family
compilation while SG1-SG5 are implemented.

Current post-R8 repair slice (2026-07-23): release traces for the stable
password/login verification cluster show a shared observation defect. Native
`label` elements without independent interaction semantics are emitted as
`button/activate` affordances, while their adjacent password/text controls keep
weak id-derived labels. The Planner fills the first field, then selects the
descriptive label instead of the next typed control; both `enter-password` and
`login-user` reproduce this pattern for all five seeds. Repair this at the
generic DOM actionability and label-association boundary: descriptive/proxy
labels must not become independent actions solely because an authored marker
exists, and an unambiguous explicit, nested, or adjacent label must enrich its
labelable control. Required proof is a non-BrowserGym DOM unit test, an authored
extension conformance test, negative controls for genuinely interactive custom
elements and explicit roles, then the original failures, corresponding generic
form family, PR 18, and a new diagnostic sweep. Do not add task-name, URL,
benchmark-family, Prompt, or model-specific branches.

The clean `4c66648` two-task reproduction confirms the observation half of the
slice but does not close the failure: descriptive labels disappear and the two
typed controls receive `Password` / `Verify password` or `Username` /
`Password`, yet both episodes terminate at reward 0. Their new traces retain
the verified first-field target in `satisfied_action_targets`; the remaining
defect is generic completion cardinality. Current text completion treats any
one observed/verified quoted value as sufficient and exposes a submit-like
terminal while other explicitly requested writable fields remain unsatisfied.
Add a typed form-field obligation compiler for unambiguous label-to-quoted-value
relations and explicit `both fields` cardinality. It must bind one current
semantic target/value at a time, use verified target progress rather than
password value disclosure, and expose a terminal only after every obligation
is satisfied. Ambiguous values or fields must fall through to System 2; no
guessing and no task-name branch.

R9 validation result (2026-07-23): clean `b4e596e` passes the original two
failures 2/2, their 2-task x 10-seed family 20/20, and PR 18/18, all at official
reward 1.0 with no FailureEnvelope, provider failure, or retry. The complete
30-task x seed-0 diagnostic is 29/30 (0.9667), with no missing episode,
provider/retry failure, or batch circuit. Its sole failure is a planning-budget
envelope: the generic exact-value obligation misclassifies a quoted prefix in
a suggestion-selection intent, repeatedly alternating fill-prefix and select.
Freeze this diagnostic as evidence. The next generic boundary is typed
exact-value versus prefix/suggestion constraints with negative controls; do not
raise budgets, change Prompt/model, or add task/benchmark dispatch. M8.2B
therefore remains in progress. See
[R9 evidence](evidence/m8.2b-r9-form-obligations-20260723.md).

Completed R9 follow-up implementation slice (clean `7d0ada0`): replaced the accidental
quote-equals-exact-value assumption with typed text obligations. Exact field
assignments remain eligible only when grammar binds a literal to a writable
field (or explicitly declares shared field cardinality). A `starts with` /
optional `ends with` request over a typed autocomplete control is a separate
prefix/suggestion obligation: first establish the required prefix, then bind a
currently observed matching semantic option, and regard a longer current value
that satisfies the declared prefix/suffix as progress rather than a reason to
refill. Multiple autocomplete controls or multiple matching options without a
unique semantic binding must fall through to System 2. Required proof: generic
DOM contexts for empty, prefix-current, matching-value-current, ambiguous
target/option, and ordinary exact multi-field cases; declarative compiler
evidence and action declarations; focused tests; full Ruff/mypy/pytest gate;
then the frozen failure reproduction, selection/form family, PR 18, and a new
diagnostic. Do not use task ids, URLs, suite names, model/Prompt branches, raw
DOM handles, or a larger call budget. The generic gate passes 532 tests, Ruff,
and mypy across 89 source files. The clean benchmark ladder passes the original
failure 1/1, corresponding task family 10/10, PR 18/18, diagnostic 30/30, and
frozen nightly 300/300 at reward 1.0, with no missing episode,
FailureEnvelope, provider/retry failure, or batch circuit. Do not rerun the
625-episode residual release for this isolated repair; select the next generic
capability boundary from its already frozen cross-task clusters. See
[typed suggestion evidence](evidence/m8.2b-r9-suggestion-selection-20260723.md).

Current post-R9 diagnostic slice: the next frozen release cluster is the four
collapsible-control variants (20/20 failed episodes): two families finish with
official reward zero after selecting a submit terminal before expansion, while
two families issue `press_key` to section headers and fail the generated
`control_state` verifier before they can search the newly exposed content.
Treat these as one generic stateful-disclosure cluster until trace and current
reproduction evidence disproves that grouping. Audit typed observation of
expanded/collapsed state, semantic action compatibility for disclosure
controls, terminal deferral, postcondition generation, and fresh-child
discovery. The intended Runtime capability is a generic disclosure obligation:
open the uniquely scoped collapsed control, verify its current expanded state,
reobserve the new inventory, and only then bind a requested descendant or
terminal. Do not recognize accordion markup, task ids, section numbers, page
URLs, or benchmark families in Core. Before implementation, reproduce all four
seed-0 cases on one clean current SHA and compare their inventories, contracts,
executor encodings, and post-action observations.

Clean `406d53e` reproduces all four seed-0 cases with the same split. Real
rendered-DOM inspection shows a generic ARIA gap: every header is a standard
`role=tab` with a backend handle, `aria-expanded`, and `aria-controls`, but the
DOM Adapter's incomplete ARIA action map admits only the roving `tabindex=0`
header and classifies it as generic `press`; sibling tabs with `tabindex=-1`
are omitted. The model consequently emits `ArrowDown`, which changes focus but
does not disclose content, while BrowserSession omits `aria-expanded` and the
press verifier falls back to unrelated `context_text`. Implement this slice by
recognizing standard ARIA tab actions independently of current roving focus,
normalizing disclosure/expanded/controls state, compiling one semantic
`ACTIVATE` over a collapsed disclosure when the objective explicitly requires
expansion, and strongly verifying the expected expanded toggle. For a named
descendant search, traverse current disclosure siblings in observation order,
reobserving after each verified activation and stopping as soon as the named
semantic target is visible; ambiguous non-search multi-control requests fall
through. Add generic ARIA tab/disclosure, ambiguity, ordering, terminal
deferral, live-state capture, and BrowserGym encoder verifier tests before any
benchmark rerun.

The first clean implementation reproduction at `1713859` closes both
multi-disclosure search cases but leaves both single-section cases at reward
zero. Their bounded context contains two standards-valid disclosure roles: the
named section header and a weak generated-label sibling around the terminal.
The conservative multi-control ambiguity gate therefore falls through to the
model. Resolve this generically by preferring a unique collapsed disclosure
whose semantic label overlaps the explicit objective vocabulary; retain
fallthrough when zero or multiple disclosures match. This is label-based typed
scope resolution, not DOM-parent, generated-id, page, or task recognition.

The complete clean family sweep at `29d4d01` is 38/40: both single-control
families pass 10/10, while both multi-control families fail only seed 3. The
paired traces request quoted lowercase `"proin"`; an earlier panel exposes the
different label `Proin`, and the current case-folded descendant stop condition
binds it before reaching the later exact target. Preserve quoted actionable
labels as exact, case-sensitive semantic values inside disclosure traversal.
Continue ordered disclosure search past case-insensitive near matches, and
bind a descendant deterministically only when one unique current label exactly
matches. Multiple exact matches or no remaining disclosure retain System 2
fallthrough. Add generic near-match, exact-match, and ambiguity controls before
repeating the failed seeds and full family.

## 0. M8.6 Governance Correction Gate - reopened

This section overrides the historical task-family repair narrative above. The
implementation sequence produced substantial components, but the current
closure decision is governed by the
[M8.6 Closure Audit](current-closure-audit-20260724.md). The objective is not
another BrowserGym family pass. It is to make the default Runtime path general,
behaviorally bounded, recoverable from every phase, and contained behind clear
module ownership.

### 0.1 Current diagnosis

- the default GeneralistLMPlanner invokes task-shaped semantic compilers before
  the model and can behave as a benchmark task-family dispatcher;
- source scans for task ids do not catch this soft specialization;
- planner-facing BrowserGym tasks can contain audit identity and an incorrect
  blanket read-only operation class;
- the normal BrowserGym path does not instantiate the optional task planner;
- planner exception, invalid proposal, binding failure, context degradation, and
  no-affordance states do not consistently enter Recovery Cascade;
- the existing cascade and evolution path is strongest after a contract exists;
- ordinary benchmark failure is repaired too early instead of completing the
  matrix, clustering failures, and selecting an architecture-level fix.

### 0.2 Mandatory boundary

Benchmark is an architecture auditor. It is not the planner specification,
product objective, or first-order repair target.

A strict-generalist default profile may contain only standards-based semantics,
protocol/schema normalization, safety and authority policy, and accepted
regression-gated skills. Benchmark-shaped task grammar belongs in an explicitly
named compatibility profile or is removed.

No rule, prompt, compiler, skill, or planner branch is accepted merely because
it omits task ids. Behavioral paraphrase, distractor, ambiguity, scope, and
unrequested-effect tests are mandatory.

### 0.3 Ordered implementation

#### G0: Freeze evidence and profile identity

1. preserve current score reports with immutable revision and active profile;
2. inventory compiler, prompt, model, skill, policy, and recovery digests;
3. label each rule as standards, safety, accepted skill, compatibility, or
   suspected task grammar;
4. stop score promotion and new family-specific repair.

Status on 2026-07-24: **complete**. The clean R10 300-episode report at
`bb65ac6` is frozen and retrospectively classified as historical compatibility
evidence in
`evidence/m8.6-g0-r10-compatibility-freeze-20260723.md`; it is not a current
generalist score. New checkpoints bind explicit planner profile and compiler
registry digest. The only committed score-bearing or legacy-master claims have
now been inventoried: `e463e16` is legacy unsegregated diagnostic evidence, and
v112, Runtime R7, and R10 are historical compatibility evidence reconstructed
from their immutable source paths. Current score claims remain false until a
new strict frozen M8.2B evaluation is reviewed. Evidence:
`evidence/m8.6-g0-profile-and-report-inventory-20260724.md`.

#### G1: Strict-generalist planner

1. create explicit strict-generalist and compatibility profiles;
2. remove task-family compilers from the strict registry;
3. enforce typed compiler applicability metadata;
4. apply one PlannerProposalValidator to deterministic, LM, parent-agent, skill, and
   recovery proposals;
5. add failing governance probes before implementation;
6. prove non-BrowserGym Web, visual, and WoT behavior.

Status on 2026-07-23: **completed**. `strict-generalist` is now the default;
the task-shaped compiler registry requires explicit
`historical-compatibility`, and a strict planner rejects a non-empty
compatibility registry. Governance tests cover default isolation, profile
identity, registry digests, and task-id removal from planner context. One
Coordinator-owned `PlannerProposalValidator` now gates strict LM,
compatibility, parent-adapter, accepted-skill, and future recovery proposals
before completion, clarification, binding, approval, or execution. Initial
form/suggestion/disclosure task-shape controls and strict DOM/visual/WoT
conformance pass. Strict and compatibility now have distinct frozen Prompts;
strict candidate binding/repair uses only protocol, current-target,
verifier-backed progress, and exact blocked-signature facts, while task-shaped
rewrites remain compatibility-only. The behavioral anti-specialization matrix
now covers paraphrase equivalence, distractors, extra controls, blocking
ambiguity, unrelated interfaces, unrequested terminals/destructive effects,
and target-scope expansion. Typed runtime-authored
`PlannerProposalProvenance` is mandatory before validation and distinguishes
model, deterministic rule, parent agent, accepted skill, recovery, external
policy, and runtime terminal sources. Missing provenance is rejected before
binding or execution and accepted provenance is retained in trace and state. The
physical-containment slice is complete: historical task grammar now resides in
`compatibility_planner_algorithms.py`, strict import/construction does not load
that module, and only the explicit historical profile loads it. See
`evidence/m8.6-g1-proposal-validation-20260723.md` and
`evidence/m8.6-g1-physical-containment-20260723.md`, with G1 closure recorded in
`evidence/m8.6-g1-behavior-provenance-20260723.md`.

Completed implementation steps: `PlannerProposalValidator` is the first
context-bound semantic gate in Coordinator, ContractBuilder retains defense in
depth, and compatibility task grammar is physically isolated from the strict
Planner module. G2 now owns typed intent/capability derivation and the common
TaskPlan entrypoint. G2.5 active perception and G3 owning-port recovery have
completed their reopened correctness slices and local quality gate; G5
empirical evidence remains open. G4 complete-run audit remains closed.
Recovery-produced proposals remain subject to the same Validator and
fail closed unless they carry the reserved typed `recovery` provenance.

Completed physical-containment work: the reviewed call graph moved the
compatibility-only objective parsers, terminal exposure, prefix/direction
repair, semantic rewrites, and compiler callback assembly into a dedicated
compatibility module. Keep strict proposal data, protocol/current-target
validation, verifier-backed progress exclusion, schema construction, and model
orchestration in `generalist_planner.py`. Compatibility imports the shared
proposal contracts in the reverse direction; strict uses a lazy boundary and
does not import or execute task-grammar algorithms. An explicit compatibility
profile and replay entrypoint preserve historical evidence.

#### G2: Honest intent and task planning

1. keep IntentCompiler, TaskPlanRouter, GeneralistStepPlanner, grounding, and
   contract binding as separate responsibilities;
2. derive operation class, constraints, and capabilities from typed intent;
3. keep simple tasks flat;
4. use an accepted TaskSkill or validated shallow LM plan only for real
   multi-stage work;
5. wire the same router into reference, parent-agent, and benchmark entrypoints;
6. remove suite identity and reward from planner context.

Status on 2026-07-25: **component path complete; sourced obligation gate
open**. Raw requests enter `LLMIntentCompiler` and the deterministic
`IntentDraftValidator`; `TaskSpec.task_structure` selects the
flat rule plan or a declared shallow complex planner without granting action
authority. Coordinator installs `PlanningRouter` as the common TaskSpec path,
and the reference, parent/Coordinator, raw pipeline, and BrowserGym generalist
entrypoints use that boundary. BrowserGym no longer creates a blanket
read-only TaskSpec: its raw goal is compiled before perception and planning.

Coordinator, rather than an individual adapter builder, binds trusted verifier
evidence to the active TaskPlan obligations. Existing SkillStep identities are
preserved and may also satisfy the current subgoal; evidence already bound to a
different subgoal is never rebound. Rebuilt preflight contracts receive the
same binding. A normal non-BrowserGym raw multi-stage test passes through
IntentCompiler -> LLM TaskPlan -> two serial verifier-backed subgoals.

Planner-facing TaskSpec summaries omit task/run/source identities; task-plan
context exposes only URL origin, and step-planner artifact paths are replaced
with opaque digests. The benchmark test asserts that suite identity and
official reward wording are absent. External-evaluator terminal success is
strong independent evidence, while ordinary state-delta-or-terminal evidence
remains weak. First explicitly requested medium-risk execution no longer
requires a retry mechanism; recovery still refuses blind non-idempotent retry.
See `evidence/m8.6-g2-intent-task-planning-20260723.md`.

#### G2.5: Active perception and evidence repair

1. freeze typed EvidenceGap, ProbeCapability, ProbePlan, ProbeReceipt, and
   PerceptionResolution contracts;
2. add one ActivePerceptionController above the existing PerceptionSession,
   SourceAssertion arbitration, and targeted capture primitives;
3. derive the gap from TaskSpec/SubgoalSpec evidence requirements, conflict,
   freshness, uniqueness, verifier needs, and action risk;
4. select the minimum-cost permitted read-only probe across DOM, accessibility,
   SVG, screenshot, OCR, SoM, pure visual, WoT, API, wait, and refresh;
5. place probe output into a new coherent observation epoch and rerun
   arbitration; never mutate an old snapshot in place;
6. integrate the controller into normal observation, high-risk preflight,
   inconclusive verification, and recovery commands;
7. stop safely when the evidence remains insufficient or a safety-relevant
   conflict survives the probe budget.

Exit when a structural task stays on the cheap DOM/accessibility path, a
visual/spatial task requests visual evidence without first failing an action, an
injected source conflict is resolved by a bounded targeted probe, and an
irreducible conflict blocks an effectful contract.

Status on 2026-07-24: **reopened after implementation freeze**. Core owns strict `EvidenceGap`,
`ProbeCapability`, `ProbeCommand`, `ProbePlan`, `ProbeReceipt`, and
`PerceptionResolution` contracts plus one deterministic
`ActivePerceptionController`. Coordinator derives gaps after ordinary
observation and at preflight, verification-evidence repair, and lower-half
recovery inspection call sites. Each successful probe passes through
`PerceptionSession.capture_targeted`, must create one fresh coherent epoch, and
is re-arbitrated before it can resolve a gap. Probe selection is read-only,
relevance/capability/budget gated, prefers an independent source for conflicts,
and prevents an equivalent retry within the same gap epoch. Material unresolved
evidence blocks effectful execution; verification repair never repeats the
effect. Structural paths with sufficient evidence produce no probe. Evidence:
`evidence/m8.6-g2.5-active-perception-20260723.md`.

This establishes G2.5 infrastructure and call-site integration, but closure
requires strict budget intersection and target-relevant semantic evidence rather
than source/artifact presence. G3 subsequently reused those
ports through one `FailureEnvelope`, command validator, changed-strategy guard,
and phase-general `RecoveryCoordinator`; active perception remains owned by its
controller rather than by recovery.

#### G3: Full-phase Recovery Coordinator

G3 begins after G2.5 contracts and normal-path integration are stable. Recovery
may request active perception for a typed evidence gap, but it does not own
observation, infer missing facts, or execute the resulting action directly.

1. define one FailureEnvelope for intake, observation, fusion, task planning,
   step planning, proposal validation, grounding/binding, preflight, execution,
   verification, provider/context, and skill activation;
2. add semantic cascade matching in addition to exact debug signatures;
3. require every retry to change observation, assumption, subgoal, candidate,
   route, verifier, provider/context, skill use, or user information;
4. load accepted recovery profiles explicitly;
5. preserve inspect-before-repeat and effect uncertainty;
6. ask the user or abort when no safe change exists.

Status on 2026-07-24: **reopened after implementation freeze**. One strict `FailureEnvelope`, typed command
union, plan validator, receipts, non-empty deltas, semantic cascade key, and
pure `RecoveryCoordinator` now cover representative failures from intake
through provider/context, skill activation, preflight, execution, and
verification. `RunCoordinator` remains the only phase writer and applies each
command through the owning port. Uncertain effects are inspected before repeat;
retry requires effect-status and idempotency proof. Replan commands complete
only after an accepted TaskPlan or validated proposal exists, and an equivalent
failure changes strategy or terminates before budget exhaustion. Accepted
profile provenance requires an explicitly loaded artifact and digest. Evidence:
`evidence/m8.6-g3-full-phase-recovery-20260723.md`.

This closes G3 only. G4 subsequently closes complete-run accounting, while
generalization proof, external-suite readiness, and benchmark score promotion
remain pending under G5.

#### G4: Complete-run benchmark audit

1. continue after ordinary task failures;
2. fail fast only for safety, result corruption, non-comparable environment,
   profile-wide infrastructure/provider invalidation, or isolation failure;
3. persist partial results and resume only unobserved cases;
4. cluster by Runtime phase and semantic failure family before repair;
5. reproduce and fix outside the benchmark first;
6. use targeted and breadth replay only as confirmation.

Status on 2026-07-24: **complete**. Generic `EvaluationRunIdentity`,
`EvaluationRunAudit`, typed batch stops, per-case dispositions, and exact resume
selection now govern complete-run evidence. BrowserGym uses protocol
`three-layer-breadth-first-audit-v2`, v6 immutable checkpoint identity, atomic
checkpoint/report publication, explicit Runtime/external outcomes, and formal
family plus cross-family Runtime-owner clusters only after collection closure.
Ordinary case failures continue; only allowlisted batch-wide conditions stop or
invalidate. Partial, stopped, invalidated, and complete evidence cannot be
confused, and score promotion remains false. A deterministic non-provider,
non-browser 30-case conformance collection accounts for every scheduled case
before clustering. Evidence:
`evidence/m8.6-g4-complete-run-audit-20260724.md`.

This closes collection governance, not benchmark performance. G5 subsequently
closes internal profile-separated generalization evidence; historical scores
remain unpromoted.

#### G5: Generalization evidence

Report strict-generalist, strict-generalist plus accepted skills, historical
compatibility, and ablation profiles separately. Required controls include
unseen local interfaces, paraphrases, distractors, ambiguity, extra controls,
DOM/accessibility/SVG/visual/WoT sources, provider/context stress, recovery
injection, and external suites after independent provisioning.

Status on 2026-07-24: **evidence schema/conformance complete; empirical
profile proof reopened; external confirmation unprovisioned**. A strict typed report isolates the four
profile identities, recomputes case metrics and shared-case comparisons,
requires all perturbation/source controls and zero safety regression, binds
accepted skill digest/artifact identity through the real Coordinator, and
rejects hidden compatibility, undeclared ablations, tampered aggregates, or a
score-only claim. Provider-free Runtime conformance covered governance,
unseen/variant controls, DOM/accessibility/SVG/visual/WoT, provider/context,
active perception, full-phase recovery, and accepted-profile replay. The old
`generalization-v1` aggregate is always incomplete and diagnostic. Evidence:
`evidence/m8.6-g5-generalization-proof-20260724.md`.

### 0.4 Exit criteria

M8.6 closes only when:

- benchmark identity leak into planner context is zero;
- known negative probes do not trigger unrequested actions or scope expansion;
- the strict profile contains no benchmark task grammar;
- every proposal source passes PlannerProposalValidator;
- simple and multi-stage local tasks use the declared task-plan chain;
- every targeted probe is read-only, budgeted, task-relevant, and produces a
  new coherent observation epoch;
- normal, preflight, verification, and recovery paths share one active
  perception controller rather than hidden source-specific retries;
- representative failures from every Runtime phase enter one Recovery
  Coordinator;
- repeated equivalent failure changes strategy or stops before budget
  exhaustion;
- uncertain effects are inspected before repeat and duplicate effect count is
  zero;
- one complete diagnostic matrix is clustered before any repair;
- non-benchmark conformance and safety evidence precede benchmark replay;
- README, status, and reports identify exact revision and active profile.

These criteria are now met for implementation revision
`c9390517624eaf28a84aee9e77d0ba83ff533106`. G2.5 budget/evidence truth, G3 real
owning-port effects, responsibility containment, and the fresh G5 rollout pass
under the [M8.6 Closure Audit](current-closure-audit-20260724.md). M8.2B may now
collect a new strict frozen diagnostic evaluation. No historical result is
promoted and `official_score_claimed` remains false.

### 0.5 Reopened closure sequence

Execute in this order:

1. **completed locally** - enforce strict task/run/capability intersection for
   probe budgets;
2. **completed locally** - distinguish source/artifact availability from
   target-relevant semantic evidence;
3. **normal-entrypoint component integration complete; empirical gate open** -
   execute each enabled recovery command through a supplied owning port and
   reject no-op success; BrowserGym and `GeneralistTaskPipeline` provide the
   context/schema owners, while every-entrypoint coverage and level-4
   effectiveness remain open;
4. **first containment ratchet complete; reduction target open** - TaskPlan containment extraction - active-perception
   flow, recovery command dispatch, evidence projections, and stateless
   TaskPlanFlow are extracted while preserving one authoritative task-execution state/trace
   commit sequence; the Coordinator feature freeze remains and its active
   ratchet is 3473/26;
5. **completed** - publish fresh four-profile non-BrowserGym Runtime runs with
   trace, contract, receipt, verifier, environment, and artifact identities;
6. **current** - run one new strict frozen diagnostic matrix,
   collect ordinary failures to completion, cluster, repair Runtime-first, and
   confirm with targeted plus breadth replay.

Current strict re-evaluation update (2026-07-24): the intent-owned
exact/prefix/suffix schema and source lineage now reach the strict Planner.
Successive clean `use-autocomplete` replays prove authorized prefix input,
correct visible-option selection, and retirement of the satisfied textbox from
the next `type_text` schema. The remaining plain `Submit` button has no trusted
form/effect descriptor; strict mode safely asks rather than treating its page
label as authority. Do not add a MiniWoB/autocomplete submit branch. Environment
commit support requires typed adapter-declared effect/risk evidence and
independent negative controls. Active repair selection now moves to the frozen
pagination/global-ordinal residual: model page windows and next/previous
relations explicitly before mapping a global ordinal to a local candidate.
See [the strict re-evaluation execution plan](evidence/m8.2b-strict-reevaluation-plan-20260724.md).

The normative
[Responsibility Containment Boundary](responsibility-containment-boundary.md)
continues to block feature additions to `coordinator.py`; the reduced ratchet is
a containment checkpoint, not permission to resume feature growth.
M9, external suites, and distributed infrastructure cannot substitute for this
closure work.

## 1. Authority

This document is the implementation profile for the current repository. It is
the plan contributors should follow when deciding what to build now.

The [Complete Architecture Blueprint](complete-architecture-blueprint.md)
describes a possible production-scale destination. It does not create current
release requirements. When the two documents differ, this implementation plan
wins until a production feature is explicitly promoted through the decision
gate in the main [Project Plan](project-plan.md).

The [Runtime-First Architecture Boundary](runtime-first-boundary.md),
[Responsibility Containment Boundary](responsibility-containment-boundary.md),
[Horizontal Architecture Governance Track](architecture-governance-track.md),
and
[Benchmark Governance and Anti-Specialization Boundary](benchmark-governance-boundary.md)
are jointly normative. BrowserGym is an external adapter and evaluation
consumer.

No benchmark task family, selector, coordinate, authored answer,
fixture-specific semantic solver, or behaviorally equivalent task-grammar
compiler may enter the strict-generalist Runtime path. Static source scans are
not sufficient. Planner behavior must pass paraphrase, distractor, ambiguity,
scope, and unrequested-effect controls before benchmark confirmation.

The governing strategy is:

```text
complete vertical loop
limited horizontal breadth
```

The runtime must demonstrate reliable execution, evaluation, diagnosis, and
controlled evolution end to end. It does not need distributed infrastructure
or many interchangeable implementations of every component.

## 2. Product Definition

Affordance Runtime is a single-process, asynchronous, planner-neutral GUI agent
harness runtime. It converts DOM, visual, accessibility, and WoT observations
into versioned affordances, executes one validated Action Contract at a time,
verifies effects, records evidence, evaluates traces, and regression-gates
harness improvements derived from failures.

The complete product loop is:

```text
UserRequest or parent TaskSpec
  -> Intent Compiler
  -> immutable TaskSpec
  -> Observe
  -> Affordance Snapshot
  -> Generalist Planner Proposal
  -> Grounder / ContractBuilder
  -> Action Contract
  -> Policy + Preflight
  -> Route + Execute
  -> Post-Action Observe
  -> Verify
  -> Recover / Continue / Finish
  -> Trace
  -> Benchmark
  -> Failure Classification
  -> Skill / Policy / Verifier Proposal
  -> Regression Replay
  -> Accept / Quarantine / Reject
```

The implementation is a modular monolith:

```text
User / Parent Agent / Benchmark
                |
                v
       Reference Intake or PlannerPort
                |
                v
          RunCoordinator
     observe / gate / act / verify
        /          |           \
   Adapters     Trace Store   Recovery
        \          |           /
                Evaluator
                    |
              Evolution Gate
```

## 3. What Must Exist

The following capabilities are required to prove the project thesis:

| Capability | Current implementation target |
| --- | --- |
| Task intake | sourced user request, ambiguity-aware compiler, immutable versioned `TaskSpec` |
| Unified Affordance Model | common envelope plus typed DOM, visual, accessibility, and WoT payloads |
| Planner boundary | environment-general `PlannerPort` returning semantic proposals, with scripted, LM, parent-agent, and benchmark adapters |
| Contract building | deterministic proposal-to-`ActionContract` binding; no LM output executes directly |
| Coordinator | one authoritative state writer and action scheduler per run |
| Action Contract | the only object that may enter an executor |
| State validity | snapshot identity, page revision, target fingerprint, and expiration |
| Policy | task constraints, capability checks, and approval for effectful actions |
| Adaptive routing | choose a verified perception, grounding, executor, and verifier route from DOM, accessibility, SoM, pure visual, WoT, and API candidates according to task needs and current environment evidence |
| Verification | receipt separated from independent postcondition evidence |
| Recovery | small deterministic matrix with explicit budgets and no blind effectful retry |
| Trace | append-only event log plus artifact references |
| Evaluation | resettable fixtures, baselines, perturbations, ablations, and independent oracles |
| Evolution | verified-success TaskSkill mining plus failure/recovery artifact proposal, quarantine, replay, registry decision, and rollback |

## 4. What Is Intentionally Narrow

Each required capability begins with one useful implementation:

| Area | First implementation |
| --- | --- |
| Planner | scripted diagnosis planner plus one provider-neutral `GeneralistLMPlanner`; framework adapters stay optional |
| Browser backend | Playwright |
| DOM observation | Playwright DOM and accessibility state |
| Visual adapter | Set-of-Marks fixture-level grounding |
| WoT adapter | Thing Description parser plus local device fixture |
| State | in-memory `RunState` for one active run |
| Trace | JSONL and filesystem artifacts |
| Benchmark | three local SaaS scenarios |
| Recovery | stale, locator, modal, timeout, verifier, and capability cases |
| Evolution | declarative skill, policy, verifier, affordance-rule, or fixture patches |
| External interface | CLI first; task-level MCP later |

Completeness comes from connecting these components, not from adding many
providers, frameworks, backends, or services.

## 5. Core Runtime

### 5.1 Coordinator Rule

Each run has one `RunCoordinator` that owns authoritative state transitions and
dispatches every executable contract. Other components return immutable
observations, proposals, decisions, receipts, or reports.

```text
Parent Agent -> task, context, approval
Planner      -> proposal
Policy       -> allow, deny, or approval required
Executor     -> execution receipt
Verifier     -> verification report
Recovery     -> bounded recovery proposal
Coordinator -> only component that advances RunState
```

The planner cannot grant capability or execute actions. The executor cannot
reinterpret a contract. The verifier cannot mutate task state.

### 5.2 Runtime State Machine

The current implementation uses one task-level state machine:

```text
CREATED
OBSERVING
PLANNING
PREFLIGHT
WAITING_APPROVAL
ACTING
VERIFYING
RECOVERING
DONE
FAILED
ABORTED
```

Main path:

```text
CREATED -> OBSERVING -> PLANNING -> PREFLIGHT
        -> ACTING -> VERIFYING -> OBSERVING | PLANNING | DONE
```

Control and failure paths:

```text
PREFLIGHT -> OBSERVING          stale or expired state
PREFLIGHT -> WAITING_APPROVAL   approval required
PREFLIGHT -> ABORTED            policy denied
ACTING -> RECOVERING            execution failed or became uncertain
VERIFYING -> RECOVERING         expected effect not established
RECOVERING -> OBSERVING         bounded recovery is safe
RECOVERING -> FAILED            budget exhausted or risk too high
```

Browser and container availability remain ordinary runtime fields until an
independent worker actually exists.

### 5.3 RunState and Memory

`RunState` stores only information needed for the next safe decision:

```text
run_id, task_spec, phase
current observation, snapshot, contract
constraints, capabilities, pending approval
active subgoal, obligations, evidence refs
step and recovery budgets
latest receipt and verification
final result
```

Memory has three practical layers:

| Layer | Contents |
| --- | --- |
| Working state | current goal, constraints, snapshot, contract, evidence obligations, and budgets |
| Episodic trace | all events and artifact references from this run |
| Accepted harness knowledge | regression-approved skills, policies, verifier rules, and fixtures |

Raw DOM, screenshots, downloads, and complete histories are stored as artifacts,
not accumulated in `RunState`. No vector database is required for the current
runtime.

### 5.4 Task Intake and Generalist Planner

The full current specification is
[Task Intake and Generalist Planner](task-intake-and-planner.md).

The legacy `TaskEnvelope(goal: str)` and scripted planners remain compatibility
scaffolding. M8.2A completed the following boundary:

```text
UserRequest
  -> LLMIntentCompiler
  -> IntentDraft
  -> deterministic ambiguity/policy validation
  -> immutable TaskSpec revision
  -> GeneralistLMPlanner
  -> PlannerProposal
  -> deterministic ContractBuilder
  -> ActionContract
```

The compiler may request clarification but cannot grant capability. The planner
may propose a semantic action but cannot bind authority, select an unchecked
surface payload, or execute it. BrowserGym and AgentLab are benchmark adapters
to this boundary, not the product definition.

## 6. Affordance and Contract Model

### 6.1 Affordance

The shared envelope supports common routing, policy, trace, and evaluation:

```text
id, surface, kind, label, semantic role
state, confidence, risk
backend candidates, evidence refs
snapshot id, target fingerprint
typed payload
```

Typed payloads preserve surface detail:

```text
DOM: locator candidates, role/name, form context, uniqueness
Visual: bbox, mark id, screenshot ref, descriptor
Accessibility: role/name/path, enabled/focused state
WoT: href, operation, method, schemas, security metadata
```

### 6.2 Validity Boundary

The first implementation uses:

```text
snapshot_id
page_revision
target_fingerprint
expires_at
artifact content hash
```

Preflight checks that the snapshot is current, the lease has not expired, the
target fingerprint still matches, preconditions hold, and capability/approval
is valid. More revision dimensions are introduced only if benchmark evidence
shows this representation is insufficient.

### 6.3 Action Contract

An Action Contract binds semantic intent to an executable target and verifier:

```text
schema_version, contract_id, run_id
snapshot_id, page_revision, target affordance, target fingerprint
intent, action, backend, parameters
preconditions, expected effects, verifier plan
required capabilities, risk, approval binding
idempotency key, compensation, timeout
```

Contract data is immutable after approval and must be canonicalizable for
hashing and trace replay.

## 7. Execution, Verification, and Recovery

Execution follows:

```text
pre-observation
  -> policy and preflight
  -> execute contract
  -> ExecutionReceipt
  -> post-observation
  -> VerificationEvidence
  -> VerificationReport
```

An executor receipt proves a technical attempt, not task success. Verification
states are `PASSED`, `FAILED`, `INCONCLUSIVE`, and `ERROR`.

The first verifier set is deliberately small:

- DOM state and URL verifiers
- fixture API or database verifier
- file/download receipt and hash verifier
- screenshot evidence verifier
- model judgment only as weak supporting evidence

Recovery is bounded:

| Failure | Response |
| --- | --- |
| stale snapshot | re-observe and replan |
| locator missing | rebuild affordances, then one backend fallback |
| blocking modal | apply a registered low-risk modal policy or ask/abort |
| execution timeout | observe first, then decide whether retry is safe |
| inconclusive verification | gather one stronger evidence source, then replan/fail |
| capability denied | request approval or abort |

Effectful actions are never blindly retried after timeout or uncertain
execution.

## 8. Async and Docker Boundary

The runtime uses `async` I/O while preserving serial action semantics:

```text
one run
one coordinator
one browser session
one active Action Contract
```

Read-only observation capture, independent verifiers, and artifact hashing may
run concurrently when they refer to the same observation epoch. State mutation,
approval consumption, effectful execution, compensation, and trace sequencing
remain serial.

Docker is used for reproducibility and isolation. M8.1 added a deliberately
small profile:

```text
docker compose
  fixture-web
  runtime-test
  benchmark
  shared artifact volume
```

The fixture keeps canonical state in its in-memory server, so the plan does not
invent a fixture database. The profile pins Playwright/Chromium, runs as a
non-root user, exposes a health check, and writes the same reports/artifacts as
host execution. Official benchmark stacks may join through optional profiles
or an external network.

Docker is not used to create scheduler, coordinator, browser-worker,
event-broker, or memory microservices. M8.1 exits when a clean checkout passes
`docker compose build`, `docker compose run --rm runtime-test`, and
`docker compose run --rm benchmark`.

An optional `wot-proof` profile selectively migrates the old repository's
mature node-wot fixture and the minimum dashboard surface needed for a
cross-surface test. It is not the default product demo and does not copy the old
root Dockerfile or Compose topology wholesale.

The conformance task exposes one reversible state through three surfaces:

```text
DOM dashboard control
real screenshot / SoM control
WoT Thing Description operation
             |
             v
same TaskSpec, capability, expected effect, and independent state oracle
             |
             v
same ActionContract envelope, Coordinator, verifier, trace, and evaluator
```

DOM remains the primary real-browser path; visual remains a controlled
screenshot-grounding path; WoT remains a non-Web adapter proof. The gate proves
shared harness semantics, not equal product maturity across all three.

## 9. Trace, Benchmark, and Evolution

### 9.1 Trace

Canonical run storage is an append-only `events.jsonl` file plus artifacts:

```text
artifacts/<run_id>/
  run.json
  events.jsonl
  observations/
  screenshots/
  dom/
  receipts/
  downloads/
  eval_report.json
```

Events cover observation, snapshot, proposal, contract, policy/preflight,
approval, execution, verification, recovery, and final result. Parent links may
derive causal views without requiring a graph database.

### 9.2 Benchmark

The primary fixtures are:

1. read-only pricing extraction
2. reversible settings update
3. approval-gated report export

The core comparison is Direct Playwright versus Affordance Runtime. Required
ablations are no preflight, no structural verifier, no capability gate, and no
recovery.

Release-facing metrics are limited to:

```text
task_success_rate
stale_detection_recall
verifier_false_accept_rate
constraint_violation_rate
recovery_success_rate
regression_delta
```

Latency, cost, action count, observation count, and fallback count remain
supporting telemetry.

MiniWoB++ is a secondary generalization suite, not a replacement for the local
SaaS fixtures. The M8 adapter pins the official Farama source, owns episode
start/reset, instruction extraction, termination/reward collection, artifact
capture, diagnostics, and report aggregation, and covers click, type, select,
dialog, sequence, and form across three seeds. It is labelled a curated runtime
subset, never a full MiniWoB++ score.

The public benchmark ladder after M8 is:

```text
PR smoke: current 6 MiniWoB++ task families x 3 seeds
Nightly: at least 30 MiniWoB++ task types x 10 seeds
Release: every task supported by the pinned BrowserGym adapter x 5 seeds

External:
  ScreenSpot full offline grounding
  WorkArena L1
  WebArena-Verified stratified subset, then hard subset
  WASP security subset
  VisualWebArena after multimodal action routing is stable
  OSWorld only as a future cross-application boundary
```

BrowserGym is the preferred environment adapter where it already owns reset,
task registration, and benchmark semantics. Affordance Runtime still owns
affordance conversion, contracts, policy/preflight, verification, recovery,
trace, and diagnostics. Unsupported families are reported rather than silently
omitted. Official scores and harness fault-injection scores are separate.

### 9.3 Controlled Harness Evolution

The evolution loop is required, but it operates on declarative artifacts rather
than arbitrary source-code mutation:

```text
failed trace
  -> classify perception / planning / grounding / execution /
     verification / recovery / safety failure
  -> propose Skill, PolicyPatch, VerifierPatch, AffordanceRule,
     or BenchmarkFixture
  -> replay the original failure and related task family
  -> run safety smoke tests
  -> accept, quarantine, reject, or roll back
```

A failure classifier and a report comparing an existing full-runtime variant
against a broken ablation are useful prototype evidence, but do not yet prove
self-evolution. The claim requires a typed artifact with executable payload,
loading it into a fresh candidate runtime, rerunning the suites, persisting the
registry decision, and proving rollback.

M6 first proved the loop for a structural `verifier_patch`. M8.3 extends it to
bounded recovery: attempts are grouped into an incident, repeated signatures
and oscillation are detected, root cause is separated from symptoms, and
declarative recovery skill/policy payloads are executable.

```text
trace events -> RecoveryIncident -> FailureSignature per attempt
  -> repeat / no-progress / A-B oscillation detector
  -> root failure plus symptom chain
  -> declarative RecoveryPolicyPatch or Skill
  -> fresh original/family/global/safety replay
  -> accept, quarantine, reject, or roll back
```

Online behavior only detects and safely aborts a repeated cascade within the
existing recovery budget. Learning remains offline and regression-gated.

## 10. Milestones

### M0: Design Alignment - done

Freeze one state machine, current wire contracts, trace schema, scenario specs,
and declarative evolution artifact schema.

### M1: Web Runtime Core - done

Deliver the pricing fixture, Playwright observer/executor, DOM affordances,
scripted planner, contract/preflight, post-action verification, artifact-backed
trace, CLI, and Direct Playwright baseline.

### M2: Reliability and Cross-Surface Proof - done through M8

The three local scenarios and 3 x 7 matrix run successfully across three
distinct seeded layouts. SoM and WoT prove common contract reuse; M8 adds a
real screenshot-pixel visual grounding path and held-out layout evidence.

### M3: Assisted Evolution Prototype - done through M6

Implemented: classification, proposal types, direction-aware gates,
replay-category accounting, and before/after reporting.

M6 applied a SHA-bound executable verifier proposal to a fresh candidate,
generated new replay traces, persisted the registry decision, and proved
rollback.

### M4: Local Integration Boundary - done through M7

Implemented: in-process task service, bounded parent-agent-shaped tool adapter,
external task JSON-RPC, and a real LangGraph parent in a separate process. The
parent has no access to primitive click/type/observe operations.

### M5: Evidence Freeze - done

- commit the current implementation as a reviewable unit
- add CI for tests, Ruff, mypy, package build, and focused Chromium smoke
- record runtime commit, browser version, fixture version, and seed semantics
- publish reproducible benchmark and evolution summaries
- keep README and status claims aligned with generated evidence

Exit: a clean checkout reproduces the local gold path, 3 x 7 matrix, and
evolution prototype.

Evidence: `./scripts/reproduce_local.sh` passed from a clean clone at commit
`4528f25baab0778a6eec4ce37a9fba82f2a7635e`; see
`evidence/m5-4528f25.md`. That historical M5 report records
`label_only_v1`; M8 supersedes current seed semantics with
`deterministic_distinct_layout_v2`.

### M6: Executable Harness Evolution - done

- add an executable payload for at least one verifier or policy patch
- load it into a fresh candidate runtime
- replay original, task-family, global-smoke, and safety-smoke suites
- persist artifact/registry versions and demonstrate rollback

Exit: one failed trace produces an applied artifact that fixes the failure with
zero safety regression.

Evidence: a clean clone at `4cccc96a0dc14ebdd5c11f03896ff307835ad69c`
loaded `verifier_patch-reversible_settings_update@1.0.0` into a fresh
no-verifier runtime, produced six new Chromium traces across all mandatory
categories, persisted acceptance, and proved runtime plus registry rollback.
See `evidence/m6-4cccc96.md`.

### M7: Real Parent-Agent Integration - done

Expose the bounded API through MCP or an equivalent external protocol. One real
Codex, Claude, OpenHands, or LangGraph parent must complete the pricing flow and
the approval-gated export flow while Runtime remains authoritative.

Evidence: a clean clone at `9a9796e66be882b03a9f8059e89dbb22c9e5b056`
compiled LangGraph 1.2.9 and called a separate runtime process through
`affordance-task-rpc/1.0`. Pricing succeeded; export stopped for scoped
approval and then succeeded with file-hash evidence; only eight task-level
tools were exposed. See `evidence/m7-9a9796e.md`.

### M8: Generalization Evaluation - done

- make seeds produce distinct fixture variants
- add unseen layouts or hidden perturbations
- add a pinned official MiniWoB++ adapter and repeated curated subset
- cover click, type, select, dialog, sequence, and form families
- add a real visual grounding path, not only a static SoM contract proof
- report official MiniWoB success/reward and runtime failure diagnostics

Evidence: `./scripts/reproduce_local.sh` passed from a clean clone at
`e463e160aea9c151667877d5aac40995196075a9`. It produced three distinct
training layout fingerprints and 63 accepted matrix runs; six successful
held-out scenario runs; five successful screenshot-grounded visual runs with
five distinct boxes and no DOM coordinates; and 18/18 raw-reward-successful
episodes over six task families from official Farama commit
`eb59fed60fabe8951350275ba8650633b740013b`. See
`evidence/m8-e463e16.md`.

### M8.1: Reproducible Container Profile - done

- add a pinned Playwright/Chromium Dockerfile, `.dockerignore`, and Compose
- provide fixture, test, and benchmark services with mounted artifacts
- run non-root, add fixture health/reset, and record environment identity
- keep public benchmark stacks as optional profiles or networks
- add an optional `wot-proof` profile from the audited node-wot fixture
- run one reversible cross-surface task through DOM, real screenshot/SoM, and
  WoT without bypassing the Coordinator

Exit: a clean checkout reproduces tests and the local benchmark in containers,
with host/container agreement on outcomes and oracle decisions. The optional
cross-surface run reaches the same oracle state through all three surfaces and
emits contract-compatible, verifier-backed traces for each backend.

Clean commit `40fd93b` passed this exit gate with 58 container tests, a 63-run
benchmark matching the host report on every stable outcome/oracle field, and
DOM, screenshot/SoM, and real node-wot traces against one shared oracle. See
`evidence/m8.1-40fd93b.md`.

### M8.2: Planner Contracts and Public Benchmark Audit - diagnostic repair in progress

#### M8.2A: Task Intake and Planner Contracts - locally complete; empirical generality open

The schemas and contract boundaries below are retained. The default
GeneralistLMPlanner and compiler registry are not accepted as generalization
proof until M8.6 isolates task-family behavior and passes behavioral controls.
All later task-family narratives in this M8.2 section are historical evidence,
not authorized current work. SG1-SG6 are locally complete; SG7 confirmation is
the next vertical step when authorized, with horizontal gates applied in
parallel.

Implement the schemas and gates in
[Task Intake and Generalist Planner](task-intake-and-planner.md):

- compile raw requests into sourced, ambiguity-aware, versioned `TaskSpec`;
- keep requested capability distinct from granted authority;
- return semantic `PlannerProposal` rather than a ready contract;
- bind proposals through a deterministic `ContractBuilder`;
- add provider-neutral `ModelPort`, `LLMIntentCompiler`, and
  `GeneralistLMPlanner`;
- retain scripted, parent-agent, and AgentLab benchmark adapters;
- trace prompt/model/schema versions and proposal-to-contract lineage;
- evaluate intent compilation, canonical-task planning, and end-to-end behavior
  separately.

Exit: raw natural language completes read-only, reversible-write,
approval-gated, and cross-surface tasks through the full Coordinator; blocking
ambiguity stops safely; clarification revisions invalidate stale proposals; no
LM output grants authority or bypasses contracts; compiler and planner failures
are attributable separately from runtime failures.

Evidence: `docs/evidence/m8.2a-7edaa97.md` records the controlled 30-request
Mistral compiler suite, verified local SaaS read/write/approval paths, common
DOM/SoM/WoT GeneralistLMPlanner tests, and an official BrowserGym smoke through
the same planner boundary.

#### M8.2B: Public Benchmark Expansion - in progress

Before scaling public suites, complete this bounded consolidation gate:

- align README, implementation status, evidence wording, and executable
  verification commands with the current repository;
- use the committed Web or BrowserGym reproducibility constraints when
  rebuilding evidence, so Pydantic, LangGraph, Pillow, and test tooling cannot
  silently change; the two Playwright profiles remain isolated;
- retain the completed BrowserGym split across action schema, environment
  adapter/episode execution, matrix/checkpoint, and MiniWoB task source;
  public facade imports and runtime behavior remain stable;
- retain the completed `miniwob-action-family-v1` nightly manifest: 30 tasks
  across ten action families, independent of Gym registration order; absent
  registered tasks must remain visible as missing coverage rather than shrink
  the matrix;
- retain the current GPU-local gate before scaling: repaired families, PR, and
  breadth pass 30/30, 18/18, and 60/60; clean v112 then passes the immutable
  30 x 10 nightly at official success/reward 1.0 without acceptance,
  runtime/provider/429/retry, unsupported-action, or failure-cluster errors;
- keep `RunCoordinator` free of benchmark-specific branches. External suites
  provide task sources, environment adapters, artifacts, and official
  evaluators;
- keep benchmark attributes and authored family logic out of shared DOM/planner
  modules; R5 moved them behind adapter profiles and proved replacement
  capabilities with non-BrowserGym and negative-control evidence;
- retain the implemented screenshot-capable `VisualGrounderPort` before
  claiming an official ScreenSpot prediction result; it accepts immutable
  screenshot input and returns only a bounded point artifact.

This gate remains an internal cleanup, not a framework redesign. The one
permitted scheduling addition is the BrowserGym matrix's seed-major,
single-process three-layer protocol with immutable checkpoints and batch-level
diagnosis. Do not add a worker pool, second state machine, distributed event
bus, or benchmark-specific Coordinator path.

##### M8.2B.1: Provider and Runtime Reliability Gate - completed locally

The initial 2026-07-21 diagnostics proved that increasing the 150-second episode
timeout alone would hide independent failures rather than close M8.2B:

- an explicit Gemini BrowserGym probe failed before its first action with HTTP
  429 `RESOURCE_EXHAUSTED`. The response named the free-tier
  per-project/per-model request quota, reported a quota value of 20, and
  supplied a retry delay of about 17 seconds;
- the HTTP adapter at diagnosis time retried a 429 only once, used a one-second
  fallback, caps a server hint at five seconds, and ignores structured
  `google.rpc.RetryInfo`. It cannot distinguish transient throttling from
  exhausted quota;
- the native Ollama adapter completed one real `click-button` episode with
  official reward 1.0, but its planner call took about 25.8 seconds;
- SL09 exposed the RTX 3080 device nodes to the old Ollama container, but NVML
  initialization and Ollama GPU discovery fail. The loaded `qwen2.5:7b`
  reports `size_vram=0`, so the measured run is CPU-bound;
- a real `enter-text` trace repeated `type_text("Myron")` after the
  post-observation already contained that value. Four calls took roughly
  10-20 seconds each, prompt history grew, and the next call timed out;
- BrowserGym at diagnosis time verified only the generic transport condition
  `last_action_error == ""`. This does not prove semantic effects such as
  input value, selected option, slider state, navigation, or task completion.

| Layer | Required correction |
| --- | --- |
| Provider capacity | pin one quota-sufficient remote provider or a verified GPU-local model; never merge fallback providers into one scored report |
| Provider protocol | parse bounded retry metadata, classify transient rate limit versus hard quota, circuit-break exhausted providers, and checkpoint/defer |
| Local inference | repair or recreate the NVIDIA-enabled Ollama container; require container `nvidia-smi` and Ollama `size_vram > 0` |
| Verification | add action-specific postcondition verifiers; keep execution receipt distinct from effect evidence |
| Progress | block an already-satisfied or unchanged repeated semantic action before execution |
| Context and time | compact proposal history and declare separate episode, model-call, call-count, and execution/verification budgets |

Required implementation order:

1. Verify text value, selected option, keyboard/slider state delta, and declared
   click/terminal/oracle effects instead of treating no executor error as
   success.
2. Add a deterministic progress guard keyed by action kind, stable target, and
   normalized parameters. Return `effect_already_satisfied` or
   `no_progress_repeat` and enter bounded repair/replanning.
3. Send only the current task/subgoal summary, bounded affordances, last
   verified state delta, and one relevant failure to the planner.
4. Add typed `rate_limit_transient`, `quota_exhausted`, and
   `provider_capacity` errors, bounded server-hint parsing, circuit breaking,
   and resumable deferral.
5. Use the native Ollama adapter for local evidence and repair GPU residency;
   record model digest, quantization, context, Ollama version, GPU, and VRAM.
6. Separate `episode_timeout_s`, `model_call_timeout_s`,
   `max_model_calls`, and execution reserve. A 300-second local run is
   diagnostic only and is not score-equivalent to the fixed PR/release budget.
7. Re-run in order: one click seed, one text-entry seed, six tasks x one seed,
   the 18-episode PR matrix, then the 30 x 10 nightly and release matrices.

Historical local implementation snapshot: items 1-6 were complete in that
working tree and its repository gate passed 365 local tests. Text, selection, keyboard/slider,
and click state-delta/terminal-oracle verifiers are distinct from the executor
receipt. The semantic progress guard blocks verified or unchanged duplicate
actions before execution. Planner v47 bounds affordances and keeps one proposal,
one verified delta, and one relevant failure; bounded repair calls use a
dynamically narrowed action/target schema that cannot re-admit a rejected
signature. Provider errors are typed and
quota exhaustion opens a resumable circuit-break deferral. Recreating the stale
Ollama container while retaining its named model volume restored container
NVML; the fail-closed preflight records `qwen2.5:7b` with
`size_vram=4748056984` on the RTX 3080. Checkpoint v5 binds all four explicit
time budgets, model/prompt/schema identity, the task/seed matrix, and an
executable-source digest without reading `.env`; both nightly and release now
reject dirty worktrees. The fixed local smoke budget
is `episode_timeout_s=165`, `model_call_timeout_s=10`, `max_model_calls=15`, and
`execution_reserve_s=15`. Ordered click/text checks and the six-task smoke have
passed. The fresh single-version v47 PR matrix passed 18/18 with mean official
reward 1.0, 47 model calls, no runtime/provider failures, and no retries. Item 7
is complete through the PR gate. A v36 nightly diagnostic was stopped after 89
episodes when all nine `enter-date` seeds failed on the browser-native date
format; v37 normalizes semantic dates at contract binding and passes the
targeted 10-seed date matrix. Later v42 diagnostics exposed hidden autocomplete
menus and prefix/suffix ambiguity; programmatic visible options, native-only
completion, and deterministic prefix/suffix narrowing now pass 10/10. A v42
nightly then exposed a slider objective containing both its target and a
checkbox ordinal; v43 extracts the value grammatically attached to the slider
instruction. The next v43 nightly passed 130 episodes before three systematic
`copy-paste` failures showed that label normalization removed a required
trailing space and that a verified destination did not exclude the source
textarea. v44 preserves bounded exact non-sensitive control values and binds a
copy/paste instruction to one source and destination; its targeted matrix passes
10/10. A v44 PR diagnostic then showed that slider-direction repair could still
arrive only after the bounded repair budget was consumed. v45 constrains an
unambiguous pending slider direction before decoding and passes targeted
`form-sequence` 10/10, smoke 6/6, and PR 18/18. The v45 nightly then passed 140
episodes before `text-transform` exposed missing non-interactive text
observation. v47 adds bounded, explicitly untrusted visible body text to
PlannerContext and constrains one isolated visible value for a deictic
text-entry request; the targeted matrix passes 10/10. Subsequent generic
target-discovery, role-binding, visibility, and focus-aware typing repairs now
pass `email-inbox` 10/10 and `search-engine` 10/10. The latest v101 PR gate is
18/18; v102 covers 30/30 tasks at seed 0 with 0.9667 mean reward and no
provider/runtime/429/retry failures. The clean v109 nightly then completed
300/300 and exposed three trace-backed failure clusters without promoting a
score. After generic repairs, a hierarchy-scope follow-up, PR, and breadth all
passed. The replacement clean v112 nightly passes 300/300 at official
success/reward 1.0 with `official_score_claimed=true`. The larger release
profile remains distinct; v103 continues to enforce its immutable boundary.
That complete v112 release measured 321/625 and truthfully grouped all 304
failures into eight repair clusters. The current dirty-tree repair ladder has
since closed empty dynamic schemas, animated-SVG preflight, exact copy,
structured dual-target SVG drag, date/time binding, authored color, pure-visual
SVG item observation, multi-epoch SVG numeric identity, structured authored
quantity controls, and calendar range selection. `ascending-numbers` passes 10/10 with 50 current-epoch SVG
actions and zero model calls; a four-family SVG cross-regression passes 20/20.
`order-food` and `daily-calendar` each pass 10/10 with zero model calls. The
same v149 source passes the fixed 165/10/15/15 PR and breadth at 18/18 and
60/60; the launcher now fails closed unless local Ollama has non-zero GPU
residency. These diagnostics do not replace the
immutable release result. Evidence is recorded in
`evidence/m8.2b-v112-release-boundary-20260722.md` through
`evidence/m8.2b-v149-daily-calendar-range-binding-20260722.md`.

Provider fallback is allowed only in explicitly labelled operational mode. A
scored matrix pins one provider, model, prompt/schema version, sampling
configuration, timeout policy, and task manifest.

Exit:

- the selected provider passes identity/capacity preflight;
- selected local evidence proves non-zero GPU residency;
- text entry reaches its semantic postcondition without repeated success;
- a deliberate no-progress repeat is blocked before duplicate execution;
- six-task smoke passes before the 18-episode matrix is scheduled;
- the PR report includes model-call latency, retries, typed provider failures,
  manifests, checkpoint provenance, and a fixed episode budget;
- no health check, mixed-provider run, or diagnostic timeout is promoted to an
  M8.2B completion claim.

Remaining suite expansion:

- use the implemented BrowserGym adapter to route every supported action
  through the full coordinator path and keep the scored policy external
- cover focusable keyboard controls through the semantic `press_key` proposal
  action; it may carry only a key value and is bound to a current affordance
- keep 18 episodes for PR smoke; add 30 task types x 10 seeds nightly
- use the fixed local nightly long-action budget of 165-second episodes,
  5-second model calls, at most 30 calls, and a 15-second execution reserve;
  this covers verified one-step slider horizons without a 300-second catch-all
- release-test every supported pinned MiniWoB task x 5 seeds
- retain the implemented coverage, unsupported-action, variance, official
  reward, and runtime-failure report fields while scaling the matrices
- add ScreenSpot, WorkArena L1, a 30-50 task WebArena-Verified subset, and a
  WASP security subset in that order
- defer VisualWebArena and OSWorld until their prerequisite layers are stable

Exit: no scored task-specific regex/selector solver remains, every episode
traverses the full runtime path, official/injected suites are separate, the
environment and model manifests are reproducible, and unsupported action
families remain visible rather than being silently excluded.

Recommended execution order:

```text
semantic verification, no-progress guard, and provider preflight
  -> one click seed and one text-entry seed
  -> six tasks x one seed
  -> resumable 18-episode PR matrix
  -> resumable 30 x 10 MiniWoB nightly
  -> ScreenSpot assets and visual grounding
  -> one real WebArena-Verified task, then the 30-task subset
  -> WASP security subset
  -> WorkArena when authorized access is available
```

### M8.3: Recovery-Cascade Components - partial; full-phase integration in M8.6

- normalize a `FailureSignature` from phase, error, action/backend, target,
  verifier, and relevant state revision
- group causally related attempts into a `RecoveryIncident`
- detect repeated signatures, no-progress recovery, A-B oscillation, repeated
  stale contracts/verifier failures, and fallback exhaustion
- preserve root failure separately from secondary recovery symptoms
- report cascade depth, repeated-failure rate, loop aborts, duplicate-effect
  risk, and recovery-action effectiveness
- implement narrow executable `RecoveryPolicyPatch` and `Skill` schemas
- replay original, family, global smoke, and safety smoke in a fresh runtime

Exit: one real repeated recovery failure produces a quarantined artifact; the
accepted candidate breaks the loop or reduces cascade depth, adds no unsafe
effect or blind retry, persists its decision, and rolls back.

Clean commit `07e406f` meets this exit. The baseline Coordinator records one
incident and aborts the repeated/no-progress cascade at depth two. A
digest-validated policy patch is first persisted as quarantined, then loaded
into fresh original/family/global/safety candidates; it reduces the matched
cascades to depth one, preserves the successful global path, explicitly
observes uncertain effect before failing safe, persists acceptance, and is
removed by a verified rollback. See `evidence/m8.3-07e406f.md`.

### M8.4: Adaptive Shallow Task Planning - component done

Implement the bounded design in
[Task Intake and Generalist Planner](task-intake-and-planner.md):

The first implementation slice provides immutable `TaskPlan`/`SubgoalSpec`,
separate `PlanProgress`, `TaskPlanValidator`, a flat `PlanningRouter`/
`RuleTaskPlanner`, StateKernel storage, one bounded LM repair, and a controlled
Flat/Always-plan/Adaptive sequencing experiment.

Runtime-first R1 requires fresh strong evidence with explicit identities and
complete mandatory criterion/evidence coverage before a Subgoal or SkillStep
advances. R2 adds bounded `TaskPlanningContext`, evidence/failure/recovery/
environment/budget summaries, monotonic replacement lineage, preservation of
verified subgoals, and an optional real Chromium pricing path through the
normal CLI entrypoint. See
`evidence/runtime-r2-task-planning-context-20260722.md`,
`evidence/runtime-r1-criteria-evidence-20260722.md`,
`evidence/m8.4-task-planning-ablation.md`, and
`current-architecture-audit-20260722.md`.

- route simple tasks to one synthetic subgoal and exact accepted templates to a
  deterministic `RuleTaskPlanner`;
- use `LLMTaskPlanner` only for open-world, multi-stage, cross-application, or
  data-dependent tasks;
- validate rule, LM, parent, and evolution plans through one deterministic
  `TaskPlanValidator`;
- represent 2-8 outcome-oriented subgoals for multi-stage plans with optional
  `depends_on`; simple rule plans retain one outcome, and Runtime executes one
  ready subgoal at a time;
- keep the existing `GeneralistLMPlanner` as the one-action planner inside each
  subgoal;
- let verifier evidence, never planner self-report, advance plan progress;
- reserve task-level replanning for disproved assumptions, exhausted subgoal
  budgets, TaskSpec revision, missing mandatory stages, or repeated-error
  incidents;
- compare Flat, Always-plan, and Adaptive profiles.

Exit: simple tasks retain the flat path; criteria-bound evidence advances only
the matching subgoal; replanning receives environment, evidence, failure, and
budget context; plan version lineage is complete; one real non-BrowserGym
multi-stage task runs through a normal entrypoint; traces distinguish task
planning, action planning, local recovery, and task-level replanning.

This milestone does not add recursive hierarchy, parallel effectful subgoals, a
generic DAG scheduler, one agent per node, continuous watching, or a runtime
framework dependency.

### M8.5: Unified Adaptive Routing and Skill Internalization - component done

Objective: promote the current shared execution shell into one adaptive decision
plane. The same semantic target may have DOM, accessibility, SoM, pure-visual,
WoT, or API grounding candidates. The Runtime selects the most effective
verified route for the active subgoal, safely changes route when evidence
invalidates the first choice, and internalizes repeated verified behavior as
regression-gated semantic skills.

Entry criteria:

- use M8.2B semantic-verification and no-progress failures as diagnostic input,
  but do not gate Runtime architecture on benchmark score or family repair;
- retain M8.3 RecoveryIncident/cascade detection and executable registry
  boundary;
- retain M8.4 verified serial subgoal progress;
- preserve one Coordinator, one authoritative RunState, and one effectful
  ActionContract at a time.

M8.5 implementation baseline (the first two bullets describe retained inputs;
the remaining bullets reflect the current working-tree implementation):

- DOM, SoM visual, and WoT affordances already share the Coordinator,
  ActionContract, verifier, trace, and evaluator path;
- typed `GroundingCandidate`, `UnifiedAffordance`, and `RoutePlan` apply
  deterministic hard gates before backend encoding;
- the Planner names semantic target ids only, and the core `ContractBuilder`
  binds selected single- or dual-target candidates, leases, fingerprints,
  policy, and route identity;
- SVG geometry and observation-time visual candidates share the unified route
  and `VisualContractBinder`; BrowserGym remains a backend encoder;
- recovery re-observes and builds a new immutable contract with candidate
  exclusion when a route is proven bad, plus source/supersession lineage;
- sourced state assertions now retain freshness/provenance, apply
  property-specific rule-first arbitration, block unresolved material
  conflicts at Unified Route, and request bounded coherent active perception;
- deterministic DOM failure now excludes the failed candidate and completes
  through a fresh pixel-grounded visual contract with independent Chromium
  post-state verification;
- conservative fusion keeps ambiguous same-source siblings separate and in
  observation order so ordinal identities are not erased;
- RecoverySkillPayload is executable through an explicitly loaded Runtime
  profile, and TaskSkill mining/execution components pass controlled tests;
  criteria-bound SkillStep checkpoints now exist; canonical persisted trace
  extraction, normal-entrypoint profile loading, and automatic trace-to-skill
  activation remain open.

The target is not a lowest-common-denominator parser. It is one semantic target
with multiple typed, provenance-preserving ways to perceive, ground, execute,
and verify it.

The existing local code, tests, ablation, and Chromium diagnostics prove
important M8.5 components, not the complete generic main path. Runtime-first R3
now closes task-aware perception, ordinary assertions and active perception;
R4 closes target-specific evidence, verifier-backed scoped calibration, and
geometry-aware conservative fusion; R5 closes planner/observation
de-specialization; R6 closes canonical trace mining, replay-bound learning, and
normal-entrypoint profile loading. The prior
completion audit is retained as component evidence, not milestone closure.

#### M8.5A: Unified Target and Route Contracts

Add immutable boundary types:

~~~text
PerceptionRequirements
  required properties: textual, structural, visual appearance, spatial,
  device state
  acceptable evidence kinds
  minimum confidence and verifier strength
  observation, model-call, latency, and cost budgets
  task risk and freshness requirements

SourceObservation
  source and parser identity
  observation epoch and revision
  artifact references
  latency and monetary/model cost
  freshness and calibrated confidence semantics

UnifiedAffordance
  semantic_target_id
  role, label, actions, and accepted semantic state
  unresolved conflicts
  grounding_candidates

GroundingCandidate
  source: DOM, accessibility, SVG geometry, SoM, pure visual, WoT, or API
  typed source-specific payload
  compatible executor
  snapshot and target fingerprint
  supported actions
  confidence, freshness, cost, latency, and evidence references

RoutePlan
  active semantic target
  selected GroundingCandidate
  ordered viable alternatives
  required verifier plan
  hard-gate results, score components, and decision reason
~~~

SemanticEntityResolver aligns candidates only when role/name, action semantics,
container context, and geometry provide sufficient evidence. It retains
separate entities or returns CONFLICT rather than forcing an uncertain merge.
Source-specific payloads remain typed and are never collapsed into one opaque
locator dictionary.

ActionContract continues to represent exactly one selected attempt. RoutePlan,
not a mutable contract, owns alternatives. A fallback re-observes, selects a
fresh candidate, and builds a new contract linked by
`supersedes_contract_id`, `source_contract_id`, and a typed fallback reason.

#### M8.5B: Task- and Environment-Aware Route Selection

Task intake or the active SubgoalSpec derives PerceptionRequirements. The
task/action planner continues to propose semantic intent and target criteria;
it cannot select a raw selector, coordinate, backend, capability, or approval.

PerceptionOrchestrator uses staged, lazy observation:

~~~text
cheap environment/source probe
  -> primary structured observation when suitable
  -> targeted additional source on missing evidence, ambiguity, or conflict
  -> expensive VLM grounding only when task requirements or failure justify it
~~~

Typical policy examples:

- ordinary Web form control: DOM plus accessibility first;
- visual appearance, layout, or vibe: screenshot evidence is primary, with DOM
  metadata as optional support;
- SVG coordinate/spatial target: capture DOM/accessibility, selective SVG
  geometry, and screenshot in one coherent epoch; prefer structured SVG
  grounding when semantics are sufficient and visual grounding otherwise;
- canvas or remote-rendered control: SoM or pure visual is primary;
- authoritative device state/action: WoT or API first, with GUI as fallback;
- safety-relevant cross-source disagreement: active perception or safe
  inconclusive, never arbitrary source precedence.

Route selection first applies deterministic hard gates:

~~~text
source and executor available
snapshot and target current
action kind supported
capability and approval valid
confidence and evidence meet task requirements
required verifier is available
no unresolved material conflict
~~~

Only viable candidates are ranked using calibrated verifier-backed success,
latency, model/API cost, task preference, and risk. Executor receipt success is
not a routing success label. Route statistics update only after postcondition
verification and remain scoped by environment family, action kind, and source.

#### M8.5C: Safe Cross-Surface Fallback

Fallback semantics depend on the phase:

| Failure point | Required response |
| --- | --- |
| no target candidate | activate the next permitted perception source |
| duplicate or ambiguous structured target | use accessibility, SoM, or visual evidence to disambiguate |
| material source conflict | targeted re-observation; unresolved safety conflict blocks execution |
| stale snapshot or fingerprint | rebuild the observation bundle, route plan, and contract |
| executor fails before dispatch | re-observe, then select a fresh alternate route |
| timeout or uncertain external effect | inspect post-state before any retry or reroute |
| verifier is inconclusive | acquire a stronger verifier/source without repeating the effect |
| verifier confirms effect absent | reroute only when idempotency or compensation permits |
| policy or capability denied | never use another source/backend to bypass policy |
| route/recovery budget exhausted | fall through to System 2, ask the user, or abort safely |

Fallback Controller may exclude a failed candidate or source for the current
attempt, but cannot mutate an old contract in place. Every decision, exclusion,
new observation, candidate, contract, receipt, verifier result, and fallback
outcome enters the canonical trace.

#### M8.5D: Complete SVG, SoM, Pure-Visual, and Gesture Routes

Add four bounded ports:

~~~text
SvgGeometryObserverPort
  current SVG/viewport -> viewBox, labelled or marked geometry, bid/role/action
  metadata, coordinate transforms, and evidence references

VisualRegionProposerPort
  screenshot -> regions, OCR descriptors, marks, and rendered overlay artifact

VisualGrounderPort
  raw or marked screenshot plus semantic target -> bounded point, box, or mark

VisualContractBinder
  SVG geometry or visual point/box/mark plus current revisions
  -> typed GroundingCandidate
~~~

SVG collection is selective. Preserve labelled, actionable, BrowserGym-marked,
or task-relevant geometry and its `viewBox`/viewport transform; do not flatten
every decorative path, line, and shape into planner context.

When a TaskSpec or active SubgoalSpec requires `visual + spatial`, the
PerceptionOrchestrator captures DOM/accessibility, SVG geometry when present,
and a screenshot in one coherent observation epoch. Implementations may acquire
them concurrently or serially, but the artifacts must describe the same current
environment state before fusion.

The required end-to-end path is:

~~~text
user task / active subgoal
  -> derive visual + spatial PerceptionRequirements
  -> coherent DOM/accessibility + SVG geometry + screenshot observation
  -> SVG or visual grounding to a point, box, mark, or source/target pair
  -> attach visual/SVG GroundingCandidate to a UnifiedAffordance
  -> RoutePlan selects the viable SVG or visual path
  -> build one fresh ActionContract
  -> BrowserGym mouse_click/drag_and_drop or the bounded VisualExecutor
  -> post-action observation and independent verification
~~~

Extend the semantic action vocabulary with bounded `POINT_ACTIVATE` and `DRAG`
intent. The task/action planner names semantic target ids, or semantic source
and destination ids for drag; it never emits raw x/y coordinates, a mouse path,
selector, or backend. The binder maps a current candidate to:

- `click(bid)` or `drag_and_drop(from_bid, to_bid)` when reliable BrowserGym
  marks exist;
- `mouse_click(x, y)` for a verified point/box candidate;
- bounded `mouse_down`/`mouse_move`/`mouse_up` or an extended VisualExecutor
  only when source and destination are freshly grounded.

The binder validates image dimensions, SVG `viewBox` to viewport transforms,
coordinate space, screenshot/page revision, target fingerprint, viewport
bounds, and blocking overlays. It binds expiration and never grants authority.
The selected candidate then uses normal policy, ContractBuilder, preflight,
post-action screenshot/observation, verifier, trace, and recovery.

The first end-to-end visual/SVG gate must use real Chromium pixels and no hidden
DOM coordinates or task-specific coordinate constants. ScreenSpot remains a
grounding benchmark; it does not by itself prove action execution or
postcondition verification.

#### M8.5E: Verified-Success TaskSkill Mining

Add a second learning stream beside failure evolution:

~~~text
verified successful traces
  -> SemanticTraceNormalizer
  -> repeated sequence clustering and parameter-slot extraction
  -> quarantined TaskSkill proposal

RecoveryIncident and failed traces
  -> Failure/Recovery Miner
  -> RecoverySkill or RecoveryPolicyPatch proposal

both streams
  -> fresh original/family/held-out/global/safety replay
  -> accept, remain quarantined, reject, or roll back
~~~

A TaskSkill stores parameterized semantic behavior:

~~~text
skill id, version, and task trigger
typed parameter schema
ordered outcome-oriented SkillSteps
semantic target query per step
action intent and parameter binding
preconditions and invalidation rules
postconditions and evidence requirements
capability, approval, and risk requirements
source traces, negative examples, and applicability
~~~

It must not store raw CSS/XPath, DOM index, WoT URL, mark id, screenshot
coordinate, browser handle, or approval token. Concrete grounding remains the
responsibility of the current Unified Route Planner.

Mining requires a configurable minimum of independently verified traces. The
first controlled gate uses at least three traces across at least two
layout/environment variants, independent postcondition evidence for every
step, zero policy violations and verifier false accepts, extractable typed
parameters, and a successful held-out replay. Trace count alone never activates
a skill.

TaskSkill execution is incremental:

~~~text
match accepted skill and bind typed parameters
  -> expose one semantic SkillStep
  -> observe and build UnifiedAffordance candidates
  -> choose RoutePlan and build a fresh ActionContract
  -> execute and verify
  -> checkpoint verified skill progress
  -> expose the next step
~~~

A SkillExecutor is therefore not a primitive macro player. It cannot skip
observation, routing, policy, preflight, or verification, and it does not replay
the whole sequence after a later step fails.

#### M8.5F: Recovery Cascade and Skill Failure

TaskSkill and RecoverySkill remain separate artifact types:

| Artifact | Trigger | Payload |
| --- | --- | --- |
| TaskSkill | matching task/parameter pattern | normal semantic subgoal/action sequence |
| RecoverySkill | matching FailureSignature/RecoveryIncident | bounded observe, verify, reroute, ask, compensate, or abort sequence |
| RecoveryPolicyPatch | matching incident rule | one constrained recovery decision |

A skill-step failure records skill id/version, step id, selected route, source
evidence, failure signature, state transition, recovery action, and outcome.
The bounded escalation order is:

~~~text
reobserve
  -> alternate grounding candidate
  -> alternate executor route
  -> replan the current semantic step
  -> abandon the skill and resume System 2 task/action planning
  -> ask user or abort
~~~

Verified progress from earlier steps is retained. Uncertain effects always
cause post-state inspection before reroute. Repeated successful recovery may
propose a RecoverySkill, but it follows the same quarantine and mandatory
replay gate as the existing M8.3 artifacts.

#### M8.5G: System 1, System 2, and Controlled Learning

Accepted TaskSkill plus calibrated route hints form the System 1 normal fast
path. Accepted RecoverySkill/Policy forms a narrow known-failure fast path.
Generalist task/action planning, stronger perception, VLM grounding, and
ask-user handling form System 2.

System 1 still creates fresh contracts and passes all guards. System 2 output
remains a proposal. Online runs may update session-scoped health statistics,
but cross-run TaskSkill, RecoverySkill, AffordanceRule, or RoutingPolicyPatch
activation remains offline, versioned, digest-validated, regression-gated, and
rollbackable.

#### M8.5H: Evaluation

Compare:

~~~text
DOM-only
pure-visual-only
fixed DOM-to-visual cascade
adaptive unified routing
adaptive routing plus accepted TaskSkill
always-System-2 planner
~~~

Required perturbations include healthy DOM, stale locator, duplicate label,
blocking overlay, BrowserGym-marked custom controls, SVG coordinate grids,
SVG viewport transforms, DOM- and visually-grounded drag, canvas-only
controls, visual-property tasks, shifted layout, unavailable visual model,
authoritative WoT state, cross-source conflict, and uncertain effect after
dispatch.

Report at least task success, verifier false accept, constraint violation,
duplicate-effect risk, stale block, route-selection/fallback success,
unnecessary visual-model call rate, latency, model calls, cost, skill activation
precision, skill fallthrough, and regression delta.

Implementation order:

1. add typed GroundingCandidate, UnifiedAffordance, and RoutePlan;
2. derive task-level PerceptionRequirements and add selective SVG geometry
   observation with coherent epoch identity;
3. group real DOM, SVG, and screenshot candidates under semantic targets;
4. integrate VisualGrounder output through VisualContractBinder and
   VisualExecutor;
5. add semantic POINT_ACTIVATE and DRAG binding to current bid/point/box
   candidates without exposing raw coordinates to the planner;
6. make fallback create a fresh route/contract after re-observation;
7. prove DOM failure to visual success, SVG point execution, semantic drag, and
   uncertain-effect no-duplicate paths;
8. add SourceAssertion conflict handling and targeted active perception;
9. add SemanticTraceNormalizer, TaskSkill schema, miner, incremental executor,
   quarantine, and held-out replay;
10. connect skill failure to the existing RecoveryIncident cascade;
11. calibrate route/System 1 policy through the declared ablations.

Exit:

- a normal structured task selects the cheaper structured route without an
  unnecessary VLM call;
- a task requiring visual evidence selects visual perception as primary;
- a real SVG/spatial task derives a current point candidate and completes
  through a fresh, verified mouse contract without planner-authored coordinates;
- a semantic drag binds current source/destination candidates and verifies the
  resulting state;
- a broken/stale DOM route safely completes through a fresh visual contract;
- an authoritative WoT/API candidate can outrank a GUI route when appropriate;
- an uncertain effect never produces a blind duplicate through fallback;
- repeated verified traces create a parameterized TaskSkill candidate that
  passes quarantine and held-out replay, reduces model calls or latency, and
  preserves success and safety;
- a skill mismatch or failed step falls through to System 2 or Recovery Cascade
  without losing verified progress;
- traces and reports attribute perception, grounding, routing, execution,
  verification, skill, and recovery decisions separately.

This milestone does not add a second Coordinator, mutable shared blackboard,
raw action-sequence replay, arbitrary online code mutation, a general
distributed workflow engine, or simultaneous effectful control of one session.

### M8.5R: Runtime-First Completion Sequence

This sequence is mandatory before further benchmark-family repair is promoted
as architecture work. The detailed historical findings and gates are maintained
in `current-architecture-audit-20260722.md`.

R1-R8 remain component evidence. M8.6 supersedes this sequence for default
planner governance, benchmark identity isolation, normal TaskPlan wiring, and
full-phase Recovery Coordinator integration.

1. **Criteria-bound progress — complete:** one CriteriaEvidenceMatcher now
   governs SubgoalSpec, SkillStep, and plan/skill completion; it rejects
   unrelated, partial, stale, weak, or insufficient evidence and traces
   criterion-to-evidence links.
2. **Context-rich task planning — complete:** TaskPlanningContext carries the
   current environment, verified progress, failures, recovery, disproved
   assumptions, budgets, and plan lineage through a normal non-BrowserGym
   entrypoint.
3. **Generic perception orchestration — Runtime exit complete:**
   PerceptionRequirements are derived from TaskSpec/SubgoalSpec and passed
   through Coordinator to BrowserSession; DOM, bounded accessibility, SVG,
   screenshot, visual candidates, sourced assertions, and targeted
   reobservation share fresh coherent epochs. Non-BrowserGym visual-primary,
   DOM-to-visual escalation, persistent-conflict blocking, and real Chromium
   evidence are recorded in
   `evidence/runtime-r3-generic-perception-20260722.md`. Legacy BrowserGym
   observer cleanup was completed by R5 adapter de-specialization.
4. **Target-specific unified routing — complete:** candidates align
   conservatively with semantic and geometry evidence, requirements apply to
   the selected target, and route statistics update only from strong,
   postcondition-verifier outcomes.
5. **Remove benchmark specialization — complete:** BrowserGym attributes and
   action syntax live in its adapter; environment-independent rules use a typed
   SemanticCompilerRegistry with non-BrowserGym and negative-control evidence;
   a source-boundary test rejects benchmark vocabulary in shared modules. See
   `evidence/runtime-r5-despecialized-planner-dom-20260722.md`.
6. **Complete Harness Learning — complete:** canonical JSONL causality and
   strong evidence are validated before semantic extraction; cross-variant
   traces mine parameterized quarantined TaskSkills; replay binds source,
   report, and payload digests; accepted TaskSkill and RecoverySkill profiles
   load explicitly in normal entrypoints. See
   `evidence/runtime-r6-canonical-harness-learning-20260722.md`.
7. **Reproducible public evaluation — complete:** separate compatible Web and
   BrowserGym dependency profiles use the fixed Python 3.12 environment;
   current-HEAD smoke, PR, diagnostic, nightly, and residual release evidence
   is frozen at clean `7e1c7db`. See
   `evidence/runtime-r7-clean-public-evaluation-20260722.md`.
8. **Contain modules after semantics stabilize — complete:** stateless
   TaskPlanFlow/TaskPlanLifecycle, PerceptionSession, ContractExecutionLoop, and
   RecoveryHandler collaborators now own immutable plan preparation/validation,
   observation-port acquisition, stateless contract stages, and read-only
   recovery assessment respectively, while Coordinator and StateKernel retain
   all authoritative mutation, budgets, approval consumption, incident updates,
   and trace order. Generalist PlannerContextBuilder is now separate with its
   context-policy version and public compatibility function unchanged. The
   ordered default SemanticCompiler profile now has a typed declarative factory
   outside the planner; Generalist injects the existing semantic algorithms
   through a callback bundle and retains its compatible public entrypoint. A
   stateless PlannerModelOrchestrator now owns provider-neutral structured
   generation, dynamic candidate schemas, and bounded repair while Generalist
   retains Prompt/model configuration, call-budget reservation, semantic
   policy, proposal binding, fallback order, and trace assembly. BrowserGym
   observation capture, metadata normalization, drag-geometry enrichment, DOM
   candidate refresh, and visual candidate fusion now live in an adapter-owned
   observer module while the bridge facade preserves its imports. BrowserGym
   contract/action, gesture, point, native-value, and verifier encoding now
   also live in an adapter-owned encoder module; Core still owns semantic
   gesture binding and preflight. BrowserGym episode execution/process isolation,
   protocol metadata, FailureEnvelope taxonomy, and aggregate reporting are now
   separated while matrix scheduling/checkpoints remain cohesive. The final
   ownership audit confirms no additional authoritative state/trace writer and
   preserves facade identities. See
   `evidence/runtime-r8-task-plan-lifecycle-20260722.md`,
   `evidence/runtime-r8-perception-session-20260722.md`,
   `evidence/runtime-r8-contract-execution-loop-20260722.md`,
   `evidence/runtime-r8-recovery-handler-20260722.md`,
   `evidence/runtime-r8-planner-context-builder-20260722.md`,
   `evidence/runtime-r8-default-semantic-registry-20260722.md`,
   `evidence/runtime-r8-planner-model-orchestrator-20260722.md`,
   `evidence/runtime-r8-browsergym-observer-20260722.md`,
   `evidence/runtime-r8-browsergym-encoder-20260722.md`,
   `evidence/runtime-r8-browsergym-episode-runner-20260722.md`,
   `evidence/runtime-r8-browsergym-report-20260722.md`, and
   `evidence/runtime-r8-closure-20260722.md`.

   **Completed R8 registry slice:** moved only the declarative default
   semantic-compiler registry assembly (rule order, applicability declarations,
   evidence, operation classes, output kinds, and negative examples) behind a
   typed factory. Semantic compilation algorithms remain in the Generalist
   planner pending an ownership review, and its public registry entrypoint
   remains compatible. Direct generic tests freeze rule precedence and
   metadata, reject empty/unsupported contexts, and retain the existing
   non-BrowserGym DOM integration proof without invoking a benchmark adapter.

   **Completed R8 model-orchestration slice:** isolated provider-neutral model
   invocation and bounded schema repair behind a stateless collaborator. The
   public candidate schema remains field-for-field equivalent; Prompt/model
   configuration, call-budget reservation, structured-error handling,
   compiler-before-model order, proposal binding, and planner-context trace
   payload remain unchanged. Direct provider-neutral tests cover first-pass
   success, one repair on the same context, exhausted semantic validation,
   provider schema failure, and call-budget exhaustion.

   **Completed R8 BrowserGym observer slice:** mapped observer, action encoder,
   episode runner, and report/checkpoint dependencies, then extracted the
   cohesive adapter-owned observation component. Public facade imports,
   observation metadata, coherent-epoch retry bounds, geometry-derived target
   fingerprints, unified candidates, and visual fallback semantics remain
   compatible. Scheduling, circuit-break, resume, CLI/report, executor, and
   shared Runtime code were not changed.

   **Completed R8 BrowserGym encoder slice:** moved backend contract/action
   encoding, semantic gesture-to-`drag_and_drop`, current-viewport point
   conversion, native date/time value conversion, and action verifier mapping
   into an adapter-owned module. Core retains dual-target gesture validation,
   leases/fingerprints, route/policy/capability decisions, and preflight;
   BrowserGym retains `bid`, coordinate, and action-string translation. Bridge
   imports remain compatible and incomplete backend bindings fail closed.

   **Completed R8 BrowserGym episode-runner slice:** extracted one-episode setup,
   Coordinator traversal, backend execution, external-policy lifecycle, and
   killable child-process timeout/exit/cleanup handling into an adapter-owned
   runner module. Keep breadth-first suite scheduling, frozen-run identity,
   checkpoints, circuit breaking, FailureEnvelope aggregation, and report
   publication outside this component. Preserve the bridge facade and all
   typed result fields; add no task/family dispatch and no second Runtime state
   owner. The facade retains compatible exports; direct tests prove timeout
   termination, queue cleanup, and worker-exit diagnostics. See
   `evidence/runtime-r8-browsergym-episode-runner-20260722.md`.

   **Completed R8 BrowserGym report/taxonomy slice:** separated protocol metadata,
   FailureEnvelope construction/clustering, aggregate report publication, and
   checkpoint/scheduling machinery without changing the three-layer run
   protocol. For tasks outside the fixed nightly manifest, derive a bounded
   observed-action capability family from episode evidence; retain an explicit
   unresolved family when no action evidence exists. Do not infer families from
   task-name branches and do not rewrite the completed frozen release artifact.
   Matrix compatibility exports remain stable; scheduling/circuit state and
   atomic checkpoints remain in the matrix component. See
   `evidence/runtime-r8-browsergym-report-20260722.md`.

Runtime-first acceptance requires, for every benchmark-discovered repair:

~~~text
generic invariant
  -> unit test without BrowserGym import
  -> non-BrowserGym integration proof
  -> negative control and safety proof
  -> BrowserGym adapter conformance
  -> targeted and breadth benchmark confirmation
~~~

BrowserGym-only success cannot close M8.4, M8.5, or any future architecture
milestone. The benchmark remains an external pressure test of the Runtime main
path.

### M8.6: Generalist Planner, Active Perception, and Full-Phase Recovery Governance - internal gate done

The implementation freeze remains valuable component evidence, but the closure
audit found unmet behavioral and containment gates. The authoritative execution
sequence and exit gates are in Section 0,
[Active Perception and Online Recovery Architecture](active-perception-and-online-recovery.md),
and the
[Planner, Recovery, and Benchmark Governance Audit](planner-recovery-governance-audit-20260723.md).
This milestone supersedes benchmark-family repair as the current work order.
G0-G4 remain accepted only at their documented component-evidence scope. The
reopened G2.5, G3 injectable path, first responsibility-containment ratchet, and
G5 fresh immutable four-profile Runtime evidence pass for `c939051`. M8.2B has
completed a strict frozen diagnostic at 24/60; the result and prior
compatibility/legacy evidence remain unpromoted.

### M9: Durable Single-Run Recovery - conditional

Promote only after restart, approval-wait, or uncertain-effect tests expose a
real need. Use a simple durable store for run state, events, idempotent commands,
and effect inspection. Do not add a worker pool or distributed queue.

### PiP Decision Gate

PiP remains optional. It is an observer/human-takeover UI, not browser isolation
or a second runtime. Begin it only if M7 testing shows trace streaming and the
normal run console are insufficient.

## 11. Explicitly Deferred

- durable run queue and scheduler
- browser worker pool and independent browser RPC
- worker lease, heartbeat, and fencing token
- distributed checkpoint and takeover
- multi-tenant authorization and quotas
- Kubernetes, Kafka, or a distributed event bus
- multiple planners competing online for one browser session
- multiple agents controlling the same page
- unrestricted cross-run vector memory
- automatic arbitrary source-code mutation
- continuous watcher until it beats post-action observation
- Picture-in-Picture implementation before the M4 entry conditions and a
  demonstrated standalone or human-takeover use case

These remain available in the complete blueprint. They become current work only
after a measured bottleneck, a scenario requirement, and an explicit project
plan update justify them.

## 12. Governance and Correctness Gates

### 12.1 Evidence Boundary

The external review and follow-up plans for the earlier C009 modular-action
repository are historical inputs, not reviews of this repository. They are
used only as governance principles and as a source of selectively migrated
components. Concrete statements about Affordance Runtime must be supported by
this repository's current code, tests, traces, and benchmark artifacts.

Applicable historical principles:

- composition evidence is stronger than disconnected component demos;
- a selected recovery action is not implemented until the main loop executes
  and verifies it;
- state, routing, and trace truth require one canonical owner;
- confidence and fusion claims require provenance and calibration data;
- visual and public-benchmark claims must identify real assets, scored paths,
  and limitations;
- each metric identifies episodes, denominator, environment, planner, and
  commit.

These principles do not imply that old C009 defects exist here and do not
justify merging the two runtime architectures.

### 12.2 Current Correctness Queue

| Priority | Finding | Required correction |
| --- | --- | --- |
| done (R1) | Subgoal and SkillStep progress previously accepted unbound evidence | shared matcher now requires explicit, fresh, strong, complete criterion/evidence links; see `evidence/runtime-r1-criteria-evidence-20260722.md` |
| P0 | the initial Coordinator path records the same observation twice | record it once and increment state and budget counters once |
| done (R2) | replacement plans previously lacked a monotonic plan-version chain | accepted replacements now increment version, bind supersession, preserve verified subgoals, and trace lineage |
| P0 | recovery can select compensation, retry, or reroute without an explicit executed recovery command | add a bounded RecoveryExecutor with receipt, post-state inspection, and verification |
| P0 | Web and BrowserGym intentionally require incompatible Playwright versions | publish and test separate core, Web, BrowserGym, and visual commands |
| done (R2) | task replanning previously received insufficient failure, evidence, and environment context | bounded TaskPlanningContext and monotonic lineage now drive initial planning and replanning |
| P1 | RunCoordinator is approaching a god-object boundary | extract task-plan lifecycle, contract execution, and recovery collaborators without another state owner |
| P1 | core affordance payloads still accept untyped dictionaries | migrate boundary payloads to a tagged surface union |
| P1 | working state can retain unbounded observations and receipts | retain current references and bounded summaries; keep full history in trace and artifact stores |
| P1 | controlled visual grounding and the unfinished public scorer path are easy to conflate | require official assets and prediction artifacts for public visual claims |

The Coordinator remains the sole state writer. Internal collaborators return
immutable results and may not own a second run state, event log, or execution
authority.

### 12.3 Selective C009 Reuse

Reuse is accepted only when it strengthens the current contract-driven loop
without importing a second runtime.

Candidates for bounded migration:

- sourced state assertions, explicit conflicts, and rule-first arbitration;
- active re-observation when evidence conflicts or confidence is insufficient;
- stable state fingerprints and affordance keys;
- Thing Directory and real node-wot discovery;
- backend confidence and cost calibration plus safety-gated reflex lookup;
- chaos injection and oracle-backed calibration fixtures;
- checkpoint/restore verbs and supervised takeover semantics.

Do not migrate:

- the complete ContinuousInteractionManager;
- the old goal-plan-primitive-action authority chain;
- smart-room-specific routing policy;
- duplicate planner/router namespaces or a second CognitiveMap;
- browser-context isolation described as Picture-in-Picture;
- proposals activated without fresh replay acceptance;
- probabilistic fusion before labelled calibration data exists.

If multi-source evidence is added, it follows:

    Observation
      -> SourceAssertions
      -> rule-first arbitration
      -> accepted evidence or unresolved conflict
      -> AffordanceSnapshot

It does not create a second mutable world model. A transition view is derived
from the canonical trace and links pre-snapshot, contract, backend, receipt,
post-snapshot, verification, recovery, and fault context.

### 12.4 Historical Governance Queue and Horizontal Admission

The queue below records the earlier ordering rationale. It is not a unified
refactor prerequisite. Current changes are admitted through the always-active
[Horizontal Architecture Governance Track](architecture-governance-track.md);
only the violating change is blocked. Remaining items below are selected when
their owning milestone or correctness slice is active.

#### G0: Correctness and Claim Integrity

- close the P0 findings;
- split and verify outstanding benchmark and visual changes;
- label every capability implemented, experimental, planned, or deferred;
- make each reproduction command name one compatible dependency profile;
- bind result claims to commit, planner/model manifest, task manifest, and
  generated artifacts.

Exit: each documented profile works from a clean checkout, every implemented
claim has executable evidence, and partial recovery or visual paths are not
presented as complete.

#### G1: Architecture Containment

- extract TaskPlanController, ContractExecutionEngine, and RecoveryExecutor as
  internal collaborators;
- retain one RunCoordinator, one RunState, and one canonical task-execution
  trace within that Runtime scope;
- add versioned planning context and typed surface payloads;
- bound working-state growth.

Exit: no collaborator can execute outside an Action Contract and no duplicate
authority is introduced.

The active growth, long-method, dependency, and authority baselines are owned by
the horizontal track and executable architecture tests; historical line counts
in this section are not current ceilings.

#### G2: Environment Truth and Transition Evidence

This historical governance section is now governed by
[Active Perception and Online Recovery Architecture](active-perception-and-online-recovery.md).
Its foundations are retained, but M8.6 G2.5 defines the completion boundary and
execution order.

- add sourced assertions with provenance, timestamp, confidence, and artifact
  references where multi-source reasoning is needed;
- add rule-first conflict arbitration and targeted active perception;
- derive transition records from canonical trace events;
- calibrate confidence and routing with fault injection and independent
  oracles;
- extend real WoT discovery without making it the primary product line.

Current status: DOM, visual, and WoT adapters already share the Affordance,
Action Contract, Coordinator, verifier, and trace path. SourceAssertion,
FusedAssertion, rule-first arbitration, ActivePerceptionRequest, and targeted
capture foundations are implemented. `ActivePerceptionController` and
`ActivePerceptionFlow` now provide typed probe planning/resolution with bounded
normal/preflight/verification/recovery integration. Held-out calibration and
empirical effectiveness remain open; no additional controller may be added as
a parallel authority.

##### G2A: Sourced Assertions and Rule-First Arbitration

Deliverables:

- add typed SourceAssertion with entity/property identity, typed value/unit,
  source, observed time, freshness, confidence semantics, parser version, and
  artifact reference;
- normalize DOM, accessibility, visual, WoT, and API evidence into comparable
  property assertions without discarding source-specific payloads;
- add a property-level source policy rather than a global DOM/WoT/visual
  priority;
- return ACCEPTED, CONFLICT, REOBSERVE, or INCONCLUSIVE;
- keep raw assertions and the arbitration decision in the canonical trace;
- allow only accepted state to enter target fingerprints, preconditions, and
  verifier inputs.

Exit: agreeing sources produce one provenance-preserving accepted view; stale
evidence is rejected; a material DOM/WoT or DOM/visual disagreement cannot
silently reach an effectful contract.

##### G2B: Targeted Active Perception

Deliverables:

- map each unresolved property conflict to permitted probes such as refresh DOM,
  repeat accessibility capture, recapture screenshot, repoll WoT, or query an
  independent fixture/API oracle;
- bind every probe to observation, time, and recovery budgets;
- re-run arbitration after each probe;
- return a safe inconclusive result when the conflict survives the budget;
- trace the original assertions, selected probe, new evidence, and final
  resolution.

Exit: at least one injected stale-source case resolves after a targeted probe,
and one irreducible safety-relevant conflict blocks execution without an
arbitrary source winner.

##### G2C: Gated System 1 Fast Path

Entry:

- G2A and G2B are complete;
- source confidence and routing thresholds have held-out calibration evidence;
- an accepted skill or grounding has stable semantic identity and invalidation
  rules.

Deliverables:

- add a small ReflexPolicy/cache keyed by accepted skill, surface semantics, and
  backend rather than raw selector alone;
- require current snapshot lease, matching target fingerprint, no unresolved
  source conflict, calibrated confidence, valid capability/approval, and an
  available verifier;
- create a fresh Action Contract and run normal preflight even on a cache hit;
- invalidate cached grounding after stale state, execution failure, verification
  failure, policy change, or incompatible task/surface revision;
- record cache hit, routing latency, validation outcome, success, and
  invalidation reason.

Exit: the gated path reduces median planning/grounding latency on repeated safe
tasks without increasing stale execution, verifier false accepts, constraint
violations, or unsafe side effects relative to the always-deliberative
baseline.

##### G2D: System 2 Escalation Integration

System 2 reuses the existing GeneralistLMPlanner, TaskPlanner, stronger
observation, bounded recovery, and ask-user/abort paths. It does not introduce a
second Coordinator or execution runtime.

Trigger it for:

- new or complex tasks without an exact accepted skill;
- missing or low-confidence grounding;
- unresolved source conflict;
- stale snapshot or failed precondition;
- unavailable backend;
- failed or inconclusive verification;
- repeated recovery or no-progress incidents;
- high-risk actions requiring clarification or approval.

The escalation payload contains current TaskSpec/subgoal, accepted and
conflicting evidence, available affordances, failed contract/receipt,
verification report, remaining budgets, and an allowlist of probes or recovery
actions. System 2 output remains a proposal and must pass the normal validator,
ContractBuilder, policy, preflight, execution, and verification chain.

Exit: traces distinguish fast-path acceptance, fast-path rejection, active
perception, action replanning, task replanning, recovery, and human escalation.
A controlled comparison reports always-System-2 versus gated-System-1/System-2
success, safety, latency, model calls, and recovery rate.

Do not migrate the legacy ContinuousInteractionManager or its mutable
CognitiveMap. Implement these stages as bounded modules under the current
single-writer Coordinator.

Exit: a reproducible trace shows conflicting sources causing re-observation and
either evidence-backed resolution or a safe inconclusive result.

#### G3: Public Evaluation and Controlled Evolution

- expand agentic MiniWoB separately from scripted runtime tests;
- score official ScreenSpot assets only with real prediction artifacts;
- provision WebArena-Verified and WASP before reporting suite results;
- add WorkArena when authorized access is available;
- require original, family, global, and safety replay before activating an
  evolution artifact;
- retain calibrated heuristic arbitration unless held-out data demonstrates a
  benefit from more complex fusion.

Exit: public results are reproducible, planner and runtime failures remain
attributable, and accepted patches do not regress mandatory safety suites.

### 12.5 Claim and Change Rules

1. A class, schema, proposal, or selected enum is not an implemented capability
   until the Coordinator path consumes it.
2. A recovery action requires an execution receipt and post-recovery
   verification.
3. A subgoal completes only from evidence matched to its own obligations.
4. A public benchmark result names the official evaluator and scored path.
5. A synthetic or controlled fixture remains labelled as such.
