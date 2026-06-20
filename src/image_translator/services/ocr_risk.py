from __future__ import annotations

from image_translator.domain._base import DomainModel, UnitInterval
from image_translator.domain.ids import RegionId
from image_translator.domain.ocr import RawOCRRegion, ReadingOrder, TextRole


class OCRRiskPolicy(DomainModel):
    min_confidence: UnitInterval = 0.8
    min_writing_mode_confidence: UnitInterval = 0.75
    min_reading_order_confidence: UnitInterval = 0.8
    reading_order_alternative_margin: UnitInterval = 0.15
    review_threshold: UnitInterval = 0.5
    low_confidence_weight: UnitInterval = 0.35
    low_writing_mode_confidence_weight: UnitInterval = 0.25
    abnormal_character_weight: UnitInterval = 0.2
    reading_order_ambiguity_weight: UnitInterval = 0.3
    ruby_ambiguity_weight: UnitInterval = 0.3


class OCRRiskScore(DomainModel):
    region_id: RegionId
    score: UnitInterval
    signals: tuple[str, ...] = ()
    requires_review: bool


def score_ocr_risk(
    raw_region: RawOCRRegion,
    *,
    reading_order: ReadingOrder,
    text_role: TextRole,
    ruby_target_region_id: RegionId | None = None,
    policy: OCRRiskPolicy | None = None,
) -> OCRRiskScore:
    active_policy = policy or OCRRiskPolicy()
    weighted_signals = _weighted_signals(
        raw_region=raw_region,
        reading_order=reading_order,
        text_role=text_role,
        ruby_target_region_id=ruby_target_region_id,
        policy=active_policy,
    )
    score = min(sum(weight for _, weight in weighted_signals), 1.0)
    signals = tuple(signal for signal, _ in weighted_signals)

    return OCRRiskScore(
        region_id=raw_region.region_id,
        score=score,
        signals=signals,
        requires_review=score >= active_policy.review_threshold,
    )


def _weighted_signals(
    *,
    raw_region: RawOCRRegion,
    reading_order: ReadingOrder,
    text_role: TextRole,
    ruby_target_region_id: RegionId | None,
    policy: OCRRiskPolicy,
) -> tuple[tuple[str, float], ...]:
    signals: list[tuple[str, float]] = []

    if raw_region.confidence < policy.min_confidence:
        signals.append(("low_confidence", policy.low_confidence_weight))
    if raw_region.writing_mode_confidence < policy.min_writing_mode_confidence:
        signals.append(
            (
                "low_writing_mode_confidence",
                policy.low_writing_mode_confidence_weight,
            )
        )
    if _has_abnormal_characters(raw_region.raw_text):
        signals.append(("abnormal_characters", policy.abnormal_character_weight))
    if _has_reading_order_ambiguity(reading_order, policy):
        signals.append(
            ("reading_order_ambiguity", policy.reading_order_ambiguity_weight)
        )
    if text_role is TextRole.ruby and ruby_target_region_id is None:
        signals.append(("ruby_ambiguity", policy.ruby_ambiguity_weight))

    return tuple(signals)


def _has_abnormal_characters(text: str) -> bool:
    return any(character in text for character in ("\ufffd", "\u25a1", "\u25a0"))


def _has_reading_order_ambiguity(
    reading_order: ReadingOrder,
    policy: OCRRiskPolicy,
) -> bool:
    if reading_order.confidence < policy.min_reading_order_confidence:
        return True

    return any(
        abs(reading_order.confidence - candidate.confidence)
        <= policy.reading_order_alternative_margin
        for candidate in reading_order.alternatives
    )


__all__ = ["OCRRiskPolicy", "OCRRiskScore", "score_ocr_risk"]
