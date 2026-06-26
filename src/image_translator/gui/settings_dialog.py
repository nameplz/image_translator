from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

from image_translator.config.settings import (
    ApiKeyReference,
    ApiKeySource,
    ProviderEndpointSettings,
    ProviderRuntimeSettings,
)
from image_translator.domain.quality import QualitySeverity


@dataclass(frozen=True, slots=True)
class SettingsValidationIssue:
    issue_code: str
    safe_message: str
    severity: QualitySeverity = QualitySeverity.error
    environment_variable: str | None = None

    @classmethod
    def from_message(
        cls,
        *,
        issue_code: str,
        message: str,
        secret_values: tuple[str, ...] = (),
        severity: QualitySeverity = QualitySeverity.error,
        environment_variable: str | None = None,
    ) -> SettingsValidationIssue:
        return cls(
            issue_code=issue_code,
            safe_message=_redact_secret_values(message, secret_values),
            severity=severity,
            environment_variable=environment_variable,
        )


@dataclass(frozen=True, slots=True)
class SettingsDialogState:
    provider_settings: ProviderRuntimeSettings
    primary_ocr_provider_id: str
    secondary_ocr_provider_id: str | None = None
    inpainting_backend_order: tuple[str, ...] = ()
    validation_issues: tuple[SettingsValidationIssue, ...] = ()


class SettingsDialog(QDialog):
    def __init__(self, state: SettingsDialogState, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._state = state

        self.primary_ocr_value = QLabel(state.primary_ocr_provider_id, self)
        self.primary_ocr_value.setObjectName("primaryOcrProviderValue")
        self.secondary_ocr_value = QLabel(state.secondary_ocr_provider_id or "none", self)
        self.secondary_ocr_value.setObjectName("secondaryOcrProviderValue")
        self.translation_provider_value = QLabel(
            _format_endpoint(state.provider_settings.translator),
            self,
        )
        self.translation_provider_value.setObjectName("translationProviderValue")
        self.review_provider_value = QLabel(
            _format_endpoint(state.provider_settings.reviewer),
            self,
        )
        self.review_provider_value.setObjectName("reviewProviderValue")
        self.fallback_order_value = QLabel(_format_fallback_order(state.provider_settings), self)
        self.fallback_order_value.setObjectName("fallbackOrderValue")
        self.inpainting_backend_order_value = QLabel(
            ", ".join(state.inpainting_backend_order) or "none",
            self,
        )
        self.inpainting_backend_order_value.setObjectName("inpaintingBackendOrderValue")

        self.visual_mode_checkbox = QCheckBox("Visual mode", self)
        self.visual_mode_checkbox.setObjectName("visualModeCheckbox")
        self.visual_mode_checkbox.setChecked(state.provider_settings.visual_mode_default)
        self.visual_mode_checkbox.toggled.connect(self._refresh_validation)
        self.image_transmission_consent_checkbox = QCheckBox(
            "I consent to image transmission for visual checks",
            self,
        )
        self.image_transmission_consent_checkbox.setObjectName(
            "imageTransmissionConsentCheckbox"
        )
        self.image_transmission_consent_checkbox.setChecked(
            state.provider_settings.image_transmission_consent_default
        )
        self.image_transmission_consent_checkbox.toggled.connect(self._refresh_validation)
        self.visual_transmission_value = QLabel(
            _format_visual_transmission_notice(state.provider_settings),
            self,
        )
        self.visual_transmission_value.setObjectName("visualTransmissionValue")
        self.visual_transmission_value.setWordWrap(True)

        self.same_provider_warning_label = QLabel(self)
        self.same_provider_warning_label.setObjectName("sameProviderWarningLabel")
        self.same_provider_warning_label.setWordWrap(True)
        self.validation_result_value = _read_only_text("configValidationResultValue")

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            self,
        )
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        accept_button = self.button_box.button(QDialogButtonBox.StandardButton.Ok)
        if accept_button is None:
            raise RuntimeError("settings dialog OK button was not created")
        self.accept_button = accept_button
        self.accept_button.setObjectName("settingsAcceptButton")

        self.setWindowTitle("Provider and Privacy Settings")
        layout = QVBoxLayout(self)
        form_container = QWidget(self)
        form = QFormLayout(form_container)
        form.addRow("Primary OCR", self.primary_ocr_value)
        form.addRow("Secondary OCR", self.secondary_ocr_value)
        form.addRow("Translation provider", self.translation_provider_value)
        form.addRow("Review provider", self.review_provider_value)
        form.addRow("Fallback order", self.fallback_order_value)
        form.addRow("Visual mode", self.visual_mode_checkbox)
        form.addRow("Image transmission consent", self.image_transmission_consent_checkbox)
        form.addRow("Visual transmission", self.visual_transmission_value)
        form.addRow("Inpainting backend order", self.inpainting_backend_order_value)
        form.addRow("Config validation", self.validation_result_value)
        layout.addWidget(form_container)
        layout.addWidget(self.same_provider_warning_label)
        layout.addWidget(self.button_box)

        self._refresh_validation()

    def visible_text(self) -> str:
        values = (
            self.primary_ocr_value.text(),
            self.secondary_ocr_value.text(),
            self.translation_provider_value.text(),
            self.review_provider_value.text(),
            self.fallback_order_value.text(),
            self.inpainting_backend_order_value.text(),
            self.visual_transmission_value.text(),
            self.same_provider_warning_label.text(),
            self.validation_result_value.toPlainText(),
        )
        return "\n".join(values)

    def _refresh_validation(self) -> None:
        same_provider_warning = _same_provider_warning(self._state.provider_settings)
        if same_provider_warning:
            self.same_provider_warning_label.setText(same_provider_warning)
            self.same_provider_warning_label.setHidden(False)
        else:
            self.same_provider_warning_label.setText("")
            self.same_provider_warning_label.setHidden(True)

        validation_lines = [
            *_format_validation_issues(self._state.validation_issues),
            *_derived_validation_lines(
                visual_mode=self.visual_mode_checkbox.isChecked(),
                image_transmission_consent=(
                    self.image_transmission_consent_checkbox.isChecked()
                ),
            ),
        ]
        self.validation_result_value.setPlainText(
            "\n".join(validation_lines) if validation_lines else "Configuration valid."
        )
        self.accept_button.setEnabled(
            not (
                self.visual_mode_checkbox.isChecked()
                and not self.image_transmission_consent_checkbox.isChecked()
            )
        )


def default_settings_dialog_state() -> SettingsDialogState:
    provider_settings = ProviderRuntimeSettings(
        translator=ProviderEndpointSettings(
            provider_id="mock-translator",
            model_id="mock-translator-model-v1",
        ),
        reviewer=ProviderEndpointSettings(
            provider_id="mock-reviewer",
            model_id="mock-reviewer-model-v1",
        ),
    )
    return SettingsDialogState(
        provider_settings=provider_settings,
        primary_ocr_provider_id="mock-ocr",
        secondary_ocr_provider_id="none",
        inpainting_backend_order=("local-mask-fill",),
    )


def _read_only_text(object_name: str) -> QPlainTextEdit:
    field = QPlainTextEdit()
    field.setObjectName(object_name)
    field.setReadOnly(True)
    field.setMaximumBlockCount(100)
    field.setFixedHeight(76)
    return field


def _format_endpoint(endpoint: ProviderEndpointSettings) -> str:
    return (
        f"{endpoint.provider_id} | model={endpoint.model_id} | "
        f"timeout={endpoint.timeout_seconds:g}s | {_format_api_key(endpoint.api_key)}"
    )


def _format_api_key(api_key: ApiKeyReference | None) -> str:
    if api_key is None:
        return "API key: not configured"
    if api_key.source is ApiKeySource.environment_variable:
        return f"API key: environment variable {api_key.name}"
    return f"API key: user config reference {api_key.name}"


def _format_fallback_order(settings: ProviderRuntimeSettings) -> str:
    if not settings.fallback_order:
        return "none"
    return ", ".join(
        f"{fallback.role.value}:{fallback.provider_id}@{fallback.model_id}"
        for fallback in settings.fallback_order
    )


def _format_visual_transmission_notice(settings: ProviderRuntimeSettings) -> str:
    providers = ", ".join(
        (
            settings.translator.provider_id,
            settings.reviewer.provider_id,
        )
    )
    return (
        f"Providers: {providers}; targets: full image, crop; purpose: OCR correction, "
        "translation review, final result review."
    )


def _same_provider_warning(settings: ProviderRuntimeSettings) -> str | None:
    if settings.translator.provider_id != settings.reviewer.provider_id:
        return None
    return "Warning: translation and review providers are the same; independence is reduced."


def _format_validation_issues(issues: tuple[SettingsValidationIssue, ...]) -> tuple[str, ...]:
    return tuple(_format_validation_issue(issue) for issue in issues)


def _format_validation_issue(issue: SettingsValidationIssue) -> str:
    env_suffix = (
        f" (environment variable: {issue.environment_variable})"
        if issue.environment_variable is not None
        else ""
    )
    severity = issue.severity.value
    return f"{severity}:{issue.issue_code}: {issue.safe_message}{env_suffix}"


def _redact_secret_values(message: str, secret_values: tuple[str, ...]) -> str:
    redacted = message
    for secret_value in secret_values:
        if secret_value:
            redacted = redacted.replace(secret_value, "[redacted]")
    return redacted


def _derived_validation_lines(
    *,
    visual_mode: bool,
    image_transmission_consent: bool,
) -> tuple[str, ...]:
    if visual_mode and not image_transmission_consent:
        return (
            "error:visual_consent_required: "
            "Visual mode requires image transmission consent before images or crops are sent.",
        )
    return ()


__all__ = [
    "SettingsDialog",
    "SettingsDialogState",
    "SettingsValidationIssue",
    "default_settings_dialog_state",
]
