# Architecture Change Admission Template

> **Lifecycle:** CURRENT TEMPLATE
> **Authority:** [Canonical GUI Agent Execution Architecture](../task-execution-authority-map.md)
> **Use before:** changing an owner, retained state, AgentDecision/tool schema,
> planner/objective/evidence contract, execution ordering, projection boundary,
> or benchmark composition path

Copy this template into a dated change-admission record before production code
is edited. Empty, multiple-owner, or “TBD” authority answers mean the work is an
architecture review, not an implementation patch.

## Problem and evidence

- Observed behavior:
- Exact revision/profile:
- Evidence artifact:
- Why this is a shared invariant gap rather than a case-specific defect:

## Canonical comparison

| Required question | Answer |
|---|---|
| Which exact stage in authority-map section 3 changes? | |
| Who is the single primary owner? | |
| Which section-2 invariant is affected? | |
| What authoritative input changes? | |
| What typed output/outcome changes? | |
| Which complete consumers read that output? | |
| Does the main Agent decision algebra change? Why is that unavoidable? | No / |
| Does any projection become authoritative? | No |
| Which old owner/path will be deleted? | |
| Does temporal ordering change? | No / |
| Which unsupported cases fail closed, and how? | |

## Causal model

- Root mechanism:
- Violated invariant:
- Architecture defect vs implementation defect vs provider/environment defect:
- Known witnesses explained by the same mechanism:
- Evidence that would falsify this explanation:

## Smallest coherent change

- Canonical contract changes:
- Production modules changed:
- Consumers migrated:
- Displaced files/callers/tests/docs deleted:
- Explicit non-goals:

## Verification

- Property/state-machine tests:
- Projection/currentness/exceptional-path tests:
- Known regression witnesses:
- Held-out or generated variations:
- Fresh real benchmark/profile:
- Exact closure evidence location:

Implementation completion and verified closure must be recorded separately.
