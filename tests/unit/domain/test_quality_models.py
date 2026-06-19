from __future__ import annotations

import pytest
from pydantic import ValidationError

from image_translator.domain.quality import (
    QualityIssue,
    QualitySeverity,
    RegionReview,
    RubricScores,
)


def test_rubric_scores_must_be_between_one_and_five() -> None:
    with pytest.raises(ValidationError):
        RubricScores(
            semantic_fidelity=0.99,
            completeness=5.0,
            naturalness=5.0,
            character_voice=5.0,
            context_fit=5.0,
            terminology=5.0,
            text_role_fit=5.0,
            renderability=5.0,
        )

    with pytest.raises(ValidationError):
        RubricScores(
            semantic_fidelity=5.0,
            completeness=5.01,
            naturalness=5.0,
            character_voice=5.0,
            context_fit=5.0,
            terminology=5.0,
            text_role_fit=5.0,
            renderability=5.0,
        )


def test_quality_issue_uses_tuple_region_ids_and_is_immutable() -> None:
    issue = QualityIssue(
        issue_code="meaning_reversal",
        severity=QualitySeverity.critical,
        scope="translation",
        region_ids=["region-1", "region-2"],
        summary="Meaning was reversed",
        evidence_references=["review-1"],
        recommended_action="retry_translation",
    )

    assert issue.region_ids == ("region-1", "region-2")
    assert issue.evidence_references == ("review-1",)
    with pytest.raises(ValidationError):
        issue.resolved = True


def test_region_review_total_score_uses_rubric_score_bounds() -> None:
    scores = RubricScores(
        semantic_fidelity=4.0,
        completeness=4.0,
        naturalness=4.0,
        character_voice=4.0,
        context_fit=4.0,
        terminology=4.0,
        text_role_fit=4.0,
        renderability=4.0,
    )

    with pytest.raises(ValidationError):
        RegionReview(
            region_id="region-1",
            rubric_scores=scores,
            total_score=5.1,
            evidence_summary="score out of range",
            improvement_instruction=None,
            decision="needs_review",
        )
