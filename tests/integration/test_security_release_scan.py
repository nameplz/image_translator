from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]


def test_release_scan_reports_current_committed_release_surfaces_clean() -> None:
    module = _load_scan_module()

    assert module.scan_release_surfaces(ROOT) == ()


def test_release_scan_flags_config_secrets_and_personal_paths(tmp_path: Path) -> None:
    module = _load_scan_module()
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "providers.toml").write_text(
        "\n".join(
            (
                'api_key = "sk-proj-abcdefghijklmnopqrstuvwxyz123456"',
                'recent_file = "/Users/alice/private/page.png"',
            )
        ),
        encoding="utf-8",
    )

    findings = module.scan_release_surfaces(tmp_path)

    assert {finding.kind for finding in findings} == {
        "generic_secret_assignment",
        "openai_secret_key",
        "personal_path",
    }
    assert all("abcdefghijklmnopqrstuvwxyz" not in finding.excerpt for finding in findings)
    assert all("/Users/alice" not in finding.excerpt for finding in findings)


def test_release_scan_ignores_test_code_placeholders_and_binary_outputs(
    tmp_path: Path,
) -> None:
    module = _load_scan_module()
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_placeholder.py").write_text(
        'DUMMY = "sk-test-secret-value"\n',
        encoding="utf-8",
    )
    (tmp_path / "result.png").write_bytes(b"\x89PNG\r\n\x1a\n")

    assert module.scan_release_surfaces(tmp_path) == ()


def _load_scan_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "security_release_scan",
        ROOT / "scripts" / "security_release_scan.py",
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("security_release_scan.py could not be loaded")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module
