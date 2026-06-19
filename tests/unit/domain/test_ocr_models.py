from __future__ import annotations

import pytest
from pydantic import ValidationError

from image_translator.domain.geometry import Point, Polygon
from image_translator.domain.ocr import (
    NormalizedTextRegion,
    OCRCandidate,
    RawOCRRegion,
    ReadingOrder,
    TextOrientation,
    TextRole,
    WritingMode,
)


def _geometry() -> Polygon:
    return Polygon(
        points=(
            Point(x=0, y=0),
            Point(x=20, y=0),
            Point(x=0, y=20),
        )
    )


def _reading_order() -> ReadingOrder:
    return ReadingOrder(page_index=0, group_index=0, item_index=0, confidence=0.98)


def test_normalized_text_region_requires_non_null_geometry() -> None:
    with pytest.raises(ValidationError):
        NormalizedTextRegion(
            region_id="region-1",
            source_text="こんにちは",
            geometry=None,
            source_language="ja",
            writing_mode=WritingMode.vertical_rl,
            orientation=TextOrientation.upright,
            reading_order=_reading_order(),
            text_role=TextRole.dialogue,
            ocr_provenance=("provider-request-1",),
        )


def test_normalized_text_region_is_immutable_and_tuple_based() -> None:
    region = NormalizedTextRegion(
        region_id="region-1",
        source_text="こんにちは",
        geometry=_geometry(),
        source_language="ja",
        writing_mode=WritingMode.vertical_rl,
        orientation=TextOrientation.upright,
        reading_order=_reading_order(),
        text_role=TextRole.dialogue,
        ruby_target_region_id=None,
        ocr_provenance=["provider-request-1", "provider-request-2"],
    )

    assert region.ocr_provenance == ("provider-request-1", "provider-request-2")
    with pytest.raises(ValidationError):
        region.source_text = "changed"


def test_raw_ocr_region_and_candidate_capture_safe_provider_summaries() -> None:
    raw_region = RawOCRRegion(
        region_id="region-1",
        raw_text="こんにちは",
        confidence=0.87,
        geometry=_geometry(),
        writing_mode=WritingMode.vertical_rl,
        writing_mode_confidence=0.91,
        provider_id="primary-ocr",
        metadata_summary=["detected vertical text"],
    )
    candidate = OCRCandidate(
        region_id="region-1",
        text="こんにちは",
        language="ja",
        provider_id="primary-ocr",
        confidence=0.87,
        evidence_summary="primary OCR high confidence",
    )

    assert raw_region.metadata_summary == ("detected vertical text",)
    assert candidate.region_id == raw_region.region_id
