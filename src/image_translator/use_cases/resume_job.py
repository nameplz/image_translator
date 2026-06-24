from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, cast

from pydantic import BaseModel

from image_translator.domain.errors import WorkflowCancelled
from image_translator.domain.ids import RevisionId, WorkflowThreadId
from image_translator.domain.job import JobDefinition, JobSnapshot, JobStatus
from image_translator.observability.progress import ProgressMapper
from image_translator.persistence.checkpoints import (
    SQLiteCheckpointStore,
    WorkflowCheckpoint,
    WorkflowGraphKind,
    workflow_thread_id,
)


class ResumableWorkflow(Protocol):
    async def run(self, job: JobDefinition) -> Any: ...


@dataclass(frozen=True, slots=True)
class ResumeJobResult:
    snapshot: JobSnapshot
    workflow_result: Any | None = None
    resumed_from_checkpoint: bool = False


class ResumeJobUseCase:
    def __init__(
        self,
        *,
        checkpoint_store: SQLiteCheckpointStore,
        workflow: ResumableWorkflow,
        graph_kind: WorkflowGraphKind,
        revision_id: RevisionId,
        progress_mapper: ProgressMapper | None = None,
        raise_on_cancel: bool = False,
    ) -> None:
        self._checkpoint_store = checkpoint_store
        self._workflow = workflow
        self._graph_kind = graph_kind
        self._revision_id = revision_id
        self._progress_mapper = progress_mapper or ProgressMapper()
        self._raise_on_cancel = raise_on_cancel

    def thread_id_for(self, job: JobDefinition) -> WorkflowThreadId:
        return workflow_thread_id(
            job_id=job.job_id,
            revision_id=self._revision_id,
            graph_kind=self._graph_kind,
        )

    async def resume(self, job: JobDefinition) -> ResumeJobResult:
        thread_id = self.thread_id_for(job)
        checkpoint = self._checkpoint_store.load(thread_id)
        if checkpoint is not None and _is_terminal_status(checkpoint.status):
            snapshot = _snapshot_from_checkpoint(job, checkpoint)
            return ResumeJobResult(snapshot=snapshot, resumed_from_checkpoint=True)

        try:
            workflow_result = await self._workflow.run(job)
        except asyncio.CancelledError as exc:
            snapshot = self._cancelled_snapshot(job)
            self._checkpoint_store.save(
                WorkflowCheckpoint(
                    thread_id=thread_id,
                    job_id=job.job_id,
                    revision_id=self._revision_id,
                    graph_kind=self._graph_kind,
                    status=JobStatus.cancelled.value,
                    state={"snapshot": snapshot},
                )
            )
            if self._raise_on_cancel:
                raise WorkflowCancelled("workflow cancelled") from exc
            return ResumeJobResult(snapshot=snapshot)

        snapshot = _final_snapshot(job, workflow_result, self._progress_mapper)
        self._checkpoint_store.save(
            WorkflowCheckpoint(
                thread_id=thread_id,
                job_id=job.job_id,
                revision_id=self._revision_id,
                graph_kind=self._graph_kind,
                status=snapshot.status.value,
                state={
                    "snapshot": snapshot,
                    "result_summary": _safe_result_summary(workflow_result),
                },
            )
        )
        for fingerprint in _fingerprints_from_sources(workflow_result, self._workflow):
            self._checkpoint_store.record_provider_call_completed(
                thread_id=thread_id,
                request_fingerprint=fingerprint,
                result_summary={"status": snapshot.status.value},
            )
        return ResumeJobResult(snapshot=snapshot, workflow_result=workflow_result)

    def _cancelled_snapshot(self, job: JobDefinition) -> JobSnapshot:
        return JobSnapshot(
            job_id=job.job_id,
            status=JobStatus.cancelled,
            progress=1.0,
            stage="cancelled",
            message="Workflow cancelled",
            can_cancel=False,
        )


def _is_terminal_status(status: str) -> bool:
    return status in {
        JobStatus.cancelled.value,
        JobStatus.complete.value,
        JobStatus.ready_to_export.value,
        JobStatus.waiting_for_user.value,
        JobStatus.failed.value,
    }


def _snapshot_from_checkpoint(
    job: JobDefinition,
    checkpoint: WorkflowCheckpoint,
) -> JobSnapshot:
    raw_snapshot = checkpoint.state.get("snapshot")
    if isinstance(raw_snapshot, Mapping):
        return JobSnapshot.model_validate(raw_snapshot)
    return JobSnapshot(
        job_id=job.job_id,
        status=JobStatus(checkpoint.status),
        progress=1.0 if checkpoint.status != JobStatus.waiting_for_user.value else 0.0,
        stage=checkpoint.graph_kind.value,
        message=f"Resumed {checkpoint.status} checkpoint",
        can_cancel=checkpoint.status not in {JobStatus.cancelled.value, JobStatus.complete.value},
    )


def _final_snapshot(
    job: JobDefinition,
    workflow_result: Any,
    progress_mapper: ProgressMapper,
) -> JobSnapshot:
    snapshots = getattr(workflow_result, "snapshots", ())
    if snapshots:
        return cast(JobSnapshot, snapshots[-1])
    return progress_mapper.map_update(
        job_id=job.job_id,
        update={"stage": "save", "status": JobStatus.complete.value, "progress": 1.0},
    )


def _safe_result_summary(workflow_result: Any) -> dict[str, Any]:
    final_image_result = getattr(workflow_result, "final_image_result", None)
    export_decision = getattr(workflow_result, "export_decision", None)
    return {
        "result_type": type(workflow_result).__name__,
        "final_approval_status": str(getattr(final_image_result, "approval_status", "")),
        "export_allowed": getattr(export_decision, "allowed", None),
    }


def _fingerprints_from_sources(*sources: Any) -> tuple[str, ...]:
    found: tuple[str, ...] = ()
    seen_object_ids: set[int] = set()
    for source in sources:
        for fingerprint in _iter_fingerprints(source, seen_object_ids):
            if fingerprint not in found:
                found = (*found, fingerprint)
    return found


def _iter_fingerprints(value: Any, seen_object_ids: set[int]) -> tuple[str, ...]:
    if value is None or isinstance(value, str | int | float | bool):
        return ()
    value_id = id(value)
    if value_id in seen_object_ids:
        return ()
    seen_object_ids.add(value_id)
    if isinstance(value, BaseModel):
        return _iter_fingerprints(value.model_dump(mode="json"), seen_object_ids)
    if isinstance(value, Mapping):
        current: tuple[str, ...] = ()
        fingerprint = value.get("request_fingerprint")
        if isinstance(fingerprint, str):
            current = (fingerprint,)
        for child in value.values():
            current = (*current, *_iter_fingerprints(child, set(seen_object_ids)))
        return current
    if isinstance(value, tuple | list):
        sequence_fingerprints: tuple[str, ...] = ()
        for child in value:
            sequence_fingerprints = (
                *sequence_fingerprints,
                *_iter_fingerprints(child, set(seen_object_ids)),
            )
        return sequence_fingerprints
    recorded_requests = getattr(value, "recorded_requests", None)
    if recorded_requests is not None:
        return _iter_fingerprints(recorded_requests, seen_object_ids)
    instance_attributes = getattr(value, "__dict__", None)
    if isinstance(instance_attributes, dict):
        attribute_fingerprints: tuple[str, ...] = ()
        for child in instance_attributes.values():
            attribute_fingerprints = (
                *attribute_fingerprints,
                *_iter_fingerprints(child, set(seen_object_ids)),
            )
        return attribute_fingerprints
    return ()


__all__ = [
    "ResumableWorkflow",
    "ResumeJobResult",
    "ResumeJobUseCase",
]
