from __future__ import annotations

from dataclasses import dataclass

from image_translator.domain._base import PositiveInt
from image_translator.domain.ids import RegionId
from image_translator.domain.quality import QualityIssue, QualitySeverity
from image_translator.domain.render import RenderedRegion
from image_translator.services.rendering import (
    contrast_ratio,
    geometry_bounds,
    text_has_supported_glyphs,
)

MINIMUM_CONTRAST_RATIO = 4.5
MINIMUM_FONT_SIZE = 8


@dataclass(frozen=True, slots=True)
class ResultValidationPolicy:
    minimum_font_size: PositiveInt = MINIMUM_FONT_SIZE
    minimum_contrast_ratio: float = MINIMUM_CONTRAST_RATIO
    assumed_background_color: tuple[int, int, int] = (255, 255, 255)


@dataclass(frozen=True, slots=True)
class ResultLayoutValidation:
    issues: tuple[QualityIssue, ...]

    @property
    def passed(self) -> bool:
        return not any(
            issue.severity in {QualitySeverity.error, QualitySeverity.critical}
            and not issue.resolved
            for issue in self.issues
        )


def validate_result_layout(
    *,
    expected_region_ids: tuple[RegionId, ...],
    rendered_regions: tuple[RenderedRegion, ...],
    image_size: tuple[int, int],
    policy: ResultValidationPolicy | None = None,
) -> ResultLayoutValidation:
    active_policy = policy or ResultValidationPolicy()
    issues = (
        *_missing_region_issues(expected_region_ids, rendered_regions),
        *_region_layout_issues(rendered_regions, image_size, active_policy),
        *_overlap_issues(rendered_regions),
    )
    return ResultLayoutValidation(issues=issues)


def _missing_region_issues(
    expected_region_ids: tuple[RegionId, ...],
    rendered_regions: tuple[RenderedRegion, ...],
) -> tuple[QualityIssue, ...]:
    rendered_ids = {region.region_id for region in rendered_regions}
    return tuple(
        _issue(
            code="missing_region",
            severity=QualitySeverity.critical,
            region_ids=(region_id,),
            summary=f"Region {region_id} is missing from rendered output.",
            action="create a RenderPlan for the missing region",
        )
        for region_id in expected_region_ids
        if region_id not in rendered_ids
    )


def _region_layout_issues(
    rendered_regions: tuple[RenderedRegion, ...],
    image_size: tuple[int, int],
    policy: ResultValidationPolicy,
) -> tuple[QualityIssue, ...]:
    issues: list[QualityIssue] = []
    for region in rendered_regions:
        if _is_clipped(region, image_size):
            issues.append(
                _issue(
                    code="text_clipping",
                    severity=QualitySeverity.error,
                    region_ids=(region.region_id,),
                    summary=f"Rendered text for {region.region_id} clips outside the image.",
                    action="resize or move the rendered region",
                )
            )
        if region.applied_plan.style.size < policy.minimum_font_size:
            issues.append(
                _issue(
                    code="minimum_font_size",
                    severity=QualitySeverity.error,
                    region_ids=(region.region_id,),
                    summary=f"Font size for {region.region_id} is below the minimum.",
                    action="increase font size or resize the region",
                )
            )
        if not text_has_supported_glyphs(region.applied_plan.translated_text):
            issues.append(
                _issue(
                    code="unsupported_glyph",
                    severity=QualitySeverity.error,
                    region_ids=(region.region_id,),
                    summary=f"Rendered text for {region.region_id} has unsupported glyphs.",
                    action="choose a supported font or replace unsupported characters",
                )
            )
        if _has_low_contrast(region, policy):
            issues.append(
                _issue(
                    code="low_contrast",
                    severity=QualitySeverity.error,
                    region_ids=(region.region_id,),
                    summary=f"Rendered text for {region.region_id} has low contrast.",
                    action="adjust text color or outline",
                )
            )
    return tuple(issues)


def _overlap_issues(rendered_regions: tuple[RenderedRegion, ...]) -> tuple[QualityIssue, ...]:
    issues: list[QualityIssue] = []
    for index, region in enumerate(rendered_regions):
        for other in rendered_regions[index + 1 :]:
            if _overlaps(region, other):
                issues.append(
                    _issue(
                        code="text_overlap",
                        severity=QualitySeverity.error,
                        region_ids=(region.region_id, other.region_id),
                        summary=(
                            f"Rendered regions {region.region_id} and "
                            f"{other.region_id} overlap."
                        ),
                        action="move or resize one rendered region",
                    )
                )
    return tuple(issues)


def _is_clipped(region: RenderedRegion, image_size: tuple[int, int]) -> bool:
    left, top, right, bottom = geometry_bounds(region.output_geometry)
    width, height = image_size
    return left < 0 or top < 0 or right > width or bottom > height


def _has_low_contrast(region: RenderedRegion, policy: ResultValidationPolicy) -> bool:
    ratio = contrast_ratio(
        region.applied_plan.style.color.tuple,
        policy.assumed_background_color,
    )
    return ratio < policy.minimum_contrast_ratio


def _overlaps(region: RenderedRegion, other: RenderedRegion) -> bool:
    left, top, right, bottom = geometry_bounds(region.output_geometry)
    other_left, other_top, other_right, other_bottom = geometry_bounds(other.output_geometry)
    return not (
        right <= other_left
        or other_right <= left
        or bottom <= other_top
        or other_bottom <= top
    )


def _issue(
    *,
    code: str,
    severity: QualitySeverity,
    region_ids: tuple[RegionId, ...],
    summary: str,
    action: str,
) -> QualityIssue:
    return QualityIssue(
        issue_code=code,
        severity=severity,
        scope="result_layout",
        region_ids=region_ids,
        summary=summary,
        recommended_action=action,
    )


__all__ = [
    "MINIMUM_CONTRAST_RATIO",
    "MINIMUM_FONT_SIZE",
    "ResultLayoutValidation",
    "ResultValidationPolicy",
    "validate_result_layout",
]
