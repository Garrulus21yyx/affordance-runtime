# Implementation Status

> **Lifecycle:** CURRENT IMPLEMENTATION TRUTH
> **Updated:** 2026-08-09
> **Reviewed start baseline:** `codex/migrate-world-interaction-capabilities@792d327112cd72f3cb5c9bd02c273c80f626f349`
> **Target:** [Unified World Interface and E2E AgentLoop Architecture](superpowers/specs/2026-08-05-task-contract-centered-runtime-authoritative-architecture.md)

## Status vocabulary

`NOT_STARTED` → `PROTOTYPE_EXISTS_NOT_ADMITTED` → `INTEGRATED_NON_DEFAULT` →
`DEFAULT_CUTOVER` → `DELETED`. “Implemented” below never implies default
cutover unless stated explicitly.

## Current truth

The old transactional `Coordinator → RuntimeDelta → RuntimeCommitter →
StateKernel` path remains the current product baseline/default. It is frozen
against new product capability but has not been deleted.

The target path now has:

| Capability | Status |
|---|---|
| TaskGoal / EvaluationSpec | `INTEGRATED_NON_DEFAULT` |
| TaskPlan / Milestone / LocalObjective contracts | `INTEGRATED_NON_DEFAULT` (no model planner) |
| WorldObservation / AgentWorldView / ActionSpace | `INTEGRATED_NON_DEFAULT`; exact option/binding-group fidelity and source/world currentness closed |
| ActionIntent / BoundActionRequest / ActionResult | `INTEGRATED_NON_DEFAULT`; admitted selection identity retained through binding |
| Evaluator-owned completion and bounded Turn state | `INTEGRATED_NON_DEFAULT` |
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
| LocalObjective relevance | `CLOSED_FOR_CURRENT_EXPLICIT_HINT_PROFILE`; legality and risk unchanged |
| action paging | `CLOSED_FOR_DETERMINISTIC_CURSOR_PAGER`; traversable Runtime-issued cursor; only current-page IDs admitted |
| source assurance summaries | `CLOSED_FOR_DOM_VISUAL_WOT_PROFILES`; quality metadata grants no action authority |
| criterion adjudicators | `CLOSED_FOR_DECLARED_MINIMUM`; mechanical, semantic, explicit-user and hybrid |
| current M0 model projections | `INTEGRATED_NON_DEFAULT` |
| P5-M1 model policy core | `CLOSED`; canonical context JSON, typed decision parser and Runtime admission |
| P5-M1.1 strict decision boundary | `CLOSED`; duplicate/non-finite/depth/node/byte limits and canonical seven-variant spec |
| P5-M1.1 existing ModelPort bridge | `CLOSED`; existing transport owner, outer deadline, zero retry/no fallback, typed metadata/failures |
| local HTTP provider-transport proof | `CLOSED`; one request/one execution plus 429/500/schema/deadline zero-call proofs |
| live provider profile | `UNAVAILABLE`; opt-in smoke not configured at this revision |
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
| live model-policy profile | `OPT_IN_IMPLEMENTED`; local Ollama discovered, final exact-head attestation pending |
| live semantic evaluator | `NOT_REQUIRED_FOR_FIRST_MECHANICAL_EXTERNAL_MANIFEST` |
| external smoke manifest | `REVIEWED_AND_FIXED` for BrowserGym MiniWoB 0.14.3 tasks click-button/enter-text/choose-list |
| external target-loop adapter | `PARTIAL`; official package/registry pinned, WorldEnvironment lifecycle deferred |
| external benchmark | `BLOCKED / NOT_RUN` |
| default cutover | `NOT_READY` |
| RoutePolicy | implemented, post-hard-gate only |
| BindingCache | `PROTOTYPE_EXISTS_NOT_ADMITTED` |
| ActionBatch | helper implemented; not AgentLoop-integrated |
| long-horizon TaskPlan execution | `NOT_STARTED` |
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
- SoM utilities and smart-room/mock-web assets are implemented.
- Smart-room images use committed lockfiles and `npm ci`. Audit debt remains:
  node-wot 4 vulnerabilities (2 moderate, 2 high); dashboard 2 (1 moderate,
  1 high). Fixes currently require breaking dependency upgrades.

## Proof and remaining gates

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
simultaneous sources remains future work. External full-agent
benchmarks remain blocked. Old-core deletion is not admitted.

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

P5-M0 projects TaskGoal, internal ActionSpace, bounded Turns, and optional Plan
into private-payload-free model views while retaining internal ActionSpace as
the sole admission authority. Per-observation evidence indexes resolve action
and task evidence. COMPLETE is deterministically bound to task, observation,
criteria, current evidence, requested outputs, and declared path/SHA-256 checks.
The target loop now has a provider-neutral `ModelBackedAgentPolicy` using one
injected structured call and typed failures. No real-provider profile or
live model-policy attestation is implemented; the criterion-scoped evaluator
profile is described below.
TaskEvaluation UNKNOWN waits and BLOCKED terminates explicitly.

Semantic fusion remains deliberately deferred. The small `AgentLoopState` is
complete; a distinct LoopPolicy and optional TurnRecorder remain future work.
P5-M0.1 now provides the unified disposable AgentContext, ContextIdentity,
bounded context-only intent, bounded model world/progress/pending/budget views,
typed recurrent decisions, current-page paging, explicit-hint relevance and
source-assurance summaries. Criterion adjudication and production evaluator
composition are now closed for declared-minimum profiles. Targeted observation
provider selection and the new-loop benchmark harness have not begun. WoT effectful rate limiting is implemented; property
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
proves transport composition only; live-provider reasoning/generalization is
not attested. `remote_ci_attestation: unavailable`.

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
implemented. P5-M3 internal harness work is locally attested; external
benchmarks remain blocked and were not run.

P5-M3 is now closed for its fixed internal manifest. The harness calls only the
target `AgentEpisodeRunner`/`AgentLoop`, runs cases sequentially with fresh
composition/environment/session state, and applies the manifest oracle only
after Runtime termination. Local runs at `637063ccd924` accepted internal core,
safety, and evaluation profiles. This is protocol evidence, not live-model or
cross-platform generalization evidence. External benchmarks remain blocked.

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
admission, external benchmark status and the default Coordinator path are unchanged.

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
or safety violations. External preflight is admitted. The independent
`RUN_EXTERNAL_SMOKE=1` execution opt-in is absent, so the fixed external smoke
remains `NOT_RUN`. The old Coordinator product path is unchanged.
