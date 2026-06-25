from __future__ import annotations

import asyncio
from typing import Any, ClassVar, Protocol

from PySide6.QtCore import QThread, Signal

from image_translator.domain.errors import WorkflowCancelled
from image_translator.domain.job import JobDefinition, JobSnapshot, JobStatus


class ImageTranslationUseCase(Protocol):
    async def run(self, job: JobDefinition) -> Any: ...


class ImageTranslationWorker(QThread):
    snapshot_received: ClassVar[Signal] = Signal(object)

    def __init__(self, *, job: JobDefinition, use_case: ImageTranslationUseCase) -> None:
        super().__init__()
        self._job = job
        self._use_case = use_case
        self._loop: asyncio.AbstractEventLoop | None = None
        self._task: asyncio.Task[Any] | None = None
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True
        loop = self._loop
        task = self._task
        if loop is not None and task is not None and loop.is_running():
            loop.call_soon_threadsafe(task.cancel)

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        try:
            asyncio.set_event_loop(loop)
            task = loop.create_task(self._use_case.run(self._job))
            self._task = task
            if self._cancel_requested:
                task.cancel()
            result = loop.run_until_complete(task)
            for snapshot in _snapshots_from_result(self._job, result):
                self.snapshot_received.emit(snapshot)
        except (asyncio.CancelledError, WorkflowCancelled):
            self.snapshot_received.emit(_cancelled_snapshot(self._job))
        except Exception as exc:  # noqa: BLE001 - GUI boundary converts all failures to snapshots.
            self.snapshot_received.emit(_failed_snapshot(self._job, exc))
        finally:
            self._task = None
            self._loop = None
            loop.close()
            asyncio.set_event_loop(None)


def _snapshots_from_result(job: JobDefinition, result: Any) -> tuple[JobSnapshot, ...]:
    single_snapshot = getattr(result, "snapshot", None)
    if single_snapshot is not None:
        return (_coerce_snapshot(single_snapshot),)

    raw_snapshots = getattr(result, "snapshots", ())
    if raw_snapshots:
        return tuple(_coerce_snapshot(snapshot) for snapshot in raw_snapshots)

    return (
        JobSnapshot(
            job_id=job.job_id,
            status=JobStatus.complete,
            progress=1.0,
            stage="complete",
            message="Workflow complete",
            can_cancel=False,
        ),
    )


def _coerce_snapshot(value: object) -> JobSnapshot:
    if isinstance(value, JobSnapshot):
        return value
    return JobSnapshot.model_validate(value)


def _cancelled_snapshot(job: JobDefinition) -> JobSnapshot:
    return JobSnapshot(
        job_id=job.job_id,
        status=JobStatus.cancelled,
        progress=1.0,
        stage="cancelled",
        message="Workflow cancelled",
        can_cancel=False,
    )


def _failed_snapshot(job: JobDefinition, exc: Exception) -> JobSnapshot:
    return JobSnapshot(
        job_id=job.job_id,
        status=JobStatus.failed,
        progress=1.0,
        stage="failed",
        message="Workflow failed",
        can_cancel=False,
        error_summary=type(exc).__name__,
    )


__all__ = [
    "ImageTranslationUseCase",
    "ImageTranslationWorker",
]
