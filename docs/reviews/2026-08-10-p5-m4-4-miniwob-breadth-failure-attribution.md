# P5-M4.4 MiniWoB breadth failure attribution

> **Lifecycle:** REVISION-SCOPED REVIEW
> **Decision boundary:** the rerun-blocked conclusion below records the state at
> M4.4 closure. A later separately authorized clean rerun-v3 completed at 4/60;
> see its [immutable evidence record](../evidence/runs/p5-m4-4-miniwob-60-seed7-83dc4fa-rerun-v3/README.md)
> and [current implementation status](../implementation-status.md). It does not
> rewrite or merge the historical 6/60 run described here.

## Historical evidence boundary

The immutable P5-M4.3 run at `b3b64a2c338f0bc76af5d7a16dfddfed513152c4`
remains a valid negative breadth result: 60/60 planned cases completed, 6
succeeded, and its attestation SHA-256 is
`a7f3ed5637edb7403bce454c3209a1d98fb256b5a7148416ea9c341a013f2c02`.
Its archive is unchanged. The 10% result is scoped to that exact seeded run and
does not establish general GUI or model capability.

## Failure attribution

New breadth reports preserve bounded component failure origin and code,
exception class only, the last decision and evaluation states, ActionSpace and
world-target counts, coverage, pending kind, and partial-session availability.
The classifier prioritizes official success, transport and safety status,
policy failure, Runtime terminal reason, evaluation status, then component
origin. It no longer uses `other_typed_failure` as a normal catch-all.

Read-only reclassification of the historical archive can recover one
`ask_user_unresolved` case. Twenty-seven cases remain
`unresolved_legacy_evidence` because the old schema did not retain enough
bounded stage data. This analysis does not rewrite old outcomes or invent
precise causes.

## Capability inventory v2

The v1 inventory was primitive-only and insufficient for readiness. Inventory
v2 covers all 125 pinned registry tasks once across bounded interaction,
observation, reasoning, and control requirements. Requirements are sourced
from pinned task implementations and reviewed static rules, never campaign
outcomes or benchmark answers. The historical 60-task overlay contains 15
declared-supported, 31 declared-unsupported, and 14 unassessed tasks. These
labels do not change the historical denominator or result.

## No-model local diagnostics

A deterministic hash selection chose up to three cases from each historical
non-provider outcome group. All 22 selected cases reset and projected locally
with seed 7. The raw structural source exposed 103 interactive nodes; 51 became
semantic targets (49.51% coverage), with 20 blank labels and 12 duplicate
labels. The ActionSpace exposed 51 options: 31 activate, 19 fill, and 1 select.
All 22 initial official verifier states were incomplete.

None of the three sampled historical environment failures reproduced during
the reset/projection-only probe. Conservative dispositions were 8
policy-or-reasoning candidates, 7 requirement-unsupported, and 7
requirement-unassessed. These are diagnostic candidates, not retroactive model
blame or repaired campaign results.

The seven historical provider-unavailable cases occupy positions 54–60 as one
tail streak. No provider call was made here; formal capacity is neither
declared nor demonstrated.

## Admission decision

P5-M4.4 failure attribution is `PARTIAL`: future evidence is fully attributable,
but 27 legacy cases remain unresolved. Capability inventory v2 is `CLOSED` for
the pinned registry. A new 60-task run is
`BLOCKED_WITH_EXPLICIT_ERRORS` until unresolved historical evidence is accepted
as legacy-only, provider capacity is declared and sufficient, and all readiness
gates are evaluated on a clean validated head. P5-E is
`BLOCKED_BY_SHORT_LOOP_BREADTH` and has not started.

This slice made zero live-provider calls, did not rerun or backfill MiniWoB-60,
and did not change AgentLoop, BrowserGym adapter behavior, ActionSpace behavior,
parser or Runtime admission, retry/fallback, grounding, or the default product
path.
