from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from image_translator.domain.ids import JobId
from image_translator.domain.job import JobSnapshot, JobStatus


@dataclass(frozen=True, slots=True)
class ProgressRange:
    start: float
    end: float
    status: JobStatus
    label: str

    def progress_at(self, step_progress: float | None) -> float:
        if step_progress is None:
            return self.start
        bounded = max(0.0, min(1.0, step_progress))
        return self.start + (self.end - self.start) * bounded


_RANGES: dict[str, ProgressRange] = {
    "input": ProgressRange(0.00, 0.18, JobStatus.preparing, "Input and OCR"),
    "prepare": ProgressRange(0.00, 0.18, JobStatus.preparing, "Input and OCR"),
    "ocr": ProgressRange(0.00, 0.18, JobStatus.ocr_running, "Input and OCR"),
    "ocr_cross_check": ProgressRange(0.18, 0.28, JobStatus.ocr_running, "OCR cross-check"),
    "page_analysis": ProgressRange(0.28, 0.38, JobStatus.analyzing_layout, "Page analysis"),
    "layout": ProgressRange(0.28, 0.38, JobStatus.analyzing_layout, "Page analysis"),
    "translation": ProgressRange(0.38, 0.58, JobStatus.translating, "Translation"),
    "translate_page": ProgressRange(0.38, 0.58, JobStatus.translating, "Translation"),
    "translation_review": ProgressRange(
        0.58,
        0.70,
        JobStatus.reviewing_translation,
        "Translation quality review",
    ),
    "review_page_translation": ProgressRange(
        0.58,
        0.70,
        JobStatus.reviewing_translation,
        "Translation quality review",
    ),
    "inpainting": ProgressRange(0.70, 0.80, JobStatus.inpainting, "Inpainting"),
    "rendering": ProgressRange(0.80, 0.88, JobStatus.rendering, "Rendering"),
    "result_quality": ProgressRange(
        0.88,
        0.97,
        JobStatus.reviewing_result,
        "Result quality review",
    ),
    "review_final_image": ProgressRange(
        0.88,
        0.97,
        JobStatus.reviewing_result,
        "Result quality review",
    ),
    "export_gate": ProgressRange(0.97, 1.00, JobStatus.ready_to_export, "Save preparation"),
    "save": ProgressRange(0.97, 1.00, JobStatus.ready_to_export, "Save preparation"),
}


@dataclass(slots=True)
class ProgressMapper:
    _last_progress_by_job: dict[JobId, float] = field(default_factory=dict)

    def map_update(self, *, job_id: JobId, update: Mapping[str, Any]) -> JobSnapshot:
        normalized = _normalize_update(update)
        stage = _stage_from_update(normalized)
        progress_range = _RANGES.get(stage, _RANGES["prepare"])
        status = _status_from_update(normalized, default=progress_range.status)
        explicit_progress = _coerce_progress(normalized.get("progress"))
        raw_progress = (
            explicit_progress
            if explicit_progress is not None
            else progress_range.progress_at(_coerce_progress(normalized.get("step_progress")))
        )
        if status is JobStatus.waiting_for_user:
            raw_progress = self._last_progress_by_job.get(job_id, raw_progress)
        progress = max(self._last_progress_by_job.get(job_id, 0.0), raw_progress)
        self._last_progress_by_job[job_id] = progress
        message = _message_from_update(normalized, progress_range)
        return JobSnapshot(
            job_id=job_id,
            status=status,
            progress=round(progress, 6),
            stage=stage,
            message=message,
            can_cancel=status
            not in {JobStatus.cancelled, JobStatus.complete, JobStatus.ready_to_export},
            interrupt_summary=_optional_str(normalized.get("interrupt_summary")),
            error_summary=_optional_str(normalized.get("error_summary")),
        )


def _normalize_update(update: Mapping[str, Any]) -> dict[str, Any]:
    value = update.get("workflow_state", update)
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return dict(value)
    return dict(update)


def _stage_from_update(update: Mapping[str, Any]) -> str:
    raw_stage = update.get("stage") or update.get("node") or update.get("name") or "prepare"
    stage = str(raw_stage)
    status = update.get("status")
    if status in {"context_built", "layout_classified"}:
        return "page_analysis"
    if status in {"translated", "translating"}:
        return "translation"
    if status in {"reviewed", "retrying"}:
        return "translation_review"
    return stage


def _status_from_update(update: Mapping[str, Any], *, default: JobStatus) -> JobStatus:
    raw_status = update.get("status")
    if raw_status is None:
        return default
    if isinstance(raw_status, JobStatus):
        return raw_status
    value = str(raw_status)
    try:
        return JobStatus(value)
    except ValueError:
        pass
    graph_to_job_status = {
        "needs_review": JobStatus.waiting_for_user,
        "approved": default,
        "finalized": default,
        "prepared": JobStatus.preparing,
        "ocr_scored": JobStatus.ocr_running,
        "ocr_resolved": JobStatus.ocr_running,
        "layout_classified": JobStatus.analyzing_layout,
        "context_built": JobStatus.analyzing_layout,
        "translating": JobStatus.translating,
        "translated": JobStatus.translating,
        "structure_validated": default,
        "reviewed": default,
        "retrying": default,
    }
    return graph_to_job_status.get(value, default)


def _coerce_progress(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)


def _message_from_update(
    update: Mapping[str, Any],
    progress_range: ProgressRange,
) -> str:
    message = update.get("message")
    if message is not None:
        return str(message)
    attempt = update.get("attempt")
    if attempt is None:
        return progress_range.label
    return f"{progress_range.label} attempt {attempt}"


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


__all__ = [
    "ProgressMapper",
    "ProgressRange",
]
