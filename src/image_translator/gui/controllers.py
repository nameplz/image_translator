from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Protocol

from image_translator.domain.job import JobSnapshot, JobStatus

_ACTIVE_STATUSES = {
    JobStatus.queued,
    JobStatus.preparing,
    JobStatus.ocr_running,
    JobStatus.analyzing_layout,
    JobStatus.translating,
    JobStatus.reviewing_translation,
    JobStatus.waiting_for_user,
    JobStatus.inpainting,
    JobStatus.rendering,
    JobStatus.reviewing_result,
    JobStatus.exporting,
}

_TERMINAL_STATUSES = {
    JobStatus.cancelled,
    JobStatus.complete,
    JobStatus.failed,
    JobStatus.ready_to_export,
}


@dataclass(frozen=True, slots=True)
class MainWindowState:
    input_image_path: str | None = None
    output_path: str | None = None
    latest_snapshot: JobSnapshot | None = None
    cancelling: bool = False

    @property
    def is_running(self) -> bool:
        return self.cancelling or (
            self.latest_snapshot is not None and self.latest_snapshot.status in _ACTIVE_STATUSES
        )

    @property
    def run_enabled(self) -> bool:
        return self.input_image_path is not None and not self.is_running

    @property
    def cancel_enabled(self) -> bool:
        return (
            not self.cancelling
            and self.latest_snapshot is not None
            and self.latest_snapshot.can_cancel
            and self.latest_snapshot.status in _ACTIVE_STATUSES
        )

    @property
    def save_as_enabled(self) -> bool:
        return self.latest_snapshot is not None and self.latest_snapshot.status in {
            JobStatus.ready_to_export,
            JobStatus.complete,
        }

    @property
    def stage_text(self) -> str:
        if self.latest_snapshot is None:
            return "Ready"
        return self.latest_snapshot.stage

    @property
    def status_text(self) -> str:
        if self.cancelling:
            return "Cancelling workflow..."
        if self.latest_snapshot is None:
            return "Open an image to begin."
        return self.latest_snapshot.message

    @property
    def progress_percent(self) -> int:
        if self.latest_snapshot is None:
            return 0
        return round(self.latest_snapshot.progress * 100)

    @property
    def output_path_text(self) -> str:
        if self.output_path is None:
            return "Output path: not selected"
        return f"Output path: {self.output_path}"

    def with_input_image(self, path: str) -> MainWindowState:
        return replace(self, input_image_path=path)

    def with_output_path(self, path: str) -> MainWindowState:
        return replace(self, output_path=path)

    def with_snapshot(self, snapshot: JobSnapshot) -> MainWindowState:
        if _is_stale_snapshot(self.latest_snapshot, snapshot):
            return self
        return replace(
            self,
            latest_snapshot=snapshot,
            cancelling=self.cancelling and snapshot.status not in _TERMINAL_STATUSES,
        )

    def with_cancelling(self) -> MainWindowState:
        return replace(self, cancelling=True)


def _is_stale_snapshot(current: JobSnapshot | None, incoming: JobSnapshot) -> bool:
    if current is None or current.job_id != incoming.job_id:
        return False
    if incoming.status in _TERMINAL_STATUSES:
        return False
    if current.status in _TERMINAL_STATUSES:
        return True
    return incoming.progress < current.progress


@dataclass(frozen=True, slots=True)
class ResumableCheckpointSummary:
    job_id: str
    input_path: str
    stage: str
    updated_at: datetime | None = None


class ResumableCheckpointProvider(Protocol):
    def __call__(self) -> tuple[ResumableCheckpointSummary, ...]: ...


class ResumeListController:
    def __init__(self, provider: ResumableCheckpointProvider | None = None) -> None:
        self._provider = provider or _empty_resumable_checkpoints

    def resumable_checkpoints(self) -> tuple[ResumableCheckpointSummary, ...]:
        return self._provider()


def _empty_resumable_checkpoints() -> tuple[ResumableCheckpointSummary, ...]:
    return ()


__all__ = [
    "MainWindowState",
    "ResumableCheckpointSummary",
    "ResumeListController",
]
