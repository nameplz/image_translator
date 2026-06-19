from __future__ import annotations

import pytest

from image_translator.domain import (
    VISUAL_QUALITY_UNCONFIRMED,
    ApprovalStatus,
    JobDefinition,
    QualityIssue,
    QualitySeverity,
    RegionReview,
    RubricScores,
)
from image_translator.providers import (
    LanguagePair,
    MockOCRAdapter,
    MockReviewAdapter,
    MockTranslatorAdapter,
    ProviderCapabilities,
    ProviderType,
)
from image_translator.use_cases.run_image_translation import RunImageTranslationUseCase


def _job(
    *,
    visual_mode: bool,
    image_transmission_consent: bool,
) -> JobDefinition:
    return JobDefinition(
        job_id="job-1",
        project_id="project-1",
        input_path="/safe/local/input.png",
        requested_output_path="/safe/local/output.png",
        source_language="ja",
        target_language="ko",
        provider_selection=("mock-ocr", "mock-translator", "mock-reviewer"),
        visual_mode=visual_mode,
        image_transmission_consent=image_transmission_consent,
    )


def _visual_reviewer_capabilities() -> ProviderCapabilities:
    return ProviderCapabilities(
        provider_type=ProviderType.reviewer,
        supported_language_pairs=(LanguagePair(source_language="ja", target_language="ko"),),
        supports_batch=True,
        max_batch_size=16,
        supports_structured_output=True,
        supports_visual_input=True,
        supports_full_image=True,
        supports_crop=True,
        is_cloud=False,
    )


def _critical_review(region_id: str) -> RegionReview:
    scores = RubricScores(
        semantic_fidelity=4.5,
        completeness=4.5,
        naturalness=4.5,
        character_voice=4.5,
        context_fit=4.5,
        terminology=4.5,
        text_role_fit=4.5,
        renderability=4.5,
    )
    issue = QualityIssue(
        issue_code="meaning_reversal",
        severity=QualitySeverity.critical,
        scope="translation",
        region_ids=(region_id,),
        summary="mock reviewer found a critical translation error",
        evidence_references=("review-region-2",),
        recommended_action="retry_translation",
    )
    return RegionReview(
        region_id=region_id,
        rubric_scores=scores,
        total_score=4.5,
        critical_issues=(issue,),
        evidence_summary="critical issue evidence",
        improvement_instruction="preserve the source meaning",
        decision="needs_review",
    )


@pytest.mark.asyncio
async def test_mock_core_workflow_approves_all_regions_and_allows_export() -> None:
    reviewer = MockReviewAdapter(
        capabilities=_visual_reviewer_capabilities(),
        visual_mode_enabled=True,
        image_transmission_consent=True,
    )
    use_case = RunImageTranslationUseCase(
        ocr_adapter=MockOCRAdapter(),
        translator_adapter=MockTranslatorAdapter(),
        review_adapter=reviewer,
    )

    result = await use_case.run(_job(visual_mode=True, image_transmission_consent=True))

    assert result.final_image_result.approval_status is ApprovalStatus.approved_automatic
    assert result.export_decision.allowed is True
    assert tuple(
        translation.region_id for translation in result.translation_state.approved_translations
    ) == ("region-1", "region-2")
    assert result.translation_state.unresolved_issues == ()
    assert result.final_image_result.visual_quality_checked is True
    assert tuple(snapshot.progress for snapshot in result.snapshots) == tuple(
        sorted(snapshot.progress for snapshot in result.snapshots)
    )


@pytest.mark.asyncio
async def test_mock_core_workflow_leaves_critical_region_for_review_and_blocks_export() -> None:
    reviewer = MockReviewAdapter(
        configured_reviews=(_critical_review("region-2"),),
        capabilities=_visual_reviewer_capabilities(),
        visual_mode_enabled=True,
        image_transmission_consent=True,
    )
    use_case = RunImageTranslationUseCase(
        ocr_adapter=MockOCRAdapter(),
        translator_adapter=MockTranslatorAdapter(),
        review_adapter=reviewer,
    )

    result = await use_case.run(_job(visual_mode=True, image_transmission_consent=True))

    assert tuple(
        translation.region_id for translation in result.translation_state.approved_translations
    ) == ("region-1",)
    assert tuple(issue.issue_code for issue in result.translation_state.unresolved_issues) == (
        "meaning_reversal",
    )
    assert result.final_image_result.approval_status is ApprovalStatus.needs_review
    assert result.export_decision.allowed is False
    assert result.export_decision.blocking_issue_codes == ("meaning_reversal",)


@pytest.mark.asyncio
async def test_visual_mode_off_does_not_send_image_or_crop_references_to_providers() -> None:
    translator = MockTranslatorAdapter()
    reviewer = MockReviewAdapter(
        capabilities=_visual_reviewer_capabilities(),
        visual_mode_enabled=False,
        image_transmission_consent=False,
    )
    use_case = RunImageTranslationUseCase(
        ocr_adapter=MockOCRAdapter(),
        translator_adapter=translator,
        review_adapter=reviewer,
    )

    result = await use_case.run(_job(visual_mode=False, image_transmission_consent=False))

    assert result.export_decision.allowed is False
    assert VISUAL_QUALITY_UNCONFIRMED in result.export_decision.requires_user_confirmation
    assert all(record.visual_references == () for record in translator.recorded_requests)
    assert all(record.visual_references == () for record in reviewer.recorded_requests)
