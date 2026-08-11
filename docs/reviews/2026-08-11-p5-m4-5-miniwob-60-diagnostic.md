# P5-M4.5-C MiniWoB-60 diagnostic attribution at `4924ce6`

> This document interprets one immutable diagnostic run. The byte-preserved
> payload is archived at
> [`p5-m4-5-miniwob-60-seed7-4924ce6-diagnostic`](../evidence/runs/p5-m4-5-miniwob-60-seed7-4924ce6-diagnostic/).
> That payload contains exactly the 64 JSON files produced by the run and no
> explanatory or derived files. Later code, tests or documentation must not be
> described as capabilities of this historical run.

## Evidence identity and result

- executed Git SHA / `attestation.git_sha`:
  `4924ce61748d8efdec4fcc6de494acf8a9f224cc`;
- pinned MiniWoB source commit / `attestation.source_commit`:
  `7fd85d71a4b60325c6585396ec4f48377d049838`;
- run ID: `miniwob-60:e9551acfcd31466e91481ee5923fc9af`;
- frozen manifest: `miniwob-60-seed7-v1`;
- manifest digest:
  `sha256:ae83bb8f0d16fc89f4d47262f921642a8a808eb7e378e5be19f348a6ef0f9d17`;
- profile/model/provider:
  `mistral-format-only-v1` / `mistral-medium-3-5` / `mistral`;
- evidence archive commit:
  `5f8d6acf3700831a05d73f93a5c66488a6298fd7`;
- product-code difference between the run commit and archive commit: none under
  `src/` or `tests/`;
- completed: 60/60;
- successful: 8/60 (13.33%);
- evidence valid: true;
- provider attempts: 290;
- total tokens: 555,164;
- wall time: approximately 37 minutes;
- acceptance errors: none;
- generalization claim: `NOT_CLAIMED`.

Outcome counts are 8 success, 25 task failure, 14 waiting-user/task-unknown,
10 Runtime rejection, 2 no-progress repetition and 1 case timeout. This run is
an independently authorized diagnostic record. It does not replace the
historical clean 6/60 run or the separately authorized rerun-v3 4/60 record,
does not retroactively verify M4.5-B, and has no predeclared performance or
generalization acceptance claim.

## Attribution method and confidence

Four evidence levels are kept distinct:

1. **OBSERVED_RUN_FACT** is present directly in the immutable campaign/case
   payload.
2. **DERIVED_RUN_FACT** is reproducible from those JSON files through an
   explicit selector or formula; it does not itself assert a root cause.
3. **SOURCE_BACKED_ATTRIBUTION** joins a repeated run pattern to a reachable
   implementation path in the exact `4924ce6` tree.
4. **NOT_PROVEN / FUTURE_REMEDIATION** covers hypotheses, adjacent source
   defects and later changes that require a new implementation SHA and run ID.

Targeted case names are regression witnesses, not closure evidence. Closure
requires the invariant and property gates recorded below.

## Run-attributed findings

| Run pattern | Exact result from this run | Source-confirmed attribution | Confidence | Remediation owner |
|---|---|---|---|---|
| execution and currentness accounting | 98 Runtime execute requests and currentness/backend probes; 56 BrowserGym steps = 43 click + 12 fill + 1 select; the remaining 42 requests did not step; related violation/exception counters were zero | typed acquisition, `ControlTransition`, physical attempt accounting and zero-call admission were functioning in this campaign; the 42 rejected requests are a currentness precision problem, not missing transition accounting | observed and derived run facts | maintain existing M4.5-A/B owners; no new execution ledger |
| false currentness rejection | the 42 no-step attempts are concentrated in cases 18, 35, 48, 50, 55 and 58 | observation projection fingerprints Chrome AX role/name/state, while the live probe reconstructs role/name/state with a hand-written DOM heuristic and then requires exact equality; post-run raw inspection classified 41 as false and case 35's one result as a true terminal stale | source-backed attribution; the immutable 64 JSON files do not contain per-attempt probe payloads, so the 41/1 split is not an observed payload field | P5-M4.6-A canonical BrowserGym semantics/currentness |
| empty semantic/action surface | 17 cases ended with zero targets and zero action options while the only projected coverage value was `complete` | BrowserGym projection removes every role outside the currently executable role map before creating `SemanticTarget` and before computing coverage, coupling observable semantics to executable primitives | observed/derived run fact plus exact-source reproduction; this run does not prove which missing role each task requires or that broader projection guarantees success | P5-M4.6-C semantic inventory, then M4.6-E breadth |
| page no-gain shape | 12 cases each report 10 turns, 10 policy calls, one observation, zero executions and final `RequestActionPage` | empty-cursor page requests are unconditionally admitted and `page_unchanged` only continues | derived run shape plus exact-source reproduction; the archive stores only the final decision, not all ten decision payloads | P5-M4.6-D bounded control no-gain |
| observation no-gain shape | independent cases 02, 13, 20, 39 and 60 end on `RequestObservation`, perform zero executions and retain 1–3 targets/actions; four have 10 turns/11 observations and case 13 times out after 7 turns/8 observations | observation freshness compares identity, while every BrowserGym capture advances the observation serial | derived run shape plus exact-source reproduction; the archive has no per-turn semantic digest and therefore does not prove every capture was semantically identical | P5-M4.6-D identity-free observation gain |
| verifier unknown compression | 14 cases ended as `waiting_user_task_unknown` | the three-state verifier recognizes only one success conjunction and one ongoing conjunction; all other combinations become `UNAVAILABLE`, then task `UNKNOWN` | observed result plus exact-source reproduction; the archived payload does **not** prove that any particular member was a negative terminal outcome | P5-M4.6-B verifier/task-terminal algebra |
| local repeated-action containment | 2 cases terminated as `no_progress_repetition` | the existing fill/select local liveness guard was exercised; this is not evidence for a general planner or task-progress auditor | direct run fact | retain the existing `ProgressController`; do not turn it into a universal controller |
| uncertain dispatch | zero `SENT_UNKNOWN` outcomes | the campaign supplies no live evidence for uncertain-dispatch non-replay even though an implementation/property path exists | direct absence | separate fault-injection evidence if this claim is later required |

The 12 page-loop-shaped and five observation-loop-shaped cohorts used 293,740
of 555,164 tokens (52.91%) and 1,313,164.386 of 2,230,996.871 milliseconds
(58.86%). These figures are derived from the immutable case files; they replace
any earlier informal 74%/75% estimate.

The 8/60 outcome is therefore a valid diagnostic result, but it is not a clean
measurement of policy competence alone. Currentness false rejection,
observation-semantic omission, verifier information loss and non-effect control
loops materially constrained the policy-facing world in this exact run.

### Reproducible cohort selectors

- currentness no-step cohort: cases 18, 35, 48, 50, 55 and 58;
- zero-target/action cohort: cases 04, 05, 07, 14, 17, 26, 28, 33, 34, 36,
  38, 43, 44, 47, 49, 52 and 57;
- page-loop-shaped cohort: cases 07, 14, 17, 26, 28, 33, 34, 38, 43, 44, 49
  and 52;
- observation-loop-shaped cohort: cases 02, 13, 20, 39 and 60;
- previous verifier-unknown cohort: cases 01, 03, 08, 10, 11, 21, 22, 32,
  35, 41, 42, 46, 54 and 59.

These selectors freeze the baseline cohorts. They do not authorize rewriting
the old case classifications after a repair.

## P5-M4.6-A — canonical BrowserGym semantics/currentness

The immediate implementation slice is a single canonical semantics owner used
by projection and currentness. It must preserve strict drift containment while
removing AX-versus-DOM semantic disagreement.

Required boundaries:

- AX computed role, accessible name and selected state have one canonicalizer;
- the owner-thread probe reads current AX data through the pinned read-only
  BrowserGym path and does not call public `capture()`, allocate an observation
  identity, replace bindings or count an acquisition;
- page, episode, BID existence, task-ready/done, canonical semantics,
  availability and primitive compatibility remain strict currentness axes;
- owner-scoped select options retain public labels separately from private
  native values;
- hidden, disabled, readonly or unknown-availability controls may be observed
  but cannot receive an executable binding;
- task aliases, removal of label/fingerprint checks, BID-only currentness,
  event sourcing and a new state platform are forbidden.

Run witnesses are the five false-currentness task families and the true
terminal `login-user-popup` path. Exit is property-based: unchanged canonical
world must be current; any bound semantic/physical drift must be `NOT_SENT`
with zero step; probe failure must be typed currentness-unavailable; currentness
probe count must equal the physical backend probe count.

## P5-M4.6-B — verifier and task-terminal truth

The verifier must distinguish `SUCCESS`, `INCOMPLETE`,
`TERMINAL_TASK_FAILURE` and `UNAVAILABLE` through one pure classifier. Missing,
invalid, inconsistent and unsupported facts remain bounded reason codes rather
than new top-level states.

A task-domain terminal failure must not be projected as
`RuntimeFailure(CONTROL, REJECTED)`. `TaskEvaluation`, loop control,
`AgentResult`, `CaseFacts` and benchmark classification must carry a typed task
terminal code orthogonally to Runtime failure. Negative mechanical evidence
uses neutral status-evidence references, never completion-evidence references.

The live cohort is named the **14 previous verifier-unknown cases**. It must not
be called a negative-terminal cohort until a new run records the complete
verifier facts. Deterministic truth-table/property tests and one known real
MiniWoB wrong-action terminal are required in addition to that cohort.

## P5-M4.6-C — semantic inventory truth

Existing `CoverageState.COMPLETE` retains its current meaning: the declared
projection profile was acquired without budget truncation. It is already used
to trust explicit fill/select facts and must not be redefined as task-semantic
completeness.

`SurfaceObservation` instead gains a typed semantic-inventory summary with a
profile identity, `UNASSESSED/EMPTY/REPRESENTED/PARTIAL` status and bounded
recognized/projected/actionable/non-executable/omitted/informational counts.
The model source summary copies those facts and names the old field
`projection_coverage`. `ActionSpace` remains the only action-availability
authority. Task-relative requirement coverage remains outside the adapter.

The 17 zero-target cases are first rerun without a model to validate inventory
truth. A zero target count is only honest when the inventory separately says
empty, partial or unassessed; `projection_coverage=complete` must no longer be
interpretable as proof of task-semantic completeness.

## P5-M4.6-D — bounded control no-gain

A small pure control-liveness owner records only the latest request/result
digests and consecutive streak in `AgentLoopState`. It covers
`RequestActionPage` and policy-origin `RequestObservation`, not Runtime binding,
currentness, confirmation or post-action refresh.

The first exact no-gain result returns typed feedback; the second consecutive
same request and same result terminates as
`no_progress_control_repetition`. Empty cursor is not intrinsically invalid:
returning from a later page to the first page remains legal. Observation gain
uses an identity-free public semantic digest and excludes every observation,
target, fact, evidence, binding, action, action-space, page and private BID/route
identity. Task terminal truth is evaluated before no-progress termination.

Wait retains its existing time/turn/observation budgets in this slice and is not
given the same two-strike policy without new evidence.

## P5-M4.6-E — stable identity and semantic breadth

Before adding broad informational roles, ordinal-derived target identity must
move to a run-scoped opaque digest of private stable identity. Raw BID remains
private. This adjacent identity risk is source-confirmed but was not the cause
of the 41 false stale results.

Observable and executable roles then expand separately and under quotas:
checkbox/radio/menuitem/tab first become observable and receive activation only
after primitive conformance; spinbutton/slider remain read-only without an
adjust primitive; option belongs to its select owner; table/list/heading/static
content uses bounded informational targets, facts and relations so it cannot
crowd out controls.

## Adjacent source defects not attributed to this run

The exact source tree also permits a whole-page option domain to be assigned to
every select, ordinal-sensitive target identity, and bindings for some
disabled/readonly controls. These defects belong to M4.6-A/E because they share
the canonical BrowserGym owner, but the `4924ce6` evidence does not establish
that they caused any of its 52 failures. Documentation and future reports must
retain that distinction.

## Rerun and promotion order

1. M4.6-A properties and deterministic/pinned currentness witnesses.
2. M4.6-B complete verifier algebra and the previous-unknown cohort.
3. M4.6-C no-model inventory evidence for the 17 zero-target cases.
4. M4.6-D state-machine properties and bounded live page/observation cohorts.
5. M4.6-E stable identity and staged semantic breadth.
6. One new immutable same-profile MiniWoB-60 run after the targeted gates.
7. P5-M4.7 supported-subset multi-seed only after predeclared thresholds.

No old JSON may be rewritten or reclassified in place. Every rerun gets a new
run ID, exact source SHA, immutable directory and interpretation record. A
future improvement may be compared with this 8/60 diagnostic, but it cannot be
attributed to one code change if multiple M4.6 slices are combined before the
measurement.

## Maintained status after this run

```text
P5-M4.5-A: COMPLETE_NON_DEFAULT
P5-M4.5-B: INTEGRATED_NON_DEFAULT / REOPENED_CONVERGENCE_REVIEW / IMPLEMENTED_NOT_VERIFIED
Current reviewed M4.5-B closure SHA: NONE
P5-M4.5-C diagnostic execution: COMPLETE / EVIDENCE_VALID
P5-M4.5-C performance threshold: NOT_PREDECLARED / NOT_CLAIMED
Generalization: NOT_CLAIMED
P5-M4.6 evidence-directed remediation: NOT_STARTED / NEXT
P5-M4.7 supported-subset multi-seed: NOT_STARTED / BLOCKED_BY_M4_6_GATES
P5-E long-horizon: NOT_STARTED / BLOCKED_BY_BREADTH_GATES
```

M4.5-C occurred under separate diagnostic authorization even though the prior
M4.5-B convergence document had blocked it. That historical gate remains
evidence that B was not verified; it is not permission to describe an executed
campaign as `NOT_STARTED`. M4.6 may repair source-confirmed product gaps while
the independent B assurance review remains open. Neither work item authorizes
VerifiedTaskState, TaskProgressAuditor, planner, ledger, replay, event sourcing
or state reconstruction.
