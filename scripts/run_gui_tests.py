#!/usr/bin/env python3
"""Run GUI tests through the project offscreen Qt contract."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

GUI_DEPENDENCIES = {"pyside6", "pytest-qt"}


def _dependency_name(value: str) -> str:
    match = re.match(r"\s*([A-Za-z0-9_.-]+)", value)
    return match.group(1).lower().replace("_", "-") if match else ""


def _read_pyproject(root: Path) -> dict[str, Any]:
    path = root / "pyproject.toml"
    try:
        with path.open("rb") as file:
            data = tomllib.load(file)
    except (OSError, tomllib.TOMLDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _pyproject_dependency_names(pyproject: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    project = pyproject.get("project")
    if isinstance(project, dict):
        dependencies = project.get("dependencies")
        if isinstance(dependencies, list):
            names.update(_dependency_name(item) for item in dependencies if isinstance(item, str))

        optional = project.get("optional-dependencies")
        if isinstance(optional, dict):
            for values in optional.values():
                if isinstance(values, list):
                    names.update(_dependency_name(item) for item in values if isinstance(item, str))

    dependency_groups = pyproject.get("dependency-groups")
    if isinstance(dependency_groups, dict):
        for values in dependency_groups.values():
            if isinstance(values, list):
                names.update(_dependency_name(item) for item in values if isinstance(item, str))

    return {name for name in names if name}


def _has_gui_dependencies(root: Path) -> bool:
    return bool(_pyproject_dependency_names(_read_pyproject(root)) & GUI_DEPENDENCIES)


def _has_gui_test_files(root: Path) -> bool:
    gui_tests = root / "tests" / "gui"
    if not gui_tests.exists():
        return False
    return any(
        path.is_file() and path.name.startswith("test_") and path.suffix == ".py"
        for path in gui_tests.rglob("*.py")
    )


def _gui_contract_exists(root: Path) -> bool:
    return _has_gui_dependencies(root) or _has_gui_test_files(root)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Image Translator GUI tests")
    parser.add_argument("--root", default=".", help="Project root to test")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"ERROR: root does not exist: {root}", file=sys.stderr)
        return 1

    if not _gui_contract_exists(root):
        print("GUI test gate skipped: PySide6/pytest-qt and tests/gui are not configured yet.")
        return 0

    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    command = ["uv", "run", "pytest", "-m", "gui"]
    print(f"Running GUI tests with QT_QPA_PLATFORM=offscreen: {' '.join(command)}")
    try:
        result = subprocess.run(command, cwd=root, env=env)
    except FileNotFoundError:
        print("ERROR: uv command not found while running GUI tests.", file=sys.stderr)
        return 1
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
