from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from image_translator.config.resources import ResourceRootKind, resource_path
from image_translator.persistence.checkpoints import (
    DEFAULT_CHECKPOINT_DATABASE_NAME,
    SQLiteCheckpointStore,
    default_checkpoint_database_path,
)

ROOT = Path(__file__).resolve().parents[2]
SRC_PACKAGE = ROOT / "src" / "image_translator"


def test_py_typed_marker_is_packaged_resource() -> None:
    marker = resource_path("py.typed")

    assert marker.is_file()
    assert marker.name == "py.typed"
    assert marker.read_text(encoding="utf-8").strip() == ""


def test_package_resources_load_when_imported_outside_source_tree(tmp_path: Path) -> None:
    site_root = tmp_path / "site-packages"
    outside_cwd = tmp_path / "outside"
    site_root.mkdir()
    outside_cwd.mkdir()
    shutil.copytree(
        SRC_PACKAGE,
        site_root / "image_translator",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(site_root),
        "PYTHONDONTWRITEBYTECODE": "1",
    }

    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import json; "
                "from image_translator.config.resources import ResourceLocator; "
                "location = ResourceLocator().locate('py.typed'); "
                "print(json.dumps({'path': str(location.path), 'kind': location.kind.value}))"
            ),
        ],
        cwd=outside_cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert Path(payload["path"]) == (site_root / "image_translator" / "py.typed")
    assert payload["kind"] == ResourceRootKind.installed_package.value
    assert not str(payload["path"]).startswith(str(ROOT))


def test_default_checkpoint_path_uses_app_data_override(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app_data = tmp_path / "app-data"
    monkeypatch.setenv("IMAGE_TRANSLATOR_APP_DATA_DIR", str(app_data))

    database_path = default_checkpoint_database_path()
    store = SQLiteCheckpointStore()

    assert database_path == app_data / DEFAULT_CHECKPOINT_DATABASE_NAME
    assert store.database_path == database_path
    assert store.database_path.is_file()
