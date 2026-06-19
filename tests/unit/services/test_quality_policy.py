from __future__ import annotations

import pytest

from image_translator.domain.export import ApprovalStatus
from image_translator.domain.quality import (
    QualityIssue,
    QualitySeverity,
    RegionReview,
    RubricScores,
)
from image_translator.services.quality_policy import (
    calculate_weighted_total,
    evaluate_translation_review,
)


def _scores(
    *,
    semantic_fidelity: float = 4.5,
    completeness: float = 4.0,
    naturalness: float = 4.0,
    character_voice: float = 3.5,
    context_fit: float = 4.0,
    terminology: float = 5.0,
    text_role_fit: float = 5.0,
    renderability: float = 5.0,
) -> RubricScores:
    return RubricScores(
        semantic_fidelity=semantic_fidelity,
        completeness=completeness,
        naturalness=naturalness,
        character_voice=character_voice,
        context_fit=context_fit,
        terminology=terminology,
        text_role_fit=text_role_fit,
        renderability=renderability,
    )


def _review(
    scores: RubricScores,
    *,
    critical_issues: tuple[QualityIssue, ...] = (),
    non_critical_issues: tuple[QualityIssue, ...] = (),
) -> RegionReview:
    return RegionReview(
        region_id="region-1",
        rubric_scores=scores,
        total_score=calculate_weighted_total(scores),
        critical_issues=critical_issues,
        non_critical_issues=non_critical_issues,
        evidence_summary="reviewer found the translation acceptable",
        improvement_instruction=None,
        decision="pending",
    )


def _issue(issue_code: str, severity: QualitySeverity) -> QualityIssue:
    return QualityIssue(
        issue_code=issue_code,
        severity=severity,
        scope="translation",
        region_ids=("region-1",),
        summary="quality issue",
        evidence_references=("review-1",),
        recommended_action="review",
        resolved=False,
    )


def test_review_is_automatically_approved_when_all_quality_gates_pass() -> None:
    review = _review(_scores())

    decision = evaluate_translation_review(review)

    assert decision.approved is True
    assert decision.status is ApprovalStatus.approved_automatic
    assert decision.weighted_total_score == pytest.approx(4.2)
    assert decision.reason_codes == ()
    assert decision.blocking_issue_codes == ()


def test_critical_issue_blocks_automatic_approval_regardless_of_score() -> None:
    review = _review(
        _scores(semantic_fidelity=5.0, completeness=5.0, character_voice=5.0),
        critical_issues=(_issue("meaning_reversal", QualitySeverity.critical),),
    )

    decision = evaluate_translation_review(review)

    assert decision.approved is False
    assert decision.status is ApprovalStatus.needs_review
    assert "critical_issue" in decision.reason_codes
    assert decision.blocking_issue_codes == ("meaning_reversal",)


def test_key_rubric_scores_each_have_minimum_thresholds() -> None:
    review = _review(_scores(semantic_fidelity=3.4, completeness=5.0, character_voice=5.0))

    decision = evaluate_translation_review(review)

    assert decision.approved is False
    assert decision.status is ApprovalStatus.needs_review
    assert "semantic_fidelity_below_threshold" in decision.reason_codes
    assert decision.weighted_total_score >= 4.0


def test_unresolved_error_issue_blocks_structural_auto_approval() -> None:
    review = _review(
        _scores(),
        non_critical_issues=(_issue("unknown_region_id", QualitySeverity.error),),
    )

    decision = evaluate_translation_review(review)

    assert decision.approved is False
    assert "unresolved_error_issue" in decision.reason_codes
    assert decision.blocking_issue_codes == ("unknown_region_id",)
