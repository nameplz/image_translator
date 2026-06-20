from __future__ import annotations

from image_translator.domain.geometry import Point, Polygon
from image_translator.domain.ocr import WritingMode
from image_translator.domain.render import RenderedRegion, RenderPlan, RenderStyle, RGBColor
from image_translator.services.result_validation import (
    ResultValidationPolicy,
    validate_result_layout,
)


def _polygon(left: float, top: float, right: float, bottom: float) -> Polygon:
    return Polygon(
        points=(
            Point(x=left, y=top),
            Point(x=right, y=top),
            Point(x=right, y=bottom),
            Point(x=left, y=bottom),
        )
    )


def _rendered_region(
    region_id: str,
    *,
    geometry: Polygon | None = None,
    output_geometry: Polygon | None = None,
    text: str = "hello",
    color: RGBColor | None = None,
    size: int = 14,
) -> RenderedRegion:
    plan = RenderPlan(
        region_id=region_id,
        geometry=geometry or _polygon(10, 10, 50, 30),
        translated_text=text,
        style=RenderStyle(
            size=size,
            color=color or RGBColor(red=0, green=0, blue=0),
            writing_mode=WritingMode.horizontal_ltr,
        ),
    )
    return RenderedRegion(
        region_id=region_id,
        applied_plan=plan,
        output_geometry=output_geometry or plan.geometry,
    )


def test_validate_result_layout_passes_clean_rendered_regions() -> None:
    result = validate_result_layout(
        expected_region_ids=("region-1",),
        rendered_regions=(_rendered_region("region-1"),),
        image_size=(100, 100),
    )

    assert result.passed is True
    assert result.issues == ()


def test_validate_result_layout_reports_missing_region() -> None:
    result = validate_result_layout(
        expected_region_ids=("region-1", "region-2"),
        rendered_regions=(_rendered_region("region-1"),),
        image_size=(100, 100),
    )

    assert result.passed is False
    assert tuple(issue.issue_code for issue in result.issues) == ("missing_region",)
    assert result.issues[0].region_ids == ("region-2",)


def test_validate_result_layout_reports_clipping_and_overlap() -> None:
    result = validate_result_layout(
        expected_region_ids=("a", "b"),
        rendered_regions=(
            _rendered_region("a", output_geometry=_polygon(80, 10, 130, 40)),
            _rendered_region("b", output_geometry=_polygon(90, 20, 120, 50)),
        ),
        image_size=(100, 100),
    )

    assert {issue.issue_code for issue in result.issues} == {
        "text_clipping",
        "text_overlap",
    }


def test_validate_result_layout_reports_font_contrast_and_glyph_issues() -> None:
    result = validate_result_layout(
        expected_region_ids=("region-1",),
        rendered_regions=(
            _rendered_region(
                "region-1",
                text="bad\ufffd",
                color=RGBColor(red=250, green=250, blue=250),
                size=6,
            ),
        ),
        image_size=(100, 100),
        policy=ResultValidationPolicy(minimum_font_size=8),
    )

    assert {issue.issue_code for issue in result.issues} == {
        "minimum_font_size",
        "unsupported_glyph",
        "low_contrast",
    }
