"""Typed, risk-proportionate bindings for material task fields."""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class MaterialField(StrEnum):
    RECIPIENT = "recipient"
    PAYEE = "payee"
    AMOUNT = "amount"
    CURRENCY = "currency"
    ACCOUNT = "account"
    EXTERNAL_DESTINATION = "external_destination"
    CHANNEL = "channel"
    CONTENT = "content"
    DESTRUCTIVE_TARGET = "destructive_target"
    DESTRUCTIVE_SCOPE = "destructive_scope"
    FILE = "file"
    PRINCIPAL = "principal"
    RESOURCE = "resource"
    PERMISSION = "permission"
    FORBIDDEN_EFFECT = "forbidden_effect"
    APPROVAL_CONSTRAINT = "approval_constraint"


class MaterialEffectKind(StrEnum):
    NONE = "none"
    SEND = "send"
    PAYMENT = "payment"
    DELETE = "delete"
    SHARE = "share"
    EXTERNAL_ACTION = "external_action"
    IRREVERSIBLE_ACTION = "irreversible_action"


class MaterialBindingKind(StrEnum):
    DIRECT_USER_EXPLICIT = "direct_user_explicit"
    EXACT_SOURCE_EXCERPT = "exact_source_excerpt"
    TYPED_EXTERNAL = "typed_external"
    USER_CONFIRMED = "user_confirmed"


class MaterialBinding(_FrozenModel):
    """One typed material value and the provenance form used to admit it."""

    binding_id: str = Field(min_length=1, max_length=240)
    effect_ref: str = Field(min_length=1, max_length=240)
    field: MaterialField
    value: str = Field(min_length=1, max_length=2_000)
    source_ref: str = Field(min_length=1, max_length=480)
    binding_kind: MaterialBindingKind
    source_anchor_ref: str = Field(default="", max_length=240)
    external_field_ref: str = Field(default="", max_length=480)
    confirmation_ref: str = Field(default="", max_length=480)

    @model_validator(mode="after")
    def validate_binding_form(self) -> "MaterialBinding":
        if not self.value.strip():
            raise ValueError("material binding value cannot be blank")
        if self.binding_kind == MaterialBindingKind.EXACT_SOURCE_EXCERPT:
            if not self.source_anchor_ref or self.external_field_ref or self.confirmation_ref:
                raise ValueError("exact excerpt binding requires only source_anchor_ref")
        elif self.binding_kind == MaterialBindingKind.TYPED_EXTERNAL:
            if not self.external_field_ref or self.source_anchor_ref or self.confirmation_ref:
                raise ValueError("typed external binding requires only external_field_ref")
        elif self.binding_kind == MaterialBindingKind.USER_CONFIRMED:
            if not self.confirmation_ref or self.source_anchor_ref or self.external_field_ref:
                raise ValueError("confirmed binding requires only confirmation_ref")
        elif self.source_anchor_ref or self.external_field_ref or self.confirmation_ref:
            raise ValueError("direct binding cannot claim excerpt/external/confirmation identity")
        return self
