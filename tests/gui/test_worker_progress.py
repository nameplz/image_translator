from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass, field
from typing import Any

from image_translator.domain import JobDefinition, JobSnapshot, JobStatus
from image_translator.gui.main_window import MainWindow


@dataclass(frozen=True, slots=True)
class _FakeResult:
    snapshots: tuple[JobSnapshot, ...]


@dataclass(slots=True)
class _SnapshotUseCase:
    snapshots: tuple[JobSnapshot, ...]
    started_jobs: list[JobDefinition] = field(default_factory=list)

    async def run(self, job: JobDefinition) -> _FakeResult:
        self.started_jobs.append(job)
        await asyncio.sleep(0)
        return _FakeResult(snapshots=self.snapshots)


@dataclass(slots=True)
class _BlockingUseCase:
    started: threading.Event = field(default_factory=threading.Event)
    cancelled: threading.Event = field(default_factory=threading.Event)

    async def run(self, job: JobDefinition) -> _FakeResult:
        self.started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return _FakeResult(snapshots=())


def _show_window(qtbot: Any, use_case: object) -> MainWindow:
    window = MainWindow(use_case=use_case)
    qtbot.addWidget(window)
    window.show()
    return window


def _snapshot(
    *,
    job_id: str = "job-1",
    status: JobStatus,
    progress: float,
    stage: str,
    message: str,
    can_cancel: bool = True,
) -> JobSnapshot:
    return JobSnapshot(
        job_id=job_id,
        status=status,
        progress=progress,
        stage=stage,
        message=message,
        can_cancel=can_cancel,
    )


def test_run_click_builds_valid_job_and_applies_worker_snapshots(qtbot: Any) -> None:
    use_case = _SnapshotUseCase(
        snapshots=(
            _snapshot(
                status=JobStatus.translating,
                progress=0.42,
                stage="translation",
                message="Translating page",
            ),
            _snapshot(
                status=JobStatus.ready_to_export,
                progress=1.0,
                stage="export_gate",
                message="Ready to save",
                can_cancel=False,
            ),
        )
    )
    window = _show_window(qtbot, use_case)
    window.set_input_image("/tmp/source.png")
    window.set_output_path("/tmp/result.png")

    window.run_action.trigger()

    qtbot.waitUntil(lambda: len(use_case.started_jobs) == 1)
    qtbot.waitUntil(lambda: window.status_label.text() == "Ready to save")

    job = use_case.started_jobs[0]
    assert job.input_path == "/tmp/source.png"
    assert job.requested_output_path == "/tmp/result.png"
    assert job.source_language == "ja"
    assert job.target_language == "ko"
    assert window.progress_bar.value() == 100
    assert window.stage_label.text() == "Stage: export_gate"
    assert window.cancel_action.isEnabled() is False
    assert window.save_as_action.isEnabled() is True


def test_progress_updates_are_monotonic_and_stale_snapshots_are_discarded(qtbot: Any) -> None:
    window = _show_window(qtbot, _SnapshotUseCase(snapshots=()))
    current = _snapshot(
        status=JobStatus.translating,
        progress=0.64,
        stage="translation",
        message="Translating page",
    )
    stale = _snapshot(
        status=JobStatus.ocr_running,
        progress=0.18,
        stage="ocr",
        message="Late OCR update",
    )

    window.display_snapshot(current)
    window.display_snapshot(stale)

    assert window.progress_bar.value() == 64
    assert window.stage_label.text() == "Stage: translation"
    assert window.status_label.text() == "Translating page"


def test_cancel_click_marks_cancelling_and_finishes_as_cancelled(qtbot: Any) -> None:
    use_case = _BlockingUseCase()
    window = _show_window(qtbot, use_case)
    window.set_input_image("/tmp/source.png")

    window.run_action.trigger()
    qtbot.waitUntil(use_case.started.is_set)

    assert window.cancel_action.isEnabled() is True

    window.cancel_action.trigger()

    assert window.cancel_action.isEnabled() is False
    assert window.status_label.text() == "Cancelling workflow..."

    qtbot.waitUntil(use_case.cancelled.is_set)
    qtbot.waitUntil(lambda: window.status_label.text() == "Workflow cancelled")

    assert window.stage_label.text() == "Stage: cancelled"
    assert window.cancel_action.isEnabled() is False
    assert "failed" not in window.status_label.text().lower()
