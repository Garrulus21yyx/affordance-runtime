# P5-M4.5-B control/failure convergence review

> Historical convergence snapshot. Its M4.5-C scheduling gate records the
> pre-run state and remains evidence that M4.5-B was not verified. A separately
> authorized diagnostic was subsequently executed at `4924ce6`; current status
> and attribution are owned by the
> [M4.5-C diagnostic record](2026-08-11-p5-m4-5-miniwob-60-diagnostic.md) and the
> [active implementation plan](../current-implementation-plan.md). This review
> is no longer the current execution-queue owner.

> **Lifecycle:** CURRENT REVIEW
> **Date:** 2026-08-11
> **Status authority:** [Implementation Status](../implementation-status.md)
> **Closure evidence:** none; implementation candidate only

## Decision

At the time of this snapshot, M4.5-B was `INTEGRATED_NON_DEFAULT /
REOPENED_CONVERGENCE_REVIEW / IMPLEMENTED_NOT_VERIFIED` and M4.5-C was
`NOT_STARTED / BLOCKED_BY_M4_5_B_CONVERGENCE`. The ten commits after `f04cfd5` and the baseline
dirty tree are implementation candidates, not reviewed closure evidence.

## Causal model

The reopenings share one mechanism: accepted-decision facts were added to a
mutable collector, while legality, terminality and failure precedence remained
distributed across call sites, `AgentLoopState`, session latching, snapshots,
benchmark instrumentation and public result contracts. Each held-out example
therefore found another owner that could create, infer or contradict the same
truth. Example enumeration expanded tests without closing the state algebra.

| Category | Evidence | Convergence response |
|---|---|---|
| Architecture defect | root/continuation legality was split between mutable scopes and state mutation; component origin was inferred from latest operation/request kind | pure reducer owns supported transitions; projections only copy canonical facts |
| Ambiguous contract | `AttemptReceipt` accepted arbitrary non-negative operation/count combinations | constructor enforces operation × disposition × counts/status matrix |
| Duplicated truth | Runtime/result/snapshot/instrumentation/case legacy fields could disagree; classification and result validation repeated precedence | canonical `RuntimeFailure` and `CaseFacts`; one outcome classifier; one compatibility projection |
| Verification defect | list-generated examples were called state-machine properties; impossible receipts were generated and only summed | real `RuleBasedStateMachine` compares production reducer with a small reference model after every rule |
| Governance defect | docs and governance tests required B complete and C next, binding an obsolete reviewed SHA | current truth says reopened/not verified, C blocked, reviewed SHA none; governance checks properties |
| Environmental/scope failure | dirty Runtime privacy substring filtering rejected ordinary selector/xpath/token/href prose; duplicate-key JSON work altered harness behavior | Runtime substring filtering withdrawn; duplicate-key JSON moved out of B as harness-integrity follow-up |
| Over-strict acceptance | a test treated a provider schema byte threshold as behavioral proof | threshold removed; the gate checks invariant schema identity and conformance behavior |

No evidence says the reopenings are independent. The distributed-authority and
example-only acceptance model accounts for all known reopenings.

## Authority and dependency map

```text
raw external output
  -> strict boundary payload model
  -> frozen internal domain value
  -> reduce_control(ControlState, ControlCommand)
  -> AgentLoopState current authority / ControlTransition accepted-decision fact
  -> RuntimeFailure terminal truth
  -> CaseFacts orthogonal runtime/component/watchdog/cleanup/harness facts
  -> classify_case primary benchmark outcome
  -> case evidence codec / legacy fields / export sanitizer / telemetry
```

| Fact | Authority | Consumers that may not infer/override it |
|---|---|---|
| current run control state | `AgentLoopState`, updated through `reduce_control` | transition suffix, snapshots, model views |
| legal root/continuation transition | `agent/control_reducer.py` | loop/session scopes |
| one accepted-decision record | `ControlTransition` produced by reducer command | model history, snapshots, benchmarks |
| execution ordering and retry eligibility | `AgentLoop` / `AgentRunSession` | reducer, projections, telemetry |
| physical attempt | validated `AttemptReceipt` at the port boundary | accounting, transition projection |
| terminal Runtime failure | `RuntimeFailure(stage, kind, code, root/attempt IDs)` | `CaseFacts`, legacy projection, telemetry |
| benchmark fact set | `CaseFacts` | classifier, codec, reports |
| primary benchmark outcome | `external_breadth/classification.py` | campaign/reporting |
| compatibility fields | `legacy_case_projection.py` | old evidence schema only |
| JSON schema/round trip | `case_evidence_codec.py` | reporting/attestation |
| public privacy rejection | `export_sanitizer.py` | serialized evidence tree only |

OTel/Langfuse remain one-way observability sinks and have no Runtime or benchmark
truth authority.

## Bounded supported algebra

`ControlState` contains the contiguous bounded recent root suffix, exact root
total, typed decision-kind totals, exact `SENT_UNKNOWN` total, consumed
confirmation roots, and terminal status. Root identity is sequence-bound and
adjacent roots must share the after/before observation epoch. The state
validator rechecks suffix facts, receipt identity, aggregate projections,
pending/status coherence, kind totals and terminal projection before every
command. Supported commands are:

- `AppendRoot(ControlTransition, recent_limit)` when the session is nonterminal,
  no confirmation is pending, the sequence is contiguous and the root is new;
- `ApplyContinuation(ControlContinuation)` exactly once for a retained root whose
  typed status/pending kind is `WAITING_CONFIRMATION/CONFIRMATION`.

`NONE`, `USER`, `CONFIRMATION` and `UNKNOWN_EFFECT` have an explicit matrix
against nonterminal/terminal statuses; a confirmation continuation cannot
remain confirmation-pending. Terminal states `DONE`, `BLOCKED`, `CANCELLED`
and `FAILED` are absorbing.
Unsupported commands, stale/out-of-window roots, duplicate consumption,
non-contiguous roots and pending-confirmation re-entry return `ControlRejected`
with a bounded deterministic code. The compatibility state methods translate a
typed rejection to `ControlReductionError`; the reducer itself never performs
I/O, persistence, replay or reconstruction.

The reducer is deliberately a finalized-record/state-legality reducer, not an
execution controller. `AgentLoop` and `AgentRunSession` own temporal ordering;
the physical port wrapper emits and counts one receipt per crossed boundary;
the reducer validates the committed candidate record. Non-replay therefore is
proved by the deterministic fake-port loop model comparing session decisions,
port call counts, `RunAccounting`, and reducer/reference state after each
generated step. The reducer alone is not cited as proof that an I/O call did or
did not happen. `AgentLoopState.control_terminal_status` is the single current
terminal authority after a root is committed; the latest transition is checked
as its exact projection, while `AgentResult` and benchmark fields only copy it.

The physical-attempt matrix admits one reset boundary, one independent capture
boundary, or one execute boundary. Returned and exceptional dispositions have
different required origin/status/dispatch/lineage/exception fields. A reset
receipt with execution/effectful counts, an acquired execute without exactly
one post-action acquisition, and duplicate receipt identities are impossible.
Execution and acquisition summaries are checked projections of receipts;
receipts alone own physical-attempt and `SENT_UNKNOWN` truth.

`RuntimeFailure` closes the supported stage × kind algebra. Component invalid
output and call failure are assigned at the evaluation/execute producer, while
exception latching preserves the original exception behavior and carries the
typed failure to the terminal result with root/attempt lineage. `CaseFacts`
checks canonical policy/agent failures against their closed typed codes. The
classifier has an import-time totality gate against every supported canonical
stage × kind pair; typed policy/agent codes may specialize the primary outcome
without parsing messages or code prefixes.

## Testing map and gates

| Test owner | Invariant | Gate |
|---|---|---|
| `test_control_state_machine_properties.py` | root uniqueness, terminal absorption, confirmation once, dispatch non-replay, exact totals, bounded suffix | fast reducer/property |
| `test_run_accounting_properties.py` | only legal receipts sum exactly once; invalid combinations reject at construction | fast contract/property |
| `test_control_outcome_contract.py` | typed statuses/decisions and deterministic unsupported-command rejection | fast contract |
| `test_control_transition_failures.py` | exception/cancel witnesses preserve already committed facts | focused integration |
| `test_benchmark_failure_facts_properties.py` | orthogonal facts, immutable Runtime stage, codec round trip | fast projection/property |
| `test_miniwob_breadth_classification.py` | one classification precedence owner | fast benchmark contract |
| `test_documentation_governance.py` | one status authority, B→C blocking, SHA reviewability | docs/governance |

Known regressions remain witnesses. The former fake continuation test and schema
byte-threshold test were deleted/replaced because they asserted invalid or
non-behavioral abstractions. The former edge-named control module was migrated
to the semantic exceptional-path owner.

## Mature-practice comparison

No directly comparable research SOTA defines this Runtime's exact control and
benchmark algebra, so the comparison uses mature production practices rather
than claiming research novelty:

- Hypothesis' maintained stateful-testing documentation describes chained rules,
  state-dependent preconditions and invariants checked after every step. The new
  reducer machine follows that model instead of treating a generated list as a
  state machine. [Hypothesis stateful testing, accessed 2026-08-11](https://hypothesis.readthedocs.io/en/latest/stateful.html)
- Pydantic documents strict validation and `ConfigDict` controls including
  `extra`, frozen models and instance revalidation. Boundary payload models use
  forbidden extras, frozen values and revalidation; the discriminated union has
  an explicit JSON-object construction seam because nested strict models cannot
  treat an immutable mapping as an already-built model. [Pydantic strict mode](https://docs.pydantic.dev/latest/concepts/strict_mode/), [configuration API](https://docs.pydantic.dev/latest/api/config/), accessed 2026-08-11.
- AWS reliability guidance distinguishes at-most-once, at-least-once and
  idempotent mutation semantics and warns against retrying non-idempotent side
  effects. The session/port discipline therefore permits retry only after a
  typed pre-dispatch `NOT_SENT`; committed `SENT`/`SENT_UNKNOWN` receipts are
  non-replayable. [AWS idempotent operations](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_prevent_interaction_failure_idempotent.html), [retry control](https://docs.aws.amazon.com/wellarchitected/latest/reliability-pillar/rel_mitigate_interaction_failure_limit_retries.html), accessed 2026-08-11.
- OpenTelemetry defines telemetry signals for observing software. Treating those
  signals as downstream evidence—not transactional Runtime authority—is an
  engineering inference consistent with that scope, not a claim made verbatim
  by the specification. [OpenTelemetry observability primer](https://opentelemetry.io/docs/concepts/observability-primer/), accessed 2026-08-11.

These references support the verification and boundary choices; they do not by
themselves prove this implementation correct.

## Alternatives, migration and non-goals

Rejected alternatives are event sourcing, a durable ledger, replay/state
reconstruction, a generic event bus, a provenance graph, Pydantic migration of
all Runtime state, and telemetry-driven execution truth. They add machinery
without closing the proven invariant gap.

The compatibility impact is bounded: `AgentLoopState` keeps its public fields;
legacy case fields and imports remain projections. Current evidence is explicitly
versioned as `target-loop-case.v7` because `CaseFacts` adds canonical
`RuntimeFailure`; the codec retains read compatibility for immutable v6 records.
Duplicate-key JSON validation remains a separate harness-integrity follow-up.

## Exit evidence still required

- the final candidate collected 2,073 cases and passed the full default suite as
  2,058 passed / 15 skipped in 75.69s; Ruff, mypy (428 source files),
  `git diff --check`, clean-process imports, and v6/v7 codec matrices passed;
- the pinned Python 3.12 real active-capture gate is part of the dedicated
  conformance workflow; the default full suite skips it when `MINIWOB_URL` is
  unset, while the fixed-fixture gate passed 2 tests in 2.60s and the complete
  BrowserGym conformance group passed 11 tests in 9.14s;
- fresh Hypothesis seeds 178903, 551209 and 990731 each passed the reducer/fake-
  port state-machine suite; the focused causal suite passed 163 tests in 1.37s;
- completion of the final independent fresh-context held-out review;
- clean committed HEAD and reviewed SHA agreement;
- no held-out case requiring a new production branch.

Two completed independent review rounds falsified earlier candidate states and
kept B reopened. Their findings were resolved through shared validators rather
than witness-specific branches: receipt/summary and projection coherence,
confirmation resolution, epoch/root identity, full state shape validation,
pending/status algebra, receipt identity, stage/kind/code coherence, v6 codec
stability and exact JSON collection types. A third reviewer independently found
that canonical classification omitted production-supported invalid-output
pairs; the classifier is now total by construction. None of these rounds is
closure evidence until the final reviewer, environment gate, clean commit and
reviewed SHA all agree.

Until all items pass, this document is a convergence review, not a closure
attestation. Its original queue blocked M4.5-C; the later separately authorized
diagnostic is recorded by the superseding status owners linked at the top.
