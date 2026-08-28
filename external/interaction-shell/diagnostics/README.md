# Completed-run analysis boundary

The benchmark runner persists the authoritative case result and a bounded,
non-authoritative `analysis/<case_id>.json` read model. The analysis contains
disjoint provider usage, request-admission estimates, Runtime mechanical facts,
trajectory evidence, and one typed Bad-case presentation projection.

`CompletedRunSummaryResolver` reads only explicitly configured completed-run
directories. It copies the persisted Bad-case `category | stage | origin | code |
termination_source | summary` fields and never parses failure prose, reconstructs
Runtime state, or guesses a likely upstream stage.

Langfuse remains the primary engineering-analysis surface. Shell exposes only a
bounded summary and independent Langfuse/local evidence links. Reporting,
analysis export, Viewer, or Langfuse failures cannot replace the native benchmark
outcome.
