from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import cast

from PIL import Image, ImageDraw, ImageFont

from image_translator.domain.geometry import Point, Polygon, RegionGeometry, RotatedBoundingBox
from image_translator.domain.ocr import NormalizedTextRegion, WritingMode
from image_translator.domain.render import (
    OverflowPolicy,
    RenderedRegion,
    RenderPlan,
    RenderStyle,
)
from image_translator.domain.translation import TranslationResult

DEFAULT_FONT_FALLBACKS = (
    "DejaVuSans.ttf",
    "Arial Unicode.ttf",
    "Arial.ttf",
)


@dataclass(frozen=True, slots=True)
class FontSelection:
    requested_family: str
    loaded_family: str
    fallback_used: bool


@dataclass(frozen=True, slots=True)
class RenderedPage:
    image: Image.Image
    regions: tuple[RenderedRegion, ...]
    font_selections: tuple[FontSelection, ...]


def create_render_plan(
    *,
    region: NormalizedTextRegion,
    translation: TranslationResult,
    target_language: str,
    style: RenderStyle | None = None,
    overflow_policy: OverflowPolicy = OverflowPolicy.shrink_to_fit,
) -> RenderPlan:
    if region.region_id != translation.region_id:
        raise ValueError("translation region ID must match source region ID")

    base_style = style or RenderStyle()
    writing_mode = _default_writing_mode(region, target_language)
    return RenderPlan(
        region_id=region.region_id,
        geometry=region.geometry,
        translated_text=translation.approved_translated_text,
        style=base_style.model_copy(update={"writing_mode": writing_mode}),
        overflow_policy=overflow_policy,
        source_style_evidence=("target language writing mode default",),
    )


def render_page(
    *,
    image: Image.Image,
    plans: tuple[RenderPlan, ...],
    font_fallbacks: tuple[str, ...] = DEFAULT_FONT_FALLBACKS,
) -> RenderedPage:
    output = image.copy()
    draw = ImageDraw.Draw(output)
    rendered_regions: list[RenderedRegion] = []
    font_selections: list[FontSelection] = []

    for plan in plans:
        bounds = geometry_bounds(plan.geometry)
        font, selection = _load_font(plan.style, font_fallbacks)
        font_selections.append(selection)
        lines, font = _fit_lines(plan=plan, bounds=bounds, font=font, font_paths=font_fallbacks)
        text_geometry = _draw_plan(draw=draw, plan=plan, bounds=bounds, font=font, lines=lines)
        rendered_regions.append(
            RenderedRegion(
                region_id=plan.region_id,
                applied_plan=plan,
                output_geometry=text_geometry,
            )
        )

    return RenderedPage(
        image=output,
        regions=tuple(rendered_regions),
        font_selections=tuple(font_selections),
    )


def geometry_bounds(geometry: RegionGeometry) -> tuple[float, float, float, float]:
    points = geometry.points if isinstance(geometry, Polygon) else _bbox_corners(geometry)
    xs = tuple(point.x for point in points)
    ys = tuple(point.y for point in points)
    return (min(xs), min(ys), max(xs), max(ys))


def text_has_supported_glyphs(text: str) -> bool:
    return all(_is_supported_text_character(character) for character in text)


def contrast_ratio(
    foreground: tuple[int, int, int],
    background: tuple[int, int, int],
) -> float:
    lighter = max(_relative_luminance(foreground), _relative_luminance(background))
    darker = min(_relative_luminance(foreground), _relative_luminance(background))
    return (lighter + 0.05) / (darker + 0.05)


def _default_writing_mode(
    region: NormalizedTextRegion,
    target_language: str,
) -> WritingMode:
    normalized_language = target_language.lower()
    if normalized_language in {"en", "eng", "english", "ko", "kor", "korean"}:
        return WritingMode.horizontal_ltr
    if normalized_language in {"ja", "jpn", "japanese"}:
        left, top, right, bottom = geometry_bounds(region.geometry)
        is_tall_region = (bottom - top) > (right - left)
        if is_tall_region and region.writing_mode is WritingMode.vertical_rl:
            return WritingMode.vertical_rl
        return WritingMode.horizontal_ltr
    return WritingMode.horizontal_ltr


def _load_font(
    style: RenderStyle,
    font_paths: tuple[str, ...],
) -> tuple[ImageFont.ImageFont | ImageFont.FreeTypeFont, FontSelection]:
    candidates = (style.font_family, *font_paths)
    for candidate in candidates:
        try:
            font = ImageFont.truetype(candidate, size=style.size)
        except OSError:
            continue
        return font, FontSelection(
            requested_family=style.font_family,
            loaded_family=Path(candidate).name,
            fallback_used=candidate != style.font_family,
        )

    return ImageFont.load_default(), FontSelection(
        requested_family=style.font_family,
        loaded_family="Pillow default",
        fallback_used=True,
    )


def _fit_lines(
    *,
    plan: RenderPlan,
    bounds: tuple[float, float, float, float],
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    font_paths: tuple[str, ...],
) -> tuple[tuple[str, ...], ImageFont.ImageFont | ImageFont.FreeTypeFont]:
    lines = _wrap_text(plan.translated_text, bounds, font)
    if plan.overflow_policy is not OverflowPolicy.shrink_to_fit:
        return lines, font

    left, top, right, bottom = bounds
    width = max(1, int(right - left))
    height = max(1, int(bottom - top))
    size = plan.style.size
    fitted_font = font
    fitted_lines = lines

    while size > 1:
        text_width, text_height = _text_block_size(fitted_lines, fitted_font, plan.style)
        if text_width <= width and text_height <= height:
            return fitted_lines, fitted_font
        size -= 1
        fitted_style = plan.style.model_copy(update={"size": size})
        fitted_font, _selection = _load_font(fitted_style, font_paths)
        fitted_lines = _wrap_text(plan.translated_text, bounds, fitted_font)

    return fitted_lines, fitted_font


def _wrap_text(
    text: str,
    bounds: tuple[float, float, float, float],
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
) -> tuple[str, ...]:
    if not text:
        return ("",)

    left, _top, right, _bottom = bounds
    max_width = max(1, int(right - left))
    words = text.split()
    if not words:
        return tuple(text)

    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        if _single_line_size(candidate, font)[0] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return tuple(lines)


def _draw_plan(
    *,
    draw: ImageDraw.ImageDraw,
    plan: RenderPlan,
    bounds: tuple[float, float, float, float],
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    lines: tuple[str, ...],
) -> Polygon:
    if plan.style.writing_mode is WritingMode.vertical_rl:
        return _draw_vertical(draw=draw, plan=plan, bounds=bounds, font=font)
    return _draw_horizontal(draw=draw, plan=plan, bounds=bounds, font=font, lines=lines)


def _draw_horizontal(
    *,
    draw: ImageDraw.ImageDraw,
    plan: RenderPlan,
    bounds: tuple[float, float, float, float],
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    lines: tuple[str, ...],
) -> Polygon:
    left, top, right, bottom = bounds
    text_width, text_height = _text_block_size(lines, font, plan.style)
    y = top + max(0.0, ((bottom - top) - text_height) / 2.0)

    max_right = left
    max_bottom = y
    for line in lines:
        line_width, line_height = _single_line_size(line, font)
        if plan.style.alignment.value == "right":
            x = right - line_width
        elif plan.style.alignment.value == "left":
            x = left
        else:
            x = left + max(0.0, ((right - left) - line_width) / 2.0)
        _draw_text(draw=draw, position=(x, y), text=line, plan=plan, font=font)
        max_right = max(max_right, x + line_width)
        max_bottom = max(max_bottom, y + line_height)
        y += line_height * plan.style.line_spacing

    return _polygon_from_bounds(left, top, max_right, max_bottom)


def _draw_vertical(
    *,
    draw: ImageDraw.ImageDraw,
    plan: RenderPlan,
    bounds: tuple[float, float, float, float],
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
) -> Polygon:
    left, top, right, bottom = bounds
    line_width, line_height = _single_line_size("M", font)
    x = right - line_width
    y = top
    min_left = x
    max_bottom = y

    for character in plan.translated_text:
        if y + line_height > bottom:
            x -= line_width
            y = top
        _draw_text(draw=draw, position=(x, y), text=character, plan=plan, font=font)
        min_left = min(min_left, x)
        max_bottom = max(max_bottom, y + line_height)
        y += line_height * plan.style.line_spacing

    return _polygon_from_bounds(min_left, top, right, max_bottom)


def _draw_text(
    *,
    draw: ImageDraw.ImageDraw,
    position: tuple[float, float],
    text: str,
    plan: RenderPlan,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
) -> None:
    draw.text(
        position,
        text,
        fill=plan.style.color.tuple,
        font=font,
        stroke_width=plan.style.outline_width,
        stroke_fill=(
            plan.style.outline_color.tuple
            if plan.style.outline_color is not None
            else None
        ),
    )


def _single_line_size(
    text: str,
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
) -> tuple[int, int]:
    left, top, right, bottom = font.getbbox(text)
    return (max(1, int(right - left)), max(1, int(bottom - top)))


def _text_block_size(
    lines: tuple[str, ...],
    font: ImageFont.ImageFont | ImageFont.FreeTypeFont,
    style: RenderStyle,
) -> tuple[int, int]:
    sizes = tuple(_single_line_size(line, font) for line in lines)
    width = max((size[0] for size in sizes), default=1)
    line_height = max((size[1] for size in sizes), default=1)
    height = int(line_height * len(lines) * style.line_spacing)
    return (width, max(1, height))


def _bbox_corners(bbox: RotatedBoundingBox) -> tuple[Point, Point, Point, Point]:
    half_width = bbox.width / 2.0
    half_height = bbox.height / 2.0
    return (
        Point(x=bbox.center.x - half_width, y=bbox.center.y - half_height),
        Point(x=bbox.center.x + half_width, y=bbox.center.y - half_height),
        Point(x=bbox.center.x + half_width, y=bbox.center.y + half_height),
        Point(x=bbox.center.x - half_width, y=bbox.center.y + half_height),
    )


def _polygon_from_bounds(left: float, top: float, right: float, bottom: float) -> Polygon:
    safe_right = right if right > left else left + 1.0
    safe_bottom = bottom if bottom > top else top + 1.0
    return Polygon(
        points=(
            Point(x=left, y=top),
            Point(x=safe_right, y=top),
            Point(x=safe_right, y=safe_bottom),
            Point(x=left, y=safe_bottom),
        )
    )


def _is_supported_text_character(character: str) -> bool:
    codepoint = ord(character)
    return not (
        codepoint == 0xFFFD
        or 0xE000 <= codepoint <= 0xF8FF
        or codepoint < 0x20
        and character not in {"\n", "\t"}
    )


def _relative_luminance(color: tuple[int, int, int]) -> float:
    channels = tuple(_linear_channel(value / 255.0) for value in color)
    return (0.2126 * channels[0]) + (0.7152 * channels[1]) + (0.0722 * channels[2])


def _linear_channel(value: float) -> float:
    if value <= 0.03928:
        return value / 12.92
    return cast(float, ((value + 0.055) / 1.055) ** 2.4)


__all__ = [
    "DEFAULT_FONT_FALLBACKS",
    "FontSelection",
    "RenderedPage",
    "contrast_ratio",
    "create_render_plan",
    "geometry_bounds",
    "render_page",
    "text_has_supported_glyphs",
]
