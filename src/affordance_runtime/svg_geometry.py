"""Selective, revision-bound SVG geometry observation."""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Any, Protocol, Sequence

from affordance_runtime.grounding import (
    EvidenceKind,
    GroundingCandidate,
    GroundingSource,
    SourceObservation,
    SvgGroundingPayload,
    SvgTransform,
)


class SvgPagePort(Protocol):
    def evaluate(self, expression: str, arg: Any = None) -> Any: ...


@dataclass(frozen=True)
class SvgGeometryElement:
    element_id: str
    tag: str
    label: str
    role: str
    action: str
    backend_handle: str
    view_box: tuple[float, float, float, float]
    geometry_bbox_xywh: tuple[float, float, float, float]
    viewport_bbox_xywh: tuple[float, float, float, float]
    transform: SvgTransform
    evidence_ref: str
    observed_color: str = ""
    relative_size: str = ""
    item_type: str = ""
    item_text: str = ""

    def grounding_candidate(
        self,
        *,
        semantic_target_id: str,
        source_affordance_id: str = "",
        source: SourceObservation,
        expires_at_s: float,
        executor: str,
    ) -> GroundingCandidate:
        payload = SvgGroundingPayload(
            element_id=self.element_id,
            tag=self.tag,
            view_box=self.view_box,
            geometry_bbox_xywh=self.geometry_bbox_xywh,
            viewport_bbox_xywh=self.viewport_bbox_xywh,
            transform=self.transform,
            backend_handle=self.backend_handle,
        )
        fingerprint = "sha256:" + hashlib.sha256(
            json.dumps(
                {
                    "element": self.element_id,
                    "tag": self.tag,
                    "label": self.label,
                    "action": self.action,
                    "backend_handle": self.backend_handle,
                    "observed_color": self.observed_color,
                    "relative_size": self.relative_size,
                    "item_type": self.item_type,
                    "item_text": self.item_text,
                    "view_box": self.view_box,
                    "geometry": self.geometry_bbox_xywh,
                    "viewport": self.viewport_bbox_xywh,
                    "transform": self.transform.__dict__,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        return GroundingCandidate(
            candidate_id=f"svg:{self.element_id}",
            semantic_target_id=semantic_target_id,
            source=GroundingSource.SVG,
            payload=payload,
            compatible_executor=executor,
            observation_epoch_id=source.observation_epoch_id,
            environment_revision=source.environment_revision,
            page_revision=source.page_revision,
            target_fingerprint=fingerprint,
            fingerprint_key=f"svg:{self.element_id}",
            # A drop surface participates in the semantic DRAG operation even
            # though the source affordance keeps its directional ``drop``
            # action for the core endpoint-compatibility check.
            supported_actions=frozenset({"drag" if self.action == "drop" else self.action}),
            evidence_kinds=frozenset(
                {EvidenceKind.STRUCTURAL, EvidenceKind.SPATIAL, EvidenceKind.VISUAL_APPEARANCE}
            ),
            source_affordance_id=source_affordance_id,
            confidence=source.confidence,
            expires_at_s=expires_at_s,
            evidence_refs=(self.evidence_ref,),
        )


@dataclass(frozen=True)
class SvgGeometryObservation:
    source_observation: SourceObservation
    viewport_size: tuple[float, float]
    elements: tuple[SvgGeometryElement, ...]


class SvgGeometryObserverPort(Protocol):
    def observe(
        self,
        page: SvgPagePort,
        *,
        observation_epoch_id: str,
        environment_revision: str,
        page_revision: str,
        task_terms: Sequence[str] = (),
        evidence_ref: str = "",
    ) -> SvgGeometryObservation: ...


@dataclass(frozen=True)
class SvgAuthoredExtension:
    """Optional authored SVG annotations normalized at an adapter boundary."""

    marker_attribute: str = ""
    marker_value: str = "1"
    backend_handle_attribute: str = ""


_SVG_OBSERVATION_SCRIPT = r"""
(request) => {
  const taskTerms = request.task_terms || [];
  const markerAttribute = String(request.marker_attribute || '');
  const markerValue = String(request.marker_value || '1');
  const handleAttribute = String(request.backend_handle_attribute || '');
  const normalizedTerms = (taskTerms || []).map(term => String(term).toLowerCase()).filter(Boolean);
  const dragRequested = normalizedTerms.some(term => ['drag', 'move'].includes(term));
  const itemRequested = normalizedTerms.some(term => ['shape', 'shapes', 'item', 'number', 'numbers', 'digit', 'digits', 'letter', 'letters'].includes(term));
  const actionFor = element => {
    const role = (element.getAttribute('role') || '').toLowerCase();
    if (role === 'slider') return 'point_activate';
    if (element.getAttribute('draggable') === 'true') return 'drag';
    const tag = element.tagName.toLowerCase();
    const fill = String(element.getAttribute('fill') || '').toLowerCase();
    if (dragRequested && ['circle', 'ellipse', 'rect', 'polygon'].includes(tag)) {
      if (fill === 'none' || element.id === 'shape-container') return 'drop';
      return 'drag';
    }
    return 'point_activate';
  };
  const elements = [];
  const seenElementIds = new Map();
  for (const svg of document.querySelectorAll('svg')) {
    const viewBox = svg.viewBox && svg.viewBox.baseVal;
    const svgRect = svg.getBoundingClientRect();
    const resolvedViewBox = viewBox && viewBox.width > 0 && viewBox.height > 0
      ? [viewBox.x, viewBox.y, viewBox.width, viewBox.height]
      : [0, 0, svgRect.width, svgRect.height];
    const nodes = svg.querySelectorAll('*');
    let ordinal = 0;
    for (const element of nodes) {
      const tag = element.tagName.toLowerCase();
      if (['defs', 'clippath', 'mask', 'lineargradient', 'radialgradient', 'style', 'title'].includes(tag)) continue;
      if (typeof element.getBBox !== 'function' || typeof element.getScreenCTM !== 'function') continue;
      const box = element.getBBox();
      const rect = element.getBoundingClientRect();
      const matrix = element.getScreenCTM();
      if (!matrix || box.width <= 0 || box.height <= 0 || rect.width <= 0 || rect.height <= 0) continue;
      const classLabel = typeof element.className?.baseVal === 'string' ? element.className.baseVal.replace(/[-_]+/g, ' ') : '';
      const fill = String(element.getAttribute('fill') || '').trim();
      const shapeName = ({rect: 'rectangle', polygon: 'triangle'})[tag] || tag;
      const itemText = String(element.textContent || element.getAttribute('data-index') || '').trim();
      const itemType = tag === 'text' || element.hasAttribute('data-index')
        ? (/^\d$/.test(itemText) ? 'digit' : 'letter')
        : (['circle', 'ellipse', 'rect', 'polygon'].includes(tag) ? 'shape' : '');
      const sizeMetric = tag === 'text'
        ? Number.parseFloat(element.getAttribute('font-size') || String(box.height))
        : Math.max(box.width, box.height);
      const relativeSize = Number.isFinite(sizeMetric) && sizeMetric >= 15 ? 'large' : 'small';
      const inferredDropLabel = box.x + box.width / 2 < resolvedViewBox[0] + resolvedViewBox[2] / 2
        ? 'left box'
        : 'right box';
      const action = actionFor(element);
      const inferredItemLabel = [relativeSize, fill, itemText || shapeName, itemType].filter(Boolean).join(' ');
      const inferredLabel = action === 'drop' ? inferredDropLabel : inferredItemLabel;
      const authoredLabel = element.getAttribute('aria-label') || element.querySelector(':scope > title')?.textContent || element.textContent;
      const label = (authoredLabel || (action === 'drop' ? inferredLabel : element.id || classLabel || inferredLabel) || '').trim();
      const role = (element.getAttribute('role') || (action === 'drop' ? 'drop_target' : action === 'drag' ? 'draggable' : '')).toLowerCase();
      const backendHandle = handleAttribute ? (element.getAttribute(handleAttribute) || '') : '';
      const marked = markerAttribute ? element.getAttribute(markerAttribute) === markerValue : false;
      const boundedShape = ['circle', 'ellipse', 'rect', 'polygon', 'text'].includes(tag) && Boolean(element.id || classLabel || dragRequested || itemRequested);
      const actionable = marked || Boolean(backendHandle) || boundedShape || ['button', 'link', 'slider'].includes(role) || tag === 'a' || element.getAttribute('draggable') === 'true';
      const taskRelevant = normalizedTerms.some(term => label.toLowerCase().includes(term));
      if (!actionable && !label && !taskRelevant) continue;
      if (!actionable && !taskRelevant) continue;
      ordinal += 1;
      const authoredSequenceIndex = String(element.getAttribute('data-index') || '').trim();
      const baseElementId = element.id || backendHandle || (authoredSequenceIndex ? `${tag}-data-index-${authoredSequenceIndex}` : `${tag}-${ordinal}`);
      const duplicateOrdinal = (seenElementIds.get(baseElementId) || 0) + 1;
      seenElementIds.set(baseElementId, duplicateOrdinal);
      elements.push({
        element_id: duplicateOrdinal === 1 ? baseElementId : `${baseElementId}-${duplicateOrdinal}`,
        tag,
        label,
        role,
        action,
        backend_handle: backendHandle,
        observed_color: fill,
        relative_size: relativeSize,
        item_type: itemType,
        item_text: itemText || shapeName,
        view_box: resolvedViewBox,
        geometry_bbox: [box.x, box.y, box.width, box.height],
        viewport_bbox: [rect.x, rect.y, rect.width, rect.height],
        transform: [matrix.a, matrix.b, matrix.c, matrix.d, matrix.e, matrix.f],
      });
    }
  }
  return {viewport: [window.innerWidth, window.innerHeight], elements};
}
"""


@dataclass(frozen=True)
class SelectiveSvgGeometryObserver:
    parser_id: str = "selective-svg-geometry-v1"
    max_elements: int = 64
    authored_extension: SvgAuthoredExtension | None = None

    def observe(
        self,
        page: SvgPagePort,
        *,
        observation_epoch_id: str,
        environment_revision: str,
        page_revision: str,
        task_terms: Sequence[str] = (),
        evidence_ref: str = "",
    ) -> SvgGeometryObservation:
        extension = self.authored_extension or SvgAuthoredExtension()
        raw = page.evaluate(
            _SVG_OBSERVATION_SCRIPT,
            {
                "task_terms": list(task_terms),
                "marker_attribute": extension.marker_attribute,
                "marker_value": extension.marker_value,
                "backend_handle_attribute": extension.backend_handle_attribute,
            },
        )
        if not isinstance(raw, dict):
            raise ValueError("SVG observer must return an object")
        viewport = _finite_tuple(raw.get("viewport"), 2, "SVG viewport")
        if viewport[0] <= 0 or viewport[1] <= 0:
            raise ValueError("SVG viewport dimensions must be positive")
        raw_elements = raw.get("elements")
        if not isinstance(raw_elements, list):
            raise ValueError("SVG observer elements must be a list")
        elements = tuple(self._element(item, evidence_ref) for item in raw_elements[: self.max_elements])
        source = SourceObservation(
            source=GroundingSource.SVG,
            parser_id=self.parser_id,
            observation_epoch_id=observation_epoch_id,
            environment_revision=environment_revision,
            page_revision=page_revision,
            artifact_refs=(evidence_ref,) if evidence_ref else (),
        )
        return SvgGeometryObservation(source, viewport, elements)

    def _element(self, raw: Any, evidence_ref: str) -> SvgGeometryElement:
        if not isinstance(raw, dict):
            raise ValueError("SVG geometry element must be an object")
        element_id = str(raw.get("element_id") or "")
        if not element_id:
            raise ValueError("SVG geometry element requires an id")
        view_box = _finite_tuple(raw.get("view_box"), 4, "SVG viewBox")
        geometry = _positive_box(raw.get("geometry_bbox"), "SVG geometry bbox")
        viewport = _positive_box(raw.get("viewport_bbox"), "SVG viewport bbox")
        matrix = _finite_tuple(raw.get("transform"), 6, "SVG transform")
        return SvgGeometryElement(
            element_id=element_id,
            tag=str(raw.get("tag") or ""),
            label=str(raw.get("label") or ""),
            role=str(raw.get("role") or ""),
            action=str(raw.get("action") or "point_activate"),
            backend_handle=str(raw.get("backend_handle") or ""),
            view_box=view_box,
            geometry_bbox_xywh=geometry,
            viewport_bbox_xywh=viewport,
            transform=SvgTransform(*matrix),
            evidence_ref=evidence_ref,
            observed_color=str(raw.get("observed_color") or ""),
            relative_size=str(raw.get("relative_size") or ""),
            item_type=str(raw.get("item_type") or ""),
            item_text=str(raw.get("item_text") or ""),
        )


def _finite_tuple(value: Any, length: int, label: str) -> tuple[Any, ...]:
    if not isinstance(value, (list, tuple)) or len(value) != length:
        raise ValueError(f"{label} must contain {length} numbers")
    converted = tuple(float(item) for item in value)
    if not all(math.isfinite(item) for item in converted):
        raise ValueError(f"{label} must contain finite numbers")
    return converted


def _positive_box(value: Any, label: str) -> tuple[float, float, float, float]:
    box = _finite_tuple(value, 4, label)
    if box[2] <= 0 or box[3] <= 0:
        raise ValueError(f"{label} dimensions must be positive")
    return box
