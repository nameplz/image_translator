from __future__ import annotations

from enum import StrEnum

from image_translator.domain._base import DomainModel, FiniteScore, NonEmptyStr
from image_translator.domain.ids import RegionId


class QualitySeverity(StrEnum):
    info = "info"
    warning = "warning"
    error = "error"
    critical = "critical"


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
