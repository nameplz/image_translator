from __future__ import annotations

from enum import StrEnum

from image_translator.domain._base import (
    DomainModel,
    NonEmptyStr,
    NonNegativeInt,
    UnitInterval,
)
from image_translator.domain.geometry import RegionGeometry
from image_translator.domain.ids import ProviderRequestId, RegionId


class WritingMode(StrEnum):
    horizontal_ltr = "horizontal_ltr"
    horizontal_rtl = "horizontal_rtl"
    vertical_rl = "vertical_rl"
    vertical_lr = "vertical_lr"
    rotated = "rotated"
    unknown = "unknown"


class TextOrientation(StrEnum):
    upright = "upright"
    rotated_90_cw = "rotated_90_cw"
    rotated_90_ccw = "rotated_90_ccw"
    arbitrary_angle = "arbitrary_angle"


class TextRole(StrEnum):
    dialogue = "dialogue"
    narration = "narration"
    sound_effect = "sound_effect"
    sign = "sign"
    decorative = "decorative"
    ruby = "ruby"
    unknown = "unknown"


class ReadingOrderCandidate(DomainModel):
    page_index: NonNegativeInt
    group_index: NonNegativeInt
    item_index: NonNegativeInt
    confidence: UnitInterval
    evidence_summary: NonEmptyStr | None = None


class ReadingOrder(DomainModel):
    page_index: NonNegativeInt
    group_index: NonNegativeInt
    item_index: NonNegativeInt
    confidence: UnitInterval
    alternatives: tuple[ReadingOrderCandidate, ...] = ()


class RawOCRRegion(DomainModel):
    region_id: RegionId
    raw_text: str
    confidence: UnitInterval
    geometry: RegionGeometry
    writing_mode: WritingMode = WritingMode.unknown
    writing_mode_confidence: UnitInterval = 0.0
    provider_id: NonEmptyStr
    metadata_summary: tuple[NonEmptyStr, ...] = ()


class OCRCandidate(DomainModel):
    region_id: RegionId
    text: str
    language: NonEmptyStr
    provider_id: NonEmptyStr
    confidence: UnitInterval
    evidence_summary: NonEmptyStr
    request_id: ProviderRequestId | None = None


class NormalizedTextRegion(DomainModel):
    region_id: RegionId
    source_text: str
    geometry: RegionGeometry
    source_language: NonEmptyStr
    writing_mode: WritingMode
    orientation: TextOrientation
    reading_order: ReadingOrder
    text_role: TextRole
    ruby_target_region_id: RegionId | None = None
    ocr_provenance: tuple[ProviderRequestId, ...] = ()
