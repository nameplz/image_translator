from __future__ import annotations

import pytest

from image_translator.domain.errors import ProviderConfigError
from image_translator.domain.geometry import Point, Polygon
from image_translator.domain.ocr import TextRole, WritingMode
from image_translator.domain.quality import RegionReview, RubricScores
from image_translator.domain.translation import TranslationRequest
from image_translator.providers.base import (
    ImageReference,
    ImageReferenceKind,
    LanguagePair,
    ProviderCapabilities,
    ProviderConfigIssue,
    ProviderType,
    TranslationReviewRequest,
    redact_secret_values,
)
from image_translator.providers.mock import (
    MockOCRAdapter,
    MockReviewAdapter,
    MockTranslatorAdapter,
)


def _translation_request(
    region_id: str,
    *,
    source_language: str = "ja",
    target_language: str = "ko",
    image_reference: str | None = None,
) -> TranslationRequest:
    return TranslationRequest(
        region_id=region_id,
        source_text=f"source text for {region_id}",
        source_language=source_language,
        target_language=target_language,
        text_role=TextRole.dialogue,
        writing_mode=WritingMode.vertical_rl,
        image_reference=image_reference,
    )


def _visual_translator_capabilities() -> ProviderCapabilities:
    return ProviderCapabilities(
        provider_type=ProviderType.translator,
        supported_language_pairs=(LanguagePair(source_language="ja", target_language="ko"),),
        supports_batch=True,
        max_batch_size=8,
        supports_structured_output=True,
        supports_visual_input=True,
        supports_crop=True,
        is_cloud=True,
    )


def _review(region_id: str) -> RegionReview:
    scores = RubricScores(
        semantic_fidelity=4.5,
        completeness=4.5,
        naturalness=4.0,
        character_voice=4.0,
        context_fit=4.0,
        terminology=4.0,
        text_role_fit=4.0,
        renderability=4.0,
    )
    return RegionReview(
        region_id=region_id,
        rubric_scores=scores,
        total_score=4.25,
        evidence_summary="configured mock reviewer evidence",
        improvement_instruction="retry only if policy requires it",
        decision="approve",
    )


@pytest.mark.asyncio
async def test_mock_ocr_returns_deterministic_raw_regions() -> None:
    adapter = MockOCRAdapter()
    image_ref = ImageReference(
        reference_id="page-image-1",
        kind=ImageReferenceKind.full_page,
        uri="local://page-image-1",
    )

    first_result = await adapter.detect_regions(image_ref, ("ja",))
    second_result = await adapter.detect_regions(image_ref, ("ja",))

    assert first_result == second_result
    assert len(first_result) == 2
    assert all(region.provider_id == adapter.provider_id for region in first_result)


@pytest.mark.asyncio
async def test_mock_translator_returns_exactly_one_candidate_per_request() -> None:
    adapter = MockTranslatorAdapter()
    requests = (_translation_request("region-1"), _translation_request("region-2"))

    candidates = await adapter.translate_page(requests)

    assert tuple(candidate.region_id for candidate in candidates) == ("region-1", "region-2")
    assert len(candidates) == len(requests)
    assert all(candidate.provider_id == adapter.provider_id for candidate in candidates)


@pytest.mark.asyncio
async def test_mock_translator_rejects_unsupported_language_pair() -> None:
    adapter = MockTranslatorAdapter(
        capabilities=ProviderCapabilities(
            provider_type=ProviderType.translator,
            supported_language_pairs=(
                LanguagePair(source_language="ja", target_language="ko"),
            ),
            supports_batch=True,
            max_batch_size=4,
        )
    )

    with pytest.raises(ProviderConfigError, match="unsupported language pair"):
        await adapter.translate_page(
            (_translation_request("region-1", source_language="en", target_language="ko"),)
        )


@pytest.mark.asyncio
async def test_mock_translator_rejects_batches_over_capability_limit() -> None:
    adapter = MockTranslatorAdapter(
        capabilities=ProviderCapabilities(
            provider_type=ProviderType.translator,
            supported_language_pairs=(
                LanguagePair(source_language="ja", target_language="ko"),
            ),
            supports_batch=True,
            max_batch_size=1,
        )
    )

    with pytest.raises(ProviderConfigError, match="batch size"):
        await adapter.translate_page(
            (_translation_request("region-1"), _translation_request("region-2"))
        )


def test_provider_config_issue_redacts_secret_values() -> None:
    redacted_message = redact_secret_values(
        "MOCK_PROVIDER_API_KEY rejected dummy-secret-value",
        ("dummy-secret-value",),
    )
    issue = ProviderConfigIssue(
        issue_code="invalid_api_key",
        environment_variable="MOCK_PROVIDER_API_KEY",
        safe_message=redacted_message,
    )

    assert "MOCK_PROVIDER_API_KEY" in issue.safe_message
    assert "dummy-secret-value" not in issue.safe_message
    assert "[redacted]" in issue.safe_message


@pytest.mark.asyncio
async def test_visual_reference_is_recorded_only_when_mode_consent_and_capability_allow() -> None:
    adapter = MockTranslatorAdapter(
        capabilities=_visual_translator_capabilities(),
        visual_mode_enabled=True,
        image_transmission_consent=True,
    )

    await adapter.translate_page((_translation_request("region-1", image_reference="crop-1"),))

    assert adapter.recorded_requests[-1].visual_references == (
        ImageReference(reference_id="crop-1", kind=ImageReferenceKind.crop),
    )


@pytest.mark.asyncio
async def test_visual_reference_without_consent_is_rejected_and_not_recorded() -> None:
    adapter = MockTranslatorAdapter(
        capabilities=_visual_translator_capabilities(),
        visual_mode_enabled=True,
        image_transmission_consent=False,
    )

    with pytest.raises(ProviderConfigError, match="image transmission consent"):
        await adapter.translate_page((_translation_request("region-1", image_reference="crop-1"),))

    assert adapter.recorded_requests == ()


@pytest.mark.asyncio
async def test_visual_reference_without_capability_is_rejected_and_not_recorded() -> None:
    adapter = MockTranslatorAdapter(
        visual_mode_enabled=True,
        image_transmission_consent=True,
    )

    with pytest.raises(ProviderConfigError, match="does not support visual input"):
        await adapter.translate_page((_translation_request("region-1", image_reference="crop-1"),))

    assert adapter.recorded_requests == ()


@pytest.mark.asyncio
async def test_mock_reviewer_returns_configured_reviews_without_translation_text() -> None:
    configured_review = _review("region-1")
    adapter = MockReviewAdapter(configured_reviews=(configured_review,))
    request = TranslationReviewRequest(region_ids=("region-1",))

    page_review = await adapter.review_translation(request)

    assert page_review.region_reviews == (configured_review,)
    assert not hasattr(page_review.region_reviews[0], "translated_text")


def test_mock_ocr_accepts_custom_deterministic_regions() -> None:
    geometry = Polygon(
        points=(
            Point(x=0.0, y=0.0),
            Point(x=10.0, y=0.0),
            Point(x=0.0, y=10.0),
        )
    )
    adapter = MockOCRAdapter.with_regions(
        (
            ("custom-region-1", "hello", geometry),
        )
    )

    assert adapter.configured_regions[0].region_id == "custom-region-1"
    assert adapter.configured_regions[0].raw_text == "hello"
