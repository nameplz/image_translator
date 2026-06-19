from __future__ import annotations

from dataclasses import dataclass

from image_translator.domain.quality import (
    ApprovalStatus,
    QualityApprovalDecision,
    QualityIssue,
    QualitySeverity,
    RegionReview,
    RubricScores,
)


@dataclass(frozen=True, slots=True)
class RubricWeights:
    semantic_fidelity: float = 0.25
    completeness: float = 0.15
    naturalness: float = 0.15
    character_voice: float = 0.15
    context_fit: float = 0.15
    terminology: float = 0.10
    text_role_fit: float = 0.03
    renderability: float = 0.02

    def __post_init__(self) -> None:
        values = (
            self.semantic_fidelity,
            self.completeness,
            self.naturalness,
            self.character_voice,
            self.context_fit,
            self.terminology,
            self.text_role_fit,
            self.renderability,
        )
        if any(value < 0.0 for value in values):
            raise ValueError("rubric weights must be non-negative")
        if abs(sum(values) - 1.0) > 0.000001:
            raise ValueError("rubric weights must sum to 1.0")


@dataclass(frozen=True, slots=True)
class TranslationQualityPolicy:
    weights: RubricWeights = RubricWeights()
    weighted_total_threshold: float = 4.0
    semantic_fidelity_minimum: float = 3.5
    completeness_minimum: float = 3.5
    character_voice_minimum: float = 3.5


DEFAULT_TRANSLATION_QUALITY_POLICY = TranslationQualityPolicy()


def calculate_weighted_total(
    scores: RubricScores,
    weights: RubricWeights = DEFAULT_TRANSLATION_QUALITY_POLICY.weights,
) -> float:
    weighted_total = (
        (scores.semantic_fidelity * weights.semantic_fidelity)
        + (scores.completeness * weights.completeness)
        + (scores.naturalness * weights.naturalness)
        + (scores.character_voice * weights.character_voice)
        + (scores.context_fit * weights.context_fit)
        + (scores.terminology * weights.terminology)
        + (scores.text_role_fit * weights.text_role_fit)
        + (scores.renderability * weights.renderability)
    )
    return round(weighted_total, 6)


def evaluate_translation_review(
    review: RegionReview,
    policy: TranslationQualityPolicy = DEFAULT_TRANSLATION_QUALITY_POLICY,
) -> QualityApprovalDecision:
    weighted_total = calculate_weighted_total(review.rubric_scores, policy.weights)
    reason_codes: list[str] = []
    blocking_issue_codes: list[str] = []

    for issue in _unresolved_issues(review):
        if issue.severity is QualitySeverity.critical:
            _append_unique(reason_codes, "critical_issue")
            _append_unique(blocking_issue_codes, issue.issue_code)
        elif issue.severity is QualitySeverity.error:
            _append_unique(reason_codes, "unresolved_error_issue")
            _append_unique(blocking_issue_codes, issue.issue_code)

    if weighted_total < policy.weighted_total_threshold:
        _append_unique(reason_codes, "weighted_total_below_threshold")
    if review.rubric_scores.semantic_fidelity < policy.semantic_fidelity_minimum:
        _append_unique(reason_codes, "semantic_fidelity_below_threshold")
    if review.rubric_scores.completeness < policy.completeness_minimum:
        _append_unique(reason_codes, "completeness_below_threshold")
    if review.rubric_scores.character_voice < policy.character_voice_minimum:
        _append_unique(reason_codes, "character_voice_below_threshold")

    approved = not reason_codes
    return QualityApprovalDecision(
        approved=approved,
        status=ApprovalStatus.approved_automatic if approved else ApprovalStatus.needs_review,
        weighted_total_score=weighted_total,
        reason_codes=tuple(reason_codes),
        blocking_issue_codes=tuple(blocking_issue_codes),
    )


def _unresolved_issues(review: RegionReview) -> tuple[QualityIssue, ...]:
    return tuple(
        issue
        for issue in (*review.critical_issues, *review.non_critical_issues)
        if not issue.resolved
    )


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)
