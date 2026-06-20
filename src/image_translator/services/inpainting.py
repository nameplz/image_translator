from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from PIL import Image

from image_translator.domain._base import NonNegativeInt
from image_translator.domain.ids import RegionId
from image_translator.domain.ocr import NormalizedTextRegion


@dataclass(frozen=True, slots=True)
class InpaintingRequest:
    image: Image.Image
    regions: tuple[NormalizedTextRegion, ...]
    padding: NonNegativeInt = 2
    fill_color: tuple[int, int, int] | None = None


@dataclass(frozen=True, slots=True)
class InpaintingResult:
    image: Image.Image
    changed_region_ids: tuple[RegionId, ...]
    backend_id: str


class LocalInpaintingBackend(Protocol):
    backend_id: str

    def remove_text(
        self,
        *,
        image: Image.Image,
        regions: tuple[NormalizedTextRegion, ...],
        padding: int,
        fill_color: tuple[int, int, int] | None,
    ) -> Image.Image: ...


def inpaint_text(
    request: InpaintingRequest,
    *,
    backend: LocalInpaintingBackend,
) -> InpaintingResult:
    output = backend.remove_text(
        image=request.image,
        regions=request.regions,
        padding=int(request.padding),
        fill_color=request.fill_color,
    )
    return InpaintingResult(
        image=output,
        changed_region_ids=tuple(region.region_id for region in request.regions),
        backend_id=backend.backend_id,
    )


__all__ = [
    "InpaintingRequest",
    "InpaintingResult",
    "LocalInpaintingBackend",
    "inpaint_text",
]
