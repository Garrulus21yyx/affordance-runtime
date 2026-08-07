"""Minimal trusted execution-context, coordinate, capability, and provenance contracts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field, fields, is_dataclass
from time import time
from typing import Any, Iterable, Mapping, cast
from urllib.parse import parse_qsl, unquote, urlsplit

from affordance_runtime.immutable import freeze_json, to_json_compatible

_SECRET_NAMES = frozenset({"authorization", "cookie", "credential", "password", "private_key", "secret", "signature", "token"})
_SIGNED_QUERY_NAMES = _SECRET_NAMES | frozenset(
    {"access_key", "api_key", "key", "sig", "x_amz_credential", "x_amz_signature", "x_goog_signature"}
)


def digest_payload(value: object) -> str:
    encoded = json.dumps(
        to_json_compatible(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def describe_component(component: object) -> Mapping[str, Any]:
    """Return a secret-free provenance projection including public configuration."""

    explicit = getattr(component, "provenance_descriptor", None)
    configured = explicit() if callable(explicit) else explicit
    if configured is None:
        configured = {
            name: value
            for name, value in vars(component).items()
            if not name.startswith("_") and _provenance_value_supported(value)
        }
    descriptor = {
        "component": type(component).__module__ + "." + type(component).__name__,
        "configuration": configured,
    }
    ensure_secret_free(descriptor)
    return freeze_json(to_json_compatible(descriptor))


def _provenance_value_supported(value: object) -> bool:
    if value is None or isinstance(value, (str, int, float, bool)):
        return True
    if is_dataclass(value):
        return True
    if isinstance(value, Mapping):
        return all(_provenance_value_supported(key) and _provenance_value_supported(item) for key, item in value.items())
    if isinstance(value, (list, tuple, set, frozenset)):
        return all(_provenance_value_supported(item) for item in value)
    return False


@dataclass(frozen=True)
class ExecutionContextRequirementRef:
    context_ref: str
    account_ref: str
    profile_ref: str
    tenant_ref: str

    @classmethod
    def local_public(cls) -> "ExecutionContextRequirementRef":
        return cls("context:local-public", "account:local-public", "profile:default", "tenant:local")

    def __post_init__(self) -> None:
        _require_identity(self)


@dataclass(frozen=True)
class SurfaceLease:
    lease_id: str
    run_id: str
    session_generation: str
    surface_id: str
    issued_at_s: float
    expires_at_s: float
    focus_generation: str

    def current(self, binding: "LiveSurfaceBinding", *, now_s: float | None = None) -> bool:
        current_time = time() if now_s is None else now_s
        return (
            current_time <= self.expires_at_s
            and self.run_id == binding.run_id
            and self.session_generation == binding.session_generation
            and self.surface_id == binding.surface_id
            and self.focus_generation == binding.focus_generation
        )


@dataclass(frozen=True)
class LiveSurfaceBinding:
    account_ref: str
    profile_ref: str
    tenant_ref: str
    session_generation: str
    run_id: str
    window_id: str
    tab_id: str
    frame_id: str
    document_generation: str
    focus_generation: str
    surface_id: str
    lease: SurfaceLease

    def __post_init__(self) -> None:
        _require_identity(self)
        if not self.lease.current(self, now_s=self.lease.issued_at_s):
            raise ValueError("surface lease does not bind the live surface")

    def matches_requirement(self, requirement: ExecutionContextRequirementRef) -> bool:
        return (
            self.account_ref == requirement.account_ref
            and self.profile_ref == requirement.profile_ref
            and self.tenant_ref == requirement.tenant_ref
        )

    @property
    def digest(self) -> str:
        return digest_payload(self)


@dataclass(frozen=True)
class CoordinateBinding:
    screenshot_ref: str
    viewport_width: int
    viewport_height: int
    crop_xywh: tuple[float, float, float, float]
    scroll_xy: tuple[float, float]
    device_pixel_ratio: float
    zoom: float
    scale: float
    orientation: str
    origin: str
    frame_id: str
    document_generation: str
    transform_digest: str = ""

    def __post_init__(self) -> None:
        if min(self.viewport_width, self.viewport_height) <= 0:
            raise ValueError("coordinate binding requires a positive viewport")
        if min(self.device_pixel_ratio, self.zoom, self.scale) <= 0:
            raise ValueError("coordinate scale factors must be positive")
        if not all((self.orientation, self.origin, self.frame_id, self.document_generation)):
            raise ValueError("coordinate binding requires orientation/origin/frame/document identity")
        expected = digest_payload({field.name: getattr(self, field.name) for field in fields(self) if field.name != "transform_digest"})
        if self.transform_digest and self.transform_digest != expected:
            raise ValueError("coordinate transform digest mismatch")
        object.__setattr__(self, "transform_digest", expected)

    def current_for(self, surface: LiveSurfaceBinding) -> bool:
        return self.frame_id == surface.frame_id and self.document_generation == surface.document_generation


@dataclass(frozen=True)
class ExecutorCapabilityDescriptor:
    provider_id: str
    tool_schema_digest: str
    adapter_id: str
    adapter_version: str
    supported_backends: tuple[str, ...]
    provider_actions: tuple[str, ...]
    adapter_actions: tuple[str, ...]
    provider_capabilities: tuple[str, ...] = ()
    adapter_capabilities: tuple[str, ...] = ()
    backend_actions: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    backend_provider_capabilities: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    backend_adapter_capabilities: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_identity(self)
        if not self.supported_backends:
            raise ValueError("executor descriptor requires explicit backend support")

    @property
    def supported_actions(self) -> frozenset[str]:
        return frozenset(self.provider_actions) & frozenset(self.adapter_actions)

    def actions_for(self, backend: str) -> frozenset[str]:
        declared = self.backend_actions.get(backend)
        return frozenset(declared) if declared is not None else self.supported_actions

    def provider_capabilities_for(self, backend: str) -> frozenset[str]:
        declared = self.backend_provider_capabilities.get(backend)
        return frozenset(declared) if declared is not None else frozenset(self.provider_capabilities)

    def adapter_capabilities_for(self, backend: str) -> frozenset[str]:
        declared = self.backend_adapter_capabilities.get(backend)
        return frozenset(declared) if declared is not None else frozenset(self.adapter_capabilities)


@dataclass(frozen=True)
class EffectiveCapabilities:
    capabilities: frozenset[str]
    intersection_digest: str

    @classmethod
    def intersect(
        cls,
        *,
        provider: Iterable[str],
        adapter: Iterable[str],
        product_policy: Iterable[str],
        user_grants: Iterable[str],
    ) -> "EffectiveCapabilities":
        result = frozenset(provider) & frozenset(adapter) & frozenset(product_policy) & frozenset(user_grants)
        return cls(result, digest_payload(sorted(result)))


@dataclass(frozen=True)
class RunProvenanceManifest:
    code_digest: str
    product_profile_digest: str
    policy_digest: str
    provider_digest: str
    schema_digest: str
    transform_digest: str
    acquisition_digest: str
    verifier_digest: str
    environment_digest: str

    def __post_init__(self) -> None:
        _require_identity(self)

    @property
    def digest(self) -> str:
        return digest_payload(self)

    def assert_matches(self, current: "RunProvenanceManifest") -> None:
        if self != current:
            raise ValueError("run provenance manifest drift")


@dataclass(frozen=True)
class RouteBinding:
    """Secret-free, fully pinned projection of the route that may be dispatched."""

    backend: str
    provider_id: str
    tool_schema_digest: str
    adapter_id: str
    adapter_version: str
    encoder_id: str
    encoder_version: str
    route_policy_digest: str
    action: str
    target_id: str
    destination_id: str
    target_locator_ref: str
    destination_locator_ref: str
    input_binding_refs: tuple[str, ...]
    named_parameters: Mapping[str, Any]
    application_payload: Mapping[str, Any]
    payload_digest: str
    observation_digest: str
    surface_binding_digest: str
    coordinate_transform_digest: str
    provenance_digest: str

    def __post_init__(self) -> None:
        _require_identity(self, allow_blank=("destination_id", "destination_locator_ref"))
        ensure_secret_free(
            {
                field.name: getattr(self, field.name)
                for field in fields(self)
                if field.name not in {"named_parameters", "application_payload"}
            }
        )
        ensure_secret_free(self.named_parameters)
        ensure_secret_free(self.application_payload)
        expected_payload = deterministic_application_payload(
            action=self.action,
            target_id=self.target_id,
            destination_id=self.destination_id,
            named_parameters=self.named_parameters,
        )
        if to_json_compatible(expected_payload) != to_json_compatible(self.application_payload):
            raise ValueError("application payload does not match pinned deterministic encoding")
        expected_digest = digest_payload(expected_payload)
        if self.payload_digest != expected_digest:
            raise ValueError("application payload digest mismatch")
        object.__setattr__(self, "named_parameters", freeze_json(dict(self.named_parameters)))
        object.__setattr__(self, "application_payload", freeze_json(dict(self.application_payload)))

    def assert_executor_projection(
        self,
        *,
        action: str,
        target_id: str,
        destination_id: str,
        target_locator: Mapping[str, Any],
        destination_locator: Mapping[str, Any] | None,
        parameters: Mapping[str, Any],
    ) -> None:
        """Prove the fields consumed by the executor equal the sealed route projection."""

        if action != self.action or target_id != self.target_id or destination_id != self.destination_id:
            raise ValueError("executor action or endpoint differs from RouteBinding")
        if digest_payload(target_locator) != self.target_locator_ref:
            raise ValueError("executor target locator differs from RouteBinding")
        expected_destination_ref = digest_payload(destination_locator) if destination_locator is not None else ""
        if expected_destination_ref != self.destination_locator_ref:
            raise ValueError("executor destination locator differs from RouteBinding")
        if to_json_compatible(parameters) != to_json_compatible(self.named_parameters):
            raise ValueError("executor parameters differ from RouteBinding application payload")


def deterministic_application_payload(
    *,
    action: str,
    target_id: str,
    destination_id: str,
    named_parameters: Mapping[str, Any],
) -> Mapping[str, Any]:
    if not action.strip() or not target_id.strip():
        raise ValueError("route encoding requires action and actual target")
    ensure_secret_free(named_parameters)
    payload: dict[str, Any] = {
        "action": action,
        "target": target_id,
        "parameters": {name: named_parameters[name] for name in sorted(named_parameters)},
    }
    if destination_id:
        payload["destination"] = destination_id
    ensure_secret_free(payload)
    return freeze_json(payload)


def issue_surface_binding(
    requirement: ExecutionContextRequirementRef,
    *,
    run_id: str,
    session_generation: str,
    window_id: str,
    tab_id: str,
    frame_id: str,
    document_generation: str,
    focus_generation: str,
    ttl_s: float = 5.0,
    issued_at_s: float | None = None,
) -> LiveSurfaceBinding:
    surface_id = digest_payload((session_generation, window_id, tab_id, frame_id, document_generation))
    issued = time() if issued_at_s is None else issued_at_s
    lease = SurfaceLease(
        lease_id="surface-lease:" + digest_payload((run_id, surface_id, focus_generation, issued)).split(":", 1)[1],
        run_id=run_id,
        session_generation=session_generation,
        surface_id=surface_id,
        issued_at_s=issued,
        expires_at_s=issued + ttl_s,
        focus_generation=focus_generation,
    )
    return LiveSurfaceBinding(
        account_ref=requirement.account_ref,
        profile_ref=requirement.profile_ref,
        tenant_ref=requirement.tenant_ref,
        session_generation=session_generation,
        run_id=run_id,
        window_id=window_id,
        tab_id=tab_id,
        frame_id=frame_id,
        document_generation=document_generation,
        focus_generation=focus_generation,
        surface_id=surface_id,
        lease=lease,
    )


def describe_executor(executor: object) -> ExecutorCapabilityDescriptor:
    registered = getattr(executor, "executors", None)
    if isinstance(registered, dict) and registered:
        backends = tuple(sorted(set(str(key) for key in registered)))
        adapter_ids = tuple(sorted({type(item).__name__ for item in registered.values()}))
    else:
        declared_backends = getattr(executor, "supported_backends", ())
        backends = (
            tuple(str(item) for item in declared_backends)
            if isinstance(declared_backends, (list, tuple, set, frozenset)) and declared_backends
            else (str(getattr(executor, "backend", "unknown")),)
        )
        adapter_ids = (type(executor).__name__,)
    declared_actions = getattr(executor, "supported_actions", ())
    actions = tuple(str(item) for item in declared_actions) if isinstance(
        declared_actions, (list, tuple, set, frozenset)
    ) else ()
    provider_capabilities = tuple(str(item) for item in getattr(executor, "provider_capabilities", ()))
    adapter_capabilities = tuple(str(item) for item in getattr(executor, "adapter_capabilities", ()))
    routed = getattr(executor, "executors", None)
    backend_actions = {}
    backend_provider_capabilities = {}
    backend_adapter_capabilities = {}
    if isinstance(routed, Mapping):
        for backend, concrete in routed.items():
            backend_key = str(backend)
            backend_actions[backend_key] = tuple(str(item) for item in getattr(concrete, "supported_actions", ()))
            backend_provider_capabilities[backend_key] = tuple(
                str(item) for item in getattr(concrete, "provider_capabilities", ())
            )
            backend_adapter_capabilities[backend_key] = tuple(
                str(item) for item in getattr(concrete, "adapter_capabilities", ())
            )
    identity = {
        "backends": backends,
        "adapters": adapter_ids,
        "actions": actions,
        "provider_capabilities": provider_capabilities,
        "adapter_capabilities": adapter_capabilities,
        "backend_actions": backend_actions,
        "backend_provider_capabilities": backend_provider_capabilities,
        "backend_adapter_capabilities": backend_adapter_capabilities,
    }
    return ExecutorCapabilityDescriptor(
        provider_id=type(executor).__module__ + "." + type(executor).__name__,
        tool_schema_digest=digest_payload(identity),
        adapter_id="+".join(adapter_ids),
        adapter_version="runtime-adapter@v1",
        supported_backends=backends,
        provider_actions=actions,
        adapter_actions=actions,
        provider_capabilities=provider_capabilities,
        adapter_capabilities=adapter_capabilities,
        backend_actions=backend_actions,
        backend_provider_capabilities=backend_provider_capabilities,
        backend_adapter_capabilities=backend_adapter_capabilities,
    )


def _is_secret_name(value: object, *, include_bare_key: bool = False) -> bool:
    acronym_separated = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", str(value))
    camel_separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", acronym_separated)
    normalized = re.sub(r"[^a-z0-9]+", "_", camel_separated.casefold()).strip("_")
    return any(
        (include_bare_key or secret != "key")
        and (
            normalized == secret
        or normalized.startswith(secret + "_")
        or normalized.endswith("_" + secret)
        )
        for secret in _SIGNED_QUERY_NAMES
    )


def ensure_secret_free(value: object, *, _uri_depth: int = 0) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _is_secret_name(key):
                raise ValueError(f"secret-bearing field is prohibited: {key}")
            ensure_secret_free(item, _uri_depth=_uri_depth)
    elif isinstance(value, (list, tuple)):
        for item in value:
            ensure_secret_free(item, _uri_depth=_uri_depth)
    elif is_dataclass(value):
        for item in fields(cast(Any, value)):
            ensure_secret_free(getattr(value, item.name), _uri_depth=_uri_depth)
    elif isinstance(value, str):
        decoded = unquote(value)
        if decoded != value:
            if _uri_depth >= 4:
                raise ValueError("nested URI decoding depth is prohibited")
            ensure_secret_free(decoded, _uri_depth=_uri_depth + 1)
        lowered = value.casefold().strip()
        if lowered.startswith(("bearer ", "basic ")) or "cookie:" in lowered:
            raise ValueError("secret-bearing value is prohibited")
        parsed = urlsplit(value)
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("credential-bearing URI userinfo is prohibited")
        for component in (parsed.query, parsed.fragment):
            if component:
                for key, item in parse_qsl(component, keep_blank_values=True):
                    if _is_secret_name(key, include_bare_key=True):
                        raise ValueError(f"signed or credential-bearing URI is prohibited: {key}")
                    if _uri_depth >= 4 and any(marker in item for marker in ("://", "?", "#")):
                        raise ValueError("nested URI inspection depth is prohibited")
                    ensure_secret_free(item, _uri_depth=_uri_depth + 1)


def _require_identity(value: object, *, allow_blank: tuple[str, ...] = ()) -> None:
    for field_item in fields(cast(Any, value)):
        item = getattr(value, field_item.name)
        if isinstance(item, str) and field_item.name not in allow_blank and not item.strip():
            raise ValueError(f"{type(value).__name__}.{field_item.name} cannot be blank")
