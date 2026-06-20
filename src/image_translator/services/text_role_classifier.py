from __future__ import annotations

from collections.abc import Sequence

from image_translator.domain._base import DomainModel, PositiveFiniteFloat
from image_translator.domain.geometry import Point, Polygon, RegionGeometry, RotatedBoundingBox
from image_translator.domain.ids import RegionId
from image_translator.domain.ocr import NormalizedTextRegion, TextOrientation, TextRole, WritingMode


class TextRolePolicy(DomainModel):
    max_ruby_area_ratio: PositiveFiniteFloat = 0.4
    max_ruby_gap: PositiveFiniteFloat = 12.0
    min_ruby_axis_overlap_ratio: PositiveFiniteFloat = 0.5


class TextRoleClassificationResult(DomainModel):
    regions: tuple[NormalizedTextRegion, ...]
    requires_review: bool = False
    review_reasons: tuple[str, ...] = ()


class _Bounds(DomainModel):
    left: float
    top: float
    right: float
    bottom: float

    @property
    def width(self) -> float:
        return self.right - self.left

    @property
    def height(self) -> float:
        return self.bottom - self.top

    @property
    def area(self) -> float:
        return self.width * self.height


def classify_text_roles(
    regions: Sequence[NormalizedTextRegion],
    *,
    policy: TextRolePolicy | None = None,
) -> TextRoleClassificationResult:
    active_policy = policy or TextRolePolicy()
    review_reasons: list[str] = []
    classified_regions: list[NormalizedTextRegion] = []

    for region in regions:
        classified_region, review_reason = _classify_region(
            region,
            all_regions=regions,
            policy=active_policy,
        )
        classified_regions.append(classified_region)
        if review_reason is not None:
            review_reasons.append(review_reason)

    return TextRoleClassificationResult(
        regions=tuple(classified_regions),
        requires_review=bool(review_reasons),
        review_reasons=tuple(review_reasons),
    )


def _classify_region(
    region: NormalizedTextRegion,
    *,
    all_regions: Sequence[NormalizedTextRegion],
    policy: TextRolePolicy,
) -> tuple[NormalizedTextRegion, str | None]:
    if region.text_role is TextRole.ruby:
        return _resolve_existing_ruby(region, all_regions=all_regions, policy=policy)
    if region.text_role is not TextRole.unknown:
        return region, None
    if _is_rotated_sound_effect(region):
        return region.model_copy(update={"text_role": TextRole.sound_effect}), None

    ruby_targets = _ruby_target_candidates(region, all_regions=all_regions, policy=policy)
    if len(ruby_targets) == 1:
        return (
            region.model_copy(
                update={
                    "text_role": TextRole.ruby,
                    "ruby_target_region_id": ruby_targets[0],
                }
            ),
            None,
        )
    if len(ruby_targets) > 1:
        return region, f"{region.region_id}: uncertain ruby target"

    return region, None


def _resolve_existing_ruby(
    region: NormalizedTextRegion,
    *,
    all_regions: Sequence[NormalizedTextRegion],
    policy: TextRolePolicy,
) -> tuple[NormalizedTextRegion, str | None]:
    if region.ruby_target_region_id is not None:
        target_ids = {candidate.region_id for candidate in all_regions}
        if region.ruby_target_region_id in target_ids:
            return region, None

    ruby_targets = _ruby_target_candidates(region, all_regions=all_regions, policy=policy)
    if len(ruby_targets) == 1:
        return region.model_copy(update={"ruby_target_region_id": ruby_targets[0]}), None
    return (
        region.model_copy(update={"ruby_target_region_id": None}),
        f"{region.region_id}: uncertain ruby target",
    )


def _is_rotated_sound_effect(region: NormalizedTextRegion) -> bool:
    return (
        region.writing_mode is WritingMode.rotated
        or region.orientation is TextOrientation.arbitrary_angle
    )


def _ruby_target_candidates(
    region: NormalizedTextRegion,
    *,
    all_regions: Sequence[NormalizedTextRegion],
    policy: TextRolePolicy,
) -> tuple[RegionId, ...]:
    region_bounds = _geometry_bounds(region.geometry)
    candidates: list[RegionId] = []

    for target in all_regions:
        if target.region_id == region.region_id or target.text_role is TextRole.ruby:
            continue
        if target.text_role is TextRole.decorative:
            continue
        target_bounds = _geometry_bounds(target.geometry)
        if not _is_small_enough_for_ruby(region_bounds, target_bounds, policy):
            continue
        if _is_ruby_adjacent(region, region_bounds, target, target_bounds, policy):
            candidates.append(target.region_id)

    return tuple(sorted(candidates))


def _is_small_enough_for_ruby(
    ruby_bounds: _Bounds,
    target_bounds: _Bounds,
    policy: TextRolePolicy,
) -> bool:
    return ruby_bounds.area <= target_bounds.area * policy.max_ruby_area_ratio


def _is_ruby_adjacent(
    region: NormalizedTextRegion,
    region_bounds: _Bounds,
    target: NormalizedTextRegion,
    target_bounds: _Bounds,
    policy: TextRolePolicy,
) -> bool:
    if region.writing_mode != target.writing_mode:
        return False
    if region.writing_mode in (WritingMode.vertical_rl, WritingMode.vertical_lr):
        overlap = _overlap_length(
            region_bounds.top,
            region_bounds.bottom,
            target_bounds.top,
            target_bounds.bottom,
        )
        required_overlap = region_bounds.height * policy.min_ruby_axis_overlap_ratio
        return (
            overlap >= required_overlap
            and _horizontal_gap(region_bounds, target_bounds) <= policy.max_ruby_gap
        )
    if region.writing_mode in (WritingMode.horizontal_ltr, WritingMode.horizontal_rtl):
        overlap = _overlap_length(
            region_bounds.left,
            region_bounds.right,
            target_bounds.left,
            target_bounds.right,
        )
        required_overlap = region_bounds.width * policy.min_ruby_axis_overlap_ratio
        return (
            overlap >= required_overlap
            and _vertical_gap(region_bounds, target_bounds) <= policy.max_ruby_gap
        )
    return False


def _overlap_length(
    first_start: float,
    first_end: float,
    second_start: float,
    second_end: float,
) -> float:
    return max(0.0, min(first_end, second_end) - max(first_start, second_start))


def _horizontal_gap(first: _Bounds, second: _Bounds) -> float:
    if first.right < second.left:
        return second.left - first.right
    if second.right < first.left:
        return first.left - second.right
    return 0.0


def _vertical_gap(first: _Bounds, second: _Bounds) -> float:
    if first.bottom < second.top:
        return second.top - first.bottom
    if second.bottom < first.top:
        return first.top - second.bottom
    return 0.0


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
    "TextRoleClassificationResult",
    "TextRolePolicy",
    "classify_text_roles",
]
