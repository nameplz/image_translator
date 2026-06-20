from __future__ import annotations

from enum import StrEnum

from image_translator.domain._base import DomainModel, NonEmptyStr, PositiveInt


class ImageFormat(StrEnum):
    png = "png"
    jpeg = "jpeg"
    webp = "webp"


class ImageDimensions(DomainModel):
    width: PositiveInt
    height: PositiveInt


class ImageFileReference(DomainModel):
    path: NonEmptyStr
    format: ImageFormat
    dimensions: ImageDimensions
    file_size_bytes: PositiveInt
    metadata_summary: tuple[NonEmptyStr, ...] = ()


__all__ = ["ImageDimensions", "ImageFileReference", "ImageFormat"]
