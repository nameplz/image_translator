from __future__ import annotations

from typing import cast

from PIL import Image, ImageDraw

from image_translator.domain.geometry import Point, Polygon, RegionGeometry, RotatedBoundingBox
from image_translator.domain.ocr import NormalizedTextRegion


class LocalMaskFillInpaintingBackend:
    backend_id = "local-mask-fill"

    def remove_text(
        self,
        *,
        image: Image.Image,
        regions: tuple[NormalizedTextRegion, ...],
        padding: int,
        fill_color: tuple[int, int, int] | None,
    ) -> Image.Image:
        output = image.convert("RGB").copy()
        draw = ImageDraw.Draw(output)

        for region in regions:
            bounds = _padded_bounds(
                geometry=region.geometry,
                image_size=output.size,
                padding=padding,
            )
            color = fill_color or _sample_border_color(output, bounds)
            draw.rectangle(bounds, fill=color)

        return output


def _padded_bounds(
    *,
    geometry: RegionGeometry,
    image_size: tuple[int, int],
    padding: int,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = _geometry_bounds(geometry)
    width, height = image_size
    return (
        max(0, int(left) - padding),
        max(0, int(top) - padding),
        min(width - 1, int(right) + padding),
        min(height - 1, int(bottom) + padding),
    )


def _geometry_bounds(geometry: RegionGeometry) -> tuple[float, float, float, float]:
    points = geometry.points if isinstance(geometry, Polygon) else _bbox_corners(geometry)
    xs = tuple(point.x for point in points)
    ys = tuple(point.y for point in points)
    return (min(xs), min(ys), max(xs), max(ys))


def _bbox_corners(bbox: RotatedBoundingBox) -> tuple[Point, Point, Point, Point]:
    half_width = bbox.width / 2.0
    half_height = bbox.height / 2.0
    return (
        Point(x=bbox.center.x - half_width, y=bbox.center.y - half_height),
        Point(x=bbox.center.x + half_width, y=bbox.center.y - half_height),
        Point(x=bbox.center.x + half_width, y=bbox.center.y + half_height),
        Point(x=bbox.center.x - half_width, y=bbox.center.y + half_height),
    )


def _sample_border_color(
    image: Image.Image,
    bounds: tuple[int, int, int, int],
) -> tuple[int, int, int]:
    left, top, right, bottom = bounds
    width, height = image.size
    samples: list[tuple[int, int, int]] = []

    sample_left = max(0, left - 1)
    sample_right = min(width - 1, right + 1)
    sample_top = max(0, top - 1)
    sample_bottom = min(height - 1, bottom + 1)

    for x in range(sample_left, sample_right + 1):
        if sample_top < top:
            samples.append(_pixel_rgb(image, x, sample_top))
        if sample_bottom > bottom:
            samples.append(_pixel_rgb(image, x, sample_bottom))
    for y in range(sample_top, sample_bottom + 1):
        if sample_left < left:
            samples.append(_pixel_rgb(image, sample_left, y))
        if sample_right > right:
            samples.append(_pixel_rgb(image, sample_right, y))

    if not samples:
        return (255, 255, 255)

    red = round(sum(color[0] for color in samples) / len(samples))
    green = round(sum(color[1] for color in samples) / len(samples))
    blue = round(sum(color[2] for color in samples) / len(samples))
    return (red, green, blue)


def _pixel_rgb(image: Image.Image, x: int, y: int) -> tuple[int, int, int]:
    pixel = image.getpixel((x, y))
    if isinstance(pixel, int):
        return (pixel, pixel, pixel)
    channels = cast(tuple[int, ...], pixel)
    return (int(channels[0]), int(channels[1]), int(channels[2]))


__all__ = ["LocalMaskFillInpaintingBackend"]
