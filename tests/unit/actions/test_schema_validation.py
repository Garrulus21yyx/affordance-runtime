import math

import pytest

from affordance_runtime.actions.schema_validation import (
    validate_parameter_schema_contract,
    validate_value,
)
from affordance_runtime.model.policy.tool_contracts import ToolSpec


def test_finite_schema_ast_accepts_bounded_containers_scalars_and_discriminated_union() -> None:
    schema = {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "const": "names"},
                    "values": {
                        "type": "array",
                        "items": {"type": "string", "minLength": 1, "maxLength": 8},
                        "minItems": 1,
                        "maxItems": 3,
                    },
                },
                "required": ["kind", "values"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "kind": {"type": "string", "const": "range"},
                    "value": {"type": "number", "minimum": 0, "maximum": 10},
                },
                "required": ["kind", "value"],
                "additionalProperties": False,
            },
        ]
    }

    validate_parameter_schema_contract(schema)
    ToolSpec("finite", "finite contract", schema)
    validate_value({"kind": "names", "values": ["Ada", "李"]}, schema)
    validate_value({"kind": "range", "value": 2.5}, schema)


@pytest.mark.parametrize(
    "schema",
    (
        {"type": "object", "properties": {}, "unknown": True},
        {
            "type": "object",
            "properties": {"values": {"type": "array", "items": {"type": "string"}}},
            "additionalProperties": False,
        },
        {
            "oneOf": [
                {
                    "type": "object",
                    "properties": {"kind": {"type": "string", "enum": ["same"]}},
                    "required": ["kind"],
                    "additionalProperties": False,
                },
                {
                    "type": "object",
                    "properties": {"kind": {"type": "string", "const": "same"}},
                    "required": ["kind"],
                    "additionalProperties": False,
                },
            ]
        },
        {
            "type": "object",
            "properties": {"value": {"type": "number", "minimum": math.nan}},
            "additionalProperties": False,
        },
    ),
)
def test_finite_schema_ast_rejects_unknown_unbounded_ambiguous_or_nonfinite_shapes(schema) -> None:
    with pytest.raises(ValueError):
        validate_parameter_schema_contract(schema)


def test_schema_value_validation_rejects_union_cross_product_and_nonfinite_number() -> None:
    schema = {
        "oneOf": [
            {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "const": "E1"},
                    "value": {"type": "string", "enum": ["A"]},
                },
                "required": ["target", "value"],
                "additionalProperties": False,
            },
            {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "const": "E2"},
                    "value": {"type": "string", "enum": ["B"]},
                },
                "required": ["target", "value"],
                "additionalProperties": False,
            },
        ]
    }
    with pytest.raises(ValueError, match="union"):
        validate_value({"target": "E1", "value": "B"}, schema)
    with pytest.raises(ValueError):
        validate_value(math.inf, {"type": "number"})
