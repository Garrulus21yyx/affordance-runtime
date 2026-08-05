"""One-way projection from a full Catalog to a bounded semantic page."""

from __future__ import annotations

from dataclasses import dataclass

from affordance_runtime.action_choice_catalog import ActionChoiceCatalog
from affordance_runtime.choice_contracts import ChoicePage, ChoicePresentation


@dataclass(frozen=True)
class ChoicePresentationProjector:
    page_size: int = 32
    projection_policy_id: str = "semantic-choice-v1"

    def project(self, catalog: ActionChoiceCatalog, cursor: str | None = None) -> ChoicePage:
        offset = int(cursor or 0)
        catalog_slice = catalog.page(cursor, self.page_size)
        choices = tuple(
            ChoicePresentation(
                choice_id=item.choice_id,
                action_kind=item.action_kind,
                target_id=item.target_id,
                target_label=item.target_label,
                target_role=item.target_role,
                destination_id=item.destination_id,
                requirement_refs=item.requirement_refs,
                effect_refs=item.effect_refs or item.criterion_ids,
                evidence_refs=item.evidence_refs,
                relevant_current_state=item.relevant_current_state,
                conflict_status=item.conflict_status,
                risk=item.risk,
                generation_reason_codes=item.generation_reason_codes,
            )
            for item in catalog_slice.choices
        )
        return ChoicePage(
            catalog.catalog_id,
            catalog.catalog_digest,
            catalog.count,
            len(choices),
            offset // self.page_size,
            self.page_size,
            choices,
            catalog_slice.next_cursor is not None,
            catalog_slice.next_cursor,
            self.projection_policy_id,
        )
