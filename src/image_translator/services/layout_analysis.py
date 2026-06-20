from __future__ import annotations

from collections.abc import Sequence

from image_translator.domain._base import DomainModel, UnitInterval
from image_translator.domain.errors import ReadingOrderUncertainError
from image_translator.domain.geometry import Point, Polygon, RegionGeometry, RotatedBoundingBox
from image_translator.domain.ocr import NormalizedTextRegion, ReadingOrder, WritingMode


class ReadingOrderPolicy(DomainModel):
    min_confidence: UnitInterval = 0.8
    alternative_conflict_margin: UnitInterval = 0.15
    inferred_confidence: UnitInterval = 0.9


class ReadingOrderLayoutResult(DomainModel):
    regions: tuple[NormalizedTextRegion, ...]
    requires_review: bool = False
    review_reasons: tuple[str, ...] = ()


class _Bounds(DomainModel):
    left: float
    top: float
    right: float
    bottom: float

    @property
    def center_x(self) -> float:
        return (self.left + self.right) / 2.0

    @property
    def center_y(self) -> float:
        return (self.top + self.bottom) / 2.0


def analyze_reading_order(
    regions: Sequence[NormalizedTextRegion],
    *,
    policy: ReadingOrderPolicy | None = None,
    raise_on_uncertain: bool = True,
) -> ReadingOrderLayoutResult:
    active_policy = policy or ReadingOrderPolicy()
    review_reasons = _review_reasons(regions, active_policy)
    if review_reasons:
        if raise_on_uncertain:
            raise ReadingOrderUncertainError(
                f"ambiguous reading order: {'; '.join(review_reasons)}"
            )
        return ReadingOrderLayoutResult(
            regions=tuple(regions),
            requires_review=True,
            review_reasons=review_reasons,
        )

    ordered_regions = _ordered_regions(regions)
    return ReadingOrderLayoutResult(
        regions=_with_sequential_item_indices(
            ordered_regions,
            inferred_confidence=active_policy.inferred_confidence,
        )
    )


def _review_reasons(
    regions: Sequence[NormalizedTextRegion],
    policy: ReadingOrderPolicy,
) -> tuple[str, ...]:
    reasons: list[str] = []
    for region in regions:
        reading_order = region.reading_order
        if region.writing_mode is WritingMode.unknown:
            reasons.append(f"{region.region_id}: unknown writing mode")
        if reading_order.confidence < policy.min_confidence:
            reasons.append(f"{region.region_id}: low reading order confidence")
        if _has_conflicting_alternative(reading_order, policy):
            reasons.append(f"{region.region_id}: conflicting reading order candidate")
    return tuple(reasons)


def _has_conflicting_alternative(
    reading_order: ReadingOrder,
    policy: ReadingOrderPolicy,
) -> bool:
    return any(
        abs(reading_order.confidence - candidate.confidence)
        <= policy.alternative_conflict_margin
        for candidate in reading_order.alternatives
    )


def _ordered_regions(
    regions: Sequence[NormalizedTextRegion],
) -> tuple[NormalizedTextRegion, ...]:
    return tuple(
        sorted(
            regions,
            key=lambda region: (
                region.reading_order.page_index,
                region.reading_order.group_index,
                _mode_sort_key(region),
                region.region_id,
            ),
        )
    )


def _mode_sort_key(region: NormalizedTextRegion) -> tuple[float, float, float, float]:
    bounds = _geometry_bounds(region.geometry)

    match region.writing_mode:
        case WritingMode.vertical_rl:
            return (-bounds.center_x, bounds.top, bounds.left, bounds.center_y)
        case WritingMode.vertical_lr:
            return (bounds.center_x, bounds.top, bounds.left, bounds.center_y)
        case WritingMode.horizontal_rtl:
            return (bounds.top, -bounds.center_x, bounds.center_y, bounds.left)
        case WritingMode.horizontal_ltr:
            return (bounds.top, bounds.left, bounds.center_y, bounds.center_x)
        case WritingMode.rotated:
            return (bounds.top, bounds.left, bounds.center_y, bounds.center_x)
        case WritingMode.unknown:
            return (bounds.top, bounds.left, bounds.center_y, bounds.center_x)


def _with_sequential_item_indices(
    regions: Sequence[NormalizedTextRegion],
    *,
    inferred_confidence: float,
) -> tuple[NormalizedTextRegion, ...]:
    next_item_by_group: dict[tuple[int, int], int] = {}
    updated_regions: list[NormalizedTextRegion] = []

    for region in regions:
        group_key = (
            region.reading_order.page_index,
            region.reading_order.group_index,
        )
        item_index = next_item_by_group.get(group_key, 0)
        next_item_by_group[group_key] = item_index + 1
        updated_regions.append(
            region.model_copy(
                update={
                    "reading_order": region.reading_order.model_copy(
                        update={
                            "item_index": item_index,
                            "confidence": min(
                                region.reading_order.confidence,
                                inferred_confidence,
                            ),
                            "alternatives": (),
                        }
                    )
                }
            )
        )

    return tuple(updated_regions)


def _geometry_bounds(geometry: RegionGeometry) -> _Bounds:
    points = geometry.points if isinstance(geometry, Polygon) else _bbox_corners(geometry)
    xs = tuple(point.x for point in points)
    ys = tuple(point.y for point in points)
    return _Bounds(left=min(xs), top=min(ys), right=max(xs), bottom=max(ys))


def _bbox_corners(bbox: RotatedBoundingBox) -> tuple[Point, Point, Point, Point]:
    half_width = bbox.width / 2.0
    half_height = bbox.height / 2.0
    return (
        Point(x=bbox.center.x - half_width, y=bbox.center.y - half_height),
        Point(x=bbox.center.x + half_width, y=bbox.center.y - half_height),
        Point(x=bbox.center.x + half_width, y=bbox.center.y + half_height),
        Point(x=bbox.center.x - half_width, y=bbox.center.y + half_height),
    )


__all__ = [
    "ReadingOrderLayoutResult",
    "ReadingOrderPolicy",
    "analyze_reading_order",
]
