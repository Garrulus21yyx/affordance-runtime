# Runtime-first R1: Criteria-Bound Progress Evidence

Date: 2026-07-22

## Scope

This increment closes Phase R1 from the current architecture audit without
claiming completion of M8.4 or M8.5. It is Runtime-owned and does not depend on
BrowserGym semantics.

## Implemented invariant

Successful action verification and successful task progress are separate.
Subgoal and accepted TaskSkill progress now require every mandatory criterion
and evidence requirement to be covered by explicit links from strong evidence
captured in the current observation epoch.

The shared `CriteriaEvidenceMatcher` rejects evidence when it is unrelated,
partial, weak, failed, missing an identity, or bound to a stale environment
revision or snapshot. `SubgoalVerificationReport` and
`SkillStepVerificationReport` preserve the structured result. The Coordinator
records accepted criterion-to-evidence links and rejected match reports in the
trace.

`VerifierSpec` carries trusted criterion and requirement identities into the
hashed ActionContract. `VerifierLadder` emits evidence with a stable identity,
source, strength, environment revision, snapshot, and timestamp. Planner
proposals still cannot invent backend handles, coordinates, capabilities, or
approval authority.

## Negative controls

- unrelated passed evidence does not advance progress;
- partial coverage leaves the remaining criterion pending;
- stale revision/snapshot evidence is rejected;
- receipt-only weak evidence is rejected;
- one evidence item covers multiple criteria only through explicit links;
- a passed but unbound postcondition cannot checkpoint an accepted TaskSkill.

## Verification

```text
pytest -q
412 passed

ruff check src tests scripts
All checks passed!

mypy --ignore-missing-imports src
Success: no issues found in 73 source files
```

The repository-wide Ruff formatter is not a release gate for this revision;
lint, type, test, and whitespace checks are the claimed local gates.

## Remaining gates

R2 remains next: introduce context-rich task planning, monotonic plan lineage,
and a normal non-BrowserGym multi-stage proof. R3-R5 remain unchanged. No new
benchmark-family semantic rule was added by this increment.
