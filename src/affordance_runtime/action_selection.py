"""Runtime-owned 0/1/N selection and sealed selection validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from affordance_runtime.action_choice_catalog import ActionChoiceCatalog
from affordance_runtime.choice_contracts import ActionSelection, ChoicePage, SelectChoice


class SelectionRejectionCode(StrEnum):
    INVALID_ACTION_SELECTION = "INVALID_ACTION_SELECTION"
    UNPRESENTED_CHOICE_ID = "UNPRESENTED_CHOICE_ID"
    STALE_CHOICE_CATALOG = "STALE_CHOICE_CATALOG"


class ActionSelectionError(ValueError):
    def __init__(self, code: SelectionRejectionCode, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code.value}: {detail}" if detail else code.value)


@dataclass(frozen=True)
class ActionSelectionValidator:
    def validate(
        self,
        proposal: SelectChoice,
        catalog: ActionChoiceCatalog,
        page: ChoicePage | None,
    ) -> ActionSelection:
        if page is not None and (
            page.catalog_id != catalog.catalog_id
            or page.catalog_digest != catalog.catalog_digest
        ):
            raise ActionSelectionError(SelectionRejectionCode.STALE_CHOICE_CATALOG)
        if not catalog.contains(proposal.choice_id):
            raise ActionSelectionError(
                SelectionRejectionCode.INVALID_ACTION_SELECTION, proposal.choice_id
            )
        if page is not None and proposal.choice_id not in {
            item.choice_id for item in page.choices
        }:
            raise ActionSelectionError(
                SelectionRejectionCode.UNPRESENTED_CHOICE_ID, proposal.choice_id
            )
        return ActionSelection(
            proposal.choice_id,
            catalog.ref,
            catalog.task_revision,
            catalog.plan_revision,
            catalog.state_version,
            catalog.observation_ref,
            catalog.active_step_id,
            proposal.reason,
        )

    def select_unique(self, catalog: ActionChoiceCatalog) -> ActionSelection:
        if catalog.count != 1:
            raise ActionSelectionError(SelectionRejectionCode.INVALID_ACTION_SELECTION)
        choice = catalog.page(None, 1).choices[0]
        return self.validate(SelectChoice(choice.choice_id, "runtime_unique_choice"), catalog, None)
