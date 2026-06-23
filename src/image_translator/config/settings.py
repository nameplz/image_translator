from __future__ import annotations

import os
from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, TypeAlias

from pydantic import Field, field_validator

from image_translator.domain._base import DomainModel, NonEmptyStr, UnitInterval

TimeoutSeconds: TypeAlias = Annotated[float, Field(gt=0.0, allow_inf_nan=False)]
ProviderRetryAttemptLimit: TypeAlias = Annotated[int, Field(ge=1, le=3)]
QualityRetranslationAttemptLimit: TypeAlias = Annotated[int, Field(ge=0, le=2)]


class ApiKeySource(StrEnum):
    environment_variable = "environment_variable"
    user_config = "user_config"


class ApiKeyReference(DomainModel):
    source: ApiKeySource
    name: NonEmptyStr

    def resolve(
        self,
        *,
        env: Mapping[str, str] | None = None,
        user_config_secrets: Mapping[str, str] | None = None,
    ) -> str | None:
        if self.source is ApiKeySource.environment_variable:
            environment = os.environ if env is None else env
            return environment.get(self.name)
        if user_config_secrets is None:
            return None
        return user_config_secrets.get(self.name)


class ProviderRole(StrEnum):
    translator = "translator"
    reviewer = "reviewer"


class ProviderEndpointSettings(DomainModel):
    provider_id: NonEmptyStr
    model_id: NonEmptyStr
    timeout_seconds: TimeoutSeconds = 30.0
    api_key: ApiKeyReference | None = None

    @field_validator("model_id")
    @classmethod
    def reject_latest_alias(cls, model_id: str) -> str:
        normalized = model_id.strip().lower()
        alias_parts = normalized.replace(":", "/").replace("-", "/").split("/")
        if "latest" in alias_parts:
            raise ValueError("model_id must be a pinned model ID, not a latest alias")
        return model_id


class FallbackProviderSettings(ProviderEndpointSettings):
    role: ProviderRole


class ProviderRetrySettings(DomainModel):
    max_provider_attempts: ProviderRetryAttemptLimit = 3
    max_quality_retranslation_attempts: QualityRetranslationAttemptLimit = 2
    initial_backoff_seconds: TimeoutSeconds = 0.5
    max_backoff_seconds: TimeoutSeconds = 8.0
    jitter_ratio: UnitInterval = 0.2


class ProviderRuntimeSettings(DomainModel):
    translator: ProviderEndpointSettings
    reviewer: ProviderEndpointSettings
    fallback_order: tuple[FallbackProviderSettings, ...] = ()
    retry: ProviderRetrySettings = Field(default_factory=ProviderRetrySettings)
    visual_mode_default: bool = False
    image_transmission_consent_default: bool = False


__all__ = [
    "ApiKeyReference",
    "ApiKeySource",
    "FallbackProviderSettings",
    "ProviderEndpointSettings",
    "ProviderRetrySettings",
    "ProviderRole",
    "ProviderRuntimeSettings",
]
