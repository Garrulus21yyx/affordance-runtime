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

Vision is configured as three independent provider roles, not one provider that
implicitly owns observation, identity and execution:

- `visual-only query -> point`: GLM is the default implementation. It reads
  `LLM_ZHIPU_BASE_URL`, `LLM_ZHIPU_API_KEY` and
  `LLM_ZHIPU_VISION_MODEL`; `LLM_VISUAL_PROFILE` cannot replace this role.
- open-world visual entity proposal: disabled by default. Set
  `VISUAL_REGION_PROVIDER=omniparser` and `OMNIPARSER_BASE_URL` to use the thin
  official `POST /parse/` adapter. `OMNIPARSER_API_KEY` and
  `OMNIPARSER_MODEL_ID` are optional. Setting `VISUAL_REGION_PROVIDER=vlm`
  explicitly enables the compatible VLM proposer instead.
- DOM-candidate visual disambiguation: the configured visual VLM receives a
  bounded SoM screenshot and supplied `E*` inventory, and may return only one
  offered E-ref or `null`.

`--visual-grounding` therefore enables GLM point grounding by default; it does
not silently enable GLM as an open-world region proposer. The OmniParser
adapter consumes the current server schema documented by the
[official OmniParser repository](https://github.com/microsoft/OmniParser/tree/master/omnitool/omniparserserver).
It imports none of OmniTool's planner, memory or executor.

All provider outputs remain observations or proposals. Runtime's typed visual
gate decides whether a call occurs; `EntityCorrespondence`/`WorldFusion` own
identity; action-space admission and currentness own coordinate authority.
Region-proposer action claims are discarded at all current adapter boundaries;
only the separate point-grounder result can nominate a point.
