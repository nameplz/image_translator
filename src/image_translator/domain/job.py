from __future__ import annotations

from enum import StrEnum

from image_translator.domain._base import DomainModel, NonEmptyStr, UnitInterval
from image_translator.domain.ids import JobId, ProjectId


class JobStatus(StrEnum):
    queued = "queued"
    preparing = "preparing"
    ocr_running = "ocr_running"
    analyzing_layout = "analyzing_layout"
    translating = "translating"
    reviewing_translation = "reviewing_translation"
    waiting_for_user = "waiting_for_user"
    inpainting = "inpainting"
    rendering = "rendering"
    reviewing_result = "reviewing_result"
    ready_to_export = "ready_to_export"
    exporting = "exporting"
    complete = "complete"
    failed = "failed"
    cancelled = "cancelled"


class JobDefinition(DomainModel):
    job_id: JobId
    project_id: ProjectId
    input_path: NonEmptyStr
    requested_output_path: NonEmptyStr | None = None
    source_language: NonEmptyStr
    target_language: NonEmptyStr
    provider_selection: tuple[NonEmptyStr, ...] = ()
    fallback_order: tuple[NonEmptyStr, ...] = ()
    visual_mode: bool = False
    image_transmission_consent: bool = False
    processing_profile: NonEmptyStr = "balanced"


class JobSnapshot(DomainModel):
    job_id: JobId
    status: JobStatus
    progress: UnitInterval
    stage: NonEmptyStr
    message: NonEmptyStr
    can_cancel: bool = True
    interrupt_summary: NonEmptyStr | None = None
    error_summary: NonEmptyStr | None = None
