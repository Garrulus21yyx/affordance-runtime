# Integrations

> **Lifecycle:** CURRENT NORMATIVE CONTRACT
> **Scope:** parent-agent, API, CLI, and UI boundary

## 1. Request boundary

Canonical integrations submit a TaskGoal and may attach an optional
EvaluationSpec or explicit strict-ingestion profile. They do not submit raw
selectors, coordinates, backend bindings/endpoints, file paths, approval tokens,
milestone satisfaction, or completion facts.

During migration, legacy TaskSpec-based endpoints may project one-way into new
contracts. New core code never imports those legacy request types.

## 2. Runtime outcomes

Integrations handle:

```text
Done(result)
WaitingUser(question)
WaitingConfirmation(confirmation_subject_id, semantic_summary, consequences)
Failed(reason)
```

Confirmation UX must display the concrete semantic effect/consequences and
return a decision bound to confirmation-subject identity. Runtime reobserves and
rebinds before execution; binding-only changes do not require another prompt.

## 3. Observation and action privacy

External APIs may expose AgentWorldView and privacy-safe ControlTransition
summaries. They do not
expose credentials, selectors, backend handles, signed URLs, or unrestricted
screenshots/trace by default.

## 4. Cancellation and resume

Cancellation can stop before the next primitive action. A cancel racing with an
effectful dispatch cannot claim the action did not occur; the Runtime returns
SENT_UNKNOWN and requests typed fresh acquisition when supported. Acquisition
failure does not authorize replay. Current target does not promise process-
crash checkpoint/resume.

## 5. Benchmark integrations

Benchmark adapters translate environments into the same world/action/evaluation
contracts. They cannot pass hidden expected answers or fixture metadata into
the policy or Runtime.

## 6. Evidence-gated Vision providers

Vision is configured as independent provider roles, not one provider that
implicitly owns observation, identity and execution:

- open-world visual entity proposal: disabled by default. Set
  `VISUAL_REGION_PROVIDER=omniparser` and `OMNIPARSER_BASE_URL` to use the thin
  official `POST /parse/` adapter. `OMNIPARSER_API_KEY` and
  `OMNIPARSER_MODEL_ID` are optional. Setting `VISUAL_REGION_PROVIDER=vlm`
  explicitly enables the compatible VLM proposer instead.
- DOM-candidate visual disambiguation: the configured visual VLM receives a
  bounded SoM screenshot and supplied `E*` inventory, and may return only one
  offered E-ref or `null`.
- point grounding: GLM/ShowUI/UI-TARS-style adapters remain explicit offline
  grounding or legacy-compatibility benchmark arms. They are not offered as a
  BrowserGym target-loop capability and cannot create an ActionBinding.

The target-loop BrowserGym path uses only an explicitly configured region
proposer and/or E-ref disambiguator. A legacy benchmark option may still build
a GLM point adapter for isolated comparison, but the target-loop environment
does not call or advertise it. The OmniParser
adapter consumes the current server schema documented by the
[official OmniParser repository](https://github.com/microsoft/OmniParser/tree/master/omnitool/omniparserserver).
It imports none of OmniTool's planner, memory or executor.

All provider outputs remain observations or proposals. Runtime's typed visual
gate decides whether a call occurs; `EntityCorrespondence`/`WorldFusion` own
identity; action-space admission and currentness own DOM execution authority.
Region-proposer action claims are discarded at all current adapter boundaries;
an unmatched V-ref remains observation-only.
