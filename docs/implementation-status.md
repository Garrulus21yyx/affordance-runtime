# Implementation Status

> **Lifecycle:** CURRENT IMPLEMENTATION TRUTH
> **Updated:** 2026-08-15
> **Current reviewed M4.5-B closure SHA:** `NONE`
> **Target:** [Target AgentLoop Authority Map](task-execution-authority-map.md)

## Status vocabulary

`NOT_STARTED` → `PROTOTYPE_EXISTS_NOT_ADMITTED` → `INTEGRATED_NON_DEFAULT` →
`DEFAULT_CUTOVER` → `DELETED`. “Implemented” below never implies default
cutover unless stated explicitly.

## Current truth

The old transactional `Coordinator → RuntimeDelta → RuntimeCommitter →
StateKernel` product path is physically deleted. The product/module entrypoint
and root public façade terminate at `TargetRuntime -> AgentLoop ->
AgentRunSession`; benchmark-only commands have a separate entrypoint.

The target GUI `AgentLoop` starts from `TaskGoal + IntentContext`, observes before any
page target identity exists, and uses the current `WorldObservation ->
ActionSpace -> AgentContext -> AgentDecision` chain. The incorrectly imported
`LLMIntentCompiler -> TaskSpec -> StrictTaskPlanner -> TaskPlan` start path,
hidden policy preparer capability, semantic-control mode, AgentLoop TaskProgress,
and execution-control projection are deleted. T3 also deleted the separate
workflow TaskSpec/TaskPlan/Coordinator owners and the dormant
`LocalObjectiveProposalPort` source branch after it was found to duplicate
planning and stop action selection before GUI use. The recurrent Agent decision/tool schema is
action/control-only, and the ordinary target loop has one model reasoning
phase. Fresh live benchmark revalidation remains open.

The current grounded policy no longer has a mandatory task-state updater or a
separate model-authored working-memory envelope. `AgentContext` is the only
internal context owner. A single YAML-backed binder projects its original task,
fresh Unified World, progress, bounded action/effect history, pending state,
budgets and control feedback once, alongside current public tools. The catalog
owns only tool schemas and opaque Runtime bindings. Grounded adapters receive
the typed context directly; legacy serialized context is produced only for
legacy adapters that declare they require it. Focused tests, the full
`1589 passed, 27 skipped` suite, Ruff and mypy pass. This implementation has not
received a fresh live benchmark run.

The current working tree implements the first shared interaction-onboarding
skeleton slice for existing actions. `ContextBuilder` closes each current
candidate once over canonical operation, complete bounded target semantics and
grounding, exact business schema, destination mode and complete destination
candidates, consequence projection, and its private current action lookup
identity. It no longer computes a final selector.

`GroundedToolCompiler` is the sole owner of concrete destination-row expansion,
technical partitioning, recursive shared semantic skeletons, deterministic
minimal facets, Cartesian versus sparse tuple handling, flat public `ToolSpec`
construction, and the private exact-resolution table. Required destinations
expand only admitted pairs; optional mode and empty required domains fail
typed. Semantic fields are preferred; E-ref fallback requires complete,
injective, same-context rendered grounding and fails typed on missing,
duplicate, stale, or unrendered refs. Business schemas are copied generically
without verb-specific branches or parameter renaming.

The action provider envelope now contains task/progress, bounded transition and
history, one source-lineage-preserving `ActorWorldSnapshot`, screenshot grounding, flat tools,
and bounded Runtime feedback. It contains no candidate records,
`actions.entities`, `actions.groups`, action IDs, private destination tables, or
resolver entries. The provider binder does not regroup candidates. Resolution
validates the exact emitted schema and queries only the private compiler table;
ordinary still-current ActionSpace admission/currentness/binding/execution is
unchanged. BrowserGym ActionSpace semantics are now `activate`, `type_text`, and
`select_option`, while `click`, `fill`, and `select_option` remain adapter-private
primitives.

The Actor environment representation is now separated from tools; its
single-source BrowserGym structure path is implemented.
BrowserGym retains a bounded public AX structural document in each structural
`SurfaceObservation`, including structure-only containers that have no binding
and cannot enter `ActionSpace`. On the implemented single-source path,
`ContextBuilder` projects that document, current semantic targets, inline
public state/fact evidence, source coverage, conflicts, artifacts and aligned
media exactly once into `ActorWorldSnapshot`. Semantic
targets use current E-refs; context-only nodes use non-callable N-refs. The
grounded binder serializes this snapshot and compiled ToolSpecs without
candidate/world deduplication, actionable-node removal, fact removal, or relation
regrouping. The internal `ModelWorldView` remains a bounded construction input
and is not a second grounded Actor payload.

BrowserGym raw screenshots are now an independently offered visual observation
source even without region, disambiguation or classification providers. Raw
capture contributes media only and cannot create targets, bindings or action
authority. The structure-first transport attaches media only after the fresh
world contains the selected visual source. Grounded provider schema failures
retain bounded redacted validation paths/codes and repair outcome in telemetry;
raw provider payloads remain absent.

Multi-source observed-world convergence remains open. `WorldObservation`
already retains source envelopes, BrowserGym retains source-local AX structure,
and `ActorWorldSnapshot` is non-flat; those owners are not being replaced.
However, `_source_memberships()` applies source correspondence while
`_structure_documents()` still resolves a structure node's source-local
`semantic_target_id` directly against canonical visible IDs. A corresponded
multi-source node can therefore lose its canonical E-ref/state/facts. The
accepted `_canonical_maps()` output is not retained on `WorldObservation`, so
downstream helpers can reconstruct only part of it; fused source media is also
canonicalized while the rest of its source envelope remains local. The current
`EntityCorrespondence` is trusted input rather than a proposal with a typed
accept/reject/conflict decision. The current
fusion maps and coverage are keyed by `surface`, so multiple source instances
from one adapter are not yet a closed case. Target/state merging still retains
the first input claim while recording a conflict, and therefore does not meet
the designed source-permutation/predicate-authority invariant. The current
per-source document renderer does not yet prove one Actor entity node or the
closed primary/novel-lens policy under agreeing DOM/AX/visual sources. Accurate
status is
`SOURCE_ENVELOPE_RETAINED / SINGLE_SOURCE_STRUCTURE_IMPLEMENTED /
MULTISOURCE_CORRESPONDENCE_AND_DEDUP_OPEN`.

The accepted design keeps the existing
`SurfaceObservation -> WorldFusion -> WorldObservation -> ActorWorldSnapshot`
chain and requires one correspondence rewrite, evidence-preserving canonical
coalescing, a typed predicate/source-profile policy, typed alignment outcomes,
source-instance keys, source-local structural lenses, and one bounded
Actor node per canonical entity. The accepted map will be materialized once as
`WorldObservation.entity_source_links`; downstream reconstruction and the
parallel fusion-result provenance authority will be removed. BrowserGym/
Playwright and future established
platform accessibility/OCR providers remain the source engines; no parallel
fusion pipeline, parser, detector, graph store or automation framework is
authorized. Current `1589 passed, 27 skipped` evidence does not cover these new
multi-source properties.

A.1 closes canonical identity and Actor entity-node duplication. It does not
claim that agreeing `StateFact`/future `RelationFact` rows are coalesced; that
canonical claim/evidence migration remains Step 15 and may not be simulated by
a temporary Actor-only dedup path.

Focused compiler/grounded-tool, BrowserGym world/vision, acquisition, lattice,
legacy serialization and model-policy tests pass; full `1589 passed, 27 skipped`,
Ruff, and mypy pass locally. No fresh live benchmark was run; the historical
clean `b6e0546` grid witness remains prior evidence and does not attest this
working tree or replace the pending five-case gate.

Wave-A interaction ownership and its closure repair are implemented for the
existing target actions.
One immutable, code-versioned `InteractionCapabilityRegistry` owns canonical
action names, subject kinds, parameter families, destination modes, and
permitted verification families. DOM, Visual, WoT, and BrowserGym static
support resolves through adapter-local profiles and exact primitive
translators; profile support alone creates no binding or ActionSpace member.
The registry defines six additional semantic actions. `set_value` is not a new
future binding: the pre-existing generic WoT `write_property` route is restored
and derives its `value` contract from the current native boolean/string/number
property schema. `scroll`, `press_key`, `focus`, `drag_to`, and `hover` remain
semantic-only and are not currently offered.

Business schemas now pass unchanged from `ActionBinding` through
`ActionOption`, `AgentActionOptionView`, flat `ToolSpec`, exact resolution and
ActionSpace admission. Selector fields remain compiler-owned and private route
identity remains outside model schemas. Required, forbidden, unavailable, and
unsupported optional destination states fail closed without synthesizing an
empty destination.

`ProviderCallNormalizer` owns provider wire normalization and same-catalog
representation reconciliation. `name/op` and `arguments/args` aliases are
transport tolerance only. Cross-tool normalization requires one exact current
row plus a catalog/context-bound authority-equivalence digest covering
canonical action, business schema, subject/destination mode, effect, risk,
consequence, reversibility, observation barrier, and verification contract.
Unknown, invalid, owner-mismatched, ambiguous, non-equivalent, and stale calls
are typed. The four tool-intent failures with `did_you_mean` enter one bounded
same-model re-emission; its complete call is normalized again and must resolve
exactly. No second tool-intent repair or subsequent argument repair is allowed,
so dispatch remains zero until the repaired call passes exact resolution.
The post-normalizer resolver is exact and reads no world state. Normalization
telemetry retains distinct raw and normalized operation names.

`VerificationContract` is now a sealed action-specific value over its registry-
permitted family, parameter-schema digest, semantic effects and observation
barrier. Its digest is mechanically conserved from binding through option and
selection and participates in catalog authority equivalence, route selection
and currentness. This closes the Wave-A foundation; migrating every evaluator
obligation to richer concrete postconditions remains a later bounded slice.

The old shared vocabulary module, candidate click/fill/select canonicalizer,
BrowserGym singleton role fields, and embedded catalog normalizer are deleted.
Private backend primitives and provider wire aliases remain because they own
execution mechanics and transport representation, not semantic authority.

Canonical state cutover remains
`IMPLEMENTATION_PARTIAL / STATEFACT_DUAL_WRITE_NOT_ADMITTED`. Construction now
rejects contradictory overlapping target-state/fact values. Tool compilation
does not reverse-delete referenced Actor nodes/facts, but `max_facts` and
per-target projection budgets may still truncate them with truthful metadata.
DOM, Visual, WoT, HTTP JSON, BrowserGym, fusion, and
benchmark-support producers still dual-write `SemanticTarget.state` and
`StateFact`; no full facts-first claim is made and no new interaction state is
admitted. See the
[Wave-A consumer inventory](evidence/2026-08-14-interaction-capability-wave-a-consumer-inventory.md).

P5-M4.6-F P0 is implemented locally and full-verified. `ControlTransition`
captures the matching decision-start `before_task_evaluation` as a root fact;
`ContextBuilder` deterministically projects only the latest root into a bounded
`AgentTransitionDigestView` and stores it in disposable
`AgentContext.last_transition`. The view contains previous decision, execution,
effect and task/criterion/output status transitions. The latest root is not
also rendered in older `history`. Existing confirmation and user-input
continuation reducers replace the same root slot and consume its identity once.
There is no `RuntimeTransitionDigest`, retained digest store, model call,
working memory, updater, canonical world graph delta or semantic ActionSpace
delta. Ruff, mypy and the full `2485 passed, 27 skipped` suite pass; live
benchmark evidence remains unverified.

The target path now has:

| Capability | Status |
|---|---|
| TaskGoal / EvaluationSpec | `INTEGRATED_NON_DEFAULT` |
| target thin intake / composition | `INTEGRATED_NON_DEFAULT`; closed intake outcomes and one `TargetRuntime` composition root are used by target/model-conformance benchmarks |
| AskUser task-revision continuation | `INTEGRATED_NON_DEFAULT / OFFLINE_VERIFIED`; typed pending identity, full re-intake, exact +1 revision, environment no-reset update, one-shot control continuation, and stale projection invalidation |
| canonical workflow TaskPlan / StepSpec contracts | `DELETED_WITH_LEGACY_RUNTIME_T3`; no AgentLoop ingress or compatibility projection remains |
| TaskFrontier / VerifiedTaskState / RequirementHypothesis | `DELETED_FROM_AGENTLOOP`; displaced duplicate semantic owners |
| WorldObservation / AgentWorldView / ActionSpace | `INTEGRATED_NON_DEFAULT`; exact option/binding-group fidelity and source/world currentness closed |
| Wave-A InteractionCapability owner spine | `IMPLEMENTED_WAVE_A_CLOSURE / EXISTING_ACTION_OWNER_SPINE / WOT_SET_VALUE_RESTORED / MODEL_REPAIR_CONNECTED / VERIFICATION_CONTRACT_FOUNDATION_IMPLEMENTED / STATEFACT_CUTOVER_PARTIAL / LIVE_NOT_RUN`; old vocabulary/canonicalizer/embedded-normalizer owners deleted; five not-yet-produced actions remain semantic-only |
| Target Runtime physical topology | `T0_COMPLETE / T1_COMPLETE / T2_COMPLETE / T3_COMPLETE / T4_COMPLETE / T5_READY / WAVE_A_ADMITTED`; target-only API/product CLI and sole `app/TargetRuntime -> agent/AgentLoop -> AgentRunSession` lifecycle implemented; reusable BrowserGym mechanics have one `surfaces/browsergym` owner while MiniWoB admission/verifier policy remains benchmark-owned; 335 production Python files remain, including only 4 bootstrap/cross-cutting files at package root and 113 under benchmarks; displaced paths are guarded by physical-absence/import redlines |
| WorldEnvironment independent capture | `INTEGRATED_NON_DEFAULT / CLOSED_M4_5_A`; environment-owned capabilities and offers admit typed capture without consulting AgentContext |
| post-action observation | `INTEGRATED_NON_DEFAULT / CLOSED_M4_5_A`; `ExecutionOutcome` carries the typed after acquisition and normal evaluation performs no second capture |
| ObservationAcquisition / ExecutionOutcome target contracts | `INTEGRATED_NON_DEFAULT`; reset, independent capture and post-action origins distinguish acquired, unavailable and failed |
| ActionIntent / BoundActionRequest / ActionResult | `INTEGRATED_NON_DEFAULT`; admitted selection identity retained through binding |
| Evaluator-owned completion and bounded transition state | `INTEGRATED_NON_DEFAULT`; evaluations are retained on canonical ControlTransition values |
| lossless ControlTransition | `INTEGRATED_NON_DEFAULT / REOPENED_CONVERGENCE_REVIEW / IMPLEMENTED_NOT_VERIFIED`; every accepted decision owns one root slot whose immutable value may be replaced/finalized exactly once by its admitted confirmation continuation; terminal exceptions latch the session; ordered execution/acquisition/probe/evaluation facts are monotonic |
| local ProgressController | `CLOSED_FOR_FILL_SELECT_LOCAL_LIVENESS`; other semantic actions are not precondition-contained and this owner is not a planner |
| SurfaceAdapter / UnifiedWorldEnvironment | complete for DOM, Visual-only, and WoT single-surface minimums; semantic fusion pending |
| StaticEnvironment | `INTEGRATED_NON_DEFAULT` on new World contracts |
| real-browser DOM short loop | `INTEGRATED_NON_DEFAULT`, positive C1 proof |
| Visual new-loop vertical | `INTEGRATED_NON_DEFAULT`, positive C2 proof |
| WoT new-loop vertical | `INTEGRATED_NON_DEFAULT`, local-simulation positive C3 proof |
| semantic confirmation continuation | `INTEGRATED_NON_DEFAULT`; typed request/decision, run-scoped session, fresh semantic rebind, single-send consumption |
| P5-D6.1 confirmation/evaluation contract completion | `INTEGRATED_NON_DEFAULT`; effective risk, destination identity, bounded presentation, terminal immutability, policy reselection, evidence lineage, explicit task control |
| P5-M0 model/evaluator boundary | `INTEGRATED_NON_DEFAULT`; model-safe projections, current-world evidence resolution, structured completion and target output integrity |
| AgentContext architecture | `INTEGRATED_NON_DEFAULT / CLOSED_P5_M0_1` |
| P5-M0.1.1 one-shot context epoch | `CLOSED`; monotonic per-session policy generation, stale/page-cycle/replay zero-call |
| ContextIdentity | `CLOSED`; task/observation/action-space/page/progress/pending/generation digest |
| IntentContextView | `CLOSED_FOR_BOUNDED_CONTEXT_ONLY`; always `context_only`, never TaskGoal authority |
| LocalObjective rolling execution | `DELETED_WITH_LEGACY_RUNTIME_T3`; not a current target capability or extension point |
| action paging | `CLOSED_FOR_DETERMINISTIC_CURSOR_PAGER`; traversable Runtime-issued cursor; only current-page IDs admitted |
| source assurance summaries | `CLOSED_FOR_DOM_VISUAL_WOT_PROFILES`; quality metadata grants no action authority |
| criterion adjudicators | `CLOSED_FOR_DECLARED_MINIMUM`; mechanical, semantic, explicit-user and hybrid |
| current M0 model projections | `INTEGRATED_NON_DEFAULT` |
| P5-M1 model policy core | `CLOSED`; canonical context projection, adapter-owned single parse to typed decision, and Runtime admission |
| P5-M1.1 strict decision boundary | `PHASE_CUTOVER_IMPLEMENTED / NOT_LIVE_VERIFIED`; recurrent seven-variant action/control schema is independent from the LocalObjective proposal schema; duplicate/non-finite/depth/node/byte limits and single-parse adapters retained |
| P5-M1.1 existing ModelPort bridge | `CLOSED`; existing transport owner, outer deadline, zero retry/no fallback, typed metadata/failures |
| local HTTP provider-transport proof | `CLOSED`; one request/one execution plus 429/500/schema/deadline zero-call proofs |
| deterministic ActionEvaluator/TaskEvaluator | `RETAINED` |
| production model evaluators | `CLOSED_FOR_INJECTED_AND_LOCAL_HTTP_SEMANTIC_PROPOSAL_PROFILE` |
| mechanical criterion evaluation | `CLOSED_FOR_DECLARED_MINIMUM` |
| user acceptance | `CLOSED_FOR_EXPLICIT_USER_EVIDENCE_PROFILE` |
| action effect applicability | `CLOSED_FOR_STATE_TRANSITION_AND_ARTIFACT_PROFILE` |
| success expression | `CLOSED_FOR_BOUNDED_BOOLEAN_PROFILE` |
| output semantic binding | `CLOSED_FOR_PATH_SHA_ARTIFACT_PROFILE` |
| semantic evidence entailment | `PARTIAL`; model proposals remain evidence-scoped, not general proof |
| P5-M2.1 action verification scope | `CLOSED_FOR_RUNTIME_DERIVED_CRITERION_AND_ARTIFACT_PROFILE` |
| low-risk inconclusive continuation | `CLOSED`; fresh-world continuation, never request replay |
| no-effect verification | `CLOSED_FOR_DECLARED_OBLIGATION_PROFILE` |
| semantic evidence presentation | `CLOSED`; proposal refs equal actually presented catalog refs |
| hybrid component separation | `CLOSED` |
| dynamic semantic readiness | `CLOSED_FOR_TARGET_FACT_AND_OUTPUT_PROFILE` |
| artifact deterministic absence | `DEFERRED`; absence remains UNKNOWN without complete inventory |
| new-AgentLoop benchmark harness | `CLOSED_FOR_INTERNAL_FIXED_MANIFEST` |
| M3.1 machine acceptance | `MEASURED_AND_FAIL_CLOSED` |
| real DOM/Visual/WoT adapter harness | `ATTESTED_LOCALLY` |
| local exact-head report attestation | `AVAILABLE_AFTER_FINAL_CLEAN_HEAD_RUN` |
| remote exact-head internal harness artifact | `AVAILABLE` for reviewed head `d440665`; final-head rerun pending |
| remote exact-head full regression artifact | `WORKFLOW_CONFIGURED`; final-head run pending |
| internal deterministic profile | `ATTESTED` |
| internal scripted-model profile | `ATTESTED` |
| local HTTP model-policy harness profile | `ATTESTED` |
| local HTTP semantic-judge profile | `ATTESTED` |
| live model-policy profile | `EXACT_HEAD_MISTRAL_ATTESTED`; protected executions remain explicitly gated |
| live semantic evaluator | `NOT_REQUIRED_FOR_FIRST_MECHANICAL_EXTERNAL_MANIFEST` |
| external smoke manifest | `REVIEWED_AND_FIXED` for BrowserGym MiniWoB 0.14.3 tasks click-button/enter-text/choose-list |
| external target-loop adapter | `CLOSED_FOR_PINNED_MINIWOB_MECHANICAL_PROFILE` |
| BrowserGym independent capture | `INTEGRATED_NON_DEFAULT / REAL_DEPENDENCY_CONFORMANCE_ATTESTED`; owner-thread read-only current capture refreshes structure/bindings and page-native verifier status; pinned BrowserGym/MiniWoB conformance passes locally |
| external fixed-smoke workflow | `CONFIGURED_AND_MANUALLY_GATED`; execution status is exact-head artifact-backed |
| latest formal fixed-smoke run | see the protected `browsergym-fixed-external-smoke` workflow artifact for the target SHA |
| default cutover | `NOT_READY` |
| RoutePolicy | implemented, post-hard-gate only |
| BindingCache | `PROTOTYPE_EXISTS_NOT_ADMITTED` |
| ActionBatch | helper implemented; not AgentLoop-integrated |
| historical MiniWoB-60 seed-7 run | `VALID_NEGATIVE_EVIDENCE`; clean `b3b64a2`, 6/60 |
| post-M4.4 separately authorized rerun-v3 | `VALID_NEGATIVE_EVIDENCE`; clean `83dc4fa`, 4/60, kept separate from the historical run |
| P5-M4.5-A acquisition lifecycle | `COMPLETE_NON_DEFAULT` |
| P5-M4.5-B control/failure contract | `INTEGRATED_NON_DEFAULT / REOPENED_CONVERGENCE_REVIEW / IMPLEMENTED_NOT_VERIFIED` |
| P5-M4.5-C same-profile MiniWoB-60 diagnostic | `COMPLETE_DIAGNOSTIC / EVIDENCE_VALID_AT_4924CE6 / FORMAL_EXIT_NOT_ATTESTED / PERFORMANCE_NOT_CLAIMED / GENERALIZATION_NOT_CLAIMED` |
| P5-M4.6 evidence-directed short-loop remediation | `EXISTING_ACTION_FLAT_SEMANTIC_COMPILER_IMPLEMENTED_LOCALLY / FULL_VERIFIED_2509_PASS_27_SKIP / LIVE_NOT_RUN / M4.6-A-C COMPLETE_NON_DEFAULT / M4.6-D IMPLEMENTED_NOT_VERIFIED` |
| P5-M4.7 supported-subset multi-seed | `NOT_STARTED / BLOCKED_BY_M4_6_GATES` |
| long-horizon TaskPlan execution | `NOT_STARTED / BLOCKED_BY_BREADTH_GATES` |
| default product cutover | `NOT_STARTED` |

The live DOM, Visual-only, and WoT local-simulation proofs use the same `TaskGoal` factory,
deterministic policy, semantic evaluators, and `activate` vocabulary. Each uses
an offered action ID, exact binding group, one execution, one measured surface
probe, a fresh observation, and evaluator-owned completion. DOM selectors and
Visual screenshot/region/viewport/point data stay inside private bindings.
WoT href, method, security reference, schema, rate metadata, and TD identity
also stay private. Credentials are resolved only inside the HTTP transport.

The live DOM proof uses one `TaskGoal`, a deterministic policy selecting an
offered action ID, an exact eligible-binding group, a selector-private DOM
binding, one execution, one measured live currentness probe, a fresh
observation, and an independent `TaskEvaluator` completion decision. The new
loop does not import or call the old Coordinator, StateKernel, RuntimeCommitter,
ActionContract, or ExecutionReceipt.

## Migrated foundations

- WoT TD security/rate/schema/event-description parsing and the non-default
  target-loop HTTP transport/SurfaceAdapter are implemented.
  Event subscription execution is not implemented and events are not offered
  as executable options.
- WoT read state sources carry public security-scheme, minimum-interval,
  content-type, and property-schema metadata. An unselected scheme is reported
  unavailable without transport fields, and related write/invoke affordances
  are withheld. The proof uses explicitly referenced `nosec` and Runtime
  `LOCAL_SIMULATION`; remote/physical scopes remain HIGH risk.
- SoM utilities and smart-room/mock-web assets are implemented. Grounded-tools
  v2 now reuses the existing bbox/mark/image-annotation primitives through a
  thin current BrowserGym projection; the legacy
  `Affordance/AffordanceLease` path is not restored as an authority. This is a
  model-facing grounding projection over one BrowserGym source, not proof of
  multi-source fusion or visual execution binding.
- Smart-room images use committed lockfiles and `npm ci`. Audit debt remains:
  node-wot 4 vulnerabilities (2 moderate, 2 high); dashboard 2 (1 moderate,
  1 high). Fixes currently require breaking dependency upgrades.

## Proof and remaining gates

The current convergence implementation passes the full local suite:
`2421 passed, 24 skipped`. This is implementation evidence, not live benchmark
closure; exact-head five-case and held-out reruns remain required.

Focused target tests cover source/world/fingerprint stale zero-call, Visual
screenshot/viewport/scroll/DPR/zoom/orientation/region staleness, coordinate
isolation, WoT TD/form/security stale checks, one-probe/one-send, rate limits,
credential isolation, task-forbidden
effect filtering, higher-confidence forbidden-route exclusion, distinct schema
route identity, Runtime-owned risk floors, result lineage, schema values and
unsupported-type rejection, observation/probe budgets, unknown
no-retry, initial zero-op
completion, finish-proposal rejection, receipt/effect separation, private
parameter rejection, observation identity freshness, low-risk-only admission,
bounded turns, real Chromium DOM/Visual completion, and real local HTTP WoT completion.

The instrumented/plain-DOM, Visual-only, and WoT local-simulation minimums are closed; generic business-effect
classification beyond the current coarse categories remains future work. The
new-loop DOM/Visual/WoT adapter-only symmetry is proven for the shared-state
task. This does not prove semantic fusion or physical-device confirmation. Semantic fusion across
simultaneous sources remains future work. Scoped BrowserGym/MiniWoB M4 runs
exist, while general external-suite/cross-platform expansion remains blocked.
Old-core deletion is not admitted.

P5-D is closed on the non-default target path. `ActionEvaluationStatus` now
distinguishes `EFFECT_CONFIRMED`, `NO_EFFECT_CONFIRMED`, `UNKNOWN`, and
`REJECTED`. `AgentRunSession` is process-local only: confirmation always starts
from a fresh observation, matches the semantic subject, binds the current
private route, and consumes confirmation only after `SENT`/`SENT_UNKNOWN`.
Unknown effect waits for the user and never replays automatically.

D6.1 applies the TaskGoal risk floor to the displayed and hashed effective
risk. Semantic destination identity now flows from SelectAction through
ActionSpace admission, ActionIntent and confirmation subject, while current
adapters correctly offer no destination. Confirmation summaries use only the
secret-free world view and bounded/redacted semantic parameters. Terminal
sessions return their original result. A missing exact confirmed subject returns
to policy rather than selecting a Runtime candidate. Confirmed action effects
require exact request/before/after lineage and evidence-ref fields; resolution
against the current WorldObservation is completed in P5-M0.

P5-M0 projects TaskGoal, internal ActionSpace, and bounded transition summaries
into private-payload-free model views while retaining internal ActionSpace as
the sole admission authority. Per-observation evidence indexes resolve action
and task evidence. COMPLETE is deterministically bound to task, observation,
criteria, current evidence, requested outputs, and declared path/SHA-256 checks.
The target loop now has a provider-neutral `ModelBackedAgentPolicy` using one
injected structured call and typed failures. Later exact-head Mistral policy
attestation and pinned BrowserGym runs are revision/profile-scoped; they do not
make the provider a Runtime authority.
TaskEvaluation UNKNOWN waits and BLOCKED terminates explicitly.

Semantic fusion remains deliberately deferred. `AgentLoopState` now retains an
exact accepted-decision total plus a bounded canonical `ControlTransition`
suffix; compatibility `Turn` values are derived read-only. Optional
TurnRecorder remains telemetry-only.
P5-M0.1 now provides the unified disposable AgentContext, ContextIdentity,
bounded context-only intent, bounded model world/progress/pending/budget views,
typed recurrent decisions, current-page paging, explicit-hint relevance and
source-assurance summaries. Criterion adjudication and production evaluator
composition are now closed for declared-minimum profiles. The new-loop harness
and pinned BrowserGym profile have since closed for their declared scopes;
capability-aware independent acquisition is closed on the non-default target
path. WoT effectful rate limiting is implemented; property
read-side scheduling/rate limiting is not implemented.

P5-M0.1.1 closes the operational profile: every actual policy call advances a
one-shot context generation; fresh observation is accepted only with a new
acquisition identity; page continuation is traversable and filter/objective
bound; page projection uses the configured action/destination/world budgets;
task and per-target sections report truthful truncation; failed acquisition
results do not erase adapter capability; and non-action decisions enter bounded
semantic recurrent history. Targeted provider selection remains deferred.

P5-M1/P5-M1.1 are closed for the model-policy core and existing ModelPort
bridge: deterministic AgentContext serialization, one canonical seven-variant
schema/parser, hostile-shape JSON limits, one bounded provider attempt, typed
failure/metadata handling, artifact evidence refs, and DOM/Visual/WoT proofs
reuse deterministic evaluators and Runtime admission. The local HTTP fixture
itself proves transport composition only; it does not attest live-provider
reasoning/generalization. Later narrow exact-Mistral evidence is separately
scoped. `remote_ci_attestation: unavailable` for this M1.1 record.

P5-M2 is closed for declared-minimum production evaluation on the non-default
path. Runtime normalizes criterion adjudicators, resolves current typed evidence,
computes mechanical/user/hybrid results, validates semantic proposals, bounded
success expressions, assurance and current lineage, and binds requested outputs
to path/SHA/current artifacts. The local HTTP semantic judge proof is transport
and composition evidence only. Live evaluator attestation is unavailable;
general semantic entailment remains partial; P5-M3 is closed only for its fixed
internal manifests.

P5-M2.1 closes the evidence-semantic entry gates for P5-M3. Action effect
claims now require progress against Runtime-derived criterion/output scope;
no-effect requires complete strong evidence for every declared fact obligation.
Semantic judges can cite only bounded records actually present in their request,
hybrid evidence components are separated, and complete observations with a
not-yet-created semantic scope remain INCOMPLETE so policy may act. Exact future
state prediction and general causal attribution are neither required nor
implemented. P5-M3 internal harness work is locally attested; at that slice's
closure external benchmarks had not run. Later M4 evidence is separately
profile-scoped below.

P5-M3 is now closed for its fixed internal manifest. The harness calls only the
target `TargetRuntime`/`AgentLoop`, runs cases sequentially with fresh
composition/environment/session state, and applies the manifest oracle only
after Runtime termination. Local runs at `637063ccd924` accepted internal core,
safety, and evaluation profiles. This is protocol evidence, not live-model or
cross-platform generalization evidence; later M4 MiniWoB runs do not backfill
this internal attestation.

P5-M3.1 replaces heuristic safety counters with call-boundary instrumentation,
typed measurements and manifest expectations. It also adds actual Chromium DOM,
Chromium Visual-only and local-HTTP WoT adapter cases; the older shared-state
matrix remains synthetic protocol evidence. Report attestation binds exact SHA,
dirty state, manifest digests and report hashes without serializing private
routes, credentials or raw provider payloads.

P5-M3.3 is closed for tested exact-profile diagnostics. The real-DOM
AgentContext is 4,972 bytes (`SMALL`); the canonical provider schema is 5,194
bytes with ten definitions and seven variants. Exact installed Ollama
`qwen2.5:7b` and `llama3.1:8b` profiles originally passed Levels 0/1 and failed
at full-union grammar initialization with a 2,000-character completion-summary
bound. The canonical bound is now 1,024. One format-only rerun per profile
passed Level 2; Levels 3/4 generated typed selections and were rejected by
current-page destination admission. The provider compatibility blocker is
closed. A full-union destination ladder records secret-free typed shapes:
Qwen passes D0–D3 and fails D4 with `equals_target_id`; Llama passes D0–D2,
fails D3 with `nonempty_when_forbidden`, and fails D4 with
`equals_target_id`. Runtime does not repair or admit those selections.
After that format-only attribution, exact clean-head GPU runs under
`compact-contract` passed L0–L4 at 20/20 for each listed Qwen/Llama digest.
Both per-profile attestations are accepted with status
`action_selection_supported`; provider calls had zero retry/fallback. This
L0–L4 evidence is SelectAction-centric and does not prove all recurrent decisions.
Mistral `mistral-medium-3-5` passed a fresh Level-4 call under format-only and
one under compact grounding, so its narrow no-regression gate remains green
without claiming stable support. Compact grounding is supported for the two
exact local profiles but is not the production default. Parser, Runtime
admission and external benchmark status were unchanged in that historical
provider slice; the Coordinator path was subsequently deleted in T3.

P5-M3.5 freezes `compact-contract.v1` as an explicit
`PRODUCTION_SUPPORTED_ACTION_SELECTION_PROFILE`. `model_policy_from_environment()` admits
`format-only` and `compact-contract`, with explicit argument precedence over
`LLM_DECISION_GROUNDING`; `compact-contract-v2` additionally requires the
explicit `LLM_ENABLE_EXPERIMENTAL_GROUNDING=1` conformance gate. Unknown values
and ungated v2 fail closed, and the default remains format-only. Metadata and exact-profile attestations bind schema digest
`sha256:187ef82e1205e863c2cd1e1688e92979da6439412fb1ff1541195fede955bf0f`,
summary limit 1,024 and grounding profile version.

Global compact-default cutover is `BLOCKED_WITH_EXPLICIT_ERRORS`. Complete
Qwen GPU matrices ranged from 45/70 to 60/70: Observation, AskUser and Done
were unstable, while Wait and Abort remained 0/5. Llama ranged from 35/70 to
40/70: all six non-SelectAction alternatives failed, while the 16-action middle
case was unstable. Neither profile showed first-action anchoring in the 15
non-first opportunities. Mistral format-only passed 12/12; two compact runs
completed 2/12 and 3/12 and returned typed provider-unavailable failures for
the other calls under the mandatory zero-retry profile. Exact-head remote CI is also unavailable.
`compact-contract.v2` is `EXPERIMENTAL_NOT_ADMITTED`.
Its 16-action guide is 4,031 bytes with all 16 actions and truthful
`truncated=false`; privacy, determinism and seven-contract scripted Runtime
tests pass. Qwen exact v2 candidate passed 64/75, but recurrent Page was 4/5
and Wait/Abort were 0/5. Llama passed 20/75 and selected the wrong first action
in 5/20 non-first opportunities. Neither candidate admitted a 20/20 support
run. Mistral v2 was not run because no explicit strong-provider opt-in was
configured; availability/no-regression is inconclusive. No external benchmark
or default Coordinator cutover was run.

P5-M3.6 closes a benchmark-only two-stage diagnostic without admitting a new
production profile. Scripted, local OpenAI-compatible, and local Ollama-shaped
transports pass routing, payload, end-to-end Runtime control at 7/7 and all
eight critical cases. Exact Qwen results are baseline 20/35, routing 26/35,
fixed-route payload 35/35, end-to-end 25/35, critical 30/40. Exact Llama
results are 5/35, 25/35, 35/35, 25/35, and 0/40. Each conclusion is
`routing_bottleneck`; each candidate failed, and neither admitted support
testing. The fixed-route payload result is not production-policy evidence.
Mistral two-stage is `NOT_RUN`; its prior formal paced compact-v2 candidate
remains 70/75 and `INCONCLUSIVE_PROVIDER_AVAILABILITY`, while its independent
5/5 follow-up remains non-backfilling rate-limit evidence.

Model compatibility investigation is `CLOSED_FOR_CURRENT_SCOPE` and
`NON_BLOCKING`. It is not rerun during ordinary GUI-agent development. The
declared triggers are a provider-runtime/version change, model identity change,
canonical schema change, AgentContext change, grounding-contract change, or an
explicit fully local recurrent-agent product objective. Two-stage remains
`DIAGNOSTIC_ONLY`; its fixed pacing is a benchmark/deployment profile and is
not retry, failure backoff, or AgentLoop authority.

P5-M4 closes the BrowserGym target-loop adapter for the pinned mechanical
profile. `browsergym-miniwob==0.14.3` exposes the reviewed registry IDs
`browsergym/miniwob.click-button`, `browsergym/miniwob.enter-text`, and
`browsergym/miniwob.choose-list`; all three pass real adapter conformance
through AgentContext serialization, the strict decision parser, Runtime
admission, private binding, one BrowserGym step per dispatch, fresh observation,
and official reward/termination verification. Bids, selectors, raw reward,
task IDs and oracle material remain outside model context. The adapter is
`CLOSED_FOR_PINNED_MINIWOB_MECHANICAL_PROFILE`; this does not attest model
generalization. The configured Mistral `mistral-medium-3-5` profile passed the
clean exact-head internal DOM attestation under `format-only.v1`: DONE, two
observations, one execution and one provider attempt, with zero retry/fallback
or safety violations. External preflight is admitted. Formal fixed-smoke
execution status is not hard-coded in source: it is determined by the protected
exact-head GitHub Actions run and its `browsergym-fixed-external-smoke`
artifact. The Coordinator product path referenced by that historical evidence
was subsequently deleted in T3.

## P5-M4.2 local verified-progress status

P5-M4.2 is a local-only correctness closure. `fill` and `select` effects are
mechanically evaluated from fresh, complete structural public value facts;
`activate` remains UNKNOWN unless task completion is independently established.
Already-satisfied fill/select selections make zero Binder, surface probe, step,
or execution calls. The first selection emits bounded strategy-transition
feedback; the next identical semantic attempt under unchanged narrow progress
fails with typed `NO_PROGRESS_REPETITION`. Timeout reports read an immutable,
privacy-safe partial session snapshot and identify `harness_watchdog` /
`case_timeout` without inventing a Runtime terminal reason. Real local pinned
regressions pass for enter-text normal/repeat containment, choose-list, and
click-button. The formal `cd49b8e` smoke remains `FAILED / case timeout`;
`LIVE_SMOKE=NOT_RUN_THIS_SLICE`, and no attestation was generated.

## P5-M4.3 MiniWoB-60 harness status

The `external_breadth` harness is `READY`. Its frozen manifest is derived from
the actual 0.14.3 registry, a pre-result static capability inventory, and the
namespace `miniwob-60-seeded-breadth.v1`. Exactly 60 current-primitive cases
use seed 7, ten turns, a 120-second watchdog, one-stage format-only Mistral,
global 7.5-second pacing, and zero retry/fallback. Campaign evidence may be
valid when individual tasks fail, but only after all 60 cases receive one
typed classification and report-tree, cleanup, safety, exact-head, and privacy
gates pass. The exact-head formal campaign completed at run SHA `b3b64a2` with
valid evidence and 6/60 task success; that negative breadth result is not a
general capability estimate because its historical attribution and primitive-
only inventory were incomplete. Generalization is `NOT_CLAIMED`; Runtime,
AgentLoop, parser/admission, prompt, adapter semantics, and the default
Coordinator are unchanged.

## P5-M4.4 failure attribution and capability closure

The historical immutable formal result remains valid negative evidence: 6/60
at run SHA `b3b64a2`, with generalization unclaimed. Future reports record
bounded component origin/code, exception class, last decision/evaluation
status, ActionSpace/target counts, coverage, and pending kind. Read-only legacy
analysis leaves 27 cases unresolved rather than guessing. Capability inventory
v2 covers 125/125 pinned tasks; its historical overlay is 15 supported, 31
unsupported, and 14 unassessed. Twenty-two no-model lifecycle probes all reset
and project, while projection covers 51/103 raw interactive nodes.

A later separately authorized formal rerun-v3 completed 60/60 from clean source
SHA `83dc4fa313e49b6c8772052ca44f03564f68aa63`, with valid evidence and 4/60
success. It is a separate exact-run record and neither replaces nor combines
with the historical 6/60 archive. Its typed outcomes include 7
`post_observation_failure`, 9 `unclassified_typed_failure`, and 11
`runtime_rejected`; generalization remains `NOT_CLAIMED`.

M4.5-A closes that confirmed lifecycle mismatch on the non-default target path.
The generic port now returns typed acquisitions from logical reset and capture,
and `ExecutionOutcome` preserves dispatch truth plus a mandatory typed post
acquisition. BrowserGym projects prepared initial raw exactly once, projects
step raw inside execute, and implements owner-thread read-only active capture;
it no longer relays reset/step snapshots through a public cache. Independent
capture reacquires incomplete page-native verifier state and deliberately marks
success unavailable when the full official success conjunction cannot be
proved. Local fake-backed contract tests pass. The isolated Python 3.12 runtime
with `browsergym-miniwob==0.14.3` and `playwright==1.44.0` passes all eleven
pinned BrowserGym adapter, local-progress, dependency-inventory and real
active-capture tests
against the reviewed MiniWoB source at commit `7fd85d71a4b60325c6585396ec4f48377d049838`.
The A.1 closure additionally rejects non-independent capture origins, reports
the final fallback attempt's typed cause and exact attempt count, counts an
already-performed post acquisition on ActionResult lineage failure, and removes
package-facade import-order dependence without moving projection authority.
M4.5-B is integrated on the non-default path but reopened for architecture-first
contract convergence. The previous B.1/B.2/B.3 completion claims and their test
counts are not current closure evidence. No current reviewed implementation SHA
exists.

A separately authorized M4.5-C diagnostic nevertheless executed from clean Git
SHA `4924ce61748d8efdec4fcc6de494acf8a9f224cc` and completed 60/60 with
8/60 success, valid evidence, 290 provider attempts and 555,164 tokens. Its run
ID is `miniwob-60:e9551acfcd31466e91481ee5923fc9af`; the docs-only archive
commit is `5f8d6acf3700831a05d73f93a5c66488a6298fd7` and is neither the run SHA
nor a reviewed B closure SHA. The diagnostic has no predeclared formal exit,
performance or generalization claim. Its immutable attribution and exact cohort
boundaries are recorded in the
[M4.5-C diagnostic review](reviews/2026-08-11-p5-m4-5-miniwob-60-diagnostic.md).

Patterns in that run, joined with exact `4924ce6` source review, support four
next product gaps: AX-versus-DOM currentness ownership, semantic
inventory/action projection coupling, verifier terminal information loss, and
missing bounded control feedback/repair plus exact no-gain containment for
action-page and policy-observation decisions. Their implementation/evidence identities are
tracked without rewriting the old run in the
[M4.6 remediation record](reviews/2026-08-11-p5-m4-6-evidence-directed-short-loop-remediation.md).

M4.6-A is implemented at
`896508eaf7737cd86289f93a30e5737c6b1cdf76`. Canonical/currentness
properties, the command-scoped Python 3.12 pinned real gate, the full repository
suite and a final fresh-context adversarial review passed. No immutable
targeted run artifact was produced, so its Verification run ID is `NONE`.
This is non-default declared-currentness closure only; it is not a performance,
generalization, MiniWoB-60 outcome or M4.5-B closure claim.

The original M4.6-B implementation is
`07895ede392bdff065ba3b4c0a6384ba18904143`; its immutable targeted run remains
valid as `miniwob-verifier-14:27950832769b49cf8e3c82d8cb827015`. Residual
producer/control closure is implemented at
`880e65fef0c2541be9f4b5af121e610f858685db`. Four-state
source-aware BrowserGym verifier truth now maps through canonical
`TaskOutcomeFact`, one task-evaluation control disposition, current-epoch
AgentResult/snapshot/CaseFacts v8 projection and unique benchmark precedence.
The frozen previous-verifier-unknown run completed 14/14 with valid evidence:
12 terminal-task-failure and 2 running-incomplete canonical facts; 13
TASK_FAILED and 1 RUNTIME_REJECTED outcomes. This is declared verifier-scope
closure only, with no full MiniWoB-60, performance/generalization or M4.5-B
closure claim. Generated fault-injection, state-machine, pinned real producer,
full quality gates and a fresh-context held-out review closed the residual
raw-fact producer and nonterminal task/control precedence seams without a new
campaign run ID.

M4.6-C is implemented at
`e6c410021d8b9bf11b52f24520a6258ede5d2027`. The generic frozen inventory
summary enforces exact bounded counts and the EMPTY/REPRESENTED/PARTIAL/
UNASSESSED algebra. BrowserGym now performs one canonical AX semantic analysis;
projection finalizes counts from actual targets and unique binding target IDs,
and diagnostics/model projection only copy that truth. Existing targets,
bindings, target IDs, ActionSpace options and `CoverageState` semantics are
unchanged. The accepted no-model run
`miniwob-inventory-17:6220967c47a24532b4140728627e4950` completed 17/17 with
13 EMPTY, 3 REPRESENTED and 1 PARTIAL, with all integrity/privacy errors and
all policy/provider/token/step/probe/independent-capture totals at zero. This is
declared inventory-profile closure only, not task-relative completeness or a
performance/generalization claim.

M4.6-D convergence implementation is `9e92bd2d3b55a696f06ae77fd029b4bc6db9a903`.
Typed ActionSpace/page/schema owners now produce public-safe admission facts;
one canonical `ControlFeedback` envelope projects once into the next ordinary
policy context. Request keys, request-echo-free page results and an identity-free
world/full-action-contract/task-progress epoch are distinct. AgentLoopState owns
a bounded seen-result set and the shared two-distinct-issue budget: an exact
repeat or third distinct issue terminates as `no_progress_control_repetition`,
while an unseen result grants gain once. Runtime neither edits parameters nor replays requests. Adapter-side
INVALID_PARAMETERS after Runtime admission remains execution failure truth.
ActionPager owns the sole bounded casefolded request semantics used by filtering,
page/cursor identity and the request digest. Page results and the control epoch
exclude request echoes and active filters, so request/view churn cannot reset the issue budget.
The valid fixed run
`miniwob-control-feedback-25:98e8fff597d94badb82a44f6ed1a4c44`
completed 25/25 with valid schema, identity, privacy, safety, integrity and
cleanup gates. Its feedback/correction measurements are not task-success,
performance or generalization evidence.
The earlier `ccb682a` and `8b92d13` runs remain immutable. The new run validates
the implementation identity but is not independent held-out closure evidence;
D remains implemented-not-verified and E blocked.

M4.6-D runtime-recovery implementation `1c00e331e4f310f904b70f454dad7cc55c8b47e2`
adds a bounded provider-call orchestrator above the one-attempt bridge, exact
admission-owner violation snapshots, current-page recovery constraints and
post-action semantic-effect/recovery projections. The valid v2 rerun
`miniwob-control-feedback-25:58be2cd216a24c4bb4fb7786dbebb9e6`
completed the same 25/25 selector with 16 control repetitions, two ordinary
no-progress repetitions, six task failures and one success. It recorded 69
policy calls/69 provider attempts, 10 related-decision and violation snapshots,
43 recovery-constraint snapshots, 30 feedback deliveries and zero retry,
fallback, privacy, schema, harness-integrity, cleanup or safety violations.
No semantic-effect snapshot was exercised. Because the live provider produced
no retryable failure, the run proves wiring and evidence validity but not live
retry effectiveness; controlled exceptional-path tests cover retry and typed
exhaustion. D remains implemented-not-verified pending fresh held-out review.

M4.6-E is `IN_PROGRESS / DOM_FIRST_VISION_CONVERGENCE_FULL_VERIFIED / LIVE_GATE_FAILED_DIAGNOSTIC`. BrowserGym
screenshots are carried as typed private image inputs into real multimodal model
messages; the public AX profile includes executable checkbox/radio/tab/menuitem
and bounded read-only table/list/heading/static-text structure. The valid
`b892c3a` capability-covered 15-pair A/B is run-evidence-valid but
comparison-invalid because 7 pairs contain provider failures. The 8 comparable
pairs were 8/8 text-only and 7/8 screenshot+AX, so screenshot benefit is not
demonstrated. Stable opaque entity identity, a bounded retained
entity/state/fact/relation/option inventory, fair frozen-snapshot paging and
negative-claim coverage gating are implemented. The former pre-policy
requirement-hypothesis producer and its separate call/accounting path are
deleted; semantic objective proposal now occurs only through an explicit typed
post-observation port. It is not an Agent decision or action tool.
Dynamic-tools v1 and its bounded selected-argument repair are implemented, but
the stopped clean-`7c14190` MiniWoB-60 attempt completed only 8 mixed-cohort
cases with 0 success and is not a benchmark claim. Its only
capability-covered case exposed the current shared root: raw screenshots and
anonymous `act_NN` tools have no common public target reference, while the
short-loop requirement proposer adds a second model-call path. Grounded-tools
v2 now reuses the existing SoM renderer, places one call-local `E*` namespace on
the annotated screenshot, concise allowlist `ToolPolicyView`, schema-equivalent
verb tools and previous result, and maps accepted refs back to existing
ActionOptions. The short-loop proposer is disabled. Its clean-`b9ad39a`
single-BrowserGym-source targeted gate completed `login-user`, tab and both
collapsible witnesses at 4/4 success with zero hypothesis calls, schema or
argument repairs, grounding gaps and safety errors. This does not prove source
selection, semantic fusion or route recovery.

Step 12 now closes that Unified seam. `ObservationOrchestrator` selects bounded
required and optional sources from pre-acquisition offers; source failures stay
typed; `WorldFusion` canonicalizes only explicit correspondence, conserves
provenance and exposes material conflicts; `RouteSelector` owns deterministic
private route choice; and the execution cycle allows at most one fresh
revalidation plus one equivalent retry after typed `NOT_SENT`. `SENT` and
`SENT_UNKNOWN` never reroute. `GroundingProjection` now owns E-refs, exact media
selection and SoM annotation, so `marked=true` is derived only from an image
actually emitted in that provider request. Deterministic DOM+Visual shared
acquisition and DOM+WoT equivalent-route witnesses pass, together with the
Step-11 regression set and the full repository suite.

Step 13 historically bridged the existing `VisualRegionBinding` foundation into the
current BrowserGym target loop. Phase 4 supersedes its point-authority portion. An
explicitly injected bounded proposer adds a `visual/weak` capability; provider
presence and prior selection do not invoke it. Each frame first projects DOM/AX,
then a pure typed gate selects Vision only for current missing action authority,
ambiguous structured candidates, explicit visual observation, or admitted
postcondition diagnosis. Structural and visual projections share one raw
capture. Unique compatible correspondence emits `EntityCorrespondence` and
merges visual evidence into DOM identity without a coordinate binding; unmatched
visual regions remain observation-only and create no target-loop route.
Ambiguous/conflicting correspondence,
unsupported regions, missing shared acquisition identity, and stale screenshots
are non-executable/fail closed. The route still passes through WorldFusion,
ActionSpace/admission, RouteSelector and exact page/episode/screenshot
currentness. Point grounders remain isolated benchmark/legacy compatibility
ports and are not BrowserGym target-loop capabilities. An optional thin OmniParser HTTP adapter
normalizes official parsed elements as observation-only regions; and a bounded
SoM disambiguator may return only an offered E-ref for ambiguous current DOM
candidates. Open-world proposal is disabled unless explicitly configured, so
`--visual-grounding` no longer makes GLM a region proposer implicitly. No
OmniTool, ShowUI, GUI-Actor, SeeAct, browser-use or SenseAct runtime has been
imported. Focused provider/authority tests and the remediation repository gate
pass (`2355 passed, 27 skipped`). Phase-3 replaces compound point instructions
with current atomic objectives, distinguishes single-target and visual-value
needs, preserves verifier lineage through
fusion, persists typed provider failure stage/code counters, and writes every
case plus a progress index atomically. The exact live rerun completed with valid
evidence at `1/5`: `visual-addition` succeeded without auxiliary E-ref/point
calls, while GLM point quality and a later main-policy tool-output error kept
the other cases from completion. `LIVE_GATE_FAILED_DIAGNOSTIC` therefore
remains historical diagnostic evidence; no live-provider result is inferred
from local verification. Phase 4 additionally marks all DOM elements so
clickable SVG children receive private BIDs, normalizes them into ordinary
`activate/click` E-refs, and filters tiny/low-visibility/overlapping drawing
duplicates. Real read-only/control probes show 25 executable grid circle
identities and one collapsed pie opener; identity-based clicks complete
`grid-coordinate` and the two-step `click-pie` witness at reward 1.0 without a
point-provider call. Dense SoM candidates now receive top-to-bottom,
left-to-right E-ref numbering and external labels instead of text painted over
14-pixel SVG targets. Singleton semantic tools bind their sole target inside
the Runtime catalog, eliminating redundant target serialization without
expanding authority. Follow-up remediation lets the screenshot+AX main policy
choose the semantic action and E-ref in one call, suppresses settled fills and
selected toggles from its next catalog, projects observation-only repeated-leaf
counts, and exposes selected state plus computed-style color family without
using fixture `data-*` answers. `visual-addition` then succeeds in two actions
in the clean `8741890` five-case run, and focused clean `7fae859`
`click-shades` succeeds in six structural actions with zero auxiliary E-ref or
point calls. The full suite passes (`2373 passed, 24 skipped`). The final
color-family increment has not received another complete five-case run.
Phase-5 follow-up now clusters current executable geometry into a regular
lattice, fits visible numeric axis-label groups (including screen-down versus
Cartesian-y orientation), and publishes derived membership/coordinate facts
only for one fully occupied, uniquely mapped grid. A generic task-predicate
compiler matches the public value and the quantified-objective reducer privately
closes one exact current DOM action; the lattice provider does not parse task
text and the model does not copy an E-ref. Missing axes,
irregular/duplicate cells and multiple candidate lattices publish no derived
coordinate. Clean `3ccb267` seed-7 `grid-coordinate` succeeds in one model call
and one structural dispatch with zero auxiliary E-ref, point or visual-binding
calls; the displayed ref changed to `E25` while row 4/column 3 remained stable.
The full suite passes (`2379 passed, 24 skipped`). Multi-seed and broad layout
generalization remain explicitly unclaimed.

Phase 6 has a clean bounded live witness. `ScopeSpec`, closed
candidate universes, a compositional three-valued predicate algebra, per-member
effect obligations, bounded scheduling, stability and
`SetCompletionCertificate` now form one deterministic reducer. Grounded Catalog
consumes only reducer dispositions; direct color, grid-coordinate and
next-matching-target branches were removed. Mechanically mentioned public
facts use the structural evaluator. When those facts cannot express a universal
predicate, the optional GLM batch port classifies every supplied E-ref exactly
once as `true/false/unknown`; it cannot claim scope completeness or return an
action/point, and correspondence maps its evidence back to DOM identity. Clean
commit `fb19bc2` passes all five targeted cases with valid evidence. In
`click-shades`, five blue member effects are confirmed before Submit is
released; all six dispatches use structural DOM identity, with zero visual
classifier, point, invalid-argument or repair calls. The evidence is persisted
under `docs/evidence/runs/m4-6-e-phase6-set-completion-zhipu-fb19bc2/`.
The final full suite passes (`2383 passed, 27 skipped`). Independent broad
generalization review remains open.

Phase 7 reopens and supersedes Phase 6's architectural closure claim. The five
MiniWoB cases are regression witnesses, not Runtime specifications. The current
implementation removes the raw-instruction set compiler, universal/count
keyword routing, task-relative `task_predicate_truth` projection and
repeated-leaf exact-count scanner. A persistent `SetObjectiveState` now owns
candidate scope, three-valued assessments, member obligations, actionability,
effects, stability and certificate state independently of bounded model
history. The main Agent establishes typed structural or visual predicates via
bounded tools; semantic classification returns a complete E-ref assessment
batch and never grants action authority. Catalog consumes an explicit
fail-closed directive, and a certified set excludes its member actions before
releasing only out-of-set successors. Typed evidence obligations drive the
visual router without task prose. Focused invariant, held-out and architecture
redline tests pass, and the frozen implementation full suite passes (`2398
passed, 27 skipped`). Real five-case revalidation is still pending, so
generalization and verified closure remain open.

The older `BrowserSession` perception/coordinator path remains migration debt:
it can derive task-level visual needs and heuristically group semantic entities,
but it does not own the new evidence gate or explicit correspondence authority.
It cannot serve as proof that Unified DOM/visual fusion is closed.

Scroll, focus-aware keypress, table/list ownership, dynamic
semantic deltas, multi-step verified working state and source review of the 14
readiness-unassessed cases follow as explicit shared-capability slices.
Targeted cohorts run after each slice before one frozen MiniWoB-60 rerun.
Declared gaps remain separately reported for attribution, but are no longer
treated as permanently out of product scope.
The named tasks are test witnesses only. No Runtime/policy/tool/admission path
may branch on a MiniWoB task slug, case ID, readiness cohort,
reviewed-source rule, reward or answer; only benchmark inventory/reporting
owners may retain that metadata. BrowserGym-specific mechanics remain isolated
to the environment adapter, while the capability contracts are intended for
real GUI surfaces. The
active convergence plan is the [LocalObjective de-specialization record](superpowers/plans/2026-08-13-m4-6-e-set-objective-de-specialization-plan.md).

The active plan now also freezes the v1 complexity diagnosis and reuse boundary.
`grounded_tools.v2` replaces the full-context scrub + pre-policy hypothesis +
anonymous-tool + multi-repair stack; merely adding another facade does not
satisfy the slice. Browser/OS acquisition and input, accessibility
semantics, SoM rendering, optional OCR/visual proposal, provider-native tool
transport, model reasoning, official task verification and downstream tracing
are reused or outsourced behind typed ports. Runtime continues to own current
epoch, ActionSpace/ref resolution, admission, dispatch truth/no-replay,
risk/confirmation, evidence validation and task disposition.

P5-E is `DELETED_WITH_LEGACY_RUNTIME_T3`. Sequence, set and aggregate semantics previously
entered through one explicit `LocalObjectiveProposalPort` after observation,
but target product and benchmark composition no longer expose that phase and
T3 physically deleted its source, transport, reducer and compatibility tests.
`AgentDecision` and recurrent action tools contain no objective constructor;
their schema module imports no predicate/scope/aggregate contracts. The old
TaskFrontier, VerifiedTaskState, RequirementHypothesis and objective-operation
package are deleted. This topology deletion is not fresh live benchmark closure.

## Control-transition and long-horizon gap status

The current M4.5-B candidate includes a bounded pure reducer, strict boundary
validation, a physical-attempt matrix, canonical terminal Runtime failure,
orthogonal `CaseFacts` and one benchmark classification precedence owner.
`AgentLoopState` remains current-state authority. Those owners are implemented
but their whole-loop exceptional-path and fresh held-out assurance is not a
reviewed closure. Codecs, legacy fields, privacy sanitation and telemetry remain
downstream projections and cannot infer or override truth. No ledger, replay,
event sourcing or state reconstruction is admitted.

General long-horizon planning is outside the current AgentLoop contract and is
not represented by dormant frontier state. `ProgressController` remains an
integrated fill/select local liveness guard; it is not a planner. M4.6 is
`IN_PROGRESS`: M4.6-A is `COMPLETE_NON_DEFAULT_FOR_DECLARED_CURRENTNESS_SCOPE`,
M4.6-B is `COMPLETE_NON_DEFAULT_FOR_DECLARED_VERIFIER_SCOPE`, M4.6-C is
`COMPLETE_NON_DEFAULT_FOR_DECLARED_INVENTORY_SCOPE`, M4.6-D is
`REOPENED_CONVERGENCE_REVIEW / IMPLEMENTED_NOT_VERIFIED`, and M4.6-E is
`SINGLE_AGENT_CONTEXT_CUTOVER_IMPLEMENTED / LOCALLY_VERIFIED / PUSHED_E7F9F46 / LIVE_NOT_RUN`;
M4.6-F is `IMPLEMENTED_LOCALLY / FULL_VERIFIED_2485_PASS_27_SKIP / LIVE_UNVERIFIED`;
the atomic-memory and updater diagnostics remain only negative evidence;
M4.7 multi-seed remains blocked by its
targeted gates. M4.5-B independently remains reopened until reducer properties,
held-out review, the full verification gate and a clean reviewed-commit
attestation pass; the executed diagnostic does not close it.

The following `eb19c0d` topology is historical and superseded by the current
single-`AgentContext` path. At `eb19c0d`, grounded action selection performed two cognition calls inside one
`AgentPolicy` turn. The task-state updater first receives the original task,
fresh Unified World, explicit Runtime-observed transition after the previous
decision, and prior advisory task state. It emits a complete bounded state with
goal clauses, requirement status, derived facts, next step, finalization
readiness and blockers. The actor then receives that just-authored state plus
the same fresh world and clean Runtime-issued tools. This establishes the causal
edge missing from `8f33d8a`: updated task state precedes and conditions the
current action rather than being a sibling action argument.

One `GroundedPolicyContextBinder` owns provider message construction and loads a
versioned packaged YAML prompt bundle. Task state is an independent
`AgentContext` projection; world transition remains Runtime evidence and task
state remains non-authoritative Agent belief. Grounded action schemas contain
only their legal action arguments, and `supported_decisions` no longer pretends
that attached memory is a decision capability. After current-context admission,
`AgentLoop` stores the state and routes the action through the unchanged
ActionSpace/admission/private-binding/execution/evaluation chain. There is still
one possible environment action and no second Runtime path, planner, classifier,
critic, task-family branch or semantic Runtime guard.

The clean exact-head default-4.1V five-witness run at `cdb4bc9` completed 5/5
with evidence valid but is schema-blocked at 1 success and 4
`structured_output_failure` outcomes. Seven updater decisions were attempted;
every initial task-state response violated its schema, the bounded repair
recovered three, and four repairs failed again before the actor could run. The
three recovered states correctly identified the requested grid coordinate,
decomposed the no-delay pie interaction, and enumerated all five public blue
entities. This exercises the intended updater-before-actor edge but does not
assess multi-turn retention, aggregation or finalization. The repair prompt did
receive bounded violation paths and codes; the public trace did not persist
them, so the exact repeated field-level mismatch remains unobserved. Work is
stopped without a prompt repair, critic, task branch or rerun. See the
[diagnostic evidence](evidence/2026-08-14-task-state-context-eb19c0d.md) and
[raw report](evidence/runs/p5-m4-6-e-task-state-context-five-witness-cdb4bc9/report.json).

The earlier clean default-4.1V five-witness run at `d524221` is evidence-valid at 1/5.
All 12 completed turns contain non-empty attached memory, closing the question
of whether the mechanism is exercised. It does not provide stable task state:
grid memory names `(1,-2)` while the action selects public `(2,-1)`; the failed
pie's second memory says expand while its action clicks `Y`; color-set memory
retains only one next click and times out; addition memory stores no numeric
derivation before submit. All completed turns also required structured-output
repair and two target repairs, producing 27 provider attempts. Semantic
consistency and schema/latency are therefore distinct historical causes. That
run validates only the superseded `8f33d8a` topology and is the baseline for the
new bounded experiment; `eb19c0d` has no live benchmark result yet.

The earlier default-4.1V five-case diagnostic at `b309c9d` completed
with raw 3/5 but is formally invalid because its in-repository output directory
made the final git-identity check dirty. It emitted 15 `SelectAction` decisions
and zero `UpdateWorkingMemory` decisions, so no success is attributed to the
optional memory mechanism. This establishes that optional checklist availability
alone did not change the observed policy topology. It does not establish that
a maintained memory is ineffective. This diagnostic admits neither a critic nor
repeated sampling for a favorable score. It predates and therefore does not
validate the mandatory atomic envelope at `8f33d8a`.
