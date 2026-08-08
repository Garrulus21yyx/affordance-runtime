import json
from collections.abc import Callable
from dataclasses import dataclass, field

from affordance_runtime.model_policy import ModelBackedAgentPolicy, ModelDecisionResponse, ModelMetadata

DecisionScript = Callable[[dict[str, object], int], dict[str, object] | str]


@dataclass
class ScriptedStructuredDecisionPort:
    script: DecisionScript
    calls: int = 0
    requests: list[object] = field(default_factory=list)
    context_ids: list[str] = field(default_factory=list)

    async def generate(self, request):
        self.calls += 1
        self.requests.append(request)
        context = json.loads(request.serialized_context)
        self.context_ids.append(context["context_id"])
        payload = self.script(context, self.calls)
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        return ModelDecisionResponse(raw, ModelMetadata("fixture", "scripted", f"response:{self.calls}"))


def first_action_model_policy() -> ModelBackedAgentPolicy:
    def decide(context, call):
        del call
        option = context["actions"]["options"][0]
        return {
            "type": "select_action",
            "context_id": context["context_id"],
            "action_id": option["action_id"],
            "parameters": {},
            "destination_id": "",
        }

    return ModelBackedAgentPolicy(ScriptedStructuredDecisionPort(decide))
