from __future__ import annotations

import pytest
from pydantic import ValidationError

from image_translator.domain.errors import InvalidRegionError
from image_translator.domain.geometry import Point, Polygon, RotatedBoundingBox
from image_translator.domain.image import ImageDimensions
from image_translator.domain.ocr import (
    RawOCRRegion,
    ReadingOrder,
    TextOrientation,
    TextRole,
    WritingMode,
)
from image_translator.services.ocr_normalization import normalize_ocr_regions


def _polygon(
    *,
    left: float = 10,
    top: float = 10,
    right: float = 30,
    bottom: float = 30,
) -> Polygon:
    return Polygon(
        points=(
            Point(x=left, y=top),
            Point(x=right, y=top),
            Point(x=right, y=bottom),
            Point(x=left, y=bottom),
        )
    )


def _raw_region(
    *,
    region_id: str = "region-1",
    text: str = "こんにちは",
    geometry: Polygon | RotatedBoundingBox | None = None,
    confidence: float = 0.92,
    writing_mode: WritingMode = WritingMode.vertical_rl,
    writing_mode_confidence: float = 0.88,
) -> RawOCRRegion:
    return RawOCRRegion(
        region_id=region_id,
        raw_text=text,
        confidence=confidence,
        geometry=geometry or _polygon(),
        writing_mode=writing_mode,
        writing_mode_confidence=writing_mode_confidence,
        provider_id="primary-ocr",
    )


def _reading_order(region_id: str = "region-1") -> dict[str, ReadingOrder]:
    return {
        region_id: ReadingOrder(
            page_index=0,
            group_index=0,
            item_index=0,
            confidence=0.96,
        )
    }


def test_normalizes_raw_regions_to_text_regions_without_mutating_snapshot() -> None:
    raw_region = _raw_region()
    normalized = normalize_ocr_regions(
        (raw_region,),
        image_dimensions=ImageDimensions(width=100, height=100),
        source_language="ja",
        reading_orders=_reading_order(),
        text_roles={"region-1": TextRole.dialogue},
    )

    assert len(normalized) == 1
    assert normalized[0].region_id == "region-1"
    assert normalized[0].source_text == "こんにちは"
    assert normalized[0].geometry == raw_region.geometry
    assert normalized[0].writing_mode is WritingMode.vertical_rl
    assert normalized[0].orientation is TextOrientation.upright
    assert normalized[0].text_role is TextRole.dialogue
    assert raw_region.raw_text == "こんにちは"


def test_preserves_rotated_bounding_box_geometry() -> None:
    bbox = RotatedBoundingBox(
        center=Point(x=50, y=40),
        width=20,
        height=12,
        rotation=25,
    )
    raw_region = _raw_region(
        region_id="sound-1",
        geometry=bbox,
        writing_mode=WritingMode.rotated,
    )

    normalized = normalize_ocr_regions(
        (raw_region,),
        image_dimensions=ImageDimensions(width=100, height=100),
        source_language="ja",
        reading_orders=_reading_order("sound-1"),
        text_roles={"sound-1": TextRole.sound_effect},
    )

    assert normalized[0].geometry == bbox
    assert normalized[0].orientation is TextOrientation.arbitrary_angle


def test_rejects_duplicate_page_region_ids() -> None:
    with pytest.raises(InvalidRegionError, match="duplicate region ID"):
        normalize_ocr_regions(
            (_raw_region(region_id="duplicate"), _raw_region(region_id="duplicate")),
            image_dimensions=ImageDimensions(width=100, height=100),
            source_language="ja",
            reading_orders=_reading_order("duplicate"),
        )


def test_raw_region_schema_rejects_missing_geometry() -> None:
    with pytest.raises(ValidationError):
        RawOCRRegion(
            region_id="region-1",
            raw_text="こんにちは",
            confidence=0.92,
            geometry=None,
            writing_mode=WritingMode.vertical_rl,
            writing_mode_confidence=0.88,
            provider_id="primary-ocr",
        )


def test_raw_region_schema_rejects_invalid_polygon() -> None:
    with pytest.raises(ValidationError, match="positive area"):
        _raw_region(
            geometry=Polygon(
                points=(
                    Point(x=0, y=0),
                    Point(x=1, y=1),
                    Point(x=2, y=2),
                )
            )
        )


def test_rejects_geometry_that_misses_image_bounds() -> None:
    with pytest.raises(InvalidRegionError, match="does not intersect image bounds"):
        normalize_ocr_regions(
            (_raw_region(geometry=_polygon(left=120, top=120, right=140, bottom=140)),),
            image_dimensions=ImageDimensions(width=100, height=100),
            source_language="ja",
            reading_orders=_reading_order(),
        )


def test_rejects_missing_reading_order_for_region() -> None:
    with pytest.raises(InvalidRegionError, match="missing reading order"):
        normalize_ocr_regions(
            (_raw_region(),),
            image_dimensions=ImageDimensions(width=100, height=100),
            source_language="ja",
            reading_orders={},
        )
