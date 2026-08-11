# Benchmark Plan

> **Lifecycle:** CURRENT NORMATIVE POLICY
> **Scope:** evaluation profiles, metrics, and claim gates

## 1. Evaluation objective

Measure whether one semantic agent policy can efficiently complete the same
task across heterogeneous world surfaces, while preserving local action safety
and truthful evaluation.

## 2. Required profiles

### Core positive matrix

Use the same TaskGoal, AgentPolicy, semantic action vocabulary, and evaluators.
Only the adapter/environment representation changes:

```text
DOM · AX · Visual-only · SVG · WoT
```

Initial tasks should include an activation/toggle, a structured selection, and
a spatial move where applicable. API/Device/CLI join after symmetric adapters exist.

### Safety regression

- stale observation/binding → zero executor calls;
- changed semantic confirmation subject → confirmation invalidated;
- binding-only fresh rebind with unchanged semantics → confirmation retained;
- result/receipt-only completion rejected;
- UNKNOWN effect → no duplicate attempt;
- unsupported independent capture → typed capability outcome, no raw cache error;
- failed post-action acquisition → execution/result identity retained, no replay;
- missing/mismatched required artifact rejected;
- model-injected selector/coordinate/backend payload rejected.

### Adapter conformance

Each adapter proves truthful coverage, stable target identity, supported action
reporting, binding freshness, execute result, reset acquisition, and declared
observation capabilities. Conformance tests exercise post-action acquisition
and, when declared, independent capture. Capability-unavailable and acquisition
failure are typed and distinct. Operational acquisition capability is assessed
separately from evidence modality/source assurance.

## 3. Metrics

```text
task success rate
steps to completion
observation and targeted-observation count
post-action and independent-acquisition success/unavailable/failure count
model and visual calls
latency
route selection and wrong-route count
fallback count
human-confirmation count
stale detection
unknown-effect duplicate rate
long-horizon constraint retention and verified milestone progress
ask-user correctness
batch utilization and observation-barrier rejection
cache hit and currentness rejection
```

Zero-opportunity rates are reported as N/A. Event/delta/commit metrics may be
legacy diagnostics but are not target acceptance measures.

### Long-horizon profile

At least one 20–50+ accepted-policy root-ControlTransition task spans
pages/applications or surface types and
requires milestone verification, new-information retention, ask_user, and
fact-driven plan replacement. Cross-day/background/crash-resume is excluded.

### Batch and memory ablations

Batch compares success, model calls, observations, steps and latency against
single-action execution. BindingCache/Skill comparison reports stale rejection
and must use the same ActionSpace/RiskPolicy/evaluator path.

## 4. Run identity

Every report records git revision, dirty state, task/adapter manifest, profile,
model/provider configuration, seeds, required denominators, and raw result
locations. Historical evidence does not roll forward.

## 5. Claim gate

No “cross-platform generalization” claim is allowed until all required surface
variants complete positively under the same policy/evaluators and adapter-only
variation is demonstrated. A shared failure or shared entry into the same old
pipeline is not success evidence.

## 6. External benchmark admission

Scoped BrowserGym/MiniWoB fixed and breadth runs have completed under P5-M4.
They do not admit full external-suite or cross-platform claims. Expansion to
WebArena/WorkArena/OSWorld and general external-agent benchmarking remains
**BLOCKED**. The historical first fixed-run gate required:

1. positive new-loop DOM, Visual, and WoT verticals (closed for the shared-state task);
2. the same TaskGoal, policy, evaluators, and semantic actions with adapter-only variation;
3. runtime-owned ActionSpace and evaluator-owned completion;
4. stale zero-call, fresh post-step observation, and SENT_UNKNOWN no-retry;
5. P5-D confirmation/unknown-effect core (closed on the non-default target path);
6. P5-D6.1 general confirmation/evaluation contract completion (closed non-default);
7. P5-M0 model-safe policy/evaluator trust boundary (closed non-default);
8. P5-M0.1 disposable AgentContext/context identity/paging implementation (closed non-default);
9. P5-M0.1.1 one-shot epoch/cursor paging/projection operational closure (closed non-default);
10. P5-M1 model-backed target AgentPolicy (closed);
11. P5-M1.1 strict existing-ModelPort bridge (closed locally; no live-provider generalization claim);
12. P5-M2 minimum production evaluator composition and criterion adjudicators (closed locally);
13. P5-M2.1 evidence-semantic/dynamic-readiness entry gates (closed locally);
14. P5-M3 fixed internal benchmark harness that runs the new AgentLoop rather than the retained baseline (closed locally);
15. exact-head remote CI evidence with zero forbidden side effects and duplicate unknown attempts.

The first admitted external run was a small fixed BrowserGym/MiniWoB smoke set
for harness and loop-contract validation, not a generalization claim.
WebArena/WorkArena wait for an internal long-horizon gate. OSWorld waits for
AX/Visual/CLI/app-switch contracts. Component tests and the local DOM, Visual,
and WoT verticals continue to run before any expansion gate. P5-D through
P5-M2.1 did not independently admit an external run; P5-M3/M4 supplied the
separate harness, adapter and exact-profile admission evidence.

The P5-M3 internal manifests are `internal-core`, `internal-safety`, and
`internal-evaluation`. They run sequentially through `AgentEpisodeRunner`, keep
expected terminal states outside all product inputs, record denominator-aware
rates (`N/A` for zero opportunities), and fail closed on forbidden effects,
duplicate unknown attempts, stale dispatch violations, cleanup failure, or
missing metrics. Their local acceptance did not by itself admit an external run.

P5-M3.1 adds `internal-real-adapters`, whose deterministic cases use actual DOM,
Visual-only and WoT production adapters. `MetricMeasurement` distinguishes zero
from unmeasured, manifest expectations are digest-bound, and attestation hashes
exact-head report files. These are internal adapter and protocol proofs, not
BrowserGym/MiniWoB runs or model-generalization evidence.

P5-M3.2 fixes the first external candidate to the official
`browsergym-miniwob==0.14.3` registry entries
`browsergym/miniwob.click-button`, `browsergym/miniwob.enter-text`, and
`browsergym/miniwob.choose-list`, with MiniWoB source commit `7fd85d71...`.
This manifest is mechanical-only, so a live semantic evaluator is not a gate.
The optional SDK is isolated in the `external-smoke` extra. Admission still
requires one clean exact SHA across the complete internal run set, full CI, and
live policy attestations, zero safety counters, the exact manifest digest, and
a closed target-loop environment wrapper. That wrapper was still open when
P5-M3.2 was recorded; P5-M4 later closed it for the pinned three-task mechanical
profile without expanding the manifest.
Semantic fusion remains deferred and is not an M1 prerequisite.

## Exact model conformance ladder

The diagnostic ladder covers minimal structured JSON, SelectAction-only actual
IDs, full union/minimal context, full union/current AgentContext, and the real
DOM AgentLoop. Grounding variants are format-only, compact contract, full schema
text and context-bound schema. Each attempt makes one provider call and retains
only typed stage, sizes, hash and secret-free usage metadata. The measured exact
Ollama profiles originally failed when the full union carried a 2,000-character
completion-summary bound. After narrowing the canonical semantic budget to
1,024, both exact profiles passed one Level-2 format-only diagnostic and reached
destination admission at Levels 3/4. This removes the measured provider grammar
blocker but does not establish stable model support. It does not admit
BrowserGym/MiniWoB execution.

The destination-domain diagnostic ladder keeps the full decision union while
progressing from a forbidden destination (D0), through one/two offered nested
destinations (D1/D2), the real nested action page (D3), and the complete current
AgentContext (D4). Failure reports retain only a typed shape—never the emitted
ID or raw response—and Runtime membership remains unchanged.

After the 1,024-character grammar correction, the compact-contract candidate
was rerun against D3/D4 and then the complete support ladder. Exact Qwen 2.5 7B
and Llama 3.1 8B profiles each passed L0–L4 at 20/20 on clean HEAD `b4c04d6`;
their separate attestation files are accepted for action-selection scope. The corresponding
format-only D4 destination failures remain part of the diagnosis. These are
internal real-DOM policy/runtime proofs, not BrowserGym/MiniWoB execution.

## Compact production-profile cutover matrix

M3.4 adds a fixed seven-decision plus 8/16-action and destination-domain matrix.
The oracle remains post-response benchmark data and is absent from AgentContext
and compact guide. Complete Qwen GPU runs ranged from 45/70 to 60/70;
Observation, AskUser and Done were unstable, and Wait/Abort were 0/5. Llama
ranged from 35/70 to 40/70, selecting SelectAction for all six
alternative-decision cases while the 16-action middle choice was unstable.
Both passed all tested
destination domains, and neither selected the first action in 15 non-first
opportunities. Mistral format-only passed its four-case 12/12 no-regression
matrix; two compact runs were 2/12 and 3/12 with typed provider-unavailable
outcomes and no retry. These results block a global default change and do not run or admit an
external benchmark.

## P5-M3.5 recurrent v2 evidence

The production candidate matrix now validates full payload domains and replays
parsed decisions through production Runtime control. Scripted v2 closes all 75
candidate cells. Exact GPU results are Qwen 64/75 and Llama 20/75; both fail
the candidate gate and therefore have no 20/20 recurrent support evidence.
Qwen has zero wrong first-action selections across 20 non-first opportunities;
Llama has five. Mistral v2 is `INCONCLUSIVE_PROVIDER_AVAILABILITY` because this
run had no explicit strong-provider opt-in. BrowserGym, MiniWoB, WebArena,
WorkArena and OSWorld were not run.

## P5-M3.6 two-stage diagnostic evidence

Scripted, local OpenAI-compatible, and local Ollama-shaped transport gates pass
routing 7/7, payload 7/7, end-to-end 7/7, Runtime outcomes 7/7, and all eight
critical cases. Qwen exact candidate cells are baseline 20/35, routing 26/35,
payload 35/35, end-to-end 25/35, critical 30/40. Llama cells are 5/35, 25/35,
35/35, 25/35, and 0/40. Both diagnoses are `routing_bottleneck`, both formal
candidates fail, and no 20/20 run is allowed. Mistral two-stage is not run by
default because two-stage calls increase the rate-limit burden. Progress is
atomic after each stage, secret-free, inspectable, and never auto-resumed or
replayed.

## P5-M4 fixed BrowserGym evidence

`browsergym-adapter-conformance` is a real-environment conformance profile, not
a model benchmark. It runs only the three reviewed MiniWoB IDs, serially and
with a fresh environment per case, through AgentLoop and official mechanical
verification. Required measurements include actual reset/step/probe/action,
policy/provider, observation/turn, verifier and safety counts; missing values
fail closed. Oracle-isolation scans prohibit task IDs, expected answers,
reference actions, hidden state, reward, bids and selectors from public model
artifacts. The fixed live smoke additionally requires exact-head admission,
one-stage Mistral `format-only.v1`, fixed 7.5-second pacing, zero retry/fallback,
`RUN_EXTERNAL_SMOKE=1`, and `--execute`. The exact-head Mistral internal-DOM
attestation and preflight are accepted. The protected fixed-smoke workflow is
`CONFIGURED_AND_MANUALLY_GATED`; the latest execution result is determined by
its exact-head artifact. Adapter CI is not used as a substitute.

## MiniWoB-60 seed-7 breadth campaign

`miniwob-60-seed7-v1` is selected before live execution by sorting admitted
registry IDs on `sha256("miniwob-60-seeded-breadth.v1" + NUL + task_id)` and
taking the first 60. The committed manifest binds package/source, registry and
inventory digests, case order, seed, budget, model, grounding, and pacing.
Execution is serial with a fresh environment/session per case and one global
pacing clock. Task failure continues the campaign; interruption invalidates
the run and cannot resume or merge. Summary rates include overall,
provider-available, and infrastructure-clean denominators, with zero
denominators represented as null. The classification is
`MINIWOB_60_SEEDED_BREADTH_PROFILE`; generalization remains unclaimed.

Three completed MiniWoB-60 executions are separate immutable exact-run records:

- [P5-M4.3 at `b3b64a2c338f0bc76af5d7a16dfddfed513152c4`](evidence/runs/p5-m4-3-miniwob-60-seed7-b3b64a2/README.md)
  completed 60/60 with 6 successes.
- [post-M4.4 separately authorized rerun-v3 at `83dc4fa313e49b6c8772052ca44f03564f68aa63`](evidence/runs/p5-m4-4-miniwob-60-seed7-83dc4fa-rerun-v3/README.md)
  completed 60/60 with 4 successes. It retains nine
  `unclassified_typed_failure` cases and seven observation failures requiring
  refresh-stage ownership.
- [P5-M4.5-C diagnostic at `4924ce61748d8efdec4fcc6de494acf8a9f224cc`](reviews/2026-08-11-p5-m4-5-miniwob-60-diagnostic.md)
  completed 60/60 with 8 successes and valid evidence. Its formal exit,
  performance and generalization are not attested.

No result replaces another. They differ in exact source and instrumentation and
must not be aggregated, treated as one continuous campaign, converted into a
model-capability percentage or presented as a trend. All retain
`generalization_claim=NOT_CLAIMED`.

The v1 inventory is primitive-only and insufficient for task readiness.
Inventory v2 separately declares interaction, observation, reasoning, and
control requirements, leaving unknown requirements unassessed. M4.4 local
diagnostics never execute a policy: they compare raw structural interactive
counts with projected targets and ActionSpace counts, query only the initial
mechanical verifier, and close resources.

### P5-M4.5 and M4.6 correction gates

M4.5-A closes observation acquisition before another breadth claim:

1. reset establishes a typed initial acquisition;
2. adapters declare `independent_capture` and `post_action_observation` apart
   from evidence/source assurance;
3. normal actions consume the post-action acquisition from ExecutionOutcome;
4. RequestObservation, Wait, stale/currentness refresh, and confirmation refresh
   use independent capture only when supported;
5. unsupported and failed acquisition are distinct typed outcomes, and
   SENT_UNKNOWN dispatch identity survives either outcome without replay;
6. a new capture identity never re-labels the previous step's verifier outcome
   as current evidence; verifier state is reacquired or explicitly unavailable.

M4.5-B is integrated non-default but reopened and implemented-not-verified.
Its convergence contract requires decision-scoped transition accounting:

Status mirror: M4.5-B `INTEGRATED_NON_DEFAULT / REOPENED_CONVERGENCE_REVIEW /
IMPLEMENTED_NOT_VERIFIED`; M4.5-C `COMPLETE_DIAGNOSTIC /
EVIDENCE_VALID_AT_4924CE6 / FORMAL_EXIT_NOT_ATTESTED /
PERFORMANCE_NOT_CLAIMED / GENERALIZATION_NOT_CLAIMED`; M4.6 `IN_PROGRESS /
M4.6-A COMPLETE_NON_DEFAULT_FOR_DECLARED_CURRENTNESS_SCOPE / M4.6-B
COMPLETE_NON_DEFAULT_FOR_DECLARED_VERIFIER_SCOPE / M4.6-C
COMPLETE_NON_DEFAULT_FOR_DECLARED_INVENTORY_SCOPE / M4.6-D
REOPENED_CONVERGENCE_REVIEW / IMPLEMENTED_NOT_VERIFIED / M4.6-E
IMPLEMENTED_DIAGNOSTIC_NOT_VALIDATED`.
The M4.6-B residual contract implementation is `880e65fef0c2541be9f4b5af121e610f858685db`;
the accepted targeted run remains bound to original `07895ede392bdff065ba3b4c0a6384ba18904143`.
Implementation Status is authoritative.

1. every accepted policy decision produces exactly one bounded
   `ControlTransition`, including AskUser, Abort, RequestObservation, Wait,
   RequestActionPage, ProposeDone, and post-context/schema action-admission
   rejection or later failed action paths; pre-decision provider/stale/schema
   failures do not fabricate a transition;
2. the record retains typed admission, execution/acquisition, before/after,
   ordered physical attempts, expected/actual acquisition origin, strict probes,
   epoch-matched evaluations, progress, pending, resulting status, and
   Runtime-owned reason;
3. run summaries and partial snapshots project typed data rather than infer a
   terminal class from messages or differently aged state; primary runtime/
   provider/watchdog attribution and cleanup remain independently visible, and
   custom metrics cannot override canonical counters;
4. transition storage reports total count plus a bounded suffix and remains
   in-memory, run-scoped, non-replayable, and non-durable.
5. the bounded contract distinguishes the harness-owned watchdog from component/provider timeouts,
   keeps Runtime/component/cleanup/integrity facts independent, rejects canonical
   metric collisions as evidence-integrity failures, and forbids campaign acceptance
   when any case remains unclassified or violates a frozen safety gate.

M4.5-A and M4.5-B are separate implementation/verification slices so their
effects remain attributable. M4.5-B has not passed its convergence gate. A
separately authorized M4.5-C diagnostic nevertheless executed at `4924ce6`;
that immutable fact does not close B or satisfy a formal performance gate.
M4.6 applies its evidence-directed repairs one independently measurable slice
at a time. Any targeted or full rerun is a new immutable record and cannot
amend, resume or merge any exact run above. Zero unclassified typed outcomes
remains an attribution gate, not permission to rewrite prior evidence.

M4.6-D is an implemented but reopened bounded control-feedback/repair/no-gain gate, not a new planner or
reflection benchmark. Its primary proof is a reducer/loop state machine with
deterministic fake ports:

1. a typed public parameter/page admission issue produces exactly one finalized
   zero-bind/probe/execute/capture root and one model-safe feedback view;
2. the next ordinary policy call may return a corrected decision; Runtime never
   edits it, recommends a replacement or replays the rejected decision;
3. the initial profile freezes a shared budget of two distinct repair/no-gain
   issue fingerprints per identity-free scope; an identical issue terminates on
   repeat and a third distinct issue terminates
   `no_progress_control_repetition`, even when invalid values, control-request
   kinds or fresh Runtime identities alternate;
4. adapter parameter rejection after successful Runtime admission is a typed
   adapter-contract mismatch, not model repair; risk/task terminal,
   `SENT_UNKNOWN`, budget/cancel and component/integrity failures remain outside
   repair;
5. page/policy-observation no-gain shares that budget; an identical
   request/result terminates on repeat, effectful `SENT` or semantic/task/page
   gain resets, a merely admitted no-gain decision does not, and Runtime refresh
   is exempt;
6. existing validated no-effect/already-satisfied strategy feedback remains
   visible without creating a universal action retry controller; and
7. serialized feedback contains no raw exception, parameter value, private
   binding/BID/route or internal digest, and ContextBuilder/classification infer
   no repairability.

Because AgentContext gains a declared field, the gate includes its focused
serializer/parser/real-policy conformance witness. A new targeted run covers the
direct case-37 parameter witness, the declared current-page selection witnesses
and page/observation cohorts. It records feedback delivery, repair consumption,
first- and second-opportunity corrected-decision rate, policy attempts/tokens
and final outcomes; stochastic success improvement is measured but is not
substituted for the control
properties or required from one case. The value two is an initial falsifiable
profile choice, not a SOTA constant; changing it requires these measurements,
not a newly enumerated counterexample. A separate reflector is considered only
after these measurements show correct feedback delivery but persistent policy
repetition.

After M4.6 targeted gates and a new accepted same-profile rerun, a pre-result admitted supported subset
must run across multiple seeds before P5-E. Its immutable manifest, exact seed
set, numeric provider-availability/capacity floor, success floor and maximum
seed variance are frozen before execution. Its cases are derived from the
source-bound capability inventory, not prior success labels; it reports seed
stability separately from overall breadth, must meet every frozen threshold to
admit P5-E, and does not become Runtime routing input.
