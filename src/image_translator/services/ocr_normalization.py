from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

from image_translator.domain.errors import InvalidRegionError
from image_translator.domain.geometry import Point, Polygon, RegionGeometry, RotatedBoundingBox
from image_translator.domain.ids import RegionId
from image_translator.domain.image import ImageDimensions
from image_translator.domain.ocr import (
    NormalizedTextRegion,
    RawOCRRegion,
    ReadingOrder,
    TextOrientation,
    TextRole,
    WritingMode,
)


def normalize_ocr_regions(
    raw_regions: Sequence[RawOCRRegion],
    *,
    image_dimensions: ImageDimensions,
    source_language: str,
    reading_orders: Mapping[RegionId, ReadingOrder],
    text_roles: Mapping[RegionId, TextRole] | None = None,
    ruby_target_region_ids: Mapping[RegionId, RegionId | None] | None = None,
) -> tuple[NormalizedTextRegion, ...]:
    seen_region_ids: set[RegionId] = set()
    normalized_regions: list[NormalizedTextRegion] = []

    for raw_region in raw_regions:
        if raw_region.region_id in seen_region_ids:
            raise InvalidRegionError(f"duplicate region ID: {raw_region.region_id}")
        seen_region_ids.add(raw_region.region_id)

        geometry = raw_region.geometry
        if geometry is None:
            raise InvalidRegionError(f"missing geometry for region ID: {raw_region.region_id}")
        if not _intersects_image_bounds(geometry, image_dimensions):
            raise InvalidRegionError(
                f"region {raw_region.region_id} geometry does not intersect image bounds"
            )

        reading_order = reading_orders.get(raw_region.region_id)
        if reading_order is None:
            raise InvalidRegionError(
                f"missing reading order for region ID: {raw_region.region_id}"
            )

        normalized_regions.append(
            NormalizedTextRegion(
                region_id=raw_region.region_id,
                source_text=raw_region.raw_text,
                geometry=geometry,
                source_language=source_language,
                writing_mode=raw_region.writing_mode,
                orientation=_infer_orientation(raw_region.writing_mode, geometry),
                reading_order=reading_order,
                text_role=(text_roles or {}).get(raw_region.region_id, TextRole.unknown),
                ruby_target_region_id=(ruby_target_region_ids or {}).get(
                    raw_region.region_id
                ),
                ocr_provenance=(),
            )
        )

    return tuple(normalized_regions)


def _intersects_image_bounds(
    geometry: RegionGeometry,
    image_dimensions: ImageDimensions,
) -> bool:
    min_x, min_y, max_x, max_y = _geometry_bounds(geometry)
    return (
        max_x > 0.0
        and max_y > 0.0
        and min_x < float(image_dimensions.width)
        and min_y < float(image_dimensions.height)
    )


def _geometry_bounds(geometry: RegionGeometry) -> tuple[float, float, float, float]:
    if isinstance(geometry, Polygon):
        points = geometry.points
    else:
        points = _rotated_bbox_corners(geometry)

    xs = tuple(point.x for point in points)
    ys = tuple(point.y for point in points)
    return min(xs), min(ys), max(xs), max(ys)


def _rotated_bbox_corners(bbox: RotatedBoundingBox) -> tuple[Point, Point, Point, Point]:
    half_width = bbox.width / 2.0
    half_height = bbox.height / 2.0
    angle = math.radians(bbox.rotation)
    cos_angle = math.cos(angle)
    sin_angle = math.sin(angle)
    offsets = (
        (-half_width, -half_height),
        (half_width, -half_height),
        (half_width, half_height),
        (-half_width, half_height),
    )

    corners = tuple(
        Point(
            x=bbox.center.x + (dx * cos_angle) - (dy * sin_angle),
            y=bbox.center.y + (dx * sin_angle) + (dy * cos_angle),
        )
        for dx, dy in offsets
    )
    return (corners[0], corners[1], corners[2], corners[3])


def _infer_orientation(
    writing_mode: WritingMode,
    geometry: RegionGeometry,
) -> TextOrientation:
    if isinstance(geometry, RotatedBoundingBox):
        normalized_rotation = _normalize_rotation(geometry.rotation)
        if math.isclose(normalized_rotation, 90.0, abs_tol=1e-6):
            return TextOrientation.rotated_90_cw
        if math.isclose(normalized_rotation, -90.0, abs_tol=1e-6):
            return TextOrientation.rotated_90_ccw
        if not math.isclose(normalized_rotation, 0.0, abs_tol=1e-6):
            return TextOrientation.arbitrary_angle

    if writing_mode is WritingMode.rotated:
        return TextOrientation.arbitrary_angle
    return TextOrientation.upright


def _normalize_rotation(rotation: float) -> float:
    return ((rotation + 180.0) % 360.0) - 180.0


__all__ = ["normalize_ocr_regions"]
