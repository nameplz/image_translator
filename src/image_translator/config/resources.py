from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import StrEnum
from importlib import resources
from pathlib import Path


class ResourceRootKind(StrEnum):
    source_checkout = "source_checkout"
    installed_package = "installed_package"
    pyinstaller = "pyinstaller"


@dataclass(frozen=True, slots=True)
class ResourceLocation:
    path: Path
    kind: ResourceRootKind


@dataclass(frozen=True, slots=True)
class ResourceLocator:
    package_name: str = "image_translator"

    def locate(self, relative_path: str | Path = ".") -> ResourceLocation:
        safe_relative_path = _safe_relative_path(relative_path)
        pyinstaller_base = _pyinstaller_base_path()
        if pyinstaller_base is not None:
            return ResourceLocation(
                path=(pyinstaller_base / safe_relative_path).resolve(),
                kind=ResourceRootKind.pyinstaller,
            )

        package_root = _package_root_path(self.package_name)
        return ResourceLocation(
            path=(package_root / safe_relative_path).resolve(),
            kind=_classify_package_root(package_root),
        )


DEFAULT_RESOURCE_LOCATOR = ResourceLocator()


def resource_path(relative_path: str | Path = ".") -> Path:
    return DEFAULT_RESOURCE_LOCATOR.locate(relative_path).path


def _safe_relative_path(relative_path: str | Path) -> Path:
    path = Path(relative_path)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("resource path must be relative and stay within the resource root")
    return path


def _package_root_path(package_name: str) -> Path:
    package_files = resources.files(package_name)
    return Path(str(package_files)).resolve()


def _classify_package_root(package_root: Path) -> ResourceRootKind:
    if (package_root.parent.parent / "pyproject.toml").is_file():
        return ResourceRootKind.source_checkout
    return ResourceRootKind.installed_package


def _pyinstaller_base_path() -> Path | None:
    base_path = getattr(sys, "_MEIPASS", None)
    if not isinstance(base_path, str):
        return None
    return Path(base_path).resolve()


__all__ = [
    "DEFAULT_RESOURCE_LOCATOR",
    "ResourceLocation",
    "ResourceLocator",
    "ResourceRootKind",
    "resource_path",
]
