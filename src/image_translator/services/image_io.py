from __future__ import annotations

from pathlib import Path

from PIL import Image, UnidentifiedImageError

from image_translator.domain.errors import ImageLoadError
from image_translator.domain.image import ImageDimensions, ImageFileReference, ImageFormat

SUPPORTED_IMAGE_EXTENSIONS = frozenset((".png", ".jpg", ".jpeg", ".webp"))
_EXTENSION_FORMATS = {
    ".png": ImageFormat.png,
    ".jpg": ImageFormat.jpeg,
    ".jpeg": ImageFormat.jpeg,
    ".webp": ImageFormat.webp,
}
_PIL_FORMATS = {
    "PNG": ImageFormat.png,
    "JPEG": ImageFormat.jpeg,
    "WEBP": ImageFormat.webp,
}


def load_image_reference(path: str | Path) -> ImageFileReference:
    resolved_path = _resolve_input_path(path)
    extension_format = _format_from_extension(resolved_path)
    actual_format, dimensions = _inspect_image(resolved_path)

    if actual_format is not extension_format:
        raise _image_error(
            "The selected file extension does not match the image contents.",
            f"extension={resolved_path.suffix.lower()} actual_format={actual_format.value}",
        )

    file_size = resolved_path.stat().st_size
    if file_size <= 0:
        raise _image_error("The selected image file is empty.", "empty image file")

    return ImageFileReference(
        path=str(resolved_path),
        format=actual_format,
        dimensions=dimensions,
        file_size_bytes=file_size,
    )


def validate_output_path(input_path: str | Path, output_path: str | Path) -> Path:
    resolved_input = Path(input_path).expanduser().resolve(strict=True)
    output = Path(output_path).expanduser()
    _format_from_extension(output)

    parent = output.parent if output.parent != Path("") else Path.cwd()
    if not parent.exists() or not parent.is_dir():
        raise _image_error(
            "Choose an output folder that exists.",
            f"output parent does not exist or is not a directory: {parent}",
        )

    resolved_output = output.resolve(strict=False)
    if resolved_output == resolved_input:
        raise _image_error(
            "Choose an output path that does not overwrite the input image.",
            f"output path matches input path: {resolved_output}",
        )
    return resolved_output


def _resolve_input_path(path: str | Path) -> Path:
    candidate = Path(path).expanduser()
    try:
        resolved_path = candidate.resolve(strict=True)
    except OSError as exc:
        raise _image_error(
            "The selected image file could not be found.",
            f"input path resolution failed: {exc}",
        ) from exc

    if candidate.is_symlink():
        raise _image_error(
            "Choose the original image file instead of a symlink.",
            f"input path is a symlink: {candidate}",
        )
    if not resolved_path.is_file():
        raise _image_error(
            "Choose a supported image file.",
            f"input path is not a regular file: {resolved_path}",
        )
    return resolved_path


def _format_from_extension(path: Path) -> ImageFormat:
    image_format = _EXTENSION_FORMATS.get(path.suffix.lower())
    if image_format is None:
        raise _image_error(
            "Choose a PNG, JPEG, or WebP image file.",
            f"unsupported image extension: {path.suffix}",
        )
    return image_format


def _inspect_image(path: Path) -> tuple[ImageFormat, ImageDimensions]:
    try:
        with Image.open(path) as image:
            pil_format = image.format
            width, height = image.size
            image.verify()
    except (OSError, UnidentifiedImageError) as exc:
        raise _image_error(
            "The selected file is not a readable image.",
            f"image decode failed: {exc.__class__.__name__}",
        ) from exc

    actual_format = _PIL_FORMATS.get(pil_format or "")
    if actual_format is None:
        raise _image_error(
            "Choose a PNG, JPEG, or WebP image file.",
            f"unsupported detected image format: {pil_format}",
        )
    return actual_format, ImageDimensions(width=width, height=height)


def _image_error(user_message: str, diagnostic: str) -> ImageLoadError:
    return ImageLoadError(user_message=user_message, diagnostic=diagnostic)


__all__ = ["SUPPORTED_IMAGE_EXTENSIONS", "load_image_reference", "validate_output_path"]
