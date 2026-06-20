from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from image_translator.domain import ImageFormat, ImageLoadError
from image_translator.services.image_io import load_image_reference, validate_output_path


def _write_image(path: Path, *, image_format: str = "PNG") -> None:
    Image.new("RGB", (8, 6), color=(255, 255, 255)).save(path, format=image_format)


def test_load_image_reference_validates_extension_and_contents(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    _write_image(image_path)

    reference = load_image_reference(image_path)

    assert reference.path == str(image_path.resolve())
    assert reference.format is ImageFormat.png
    assert reference.dimensions.width == 8
    assert reference.dimensions.height == 6
    assert reference.file_size_bytes > 0
    assert reference.metadata_summary == ()


def test_load_image_reference_rejects_unsupported_extension(tmp_path: Path) -> None:
    image_path = tmp_path / "page.gif"
    _write_image(image_path)

    with pytest.raises(ImageLoadError) as exc_info:
        load_image_reference(image_path)

    assert exc_info.value.user_message == "Choose a PNG, JPEG, or WebP image file."
    assert "unsupported image extension" in exc_info.value.diagnostic


def test_load_image_reference_rejects_broken_image(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    image_path.write_text("not an image", encoding="utf-8")

    with pytest.raises(ImageLoadError) as exc_info:
        load_image_reference(image_path)

    assert exc_info.value.user_message == "The selected file is not a readable image."
    assert "image decode failed" in exc_info.value.diagnostic


def test_load_image_reference_rejects_extension_mismatch(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    _write_image(image_path, image_format="JPEG")

    with pytest.raises(ImageLoadError) as exc_info:
        load_image_reference(image_path)

    assert "extension does not match" in exc_info.value.user_message
    assert "actual_format=jpeg" in exc_info.value.diagnostic


def test_load_image_reference_rejects_symlink(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    link_path = tmp_path / "link.png"
    _write_image(image_path)
    link_path.symlink_to(image_path)

    with pytest.raises(ImageLoadError) as exc_info:
        load_image_reference(link_path)

    assert "symlink" in exc_info.value.user_message
    assert "symlink" in exc_info.value.diagnostic


def test_validate_output_path_rejects_input_overwrite(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    _write_image(image_path)

    with pytest.raises(ImageLoadError) as exc_info:
        validate_output_path(image_path, image_path)

    assert "does not overwrite" in exc_info.value.user_message
    assert str(image_path.resolve()) in exc_info.value.diagnostic


def test_validate_output_path_returns_resolved_supported_path(tmp_path: Path) -> None:
    image_path = tmp_path / "page.png"
    output_path = tmp_path / "result.webp"
    _write_image(image_path)

    assert validate_output_path(image_path, output_path) == output_path.resolve()
