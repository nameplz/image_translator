from __future__ import annotations

from enum import StrEnum

from image_translator.domain._base import DomainModel, FiniteScore, NonEmptyStr
from image_translator.domain.ids import RegionId


class QualitySeverity(StrEnum):
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"


class ApprovalStatus(StrEnum):
    pending = "pending"
    approved_automatic = "approved_automatic"
    approved_user = "approved_user"
    approved_forced = "approved_forced"
    needs_review = "needs_review"
    rejected = "rejected"
    cancelled = "cancelled"


class QualityIssue(DomainModel):
    issue_code: NonEmptyStr
    severity: QualitySeverity
    scope: NonEmptyStr
    region_ids: tuple[RegionId, ...] = ()
    summary: NonEmptyStr
    evidence_references: tuple[NonEmptyStr, ...] = ()
    recommended_action: NonEmptyStr | None = None
    resolved: bool = False


class RubricScores(DomainModel):
    semantic_fidelity: FiniteScore
    completeness: FiniteScore
    naturalness: FiniteScore
    character_voice: FiniteScore
    context_fit: FiniteScore
    terminology: FiniteScore
    text_role_fit: FiniteScore
    renderability: FiniteScore


class RegionReview(DomainModel):
    region_id: RegionId
    rubric_scores: RubricScores
    total_score: FiniteScore
    critical_issues: tuple[QualityIssue, ...] = ()
    non_critical_issues: tuple[QualityIssue, ...] = ()
    evidence_summary: NonEmptyStr
    improvement_instruction: NonEmptyStr | None = None
    decision: NonEmptyStr


class QualityApprovalDecision(DomainModel):
    approved: bool
    status: ApprovalStatus
    weighted_total_score: FiniteScore
    reason_codes: tuple[NonEmptyStr, ...] = ()
    blocking_issue_codes: tuple[NonEmptyStr, ...] = ()
