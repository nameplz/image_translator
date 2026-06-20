from __future__ import annotations

import pytest

from image_translator.domain.geometry import Point, Polygon
from image_translator.domain.ocr import (
    RawOCRRegion,
    ReadingOrder,
    ReadingOrderCandidate,
    TextRole,
    WritingMode,
)
from image_translator.services.ocr_risk import OCRRiskPolicy, score_ocr_risk


def _geometry() -> Polygon:
    return Polygon(
        points=(
            Point(x=0, y=0),
            Point(x=20, y=0),
            Point(x=20, y=20),
            Point(x=0, y=20),
        )
    )


def _raw_region(
    *,
    text: str = "こんにちは",
    confidence: float = 0.91,
    writing_mode_confidence: float = 0.9,
) -> RawOCRRegion:
    return RawOCRRegion(
        region_id="region-1",
        raw_text=text,
        confidence=confidence,
        geometry=_geometry(),
        writing_mode=WritingMode.vertical_rl,
        writing_mode_confidence=writing_mode_confidence,
        provider_id="primary-ocr",
    )


def _reading_order(
    *,
    confidence: float = 0.94,
    alternatives: tuple[ReadingOrderCandidate, ...] = (),
) -> ReadingOrder:
    return ReadingOrder(
        page_index=0,
        group_index=0,
        item_index=0,
        confidence=confidence,
        alternatives=alternatives,
    )


def test_high_confidence_region_has_low_risk() -> None:
    result = score_ocr_risk(
        _raw_region(),
        reading_order=_reading_order(),
        text_role=TextRole.dialogue,
    )

    assert result.score == pytest.approx(0.0)
    assert result.requires_review is False
    assert result.signals == ()


def test_low_confidence_and_low_writing_mode_confidence_raise_risk() -> None:
    result = score_ocr_risk(
        _raw_region(confidence=0.52, writing_mode_confidence=0.41),
        reading_order=_reading_order(),
        text_role=TextRole.dialogue,
    )

    assert result.score > 0.5
    assert result.requires_review is True
    assert result.signals == ("low_confidence", "low_writing_mode_confidence")


def test_abnormal_characters_reading_order_and_ruby_ambiguity_are_signals() -> None:
    alternative = ReadingOrderCandidate(
        page_index=0,
        group_index=0,
        item_index=1,
        confidence=0.77,
        evidence_summary="near-tie layout candidate",
    )

    result = score_ocr_risk(
        _raw_region(text="こ�んに□ちは"),
        reading_order=_reading_order(confidence=0.78, alternatives=(alternative,)),
        text_role=TextRole.ruby,
        ruby_target_region_id=None,
    )

    assert result.requires_review is True
    assert "abnormal_characters" in result.signals
    assert "reading_order_ambiguity" in result.signals
    assert "ruby_ambiguity" in result.signals


def test_policy_weights_are_configurable() -> None:
    policy = OCRRiskPolicy(
        low_confidence_weight=0.2,
        low_writing_mode_confidence_weight=0.1,
        abnormal_character_weight=0.1,
        reading_order_ambiguity_weight=0.1,
        ruby_ambiguity_weight=0.1,
        review_threshold=0.75,
    )

    result = score_ocr_risk(
        _raw_region(confidence=0.5, writing_mode_confidence=0.5),
        reading_order=_reading_order(confidence=0.7),
        text_role=TextRole.dialogue,
        policy=policy,
    )

    assert result.score == pytest.approx(0.4)
    assert result.requires_review is False
