from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from image_translator.domain._base import DomainModel, NonEmptyStr
from image_translator.domain.ids import RevisionId
from image_translator.domain.quality import ApprovalStatus, QualityIssue

VISUAL_QUALITY_UNCONFIRMED = "visual_quality_unconfirmed"


class ExportMode(StrEnum):
    normal = "normal"
    forced = "forced"


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


__all__ = [
    "VISUAL_QUALITY_UNCONFIRMED",
    "ApprovalStatus",
    "ExportEligibilityDecision",
    "ExportMode",
    "FinalImageResult",
    "ForceApprovalRecord",
]
