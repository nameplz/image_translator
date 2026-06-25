from __future__ import annotations

import importlib
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_project_metadata_declares_uv_python_package() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    project = pyproject["project"]
    assert project["name"] == "image-translator"
    assert project["requires-python"] == ">=3.11"
    assert "pydantic>=2" in project["dependencies"]
    assert "langgraph" in project["dependencies"]
    assert "pillow>=12.2.0" in project["dependencies"]
    assert "numpy>=2.4.6" in project["dependencies"]
    assert "opencv-python-headless>=4.13.0.92" in project["dependencies"]
    assert "pyside6>=6.11.1" in project["dependencies"]

    dev_dependencies = pyproject["dependency-groups"]["dev"]
    for dependency in (
        "pytest",
        "pytest-asyncio",
        "pytest-cov",
        "ruff",
        "mypy",
        "pytest-qt>=4.5.0",
    ):
        assert dependency in dev_dependencies


def test_package_import_and_type_marker() -> None:
    package = importlib.import_module("image_translator")

    assert package.__version__ == "0.1.0"
    assert (ROOT / "src" / "image_translator" / "py.typed").is_file()


def test_harness_validation_uses_strict_uv_gate() -> None:
    config = json.loads((ROOT / ".harness" / "validation.json").read_text(encoding="utf-8"))

    assert config["language"] == "python"
    assert config["stack"] == "python"
    assert config["package_manager"] == "uv"
    assert [item["command"] for item in config["commands"]] == [
        ["uv", "run", "pytest", "-q"],
        [
            "uv",
            "run",
            "pytest",
            "--cov=src",
            "--cov-report=term-missing",
            "--cov-fail-under=80",
        ],
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "mypy", "src"],
        ["python3", "scripts/run_gui_tests.py"],
    ]
