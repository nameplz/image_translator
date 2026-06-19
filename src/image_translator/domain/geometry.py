from __future__ import annotations

from typing import Self, TypeAlias

from pydantic import Field, model_validator

from image_translator.domain._base import DomainModel, PositiveFiniteFloat


class Point(DomainModel):
    x: float = Field(allow_inf_nan=False)
    y: float = Field(allow_inf_nan=False)


class Polygon(DomainModel):
    points: tuple[Point, ...] = Field(min_length=3)

    @property
    def area(self) -> float:
        point_count = len(self.points)
        total = 0.0
        for index, point in enumerate(self.points):
            next_point = self.points[(index + 1) % point_count]
            total += (point.x * next_point.y) - (next_point.x * point.y)
        return abs(total) / 2.0

    @model_validator(mode="after")
    def _require_positive_area(self) -> Self:
        if self.area <= 0.0:
            raise ValueError("polygon must have positive area")
        return self


class RotatedBoundingBox(DomainModel):
    center: Point
    width: PositiveFiniteFloat
    height: PositiveFiniteFloat
    rotation: float = Field(allow_inf_nan=False)


RegionGeometry: TypeAlias = Polygon | RotatedBoundingBox
