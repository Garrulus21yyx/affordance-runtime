"""Effect-specific admission policy for material task bindings."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from affordance_runtime.material_contracts import (
    MaterialBinding,
    MaterialBindingKind,
    MaterialEffectKind,
    MaterialField,
)
from affordance_runtime.source_envelope import SourceAnchor, SourceEnvelope, SourceKind, SourceRef
from affordance_runtime.task_intake import CompilationIssue, OperationClass, RequestedEffect, UserRequest

_REQUIRED_FIELD_GROUPS: dict[MaterialEffectKind, tuple[frozenset[MaterialField], ...]] = {
    MaterialEffectKind.SEND: (
        frozenset({MaterialField.RECIPIENT}),
        frozenset({MaterialField.EXTERNAL_DESTINATION, MaterialField.CHANNEL}),
        frozenset({MaterialField.CONTENT, MaterialField.FILE}),
    ),
    MaterialEffectKind.PAYMENT: (
        frozenset({MaterialField.PAYEE, MaterialField.ACCOUNT}),
        frozenset({MaterialField.AMOUNT}),
        frozenset({MaterialField.CURRENCY}),
    ),
    MaterialEffectKind.DELETE: (
        frozenset({MaterialField.DESTRUCTIVE_TARGET}),
        frozenset({MaterialField.DESTRUCTIVE_SCOPE}),
    ),
    MaterialEffectKind.SHARE: (
        frozenset({MaterialField.PRINCIPAL}),
        frozenset({MaterialField.RESOURCE, MaterialField.FILE}),
        frozenset({MaterialField.PERMISSION}),
    ),
    MaterialEffectKind.EXTERNAL_ACTION: (frozenset({MaterialField.EXTERNAL_DESTINATION}),),
    MaterialEffectKind.IRREVERSIBLE_ACTION: (frozenset({MaterialField.DESTRUCTIVE_TARGET}),),
}

_REQUIRED_OPERATION_CLASS: dict[MaterialEffectKind, OperationClass] = {
    MaterialEffectKind.SEND: OperationClass.EXTERNAL_SIDE_EFFECT,
    MaterialEffectKind.PAYMENT: OperationClass.EXTERNAL_SIDE_EFFECT,
    MaterialEffectKind.SHARE: OperationClass.EXTERNAL_SIDE_EFFECT,
    MaterialEffectKind.EXTERNAL_ACTION: OperationClass.EXTERNAL_SIDE_EFFECT,
    MaterialEffectKind.DELETE: OperationClass.IRREVERSIBLE,
    MaterialEffectKind.IRREVERSIBLE_ACTION: OperationClass.IRREVERSIBLE,
}


@dataclass(frozen=True)
class MaterialBindingPolicy:
    """Validate typed field coverage without demanding character spans everywhere."""

    def validate(
        self,
        request: UserRequest,
        envelope: SourceEnvelope,
        effects: tuple[RequestedEffect, ...],
        bindings: tuple[MaterialBinding, ...],
    ) -> list[CompilationIssue]:
        issues: list[CompilationIssue] = []
        effect_ids = [effect.effect_id for effect in effects if effect.effect_id]
        if len(effect_ids) != len(set(effect_ids)):
            issues.append(CompilationIssue(code="duplicate_material_effect_id", field="requested_effects"))
        binding_ids = [binding.binding_id for binding in bindings]
        if len(binding_ids) != len(set(binding_ids)):
            issues.append(CompilationIssue(code="duplicate_material_binding_id", field="material_bindings"))
        effect_by_id = {effect.effect_id: effect for effect in effects if effect.effect_id}
        valid_bindings: list[MaterialBinding] = []

        material_effects = tuple(
            effect
            for effect in effects
            if effect.operation_class in {OperationClass.EXTERNAL_SIDE_EFFECT, OperationClass.IRREVERSIBLE}
            or effect.material_effect_kind != MaterialEffectKind.NONE
        )
        for index, effect in enumerate(material_effects):
            if not effect.effect_id:
                issues.append(
                    CompilationIssue(
                        code="material_effect_id_required",
                        field=f"requested_effects[{index}].effect_id",
                    )
                )
            if effect.material_effect_kind == MaterialEffectKind.NONE:
                issues.append(
                    CompilationIssue(
                        code="material_effect_kind_required",
                        field=f"requested_effects[{index}].material_effect_kind",
                    )
                )
            elif effect.operation_class != _REQUIRED_OPERATION_CLASS[effect.material_effect_kind]:
                issues.append(
                    CompilationIssue(
                        code="material_effect_operation_mismatch",
                        field=f"requested_effects[{index}].operation_class",
                        detail=effect.material_effect_kind.value,
                    )
                )

        for index, binding in enumerate(bindings):
            if binding.effect_ref not in effect_by_id:
                issues.append(
                    CompilationIssue(
                        code="material_binding_unknown_effect",
                        field=f"material_bindings[{index}].effect_ref",
                        detail=binding.effect_ref,
                    )
                )
                continue
            issue = self._validate_provenance(request, envelope, binding, index=index)
            if issue is None:
                valid_bindings.append(binding)
            else:
                issues.append(issue)

        values_by_field: dict[tuple[str, MaterialField], set[str]] = {}
        for binding in valid_bindings:
            key = binding.effect_ref, binding.field
            values_by_field.setdefault(key, set()).add(_normalized(binding.value))
        for (effect_ref, field), values in values_by_field.items():
            if len(values) > 1:
                issues.append(
                    CompilationIssue(
                        code="material_binding_conflict",
                        field=field.value,
                        detail=effect_ref,
                    )
                )

        fields_by_effect: dict[str, set[MaterialField]] = {}
        for binding in valid_bindings:
            fields_by_effect.setdefault(binding.effect_ref, set()).add(binding.field)
        for effect in material_effects:
            if not effect.effect_id or effect.material_effect_kind == MaterialEffectKind.NONE:
                continue
            present = fields_by_effect.get(effect.effect_id, set())
            for group in _REQUIRED_FIELD_GROUPS[effect.material_effect_kind]:
                if present.isdisjoint(group):
                    issues.append(
                        CompilationIssue(
                            code="material_binding_missing",
                            field="|".join(sorted(item.value for item in group)),
                            detail=effect.effect_id,
                        )
                    )
        return issues

    def binding_digest(
        self,
        envelope: SourceEnvelope,
        bindings: tuple[MaterialBinding, ...],
    ) -> str:
        if not bindings:
            return envelope.binding_digest
        payload = json.dumps(
            {
                "source_envelope_ref": envelope.identity,
                "envelope_binding_digest": envelope.binding_digest,
                "material_bindings": [
                    item.model_dump(mode="json") for item in sorted(bindings, key=lambda item: item.binding_id)
                ],
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()

    def _validate_provenance(
        self,
        request: UserRequest,
        envelope: SourceEnvelope,
        binding: MaterialBinding,
        *,
        index: int,
    ) -> CompilationIssue | None:
        anchor_by_id = {item.anchor_id: item for item in envelope.anchors}
        source_by_id = {item.source_id: item for item in envelope.sources}
        source = _resolve_source(binding.source_ref, anchor_by_id, source_by_id)
        field = f"material_bindings[{index}]"
        if source is None:
            return CompilationIssue(
                code="material_binding_provenance_insufficient",
                field=field,
                detail=binding.source_ref,
            )
        if source.kind == SourceKind.TARGET:
            return CompilationIssue(
                code="observation_cannot_authorize_material_binding",
                field=field,
                detail=binding.source_ref,
            )

        if binding.binding_kind == MaterialBindingKind.DIRECT_USER_EXPLICIT:
            if source.kind != SourceKind.REQUEST or not _contains_explicit_value(request.raw_text, binding.value):
                return CompilationIssue(
                    code="material_binding_provenance_insufficient",
                    field=field,
                    detail="direct value is not explicit in the user request",
                )
            return None

        if binding.binding_kind == MaterialBindingKind.EXACT_SOURCE_EXCERPT:
            anchor = anchor_by_id.get(binding.source_anchor_ref)
            if (
                anchor is None
                or anchor.span is None
                or anchor.material_field != binding.field
                or anchor.source_id != source.source_id
                or _digest(binding.value) != anchor.content_digest
            ):
                return CompilationIssue(
                    code="material_binding_provenance_insufficient",
                    field=field,
                    detail="exact excerpt does not match the typed field binding",
                )
            return None

        if binding.binding_kind == MaterialBindingKind.TYPED_EXTERNAL:
            if source.kind not in {
                SourceKind.CONVERSATION,
                SourceKind.ATTACHMENT,
                SourceKind.PROFILE,
                SourceKind.EXTERNAL,
            }:
                return CompilationIssue(
                    code="material_binding_provenance_insufficient",
                    field=field,
                    detail="typed external binding requires a versioned external authority source",
                )
            return None

        if source.kind != SourceKind.CONVERSATION or binding.confirmation_ref != source.external_ref:
            return CompilationIssue(
                code="material_binding_provenance_insufficient",
                field=field,
                detail="confirmation must bind a versioned conversation confirmation record",
            )
        return None


def _resolve_source(
    source_ref: str,
    anchor_by_id: dict[str, SourceAnchor],
    source_by_id: dict[str, SourceRef],
) -> SourceRef | None:
    if source_ref in source_by_id:
        return source_by_id[source_ref]
    anchor = anchor_by_id.get(source_ref)
    return source_by_id.get(anchor.source_id) if anchor is not None else None


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _contains_explicit_value(raw_text: str, value: str) -> bool:
    normalized_text = _normalized(raw_text)
    normalized_value = _normalized(value)
    return bool(
        normalized_value
        and re.search(
            rf"(?<!\w){re.escape(normalized_value)}(?!\w)",
            normalized_text,
        )
    )


def _digest(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()
