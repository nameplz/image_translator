from __future__ import annotations

import pytest

from image_translator.domain.errors import ReadingOrderUncertainError
from image_translator.domain.geometry import Point, Polygon
from image_translator.domain.ocr import (
    NormalizedTextRegion,
    ReadingOrder,
    ReadingOrderCandidate,
    TextOrientation,
    TextRole,
    WritingMode,
)
from image_translator.services.layout_analysis import analyze_reading_order


def _polygon(left: float, top: float, right: float, bottom: float) -> Polygon:
    return Polygon(
        points=(
            Point(x=left, y=top),
            Point(x=right, y=top),
            Point(x=right, y=bottom),
            Point(x=left, y=bottom),
        )
    )


def _region(
    region_id: str,
    *,
    geometry: Polygon,
    writing_mode: WritingMode,
    group_index: int = 0,
    confidence: float = 0.95,
    alternatives: tuple[ReadingOrderCandidate, ...] = (),
) -> NormalizedTextRegion:
    return NormalizedTextRegion(
        region_id=region_id,
        source_text=region_id,
        geometry=geometry,
        source_language="ja",
        writing_mode=writing_mode,
        orientation=TextOrientation.upright,
        reading_order=ReadingOrder(
            page_index=0,
            group_index=group_index,
            item_index=0,
            confidence=confidence,
            alternatives=alternatives,
        ),
        text_role=TextRole.dialogue,
    )


def test_vertical_rl_orders_top_to_bottom_then_right_to_left_columns() -> None:
    regions = (
        _region(
            "left-bottom",
            geometry=_polygon(10, 70, 25, 100),
            writing_mode=WritingMode.vertical_rl,
        ),
        _region(
            "right-bottom",
            geometry=_polygon(70, 70, 85, 100),
            writing_mode=WritingMode.vertical_rl,
        ),
        _region(
            "left-top",
            geometry=_polygon(10, 10, 25, 40),
            writing_mode=WritingMode.vertical_rl,
        ),
        _region(
            "right-top",
            geometry=_polygon(70, 10, 85, 40),
            writing_mode=WritingMode.vertical_rl,
        ),
    )

    result = analyze_reading_order(regions)

    assert tuple(region.region_id for region in result.regions) == (
        "right-top",
        "right-bottom",
        "left-top",
        "left-bottom",
    )
    assert tuple(region.reading_order.item_index for region in result.regions) == (
        0,
        1,
        2,
        3,
    )
    assert result.requires_review is False


def test_mixed_horizontal_and_vertical_groups_keep_group_flow() -> None:
    vertical = _region(
        "vertical-dialogue",
        geometry=_polygon(70, 10, 85, 70),
        writing_mode=WritingMode.vertical_rl,
        group_index=1,
    )
    horizontal = _region(
        "horizontal-narration",
        geometry=_polygon(10, 10, 60, 25),
        writing_mode=WritingMode.horizontal_ltr,
        group_index=0,
    )

    result = analyze_reading_order((vertical, horizontal))

    assert tuple(region.region_id for region in result.regions) == (
        "horizontal-narration",
        "vertical-dialogue",
    )
    assert result.regions[0].reading_order.group_index == 0
    assert result.regions[1].reading_order.group_index == 1


def test_horizontal_rtl_and_vertical_lr_are_explicitly_ordered() -> None:
    rtl_result = analyze_reading_order(
        (
            _region(
                "rtl-left",
                geometry=_polygon(10, 10, 30, 30),
                writing_mode=WritingMode.horizontal_rtl,
            ),
            _region(
                "rtl-right",
                geometry=_polygon(70, 10, 90, 30),
                writing_mode=WritingMode.horizontal_rtl,
            ),
        )
    )
    vertical_lr_result = analyze_reading_order(
        (
            _region(
                "lr-right",
                geometry=_polygon(70, 10, 90, 30),
                writing_mode=WritingMode.vertical_lr,
            ),
            _region(
                "lr-left",
                geometry=_polygon(10, 10, 30, 30),
                writing_mode=WritingMode.vertical_lr,
            ),
        )
    )

    assert tuple(region.region_id for region in rtl_result.regions) == (
        "rtl-right",
        "rtl-left",
    )
    assert tuple(region.region_id for region in vertical_lr_result.regions) == (
        "lr-left",
        "lr-right",
    )


def test_ambiguous_reading_order_raises_instead_of_auto_approving() -> None:
    alternative = ReadingOrderCandidate(
        page_index=0,
        group_index=0,
        item_index=1,
        confidence=0.77,
        evidence_summary="near-tie ordering candidate",
    )
    region = _region(
        "ambiguous",
        geometry=_polygon(10, 10, 30, 30),
        writing_mode=WritingMode.horizontal_ltr,
        confidence=0.78,
        alternatives=(alternative,),
    )

    with pytest.raises(ReadingOrderUncertainError, match="ambiguous"):
        analyze_reading_order((region,))


def test_ambiguous_reading_order_can_return_review_required_result() -> None:
    region = _region(
        "low-confidence",
        geometry=_polygon(10, 10, 30, 30),
        writing_mode=WritingMode.horizontal_ltr,
        confidence=0.4,
    )

    result = analyze_reading_order((region,), raise_on_uncertain=False)

    assert result.requires_review is True
    assert result.regions == (region,)
    assert result.review_reasons == ("low-confidence: low reading order confidence",)
