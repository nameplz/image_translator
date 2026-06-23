from __future__ import annotations

from collections.abc import Iterable

from image_translator.config.settings import (
    FallbackProviderSettings,
    ProviderEndpointSettings,
    ProviderRole,
    ProviderRuntimeSettings,
)
from image_translator.domain._base import DomainModel
from image_translator.domain.quality import QualitySeverity
from image_translator.providers.base import (
    ImageReference,
    ProviderAdapter,
    ProviderConfigIssue,
    ProviderType,
)

ROLE_PROVIDER_TYPES: dict[ProviderRole, ProviderType] = {
    ProviderRole.translator: ProviderType.translator,
    ProviderRole.reviewer: ProviderType.reviewer,
}


class ProviderRegistryValidation(DomainModel):
    issues: tuple[ProviderConfigIssue, ...] = ()

    @property
    def has_errors(self) -> bool:
        return any(
            issue.severity in {QualitySeverity.error, QualitySeverity.critical}
            for issue in self.issues
        )


class ProviderRegistry:
    def __init__(self, adapters: Iterable[ProviderAdapter]) -> None:
        adapters_by_role: dict[tuple[ProviderType, str], ProviderAdapter] = {}
        for adapter in adapters:
            provider_type = adapter.capabilities().provider_type
            key = (provider_type, adapter.provider_id)
            if key in adapters_by_role:
                raise ValueError(
                    f"duplicate provider adapter for {provider_type.value}:{adapter.provider_id}"
                )
            adapters_by_role[key] = adapter
        self._adapters_by_role = adapters_by_role

    def validate_job_settings(
        self,
        settings: ProviderRuntimeSettings,
        *,
        source_language: str,
        target_language: str,
        translator_visual_references: tuple[ImageReference, ...] = (),
        reviewer_visual_references: tuple[ImageReference, ...] = (),
        visual_mode: bool | None = None,
        image_transmission_consent: bool | None = None,
    ) -> ProviderRegistryValidation:
        effective_visual_mode = _effective_flag(visual_mode, settings.visual_mode_default)
        effective_consent = _effective_flag(
            image_transmission_consent,
            settings.image_transmission_consent_default,
        )
        issues = (
            *self._validate_endpoint(
                role=ProviderRole.translator,
                endpoint=settings.translator,
                source_language=source_language,
                target_language=target_language,
                visual_references=translator_visual_references,
                visual_mode=effective_visual_mode,
                image_transmission_consent=effective_consent,
            ),
            *self._validate_endpoint(
                role=ProviderRole.reviewer,
                endpoint=settings.reviewer,
                source_language=source_language,
                target_language=target_language,
                visual_references=reviewer_visual_references,
                visual_mode=effective_visual_mode,
                image_transmission_consent=effective_consent,
            ),
            *self._validate_fallback_order(
                settings=settings,
                source_language=source_language,
                target_language=target_language,
                visual_mode=effective_visual_mode,
                image_transmission_consent=effective_consent,
            ),
            *self._same_provider_warning(settings),
        )
        return ProviderRegistryValidation(issues=issues)

    def select_fallback(
        self,
        *,
        settings: ProviderRuntimeSettings,
        role: ProviderRole,
        failed_provider_id: str,
        source_language: str,
        target_language: str,
        visual_references: tuple[ImageReference, ...] = (),
        visual_mode: bool | None = None,
        image_transmission_consent: bool | None = None,
    ) -> FallbackProviderSettings | None:
        effective_visual_mode = _effective_flag(visual_mode, settings.visual_mode_default)
        effective_consent = _effective_flag(
            image_transmission_consent,
            settings.image_transmission_consent_default,
        )
        for fallback in settings.fallback_order:
            if fallback.role is not role or fallback.provider_id == failed_provider_id:
                continue
            validation_issues = self._validate_endpoint(
                role=role,
                endpoint=fallback,
                source_language=source_language,
                target_language=target_language,
                visual_references=visual_references,
                visual_mode=effective_visual_mode,
                image_transmission_consent=effective_consent,
            )
            if not _has_error(validation_issues):
                return fallback
        return None

    def _validate_fallback_order(
        self,
        *,
        settings: ProviderRuntimeSettings,
        source_language: str,
        target_language: str,
        visual_mode: bool,
        image_transmission_consent: bool,
    ) -> tuple[ProviderConfigIssue, ...]:
        issues: tuple[ProviderConfigIssue, ...] = ()
        for fallback in settings.fallback_order:
            issues = (
                *issues,
                *self._validate_endpoint(
                    role=fallback.role,
                    endpoint=fallback,
                    source_language=source_language,
                    target_language=target_language,
                    visual_references=(),
                    visual_mode=visual_mode,
                    image_transmission_consent=image_transmission_consent,
                ),
            )
        return issues

    def _validate_endpoint(
        self,
        *,
        role: ProviderRole,
        endpoint: ProviderEndpointSettings,
        source_language: str,
        target_language: str,
        visual_references: tuple[ImageReference, ...],
        visual_mode: bool,
        image_transmission_consent: bool,
    ) -> tuple[ProviderConfigIssue, ...]:
        provider_type = ROLE_PROVIDER_TYPES[role]
        adapter = self._adapter_for(provider_type, endpoint.provider_id)
        if adapter is None:
            return (
                _issue(
                    issue_code="provider_not_registered",
                    message=f"provider {endpoint.provider_id} is not registered for {role.value}",
                ),
            )

        capabilities = adapter.capabilities()
        issues = adapter.validate_config()
        if capabilities.provider_type is not provider_type:
            issues = (
                *issues,
                _issue(
                    issue_code="provider_type_mismatch",
                    message=(
                        f"provider {endpoint.provider_id} has type "
                        f"{capabilities.provider_type.value}, expected {provider_type.value}"
                    ),
                ),
            )
        if not capabilities.supports_language_pair(source_language, target_language):
            issues = (
                *issues,
                _issue(
                    issue_code="unsupported_language_pair",
                    message=(
                        f"provider {endpoint.provider_id} does not support "
                        f"{source_language}->{target_language}"
                    ),
                ),
            )
        if visual_references:
            issues = (
                *issues,
                *_validate_visual_references(
                    provider_id=endpoint.provider_id,
                    visual_references=visual_references,
                    visual_mode=visual_mode,
                    image_transmission_consent=image_transmission_consent,
                    adapter=adapter,
                ),
            )
        return issues

    def _adapter_for(
        self,
        provider_type: ProviderType,
        provider_id: str,
    ) -> ProviderAdapter | None:
        return self._adapters_by_role.get((provider_type, provider_id))

    @staticmethod
    def _same_provider_warning(
        settings: ProviderRuntimeSettings,
    ) -> tuple[ProviderConfigIssue, ...]:
        if settings.translator.provider_id != settings.reviewer.provider_id:
            return ()
        return (
            _issue(
                issue_code="same_translation_reviewer_provider",
                message="translation provider and reviewer provider are the same",
                severity=QualitySeverity.warning,
            ),
        )


def _validate_visual_references(
    *,
    provider_id: str,
    visual_references: tuple[ImageReference, ...],
    visual_mode: bool,
    image_transmission_consent: bool,
    adapter: ProviderAdapter,
) -> tuple[ProviderConfigIssue, ...]:
    if not visual_mode:
        return (
            _issue(
                issue_code="visual_mode_required",
                message="visual references require visual mode",
            ),
        )
    if not image_transmission_consent:
        return (
            _issue(
                issue_code="visual_consent_required",
                message="visual references require image transmission consent",
            ),
        )

    capabilities = adapter.capabilities()
    unsupported = tuple(
        reference
        for reference in visual_references
        if not capabilities.supports_visual_reference(reference)
    )
    if not unsupported:
        return ()
    unsupported_kinds = ", ".join(reference.kind.value for reference in unsupported)
    return (
        _issue(
            issue_code="unsupported_visual_reference",
            message=f"provider {provider_id} does not support visual input: {unsupported_kinds}",
        ),
    )


def _issue(
    *,
    issue_code: str,
    message: str,
    severity: QualitySeverity = QualitySeverity.error,
) -> ProviderConfigIssue:
    return ProviderConfigIssue(
        issue_code=issue_code,
        safe_message=message,
        severity=severity,
    )


def _effective_flag(override: bool | None, default: bool) -> bool:
    return default if override is None else override


def _has_error(issues: tuple[ProviderConfigIssue, ...]) -> bool:
    return any(
        issue.severity in {QualitySeverity.error, QualitySeverity.critical}
        for issue in issues
    )


__all__ = [
    "ProviderRegistry",
    "ProviderRegistryValidation",
    "ROLE_PROVIDER_TYPES",
]
