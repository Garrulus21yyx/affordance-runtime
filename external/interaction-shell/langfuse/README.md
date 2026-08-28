# Langfuse analysis configuration

Langfuse is the primary engineering-analysis UI. Runtime evidence is committed
to local JSONL first; the isolated viewer worker then creates one case root
tagged by `run_attempt_id`, suite, profile, and case. Generation observations
populate the standard model, input/output/total usage, and provider-measured
duration.

Provider usage is billable usage. Scores under
`request_admission_estimate.*` are capacity estimates and must never be added to
provider usage or cost. A generation without provider cost records
`cost_disposition=langfuse_model_definition_required`; configure its exact model
ID in Langfuse before treating cost as available. This repository does not pin
vendor prices or wrap Langfuse's dashboard API.

Create these project views and keep trace drill-down enabled:

| View | Group/filter | Values |
|---|---|---|
| Outcome / turn / cost | benchmark status, profile, case | `benchmark_status`, `runtime_mechanical.turns`, standard generation cost |
| Model usage / latency | standard model, provider/profile | standard input/output/total usage and observation duration |
| Prompt growth / composition | run attempt, case, generation sequence | standard input usage plus `request_admission_estimate.*` scores/metadata |
| Stall / recovery | case, status | `runtime_mechanical.control_stall_count`, `state_oscillation_count`, `action_policy_recovery_calls`, retries/repairs |
| Bad-case cause | `bad_case_category`, case, profile | category score plus trace metadata and linked native result |
| High-cost / high-turn queue | descending cost or turns | trace link, benchmark status, run attempt, case |

Annotation queues are for human open coding of representative successful,
failed, blocked, high-turn, and high-cost cases. Any later model-assisted label
must be observation-level, evidence-linked, calibrated against held-out human
labels, and never benchmark or Runtime truth.
