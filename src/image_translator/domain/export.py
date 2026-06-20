from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import Field, model_validator

from image_translator.domain._base import DomainModel, NonEmptyStr, PositiveInt
from image_translator.domain.ids import JobId, RevisionId
from image_translator.domain.quality import ApprovalStatus, QualityIssue

VISUAL_QUALITY_UNCONFIRMED = "visual_quality_unconfirmed"


class ExportFormat(StrEnum):
    png = "png"
    jpeg = "jpeg"
    webp = "webp"


class ExportMode(StrEnum):
    normal = "normal"
    forced = "forced"


class FormatOptions(DomainModel):
    strip_metadata: bool = True
    quality: int | None = Field(default=None, ge=1, le=100)
    lossless: bool = False


class FinalImageResult(DomainModel):
    revision_id: RevisionId
    approval_status: ApprovalStatus
    unresolved_issues: tuple[QualityIssue, ...] = ()
    requires_user_confirmation: tuple[NonEmptyStr, ...] = ()
    visual_quality_checked: bool = False


class ForceApprovalRecord(DomainModel):
    affected_revision: RevisionId
    reason: NonEmptyStr
    created_at: datetime
    unresolved_issue_codes: tuple[NonEmptyStr, ...] = ()
    requires_user_confirmation: tuple[NonEmptyStr, ...] = ()


class ExportEligibilityDecision(DomainModel):
    allowed: bool
    mode: ExportMode
    reason_codes: tuple[NonEmptyStr, ...] = ()
    blocking_issue_codes: tuple[NonEmptyStr, ...] = ()
    warning_issue_codes: tuple[NonEmptyStr, ...] = ()
    requires_user_confirmation: tuple[NonEmptyStr, ...] = ()
    force_approval_record: ForceApprovalRecord | None = None


class ExportRequest(DomainModel):
    input_path: NonEmptyStr
    output_path: NonEmptyStr
    final_image_result: FinalImageResult
    job_id: JobId | None = None
    format: ExportFormat = ExportFormat.png
    format_options: FormatOptions = FormatOptions()
    overwrite_confirmed: bool = False
    confirmed_warning_issue_codes: tuple[NonEmptyStr, ...] = ()
    confirmed_user_confirmation_reasons: tuple[NonEmptyStr, ...] = ()
    force_approval_record: ForceApprovalRecord | None = None

    @model_validator(mode="after")
    def _forced_record_matches_result(self) -> Self:
        if (
            self.force_approval_record is not None
            and self.force_approval_record.affected_revision
            != self.final_image_result.revision_id
        ):
            raise ValueError("force approval record must target the export revision")
        return self


class ExportAuditSummary(DomainModel):
    job_id: JobId | None = None
    revision_id: RevisionId
    output_path: NonEmptyStr
    format: ExportFormat
    format_options: tuple[NonEmptyStr, ...] = ()
    exported_at: datetime
    mode: ExportMode
    blocking_issue_codes: tuple[NonEmptyStr, ...] = ()
    warning_issue_codes: tuple[NonEmptyStr, ...] = ()
    requires_user_confirmation: tuple[NonEmptyStr, ...] = ()
    forced_reason_recorded: bool = False


class ExportResult(DomainModel):
    output_path: NonEmptyStr
    format: ExportFormat
    file_size_bytes: PositiveInt
    audit_summary: ExportAuditSummary
    eligibility_decision: ExportEligibilityDecision


__all__ = [
    "VISUAL_QUALITY_UNCONFIRMED",
    "ApprovalStatus",
    "ExportAuditSummary",
    "ExportEligibilityDecision",
    "ExportFormat",
    "ExportMode",
    "ExportRequest",
    "ExportResult",
    "FinalImageResult",
    "FormatOptions",
    "ForceApprovalRecord",
]
