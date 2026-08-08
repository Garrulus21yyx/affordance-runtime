"""Runtime-only semantic records for one current observation's evidence."""

from dataclasses import dataclass

from affordance_runtime.immutable import freeze_json
from affordance_runtime.world.source_profile import ObservationAssurance, ObservationModality


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_ref: str
    observation_id: str
    kind: str
    source_id: str
    source_observation_id: str = ""
    source_modality: str = ""
    source_assurance: str = ""
    subject_id: str = ""
    predicate: str = ""
    value: object = None
    artifact_kind: str = ""
    output_id: str = ""
    public_summary: str = ""

    def __post_init__(self) -> None:
        if not self.evidence_ref.strip() or not self.observation_id.strip() or not self.kind.strip():
            raise ValueError("evidence record requires current identity and kind")
        if len(self.output_id) > 240 or len(self.public_summary) > 500:
            raise ValueError("evidence record public artifact fields exceed their bounds")
        object.__setattr__(self, "value", freeze_json(self.value))

    @property
    def has_typed_source(self) -> bool:
        if not self.source_observation_id:
            return False
        try:
            ObservationModality(self.source_modality)
            ObservationAssurance(self.source_assurance)
        except ValueError:
            return False
        return True


def evidence_source_is_current(record: EvidenceRecord, observation) -> bool:
    return record.has_typed_source and any(
        source.observation_id == record.source_observation_id for source in observation.sources
    )
