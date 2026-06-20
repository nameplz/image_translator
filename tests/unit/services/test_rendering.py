from __future__ import annotations

from PIL import Image, ImageChops

from image_translator.domain.geometry import Point, Polygon
from image_translator.domain.ocr import (
    NormalizedTextRegion,
    ReadingOrder,
    TextOrientation,
    TextRole,
    WritingMode,
)
from image_translator.domain.render import RenderStyle, RGBColor
from image_translator.domain.translation import TranslationResult
from image_translator.services.rendering import (
    create_render_plan,
    render_page,
    text_has_supported_glyphs,
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


def _region(
    region_id: str = "region-1",
    *,
    geometry: Polygon | None = None,
    writing_mode: WritingMode = WritingMode.vertical_rl,
) -> NormalizedTextRegion:
    return NormalizedTextRegion(
        region_id=region_id,
        source_text="原文",
        geometry=geometry or _polygon(20, 10, 60, 90),
        source_language="ja",
        writing_mode=writing_mode,
        orientation=TextOrientation.upright,
        reading_order=ReadingOrder(
            page_index=0,
            group_index=0,
            item_index=0,
            confidence=0.95,
        ),
        text_role=TextRole.dialogue,
    )


def _translation(region_id: str = "region-1", text: str = "hello") -> TranslationResult:
    return TranslationResult(
        region_id=region_id,
        approved_translated_text=text,
        source_language="ja",
        target_language="en",
        selected_candidate_id="candidate-1",
        approval_status="approved_automatic",
    )


def test_create_render_plan_applies_target_language_writing_mode_without_rewriting_text() -> None:
    region = _region(writing_mode=WritingMode.vertical_rl)
    translation = _translation(text="Do not change me")

    plan = create_render_plan(
        region=region,
        translation=translation,
        target_language="en",
        style=RenderStyle(size=14),
    )

    assert plan.translated_text == "Do not change me"
    assert plan.style.writing_mode is WritingMode.horizontal_ltr


def test_japanese_render_plan_keeps_vertical_rl_for_tall_vertical_source_region() -> None:
    region = _region(
        geometry=_polygon(20, 10, 45, 100),
        writing_mode=WritingMode.vertical_rl,
    )

    plan = create_render_plan(
        region=region,
        translation=_translation(text="日本語"),
        target_language="ja",
    )

    assert plan.style.writing_mode is WritingMode.vertical_rl


def test_render_page_draws_text_and_records_font_fallback() -> None:
    base = Image.new("RGB", (120, 80), "white")
    plan = create_render_plan(
        region=_region(geometry=_polygon(10, 10, 110, 60)),
        translation=_translation(text="rendered"),
        target_language="en",
        style=RenderStyle(
            font_family="definitely-missing-font.ttf",
            size=18,
            color=RGBColor(red=0, green=0, blue=0),
        ),
    )

    result = render_page(image=base, plans=(plan,), font_fallbacks=())

    assert result.regions[0].region_id == "region-1"
    assert result.regions[0].applied_plan.translated_text == "rendered"
    assert result.font_selections[0].fallback_used is True
    assert ImageChops.difference(base, result.image).getbbox() is not None


def test_glyph_support_check_rejects_replacement_and_private_use_characters() -> None:
    assert text_has_supported_glyphs("hello") is True
    assert text_has_supported_glyphs("bad\ufffd") is False
    assert text_has_supported_glyphs("bad\ue000") is False
