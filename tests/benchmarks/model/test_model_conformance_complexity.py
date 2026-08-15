import json

from affordance_runtime.benchmarks.model_conformance.complexity import measure_model_input_complexity


def test_complexity_measurement_matches_actual_serialized_values() -> None:
    context = json.dumps({
        "actions": {"options": [{"destinations": {"items": [{"destination_id": "d"}]}}]},
        "world": {
            "targets": {"items": [{"target_id": "t"}]},
            "facts": {"items": [{"fact_ref": "fact:x"}]},
            "conflicts": {"items": []}, "artifact_summaries": {"items": []},
        },
        "history": {"items": [{"turn": 1}]},
    }, separators=(",", ":"), sort_keys=True)
    schema = {"$defs": {"A": {"type": "object"}}, "oneOf": [{"$ref": "#/$defs/A"}]}
    measured = measure_model_input_complexity(context, "system", schema)
    assert measured.serialized_context_bytes == len(context.encode())
    assert measured.system_prompt_bytes == len(b"system")
    assert measured.schema_defs == 1
    assert measured.schema_variants == 1
    assert measured.actions == measured.destinations == measured.targets == measured.facts == 1
    assert measured.history_turns == 1
