from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_dependency_introduction_steps_require_uv_lock_and_contract_updates() -> None:
    image_step = _read("phases/1-image-layout-rendering/step0.md")
    gui_step = _read("phases/3-gui-export-release/step0.md")

    for text in (image_step, gui_step):
        assert "uv.lock" in text
        assert "pyproject.toml" in text
        assert "AGENTS.md" in text
        assert "tests/unit/test_bootstrap_contract.py" in text

    assert "uv add pillow numpy opencv-python-headless" in image_step
    assert "uv add PySide6" in gui_step
    assert "uv add --dev pytest-qt" in gui_step


def test_workflow_checkpoint_state_contract_is_json_serializable() -> None:
    workflow_doc = _read("docs/WORKFLOWS.md")
    checkpoint_step = _read("phases/2-workflow-provider-runtime/step4.md")

    for text in (workflow_doc, checkpoint_step):
        assert "JSON-serializable" in text
        assert "model_dump(mode=\"json\")" in text
        assert "`Path`" in text
        assert "PIL image" in text
        assert "NumPy array" in text
        assert "raw provider payload" in text
        assert "full prompt" in text
        assert "API key" in text
        assert "image/crop bytes" in text


def test_visual_mode_off_export_requires_user_confirmation_contract() -> None:
    export_doc = _read("docs/EXPORT.md")
    quality_doc = _read("docs/QUALITY.md")
    core_step = _read("phases/0-core-vertical-slice/step2.md")
    result_step = _read("phases/2-workflow-provider-runtime/step2.md")

    for text in (export_doc, quality_doc, core_step, result_step):
        assert "requires_user_confirmation" in text
        assert "visual mode off" in text
        assert "ForceApprovalRecord" in text
        assert "사용자 사유" in text or "reason" in text


def test_gui_phase_uses_offscreen_wrapper_gate() -> None:
    testing_doc = _read("docs/TESTING.md")
    agents_doc = _read("AGENTS.md")
    gui_steps = [
        _read(f"phases/3-gui-export-release/step{index}.md") for index in range(5)
    ]

    assert "python3 scripts/run_gui_tests.py" in testing_doc
    assert "python3 scripts/run_gui_tests.py" in agents_doc
    for text in gui_steps:
        assert "python3 scripts/run_gui_tests.py" in text
        assert "QT_QPA_PLATFORM=offscreen" not in text
