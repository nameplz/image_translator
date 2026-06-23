from __future__ import annotations

import pytest
from pydantic import ValidationError

from image_translator.config.settings import (
    ApiKeyReference,
    ApiKeySource,
    FallbackProviderSettings,
    ProviderEndpointSettings,
    ProviderRetrySettings,
    ProviderRole,
    ProviderRuntimeSettings,
)


def _endpoint(provider_id: str, model_id: str = "mock-model-v1") -> ProviderEndpointSettings:
    return ProviderEndpointSettings(
        provider_id=provider_id,
        model_id=model_id,
        timeout_seconds=12.5,
    )


def test_runtime_settings_store_secret_references_not_secret_values() -> None:
    api_key = ApiKeyReference(
        source=ApiKeySource.environment_variable,
        name="MOCK_PROVIDER_API_KEY",
    )
    settings = ProviderRuntimeSettings(
        translator=_endpoint("mock-translator").model_copy(update={"api_key": api_key}),
        reviewer=_endpoint("mock-reviewer"),
    )

    dumped = str(settings.model_dump())

    assert "MOCK_PROVIDER_API_KEY" in dumped
    assert "dummy-secret-value" not in dumped
    assert api_key.resolve(env={"MOCK_PROVIDER_API_KEY": "dummy-secret-value"}) == (
        "dummy-secret-value"
    )


def test_api_key_reference_can_resolve_ignored_user_config_secret() -> None:
    api_key = ApiKeyReference(
        source=ApiKeySource.user_config,
        name="providers.mock.api_key",
    )

    assert api_key.resolve(user_config_secrets={"providers.mock.api_key": "local-secret"}) == (
        "local-secret"
    )


def test_runtime_settings_defaults_keep_visual_transmission_disabled() -> None:
    settings = ProviderRuntimeSettings(
        translator=_endpoint("mock-translator"),
        reviewer=_endpoint("mock-reviewer"),
    )

    assert settings.visual_mode_default is False
    assert settings.image_transmission_consent_default is False
    assert settings.retry.max_provider_attempts == 3
    assert settings.retry.max_quality_retranslation_attempts == 2


def test_provider_model_id_rejects_unversioned_latest_alias() -> None:
    with pytest.raises(ValidationError, match="latest"):
        _endpoint("mock-translator", model_id="latest")


def test_fallback_order_carries_explicit_role_provider_and_model() -> None:
    fallback = FallbackProviderSettings(
        role=ProviderRole.translator,
        provider_id="backup-translator",
        model_id="backup-model-v1",
        timeout_seconds=30.0,
    )
    settings = ProviderRuntimeSettings(
        translator=_endpoint("mock-translator"),
        reviewer=_endpoint("mock-reviewer"),
        fallback_order=(fallback,),
        retry=ProviderRetrySettings(max_provider_attempts=2),
    )

    assert settings.fallback_order == (fallback,)
    assert settings.retry.max_provider_attempts == 2
