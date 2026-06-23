from __future__ import annotations

from image_translator.providers.retry import (
    ProviderAttemptState,
    ProviderErrorKind,
    ProviderRecoveryAction,
    ProviderRetryPolicy,
    classify_provider_error,
)


def test_classifier_marks_transient_provider_errors_retryable() -> None:
    for kind in (
        ProviderErrorKind.timeout,
        ProviderErrorKind.network,
        ProviderErrorKind.rate_limit,
        ProviderErrorKind.server,
    ):
        classification = classify_provider_error(kind)

        assert classification.retryable is True
        assert classification.fallback_allowed is True


def test_classifier_marks_auth_schema_capability_and_consent_non_retryable() -> None:
    for kind in (
        ProviderErrorKind.auth,
        ProviderErrorKind.capability,
        ProviderErrorKind.schema,
        ProviderErrorKind.consent,
    ):
        classification = classify_provider_error(kind)

        assert classification.retryable is False


def test_retry_policy_retries_transient_errors_until_provider_attempt_limit() -> None:
    policy = ProviderRetryPolicy(max_provider_attempts=3)

    assert (
        policy.decide_provider_recovery(
            classify_provider_error(ProviderErrorKind.network),
            attempts=ProviderAttemptState(provider_retry_attempt=0),
            fallback_configured=False,
        )
        is ProviderRecoveryAction.retry_provider
    )
    assert (
        policy.decide_provider_recovery(
            classify_provider_error(ProviderErrorKind.network),
            attempts=ProviderAttemptState(provider_retry_attempt=3),
            fallback_configured=False,
        )
        is ProviderRecoveryAction.fail
    )


def test_retry_policy_uses_fallback_only_when_user_configured_and_allowed() -> None:
    policy = ProviderRetryPolicy(max_provider_attempts=1)

    assert (
        policy.decide_provider_recovery(
            classify_provider_error(ProviderErrorKind.auth),
            attempts=ProviderAttemptState(provider_retry_attempt=0),
            fallback_configured=True,
        )
        is ProviderRecoveryAction.use_fallback
    )
    assert (
        policy.decide_provider_recovery(
            classify_provider_error(ProviderErrorKind.auth),
            attempts=ProviderAttemptState(provider_retry_attempt=0),
            fallback_configured=False,
        )
        is ProviderRecoveryAction.fail
    )


def test_retry_policy_does_not_fallback_for_missing_visual_consent() -> None:
    policy = ProviderRetryPolicy()

    assert (
        policy.decide_provider_recovery(
            classify_provider_error(ProviderErrorKind.consent),
            attempts=ProviderAttemptState(provider_retry_attempt=0),
            fallback_configured=True,
        )
        is ProviderRecoveryAction.fail
    )


def test_provider_retry_attempt_and_quality_attempt_are_separate_counters() -> None:
    attempts = ProviderAttemptState()

    provider_retry = attempts.next_provider_retry()
    quality_retry = attempts.next_quality_retranslation()

    assert provider_retry.provider_retry_attempt == 1
    assert provider_retry.quality_retranslation_attempt == 0
    assert quality_retry.provider_retry_attempt == 0
    assert quality_retry.quality_retranslation_attempt == 1
