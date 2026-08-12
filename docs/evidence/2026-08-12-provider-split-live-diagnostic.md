# Provider-Split Live Diagnostic — 2026-08-12

> **Lifecycle:** VALID DIAGNOSTIC FAILURE EVIDENCE
> **Acceptance:** FAILED; no performance or generalization claim

## Run identity

- working-tree snapshot commit: `0a155669755b7a335f386513cfd30cb87dd5f4e7`
- model/provider: `zhipu / glm-4.1v-thinking-flashx`
- MiniWoB URL: project-local `127.0.0.1:18888/miniwob/`
- cases: frozen seed-7 visual witness set
- OmniParser: not configured; this run does not evaluate OmniParser model quality
- runner evidence validity: `true`

The snapshot is an ephemeral clean commit constructed from the current dirty
working tree. It is exact for this diagnostic but is not a clean main-repository
acceptance SHA.

## Aggregate result

- completed: `5/5`
- task success: `0/5`
- outcomes: `3 verifier_unknown`, `2 task_failed`
- visual gate acceptance: `false`
- point-grounder calls/successes: `3 / 1`
- E-ref disambiguator calls/selections: `13 / 0`
- visual bindings acquired/dispatched: `1 / 0`

| Case | Outcome | Point | E-ref | Visual binding | Primary observed failure |
|---|---|---:|---:|---:|---|
| `grid-coordinate` (`05`) | verifier unknown | 1/1 | 0/0 | 1/0 | valid point and unmatched binding existed, but task evaluation stopped before policy with `source_insufficient` |
| `click-pie-nodelay` (`34`) | verifier unknown | 1/0 | 0/0 | 0/0 | point response failed structured validation |
| `click-shades` (`42`) | task failed | 0/0 | 11/0 | 0/0 | multi-target visual attribute task was misrouted to single E-ref disambiguation; turn budget exhausted after structural actions |
| `click-pie` (`49`) | verifier unknown | 1/0 | 0/0 | 0/0 | point response failed structured validation |
| `visual-addition` (`60`) | task failed | 0/0 | 2/0 | 0/0 | visual counting task was misrouted to single E-ref disambiguation and reached terminal failure |

## Direct provider probes

The same snapshot and real provider were probed without changing production
logic.

1. For `click-pie-nodelay`, GLM returned an `answer` object explaining that no
   item labelled `0` was visible because the menu was still closed. The point
   parser correctly rejected it. This demonstrates a query/lifecycle mismatch:
   one point call received a compound two-step task rather than the current
   objective `expand the menu` followed by fresh observation.
2. For `click-shades` and `visual-addition`, candidate disambiguation failed
   strict E-ref validation. The latter response consumed the bounded response
   in a `<think>` analysis of the visual counting task and emitted no E-ref JSON.
3. The BrowserGym visual projection currently catches provider validation
   exceptions and persists only acquisition failure counters, not the provider
   error class/reason. The direct probes were necessary to recover these error
   categories.

## Causal gaps demonstrated

1. `visual-only query -> point` needs a current atomic objective, not the whole
   compound task instruction.
2. Candidate ambiguity is not sufficient to choose E-ref mode. Single-target
   disambiguation, multi-target attribute selection and visual-value extraction
   require distinct typed evidence needs.
3. The GLM thinking model needs a response contract/token strategy that reliably
   leaves room for the final bounded JSON, or a compatible non-thinking choice
   configuration.
4. Evaluator lineage must accept the authoritative structured source within a
   fused world acquisition; exact equality with the canonical fused world ID
   currently turns a usable visual binding into `source_insufficient`.
5. Provider failures need typed persisted observability; swallowing the error
   type blocks attribution between transport, schema and semantic abstention.

## Artifact hashes

- aggregate report: `sha256:ab0a9130aa3f38601443b261cd631f8403d8944fd2b75a32065936ec207a09db`
- `05`: `sha256:332294e45cce3385f16f7592dd71b2f3765da55c04bad38516e61322f20cf204`
- `34`: `sha256:f154deae7e9729ed61a78e24f66bfc0cedf2944eaa3e35d5426c01e4ed14ecaf`
- `42`: `sha256:7a365bc1e2098f3977aab9b428d71231e52837586b886a75661d57e937402191`
- `49`: `sha256:7e24b2e860564dda5312a07316697f9836fbebeeaa1efcdd90c56ecbe921c5d3`
- `60`: `sha256:360780c7e9491c5fffe20888e79c5768dc530f7d6886199d1dde4e8d1ea8fe6b`

Raw generated reports remain in the local diagnostic output directory
`/tmp/affordance-live-gate-small/output/`; this maintained record contains the
bounded reproducible conclusions and hashes.

## Phase-3 remediation rerun

Lifecycle remains **VALID DIAGNOSTIC FAILURE EVIDENCE**; the live gate is not
closed.

- exact ephemeral working-tree snapshot:
  `98ff366906ff92705b1db7f21cb45de159ea4ddc`
- full local verification before rerun: `2355 passed, 27 skipped`
- completed cases: `5/5`; durable `progress.json` reports `complete=true`
- task success: `1/5` (`visual-addition`)
- outcomes: `1 success`, `2 structured_output_failure`,
  `2 no_progress_repetition`
- report hash:
  `sha256:aa72a41a9f3a189e10c17dadcfd9b8818a29c8791f36f1749464eb76bacb452e`
- progress hash:
  `sha256:be2e0e6a144d1de64e87917f00477adce78910a31b00f07a1235b17131c47d9c`

Observed causal changes:

1. `visual-addition` made zero E-ref/point calls and completed through the
   screenshot-aware main VLM (`fill` then DOM `activate`). This validates the
   visual-value routing correction.
2. `click-shades` made two E-ref calls with two valid selections. Correspondence
   narrowed the executable world to one DOM binding, and the first click had a
   verified visual effect. The second main-policy call failed tool-argument
   validation; this is no longer arbitrary execution over 13 candidates.
3. `grid-coordinate` and both pie variants acquired point evidence in this run,
   but none completed. Isolated public probes showed GLM point predictions can
   miss the visible target materially; GLM is therefore usable as the configured
   port implementation but not quality-attested by this gate.
4. The prior fused-world `source_insufficient` failure did not recur.
5. Provider stage/code counters are present in every case artifact. This run had
   no provider-boundary validation failure; failures occurred later in grounding
   quality or main-policy tool output.
6. Each case JSON and `progress.json` was atomically persisted before the next
   case; final aggregate reporting no longer owns the only result copy.

Raw remediation artifacts remain at
`/tmp/affordance-live-gate-final-7qK9Ze/output/`. They are local diagnostic
evidence, not a clean-mainline or generalization attestation.
