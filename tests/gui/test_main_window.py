from __future__ import annotations

from typing import Any

from PySide6.QtWidgets import QTabWidget

from image_translator.domain import JobSnapshot, JobStatus
from image_translator.gui.main_window import MainWindow


def _show_window(qtbot: Any) -> MainWindow:
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    return window


def test_initial_main_window_contract(qtbot: Any) -> None:
    window = _show_window(qtbot)

    assert window.windowTitle() == "Image Translator"
    assert window.open_action.text() == "Open"
    assert window.run_action.text() == "Run"
    assert window.cancel_action.text() == "Cancel"
    assert window.output_path_action.text() == "Output Path"
    assert window.save_as_action.text() == "Save As"
    assert window.settings_action.text() == "Settings"

    assert window.run_action.isEnabled() is False
    assert window.cancel_action.isEnabled() is False
    assert window.save_as_action.isEnabled() is False
    assert window.output_path_label.text() == "Output path: not selected"
    assert window.stage_label.text() == "Stage: Ready"
    assert window.progress_bar.value() == 0
    assert window.status_label.text() == "Open an image to begin."


def test_main_window_exposes_required_panels(qtbot: Any) -> None:
    window = _show_window(qtbot)

    comparison_tabs = window.findChild(QTabWidget, "imageComparisonTabs")
    review_tabs = window.findChild(QTabWidget, "reviewTabs")

    assert comparison_tabs is not None
    assert [comparison_tabs.tabText(index) for index in range(comparison_tabs.count())] == [
        "Original",
        "OCR Overlay",
        "Inpainted",
        "Result",
    ]
    assert review_tabs is not None
    assert [review_tabs.tabText(index) for index in range(review_tabs.count())] == [
        "Region Inspector",
        "Review Queue",
        "Revision Plan",
    ]


def test_run_enables_after_input_selection_without_save_enabled(qtbot: Any) -> None:
    window = _show_window(qtbot)

    window.set_input_image("/tmp/page.png")

    assert window.run_action.isEnabled() is True
    assert window.save_as_action.isEnabled() is False
    assert window.output_path_label.text() == "Output path: not selected"


def test_progress_snapshot_updates_bottom_bar_and_cancel(qtbot: Any) -> None:
    window = _show_window(qtbot)
    snapshot = JobSnapshot(
        job_id="job-1",
        status=JobStatus.translating,
        progress=0.42,
        stage="Translation",
        message="Checking translation quality",
        can_cancel=True,
    )

    window.display_snapshot(snapshot)

    assert window.stage_label.text() == "Stage: Translation"
    assert window.progress_bar.value() == 42
    assert window.status_label.text() == "Checking translation quality"
    assert window.cancel_action.isEnabled() is True
    assert window.run_action.isEnabled() is False
