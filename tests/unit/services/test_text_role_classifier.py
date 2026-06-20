from __future__ import annotations

from image_translator.domain.geometry import Point, Polygon, RotatedBoundingBox
from image_translator.domain.ocr import (
    NormalizedTextRegion,
    ReadingOrder,
    TextOrientation,
    TextRole,
    WritingMode,
)
from image_translator.services.text_role_classifier import classify_text_roles


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
    text: str = "text",
    geometry: Polygon | RotatedBoundingBox,
    writing_mode: WritingMode = WritingMode.horizontal_ltr,
    orientation: TextOrientation = TextOrientation.upright,
    text_role: TextRole = TextRole.unknown,
) -> NormalizedTextRegion:
    return NormalizedTextRegion(
        region_id=region_id,
        source_text=text,
        geometry=geometry,
        source_language="ja",
        writing_mode=writing_mode,
        orientation=orientation,
        reading_order=ReadingOrder(
            page_index=0,
            group_index=0,
            item_index=0,
            confidence=0.95,
        ),
        text_role=text_role,
    )


def test_preserves_supported_existing_text_roles() -> None:
    region = _region(
        "narration-1",
        text="それから",
        geometry=_polygon(10, 10, 70, 30),
        text_role=TextRole.narration,
    )

    result = classify_text_roles((region,))

    assert result.regions[0].text_role is TextRole.narration
    assert result.regions[0].ruby_target_region_id is None
    assert result.requires_review is False


def test_rotated_region_is_classified_as_sound_effect() -> None:
    region = _region(
        "sfx-1",
        text="ドン",
        geometry=RotatedBoundingBox(
            center=Point(x=50, y=50),
            width=70,
            height=20,
            rotation=24,
        ),
        writing_mode=WritingMode.rotated,
        orientation=TextOrientation.arbitrary_angle,
    )

    result = classify_text_roles((region,))

    assert result.regions[0].text_role is TextRole.sound_effect
    assert result.requires_review is False


def test_vertical_ruby_links_to_single_nearby_body_region() -> None:
    body = _region(
        "body-1",
        text="今日",
        geometry=_polygon(50, 10, 80, 90),
        writing_mode=WritingMode.vertical_rl,
        text_role=TextRole.dialogue,
    )
    ruby = _region(
        "ruby-1",
        text="きょう",
        geometry=_polygon(83, 12, 93, 88),
        writing_mode=WritingMode.vertical_rl,
    )

    result = classify_text_roles((body, ruby))

    ruby_result = next(region for region in result.regions if region.region_id == "ruby-1")
    assert ruby_result.text_role is TextRole.ruby
    assert ruby_result.ruby_target_region_id == "body-1"
    assert result.requires_review is False


def test_uncertain_ruby_link_is_not_auto_confirmed() -> None:
    body_a = _region(
        "body-a",
        geometry=_polygon(40, 10, 70, 90),
        writing_mode=WritingMode.vertical_rl,
        text_role=TextRole.dialogue,
    )
    body_b = _region(
        "body-b",
        geometry=_polygon(80, 10, 110, 90),
        writing_mode=WritingMode.vertical_rl,
        text_role=TextRole.dialogue,
    )
    small_text = _region(
        "small-1",
        text="かな",
        geometry=_polygon(72, 12, 78, 88),
        writing_mode=WritingMode.vertical_rl,
    )

    result = classify_text_roles((body_a, body_b, small_text))

    small_result = next(region for region in result.regions if region.region_id == "small-1")
    assert small_result.text_role is TextRole.unknown
    assert small_result.ruby_target_region_id is None
    assert result.requires_review is True
    assert result.review_reasons == ("small-1: uncertain ruby target",)
