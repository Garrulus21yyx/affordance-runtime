# Diagnosis input boundary

`CaseDiagnosisProjector` accepts only versioned `BenchmarkResultExport` and
`PublicTraceExport` JSON. It copies canonical terminal status/stage/code and
computes only bounded, non-authoritative diagnosis fields.

Generate a deterministic local report:

```bash
cd external/interaction-shell/backend
python -m interaction_shell.diagnosis_cli result.json trace.json --output diagnosis.json
```

Langfuse projection is optional and must be called through `project_fail_open`.
Reporting, export, viewer, or Langfuse failures cannot replace the GUI task
outcome contained in the benchmark result.
