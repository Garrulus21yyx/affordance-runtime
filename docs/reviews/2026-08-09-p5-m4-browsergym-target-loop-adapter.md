# P5-M4 BrowserGym target-loop adapter review

Date: 2026-08-09
Scope: pinned BrowserGym/MiniWoB mechanical adapter and fixed smoke gates

## Decision

Model compatibility research is `CLOSED_FOR_CURRENT_SCOPE` and `NON_BLOCKING`.
The primary recurrent interface remains one-stage `AgentPolicy.decide(context)`
with the `format-only.v1` factory default. `compact-contract.v1` remains an
explicit action-selection-only profile. `compact-contract.v2` is
`EXPERIMENTAL_NOT_ADMITTED` and fails closed unless the explicit conformance
gate is set. Two-stage is `DIAGNOSTIC_ONLY` and is not imported by production
policy, AgentLoop, surfaces, or this adapter.

## Pinned API inventory

- package: `browsergym-miniwob==0.14.3` (`browsergym-core==0.14.3`)
- MiniWoB source identity: commit `7fd85d71a4b60325c6585396ec4f48377d049838`
- registry: 125 `browsergym/miniwob.*` environments in the pinned package
- reviewed IDs: `browsergym/miniwob.click-button`,
  `browsergym/miniwob.enter-text`, `browsergym/miniwob.choose-list`
- lifecycle: `reset -> (observation, info)`,
  `step -> (observation, reward, terminated, truncated, info)`, `close`
- structural inputs: goal, URL identity, accessibility tree, DOM snapshot and
  extra element properties
- official actions: `click(bid)`, `fill(bid, value)`, and
  `select_option(bid, options)`
- official mechanical state: MiniWoB reward/DONE signals exposed by BrowserGym
- browser/page/service ownership: the adapter's private owner thread; cleanup
  closes the environment, stops its BrowserGym Playwright owner and joins once

## Owner map and contracts

`browsergym_environment.py` owns lifecycle, reset, post-step cache and close.
`browsergym_projection.py` maps current structural data to WorldObservation.
`browsergym_binding.py` owns observation-scoped bids, fingerprints and private
option values. `browsergym_execution.py` validates and converts activate/fill/
select. `browsergym_verifier.py` maps current official status to COMPLETE,
INCOMPLETE or UNKNOWN and creates opaque current evidence. `composition.py`
connects the public TaskGoal, policy and mechanical evaluators. No target-core
file imports BrowserGym.

Reset creates a fresh environment at seed 7, retains the task ID only as
private metadata, admits only the public task instruction into TaskGoal, and
projects the first observation. Projection is structural/structural/structural,
bounded to 64 targets, 128 facts, 8 facts per target, 16 select options, with
truthful coverage and truncation. Bids, selectors, XPath, locators, screenshots,
reward and oracle values do not enter AgentContext.

Bindings are short-lived and tied to source observation, revision, episode,
page identity, role, label digest, state fingerprint and supported primitive.
Every execute performs exactly one read-only probe. A mismatch or unavailable
probe returns `NOT_SENT` and makes zero action calls. A successful dispatch
calls BrowserGym step once; a post-dispatch exception is `SENT_UNKNOWN`, with
no retry. The returned post-step observation is cached and consumed by the
next observe exactly once.

## Conformance and evidence

The `browsergym-adapter-conformance` profile uses a scripted structured
decision port, but still serializes AgentContext and traverses the canonical
strict parser, Runtime admission, private binding, real BrowserGym step, fresh
observation, official verifier and AgentLoop. Real pinned results are:

| case | terminal | policy calls | steps/probes | official success |
|---|---:|---:|---:|---:|
| click-button | DONE | 1 | 1/1 | 1 |
| enter-text | DONE | 2 | 2/2 | 1 |
| choose-list | DONE | 2 | 2/2 | 1 |

All cases have zero retry, fallback, forbidden effects, duplicate unknown
attempts, stale zero-call violations, SENT_UNKNOWN and cleanup failures. The
clean-head adapter attestation is the only source of
`target_loop_adapter_ready=true`; package/version, exact registry, all 3 cases,
cleanup, oracle isolation, manifest digest, source identity and clean revision
must agree.

## Live boundary

The only admitted live profile is one-stage Mistral `mistral-medium-3-5`,
`format-only.v1`, environment-native evaluator, zero retry/fallback, with a
fixed benchmark-only 7.5-second inter-policy-call interval. Pacing is neither
backoff nor AgentLoop authority. The configured profile passed the clean
exact-head internal DOM attestation: DONE, two observations, one execution,
one Mistral provider attempt, and zero retry/fallback or safety violations.
External preflight is admitted. At the time of this implementation review the
independent `RUN_EXTERNAL_SMOKE=1` opt-in was absent, so no formal smoke had
run. Current execution status is determined by the protected exact-head
workflow artifact. Adapter CI does not substitute for live smoke; the manual
workflow retains the explicit execution gate.

BrowserGym adapter status is
`CLOSED_FOR_PINNED_MINIWOB_MECHANICAL_PROFILE`; each reviewed task is
`ADAPTER_CONFORMANCE_ATTESTED`. External generalization is `NOT_CLAIMED`, and
the default Coordinator path is unchanged.
