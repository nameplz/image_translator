from __future__ import annotations

from image_translator.config.settings import (
    FallbackProviderSettings,
    ProviderEndpointSettings,
    ProviderRole,
    ProviderRuntimeSettings,
)
from image_translator.domain.quality import QualitySeverity
from image_translator.providers.base import (
    ImageReference,
    ImageReferenceKind,
    LanguagePair,
    ProviderCapabilities,
    ProviderType,
)
from image_translator.providers.mock import MockReviewAdapter, MockTranslatorAdapter
from image_translator.providers.registry import ProviderRegistry


class PrimaryTranslator(MockTranslatorAdapter):
    provider_id = "primary-translator"


class BackupTranslator(MockTranslatorAdapter):
    provider_id = "backup-translator"


class LimitedTranslator(MockTranslatorAdapter):
    provider_id = "limited-translator"


class PrimaryReviewer(MockReviewAdapter):
    provider_id = "primary-reviewer"


class SameVendorTranslator(MockTranslatorAdapter):
    provider_id = "same-vendor"


class SameVendorReviewer(MockReviewAdapter):
    provider_id = "same-vendor"


def _endpoint(provider_id: str) -> ProviderEndpointSettings:
    return ProviderEndpointSettings(
        provider_id=provider_id,
        model_id=f"{provider_id}-model-v1",
        timeout_seconds=20.0,
    )


def test_registry_accepts_matching_translator_and_reviewer_settings() -> None:
    registry = ProviderRegistry((PrimaryTranslator(), PrimaryReviewer()))
    settings = ProviderRuntimeSettings(
        translator=_endpoint("primary-translator"),
        reviewer=_endpoint("primary-reviewer"),
    )

    result = registry.validate_job_settings(
        settings,
        source_language="ja",
        target_language="ko",
    )

    assert result.has_errors is False
    assert result.issues == ()


def test_registry_warns_when_translation_and_reviewer_provider_are_same() -> None:
    registry = ProviderRegistry((SameVendorTranslator(), SameVendorReviewer()))
    settings = ProviderRuntimeSettings(
        translator=_endpoint("same-vendor"),
        reviewer=_endpoint("same-vendor"),
    )

    result = registry.validate_job_settings(
        settings,
        source_language="ja",
        target_language="ko",
    )

    assert result.has_errors is False
    assert tuple(issue.issue_code for issue in result.issues) == (
        "same_translation_reviewer_provider",
    )
    assert result.issues[0].severity is QualitySeverity.warning


def test_registry_reports_missing_or_unsupported_provider_capability() -> None:
    limited = LimitedTranslator(
        capabilities=ProviderCapabilities(
            provider_type=ProviderType.translator,
            supported_language_pairs=(
                LanguagePair(source_language="ja", target_language="ko"),
            ),
            supports_batch=True,
            max_batch_size=4,
        )
    )
    registry = ProviderRegistry((limited, PrimaryReviewer()))
    settings = ProviderRuntimeSettings(
        translator=_endpoint("limited-translator"),
        reviewer=_endpoint("primary-reviewer"),
    )

    result = registry.validate_job_settings(
        settings,
        source_language="en",
        target_language="ko",
    )

    assert result.has_errors is True
    assert "unsupported_language_pair" in {issue.issue_code for issue in result.issues}


def test_registry_requires_visual_mode_and_consent_before_visual_provider_use() -> None:
    visual_reference = ImageReference(
        reference_id="crop-1",
        kind=ImageReferenceKind.crop,
    )
    registry = ProviderRegistry((PrimaryTranslator(), PrimaryReviewer()))
    settings = ProviderRuntimeSettings(
        translator=_endpoint("primary-translator"),
        reviewer=_endpoint("primary-reviewer"),
        visual_mode_default=True,
        image_transmission_consent_default=False,
    )

    result = registry.validate_job_settings(
        settings,
        source_language="ja",
        target_language="ko",
        translator_visual_references=(visual_reference,),
    )

    assert result.has_errors is True
    assert "visual_consent_required" in {issue.issue_code for issue in result.issues}


def test_registry_does_not_select_fallback_without_user_configured_order() -> None:
    registry = ProviderRegistry((PrimaryTranslator(), BackupTranslator(), PrimaryReviewer()))
    settings = ProviderRuntimeSettings(
        translator=_endpoint("primary-translator"),
        reviewer=_endpoint("primary-reviewer"),
    )

    assert (
        registry.select_fallback(
            settings=settings,
            role=ProviderRole.translator,
            failed_provider_id="primary-translator",
            source_language="ja",
            target_language="ko",
        )
        is None
    )


def test_registry_selects_first_configured_compatible_fallback() -> None:
    registry = ProviderRegistry((PrimaryTranslator(), BackupTranslator(), PrimaryReviewer()))
    fallback = FallbackProviderSettings(
        role=ProviderRole.translator,
        provider_id="backup-translator",
        model_id="backup-translator-model-v1",
        timeout_seconds=25.0,
    )
    settings = ProviderRuntimeSettings(
        translator=_endpoint("primary-translator"),
        reviewer=_endpoint("primary-reviewer"),
        fallback_order=(fallback,),
    )

    selected = registry.select_fallback(
        settings=settings,
        role=ProviderRole.translator,
        failed_provider_id="primary-translator",
        source_language="ja",
        target_language="ko",
    )

    assert selected == fallback
