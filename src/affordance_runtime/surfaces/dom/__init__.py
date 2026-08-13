"""DOM implementation of the unified SurfaceAdapter contract."""

from affordance_runtime.surfaces.dom.adapter import DomSurfaceAdapter
from affordance_runtime.surfaces.dom.document import (
    StructuredDocumentProjection,
    project_structured_document,
)

__all__ = ["DomSurfaceAdapter", "StructuredDocumentProjection", "project_structured_document"]
