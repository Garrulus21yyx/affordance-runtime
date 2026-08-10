# P5-M4.2 verified progress and repeated-action containment

Date: 2026-08-10
Scope: local BrowserGym fill/select correctness and watchdog observability

## Decision

The formal external smoke at revision `cd49b8e` remains `FAILED / case
timeout`. Its diagnostic chain was repeated enter-text fill after the first
successful BrowserGym step because action-level evaluation remained UNKNOWN.
This record closes that local correctness gap only. No Mistral or other remote
provider was called, no protected workflow or external smoke was run, and no
attestation was generated. Local evidence cannot backfill the historical run.

## Mechanical effects

`browsergym_action_evaluator.py` owns fill/select action postconditions. Fresh,
complete structural facts confirm `EFFECT_CONFIRMED` when the public value
changes to the requested value. Already-equal or complete structurally
unchanged state is `NO_EFFECT_CONFIRMED`. Missing targets, truncated coverage,
weak assurance, conflicts, or an unresolvable value remain UNKNOWN. Evidence
always belongs to the fresh after-observation fact. `activate` stays UNKNOWN;
only the separate official BrowserGym verifier can complete the task.

## Run-scoped containment and feedback

`SemanticAttemptKey` contains semantic action/target/destination and a canonical
JSON SHA-256 parameter digest; it excludes action/context/observation/request,
binding, selector, bid, href, and raw parameter identities. Fill/select are
pre-suppressed only when current complete structural public state proves the
requested postcondition. Suppression occurs before Binder/currentness/step and
does not fabricate execution or transport evidence. The first suppression
emits a route-free bounded event and continues; the next same attempt under an
unchanged narrow task/criterion/output/target predicate fingerprint fails with
`NO_PROGRESS_REPETITION`. A different value remains legal and executable.

At most three recent events enter `AgentProgressView`, with truthful total and
truncation. The feedback says the postcondition is already satisfied and a
strategy transition is required; it does not direct Submit or choose any next
action.

## Timeout and local proof

An immutable partial episode snapshot preserves observations, executions,
currentness probes, completed policy turns, latest task/action status, latest
attempt digest, repeat/no-progress counts and last event type. Benchmark
watchdog timeout reports `termination_origin=harness_watchdog`,
`case_failure_code=case_timeout`, and `partial_episode_available=true` while
leaving `terminal_reason_code` null. It cannot resume or replay the session.

Pinned real local results with MiniWoB source commit
`7fd85d71a4b60325c6585396ec4f48377d049838` are:

| regression | result | BrowserGym steps | primitive calls |
|---|---|---:|---|
| enter-text progress-aware | DONE | 2 | fill 1, activate 1 |
| enter-text forced repeat | FAILED / NO_PROGRESS_REPETITION | 1 | fill 1 |
| choose-list | DONE | 2 | select 1, activate 1 |
| click-button | DONE | 1 | activate 1 |

The fixed manifest now uses 10 turns per case; at 7.5-second minimum pacing its
minimum schedule is below the unchanged 120-second watchdog with a fixed
5-second margin. Current manifest digest is
`sha256:d31a8ed5078c196181994dded00eb2325f867c71820b1f990fab148e9a90e112`.

Parser, current context/page/action/destination admission, ActionSpace,
format-only default, retry/fallback policy, and default Coordinator are
unchanged. General planning, liveness proof, external benchmark completion and
model generalization are not claimed.
