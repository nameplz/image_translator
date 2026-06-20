from __future__ import annotations

from PIL import Image

from image_translator.domain.geometry import Point, Polygon
from image_translator.domain.ocr import (
    NormalizedTextRegion,
    ReadingOrder,
    TextOrientation,
    TextRole,
    WritingMode,
)
from image_translator.providers.local_inpainting import LocalMaskFillInpaintingBackend
from image_translator.services.inpainting import InpaintingRequest, inpaint_text


def _polygon(left: float, top: float, right: float, bottom: float) -> Polygon:
    return Polygon(
        points=(
            Point(x=left, y=top),
            Point(x=right, y=top),
            Point(x=right, y=bottom),
            Point(x=left, y=bottom),
        )
    )


def _region(region_id: str = "region-1") -> NormalizedTextRegion:
    return NormalizedTextRegion(
        region_id=region_id,
        source_text="text",
        geometry=_polygon(4, 4, 8, 8),
        source_language="ja",
        writing_mode=WritingMode.horizontal_ltr,
        orientation=TextOrientation.upright,
        reading_order=ReadingOrder(
            page_index=0,
            group_index=0,
            item_index=0,
            confidence=0.95,
        ),
        text_role=TextRole.dialogue,
    )


def test_local_mask_fill_backend_replaces_region_with_requested_fill_color() -> None:
    image = Image.new("RGB", (16, 16), (255, 255, 255))
    for x in range(4, 9):
        for y in range(4, 9):
            image.putpixel((x, y), (0, 0, 0))

    result = LocalMaskFillInpaintingBackend().remove_text(
        image=image,
        regions=(_region(),),
        padding=0,
        fill_color=(200, 210, 220),
    )

    assert result.getpixel((6, 6)) == (200, 210, 220)
    assert image.getpixel((6, 6)) == (0, 0, 0)


def test_inpainting_service_records_changed_regions_and_backend_id() -> None:
    image = Image.new("RGB", (16, 16), (255, 255, 255))
    backend = LocalMaskFillInpaintingBackend()

    result = inpaint_text(
        InpaintingRequest(
            image=image,
            regions=(_region("a"), _region("b")),
            padding=1,
            fill_color=(240, 240, 240),
        ),
        backend=backend,
    )

    assert result.backend_id == "local-mask-fill"
    assert result.changed_region_ids == ("a", "b")
    assert result.image.getpixel((5, 5)) == (240, 240, 240)
