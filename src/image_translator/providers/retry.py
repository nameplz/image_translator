from __future__ import annotations

from enum import StrEnum
from typing import Annotated, TypeAlias

from pydantic import Field

from image_translator.domain._base import DomainModel, NonEmptyStr, NonNegativeInt

ProviderRetryAttemptLimit: TypeAlias = Annotated[int, Field(ge=1, le=3)]
QualityRetranslationAttemptLimit: TypeAlias = Annotated[int, Field(ge=0, le=2)]


class ProviderErrorKind(StrEnum):
    timeout = "timeout"
    network = "network"
    rate_limit = "rate_limit"
    server = "server"
    auth = "auth"
    capability = "capability"
    schema = "schema"
    consent = "consent"
    unknown = "unknown"


class ProviderRecoveryAction(StrEnum):
    retry_provider = "retry_provider"
    use_fallback = "use_fallback"
    fail = "fail"


class ProviderErrorClassification(DomainModel):
    error_kind: ProviderErrorKind
    retryable: bool
    fallback_allowed: bool
    safe_reason: NonEmptyStr


class ProviderAttemptState(DomainModel):
    provider_retry_attempt: NonNegativeInt = 0
    quality_retranslation_attempt: NonNegativeInt = 0

    def next_provider_retry(self) -> ProviderAttemptState:
        return self.model_copy(
            update={"provider_retry_attempt": self.provider_retry_attempt + 1}
        )

    def next_quality_retranslation(self) -> ProviderAttemptState:
        return self.model_copy(
            update={
                "quality_retranslation_attempt": self.quality_retranslation_attempt + 1,
            }
        )


class ProviderRetryPolicy(DomainModel):
    max_provider_attempts: ProviderRetryAttemptLimit = 3
    max_quality_retranslation_attempts: QualityRetranslationAttemptLimit = 2

    def decide_provider_recovery(
        self,
        classification: ProviderErrorClassification,
        *,
        attempts: ProviderAttemptState,
        fallback_configured: bool,
    ) -> ProviderRecoveryAction:
        if (
            classification.retryable
            and attempts.provider_retry_attempt < self.max_provider_attempts
        ):
            return ProviderRecoveryAction.retry_provider
        if fallback_configured and classification.fallback_allowed:
            return ProviderRecoveryAction.use_fallback
        return ProviderRecoveryAction.fail

    def should_retry_quality(
        self,
        *,
        attempts: ProviderAttemptState,
        actionable_feedback: bool,
    ) -> bool:
        return (
            actionable_feedback
            and attempts.quality_retranslation_attempt
            < self.max_quality_retranslation_attempts
        )


def classify_provider_error(error_kind: ProviderErrorKind) -> ProviderErrorClassification:
    if error_kind in _RETRYABLE_ERROR_KINDS:
        return ProviderErrorClassification(
            error_kind=error_kind,
            retryable=True,
            fallback_allowed=True,
            safe_reason=f"{error_kind.value} may be transient",
        )
    return ProviderErrorClassification(
        error_kind=error_kind,
        retryable=False,
        fallback_allowed=error_kind in _FALLBACK_ALLOWED_NON_RETRYABLE_ERROR_KINDS,
        safe_reason=f"{error_kind.value} is not provider-retryable",
    )


_RETRYABLE_ERROR_KINDS = frozenset(
    {
        ProviderErrorKind.timeout,
        ProviderErrorKind.network,
        ProviderErrorKind.rate_limit,
        ProviderErrorKind.server,
    }
)
_FALLBACK_ALLOWED_NON_RETRYABLE_ERROR_KINDS = frozenset(
    {
        ProviderErrorKind.auth,
        ProviderErrorKind.capability,
        ProviderErrorKind.schema,
    }
)


__all__ = [
    "ProviderAttemptState",
    "ProviderErrorClassification",
    "ProviderErrorKind",
    "ProviderRecoveryAction",
    "ProviderRetryPolicy",
    "classify_provider_error",
]
