"""Runtime-only semantic records for one current observation's evidence."""

from dataclasses import dataclass

from affordance_runtime.immutable import freeze_json


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
