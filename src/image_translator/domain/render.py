from __future__ import annotations

from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from image_translator.domain._base import (
    DomainModel,
    NonEmptyStr,
    NonNegativeInt,
    PositiveFiniteFloat,
    PositiveInt,
)
from image_translator.domain.geometry import RegionGeometry
from image_translator.domain.ids import RegionId
from image_translator.domain.ocr import WritingMode


class TextAlignment(StrEnum):
    align_left = "left"
    align_center = "center"
    align_right = "right"


class OverflowPolicy(StrEnum):
    shrink_to_fit = "shrink_to_fit"
    fail = "fail"
    clip = "clip"


class RGBColor(DomainModel):
    red: int = Field(ge=0, le=255)
    green: int = Field(ge=0, le=255)
    blue: int = Field(ge=0, le=255)

    @property
    def tuple(self) -> tuple[int, int, int]:
        return (self.red, self.green, self.blue)


class RenderStyle(DomainModel):
    font_family: NonEmptyStr = "DejaVu Sans"
    weight: NonEmptyStr = "regular"
    size: PositiveInt = 18
    color: RGBColor = RGBColor(red=0, green=0, blue=0)
    outline_color: RGBColor | None = RGBColor(red=255, green=255, blue=255)
    outline_width: NonNegativeInt = 0
    alignment: TextAlignment = TextAlignment.align_center
    line_spacing: PositiveFiniteFloat = 1.0
    letter_spacing: int = Field(default=0, ge=0)
    writing_mode: WritingMode = WritingMode.horizontal_ltr


class RenderPlan(DomainModel):
    region_id: RegionId
    geometry: RegionGeometry
    translated_text: str
    style: RenderStyle
    overflow_policy: OverflowPolicy = OverflowPolicy.shrink_to_fit
    source_style_evidence: tuple[NonEmptyStr, ...] = ()


class RenderedRegion(DomainModel):
    region_id: RegionId
    applied_plan: RenderPlan
    output_geometry: RegionGeometry
    validation_issue_codes: tuple[NonEmptyStr, ...] = ()

    @model_validator(mode="after")
    def _region_id_matches_plan(self) -> Self:
        if self.region_id != self.applied_plan.region_id:
            raise ValueError("rendered region ID must match applied plan")
        return self


class RenderedPageReference(DomainModel):
    image_reference: NonEmptyStr | None = None
    rendered_regions: tuple[RenderedRegion, ...]


__all__ = [
    "OverflowPolicy",
    "RGBColor",
    "RenderPlan",
    "RenderStyle",
    "RenderedPageReference",
    "RenderedRegion",
    "TextAlignment",
]
