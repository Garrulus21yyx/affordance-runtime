# P5-M4.5 MiniWoB-60 diagnostic at `4924ce6`

> Diagnostic interpretation only. The immutable JSON payload is archived at
> [`p5-m4-5-miniwob-60-seed7-4924ce6-diagnostic`](../evidence/runs/p5-m4-5-miniwob-60-seed7-4924ce6-diagnostic/).
> The payload directory contains exactly the 64 byte-preserved JSON files
> produced by the run and no explanatory or derived files.

## Evidence identity and result

- source commit: `4924ce61748d8efdec4fcc6de494acf8a9f224cc`;
- run ID: `miniwob-60:e9551acfcd31466e91481ee5923fc9af`;
- frozen manifest: `miniwob-60-seed7-v1`;
- completed: 60/60;
- successful: 8/60;
- evidence valid: true;
- generalization claim: `NOT_CLAIMED`.

Outcome counts are 8 success, 25 task failure, 14 waiting-user/task-unknown,
10 Runtime rejection, 2 no-progress repetition and 1 case timeout. The run used
290 provider attempts and 555,164 tokens. It is an independently authorized
diagnostic record, not a replacement for the historical 6/60 or rerun-v3 4/60
records and not evidence that M4.5-B is verified closed.

## Shared diagnostic findings

### Currentness semantic-owner mismatch

Forty-two currentness checks reported stale; inspection classified 41 as false
rejections. AX projection and the DOM currentness probe do not share a canonical
semantic owner:

- tabs project as AX `link / Tab #N`, while the DOM probe reports
  `presentation / ""`;
- Book Flight inputs project AX labels `From:` and `To:`, while the DOM probe
  reports an empty label.

Page identity, episode identity, BID, ready state and done state remained
unchanged in these cases. The convergence target is one shared AX canonical
normalizer used by projection and probe. Task-specific exceptions and removal
of the fingerprint are explicit non-solutions.

### Observation semantic breadth

Seventeen cases ended with zero targets and zero action options while coverage
was `complete`. Twelve cases repeatedly requested action pages for 10 turns
with zero execution; five were dominated by repeated observation requests
without acquiring new task semantics. These empty-loop patterns consumed about
74% of tokens and 75% of wall time.

The existing coverage value means that supported roles were not truncated; it
does not mean the observation contains task-complete semantics. Those two
claims require separate typed contracts.

### Verifier outcome algebra

Fourteen `waiting_user_task_unknown` outcomes currently collapse distinct
states: an explicit negative terminal environment result, genuinely unavailable
verifier evidence, and other unknown combinations. The BrowserGym verifier
projection maps multiple negative combinations to `UNAVAILABLE`, which then
becomes task `UNKNOWN`.

The required contract preserves raw reward/terminated/done semantics and adds a
typed terminal-failure fact instead of treating explicit negative termination
as verifier unavailability.

## Next diagnostic order

1. Preserve this evidence payload byte-for-byte; this note remains outside it.
2. Converge currentness projection and probe on one AX canonical normalizer.
3. Split structural coverage from task-semantic sufficiency.
4. Close the verifier terminal-failure/unavailable/unknown algebra.

No finding in this note changes the maintained status: M4.5-B remains reopened
and implemented-not-verified, and M4.5-C remains blocked.
