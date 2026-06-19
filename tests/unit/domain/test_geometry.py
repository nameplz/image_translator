from __future__ import annotations

import pytest
from pydantic import ValidationError

from image_translator.domain.geometry import Point, Polygon, RotatedBoundingBox


def test_polygon_requires_at_least_three_points() -> None:
    with pytest.raises(ValidationError, match="at least 3"):
        Polygon(points=(Point(x=0, y=0), Point(x=1, y=1)))


def test_polygon_requires_positive_area() -> None:
    with pytest.raises(ValidationError, match="positive area"):
        Polygon(
            points=(
                Point(x=0, y=0),
                Point(x=1, y=1),
                Point(x=2, y=2),
            )
        )


def test_polygon_is_immutable_and_tuple_based() -> None:
    polygon = Polygon(
        points=[
            Point(x=0, y=0),
            Point(x=2, y=0),
            Point(x=0, y=2),
        ]
    )

    assert polygon.points == (
        Point(x=0, y=0),
        Point(x=2, y=0),
        Point(x=0, y=2),
    )
    assert polygon.area == pytest.approx(2.0)
    with pytest.raises(ValidationError):
        polygon.points = (Point(x=0, y=0), Point(x=1, y=0), Point(x=0, y=1))


def test_rotated_bounding_box_requires_positive_dimensions() -> None:
    with pytest.raises(ValidationError):
        RotatedBoundingBox(center=Point(x=10, y=20), width=0, height=12, rotation=0)

    with pytest.raises(ValidationError):
        RotatedBoundingBox(center=Point(x=10, y=20), width=12, height=-1, rotation=0)
