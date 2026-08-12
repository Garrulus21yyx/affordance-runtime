"""Pure observation-derived semantics for bounded regular Cartesian lattices."""

from __future__ import annotations

import hashlib
import math
import statistics
from dataclasses import dataclass
from enum import StrEnum


class LatticeDerivationCode(StrEnum):
    DERIVED = "derived"
    NO_REGULAR_LATTICE = "no_regular_lattice"
    AXIS_LABELS_UNAVAILABLE = "axis_labels_unavailable"
    AXIS_MAPPING_AMBIGUOUS = "axis_mapping_ambiguous"
    MULTIPLE_LATTICES = "multiple_lattices"


@dataclass(frozen=True)
class SpatialNode:
    node_id: str
    group_id: str
    bbox: tuple[int, int, int, int]

    @property
    def center(self) -> tuple[float, float]:
        x, y, width, height = self.bbox
        return x + width / 2, y + height / 2


@dataclass(frozen=True)
class VisibleNumericLabel:
    label_id: str
    group_id: str
    value: int | float
    bbox: tuple[float, float, float, float]

    @property
    def center(self) -> tuple[float, float]:
        x, y, width, height = self.bbox
        return x + width / 2, y + height / 2


@dataclass(frozen=True)
class GridMembership:
    node_id: str
    grid_id: str
    row_index: int
    column_index: int
    x: int | float
    y: int | float
    confidence: float


@dataclass(frozen=True)
class RegularLatticeDerivation:
    code: LatticeDerivationCode
    memberships: tuple[GridMembership, ...] = ()
    evidence_label_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Lattice:
    nodes: tuple[SpatialNode, ...]
    rows: tuple[float, ...]
    columns: tuple[float, ...]
    cells: tuple[tuple[str, int, int], ...]


def derive_regular_lattice(
    nodes: tuple[SpatialNode, ...],
    labels: tuple[VisibleNumericLabel, ...],
) -> RegularLatticeDerivation:
    """Derive one fully evidenced regular lattice or return a typed non-result."""

    candidates = tuple(
        lattice
        for _group_id, group in _grouped_nodes(nodes)
        for lattice in (_regular_lattice(group),)
        if lattice is not None
    )
    if not candidates:
        return RegularLatticeDerivation(LatticeDerivationCode.NO_REGULAR_LATTICE)
    if len(candidates) > 1:
        return RegularLatticeDerivation(LatticeDerivationCode.MULTIPLE_LATTICES)

    derived: list[RegularLatticeDerivation] = []
    saw_axis_labels = False
    saw_ambiguous_mapping = False
    label_groups = _grouped_labels(labels)
    for lattice in candidates:
        x_fits = []
        y_fits = []
        for _group_id, group in label_groups:
            orientation = _label_orientation(group)
            if orientation == "x":
                saw_axis_labels = True
                fit = _axis_fit(
                    group, lattice.columns, cross_positions=lattice.rows, axis="x",
                )
                if fit is not None:
                    x_fits.append((fit, group))
            elif orientation == "y":
                saw_axis_labels = True
                fit = _axis_fit(
                    group, lattice.rows, cross_positions=lattice.columns, axis="y",
                )
                if fit is not None:
                    y_fits.append((fit, group))
        if len(x_fits) != 1 or len(y_fits) != 1:
            saw_ambiguous_mapping = saw_ambiguous_mapping or bool(x_fits or y_fits)
            continue
        (x_slope, x_intercept), x_labels = x_fits[0]
        (y_slope, y_intercept), y_labels = y_fits[0]
        grid_id = _grid_id(lattice)
        memberships = tuple(
            GridMembership(
                node_id,
                grid_id,
                row,
                column,
                _normalized_number(x_slope * column + x_intercept),
                _normalized_number(y_slope * row + y_intercept),
                1.0,
            )
            for node_id, row, column in lattice.cells
        )
        derived.append(RegularLatticeDerivation(
            LatticeDerivationCode.DERIVED,
            memberships,
            tuple(item.label_id for item in (*x_labels, *y_labels)),
        ))
    if len(derived) == 1:
        return derived[0]
    if len(derived) > 1:
        return RegularLatticeDerivation(LatticeDerivationCode.MULTIPLE_LATTICES)
    if saw_ambiguous_mapping:
        return RegularLatticeDerivation(LatticeDerivationCode.AXIS_MAPPING_AMBIGUOUS)
    if saw_axis_labels:
        return RegularLatticeDerivation(LatticeDerivationCode.AXIS_MAPPING_AMBIGUOUS)
    return RegularLatticeDerivation(LatticeDerivationCode.AXIS_LABELS_UNAVAILABLE)


def _grouped_nodes(nodes: tuple[SpatialNode, ...]):
    grouped: dict[str, list[SpatialNode]] = {}
    for node in nodes:
        if node.node_id and node.group_id:
            grouped.setdefault(node.group_id, []).append(node)
    return tuple((key, tuple(values)) for key, values in sorted(grouped.items()))


def _grouped_labels(labels: tuple[VisibleNumericLabel, ...]):
    grouped: dict[str, list[VisibleNumericLabel]] = {}
    for label in labels:
        if label.label_id and label.group_id:
            grouped.setdefault(label.group_id, []).append(label)
    return tuple((key, tuple(values)) for key, values in sorted(grouped.items()))


def _regular_lattice(nodes: tuple[SpatialNode, ...]) -> _Lattice | None:
    if not 4 <= len(nodes) <= 64:
        return None
    tolerance = max(2.0, statistics.median(
        min(node.bbox[2], node.bbox[3]) for node in nodes
    ) * 0.5)
    columns = _clusters(tuple(node.center[0] for node in nodes), tolerance)
    rows = _clusters(tuple(node.center[1] for node in nodes), tolerance)
    if len(columns) < 2 or len(rows) < 2 or len(columns) * len(rows) != len(nodes):
        return None
    if not _regular_spacing(columns) or not _regular_spacing(rows):
        return None
    occupied: dict[tuple[int, int], str] = {}
    for node in nodes:
        column, x_error = _nearest(node.center[0], columns)
        row, y_error = _nearest(node.center[1], rows)
        if x_error > tolerance or y_error > tolerance or (row, column) in occupied:
            return None
        occupied[row, column] = node.node_id
    if len(occupied) != len(rows) * len(columns):
        return None
    cells = tuple(
        (node_id, row, column)
        for (row, column), node_id in sorted(occupied.items())
    )
    return _Lattice(tuple(nodes), rows, columns, cells)


def _clusters(values: tuple[float, ...], tolerance: float) -> tuple[float, ...]:
    groups: list[list[float]] = []
    for value in sorted(values):
        if not groups or abs(value - statistics.mean(groups[-1])) > tolerance:
            groups.append([value])
        else:
            groups[-1].append(value)
    return tuple(statistics.mean(group) for group in groups)


def _regular_spacing(values: tuple[float, ...]) -> bool:
    differences = tuple(right - left for left, right in zip(values, values[1:], strict=False))
    if not differences or min(differences) <= 0:
        return False
    median = statistics.median(differences)
    return max(abs(value - median) for value in differences) <= max(2.0, median * 0.12)


def _label_orientation(labels: tuple[VisibleNumericLabel, ...]) -> str:
    if len(labels) < 2:
        return ""
    xs = tuple(item.center[0] for item in labels)
    ys = tuple(item.center[1] for item in labels)
    x_span, y_span = max(xs) - min(xs), max(ys) - min(ys)
    if x_span >= max(8.0, y_span * 3):
        return "x"
    if y_span >= max(8.0, x_span * 3):
        return "y"
    return ""


def _axis_fit(
    labels: tuple[VisibleNumericLabel, ...],
    positions: tuple[float, ...],
    *,
    cross_positions: tuple[float, ...],
    axis: str,
) -> tuple[float, float] | None:
    spacing = statistics.median(
        right - left for left, right in zip(positions, positions[1:], strict=False)
    )
    cross_spacing = statistics.median(
        right - left for left, right in zip(cross_positions, cross_positions[1:], strict=False)
    )
    cross_center = statistics.median(
        item.center[1] if axis == "x" else item.center[0] for item in labels
    )
    if not (
        min(cross_positions) - cross_spacing
        <= cross_center
        <= max(cross_positions) + cross_spacing
    ):
        return None
    indexed: list[tuple[int, float]] = []
    used: set[int] = set()
    for label in labels:
        coordinate = label.center[0] if axis == "x" else label.center[1]
        index, error = _nearest(coordinate, positions)
        if error > max(3.0, spacing * 0.35) or index in used:
            return None
        used.add(index)
        indexed.append((index, float(label.value)))
    if len(indexed) < 2 or len({value for _index, value in indexed}) < 2:
        return None
    mean_index = statistics.mean(index for index, _value in indexed)
    mean_value = statistics.mean(value for _index, value in indexed)
    denominator = sum((index - mean_index) ** 2 for index, _value in indexed)
    if denominator == 0:
        return None
    slope = sum(
        (index - mean_index) * (value - mean_value) for index, value in indexed
    ) / denominator
    intercept = mean_value - slope * mean_index
    residual = max(abs(value - (slope * index + intercept)) for index, value in indexed)
    if abs(slope) < 1e-9 or residual > max(0.05, abs(slope) * 0.1):
        return None
    return slope, intercept


def _nearest(value: float, positions: tuple[float, ...]) -> tuple[int, float]:
    return min(
        ((index, abs(value - position)) for index, position in enumerate(positions)),
        key=lambda item: (item[1], item[0]),
    )


def _grid_id(lattice: _Lattice) -> str:
    payload = ";".join(
        f"{center:.3f}" for center in (*lattice.columns, *lattice.rows)
    )
    return f"grid:{hashlib.sha256(payload.encode()).hexdigest()[:16]}"


def _normalized_number(value: float) -> int | float:
    nearest = round(value)
    if math.isclose(value, nearest, abs_tol=1e-9):
        return int(nearest)
    return round(value, 6)
