"""Bind evaluated outputs to current artifact evidence without model projection."""

from affordance_runtime.evaluation.contracts import EvaluatedOutput
from affordance_runtime.world.contracts import WorldObservation
from affordance_runtime.world.evidence_refs import canonical_artifact_ref


def collect_current_outputs(
    requested_output_ids: tuple[str, ...],
    observation: WorldObservation,
) -> tuple[EvaluatedOutput, ...]:
    outputs = []
    for output_id in requested_output_ids:
        matches = tuple(
            (source, value) for source in observation.sources
            for key, value in source.artifacts.items() if str(key) == output_id
        )
        if len(matches) != 1:
            continue
        source, value = matches[0]
        outputs.append(EvaluatedOutput(output_id, value, (canonical_artifact_ref(source.observation_id, output_id),)))
    return tuple(outputs)
