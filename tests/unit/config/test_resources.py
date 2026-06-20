from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

from image_translator.config.resources import ResourceLocator, ResourceRootKind, resource_path


def test_resource_path_resolves_source_checkout_package_file() -> None:
    path = resource_path("py.typed")

    assert path.is_file()
    assert path.name == "py.typed"


def test_resource_locator_rejects_traversal() -> None:
    locator = ResourceLocator()

    with pytest.raises(ValueError):
        locator.locate("../pyproject.toml")


def test_resource_locator_resolves_imported_package_outside_source_tree(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package_dir = tmp_path / "fake_resources"
    package_dir.mkdir()
    (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (package_dir / "style.json").write_text("{}", encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    importlib.invalidate_caches()
    sys.modules.pop("fake_resources", None)

    location = ResourceLocator(package_name="fake_resources").locate("style.json")

    assert location.path == (package_dir / "style.json").resolve()
    assert location.kind is ResourceRootKind.installed_package
