from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from image_translator.config.settings import (
    ApiKeyReference,
    ApiKeySource,
    ProviderEndpointSettings,
    ProviderRuntimeSettings,
)
from image_translator.domain import (
    ApprovalStatus,
    FinalImageResult,
    JobSnapshot,
    JobStatus,
    QualityIssue,
    QualitySeverity,
)
from image_translator.gui.export_controller import ExportController, ExportControllerError
from image_translator.gui.main_window import MainWindow
from image_translator.gui.settings_dialog import (
    SettingsDialog,
    SettingsDialogState,
    SettingsValidationIssue,
)


def test_settings_dialog_gates_visual_mode_on_image_transmission_consent(qtbot: Any) -> None:
    dialog = SettingsDialog(
        _settings_state(
            visual_mode=True,
            image_transmission_consent=False,
        )
    )
    qtbot.addWidget(dialog)

    assert dialog.visual_mode_checkbox.isChecked() is True
    assert dialog.image_transmission_consent_checkbox.isChecked() is False
    assert dialog.accept_button.isEnabled() is False
    assert "full image" in dialog.visual_transmission_value.text()
    assert "crop" in dialog.visual_transmission_value.text()
    assert "Visual mode requires image transmission consent" in (
        dialog.validation_result_value.toPlainText()
    )


def test_settings_dialog_redacts_secret_values(qtbot: Any) -> None:
    secret_value = "sk-test-secret-value"
    api_key = ApiKeyReference(
        source=ApiKeySource.environment_variable,
        name="OPENAI_API_KEY",
    )
    issue = SettingsValidationIssue.from_message(
        issue_code="missing_key",
        message=f"provider rejected key {secret_value}",
        secret_values=(secret_value,),
        environment_variable="OPENAI_API_KEY",
    )
    dialog = SettingsDialog(
        _settings_state(
            translator_api_key=api_key,
            validation_issues=(issue,),
        )
    )
    qtbot.addWidget(dialog)

    visible_text = dialog.visible_text()

    assert secret_value not in visible_text
    assert "OPENAI_API_KEY" in visible_text
    assert "[redacted]" in visible_text


def test_settings_dialog_warns_when_translation_and_review_provider_match(qtbot: Any) -> None:
    dialog = SettingsDialog(
        _settings_state(
            translator_provider_id="same-vendor",
            reviewer_provider_id="same-vendor",
        )
    )
    qtbot.addWidget(dialog)

    assert dialog.same_provider_warning_label.isHidden() is False
    assert "same" in dialog.same_provider_warning_label.text().lower()
    assert "independence" in dialog.same_provider_warning_label.text().lower()


def test_main_window_disables_save_as_when_export_gate_has_blocking_issue(qtbot: Any) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.display_snapshot(
        JobSnapshot(
            job_id="job-1",
            status=JobStatus.ready_to_export,
            progress=1.0,
            stage="export_gate",
            message="Ready to save",
            can_cancel=False,
        )
    )

    window.set_final_image_result(
        FinalImageResult(
            revision_id="revision-1",
            approval_status=ApprovalStatus.approved_automatic,
            unresolved_issues=(_issue("source_remnant", QualitySeverity.critical),),
            visual_quality_checked=True,
        )
    )

    assert window.save_as_action.isEnabled() is False
    assert "Save blocked" in window.status_label.text()
    assert "source_remnant" in window.status_label.text()


def test_review_before_save_mode_controls_run_without_output_path(qtbot: Any) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_input_image("/tmp/source.png")

    assert window.run_action.isEnabled() is True

    window.set_review_before_save_mode(False)

    assert window.run_action.isEnabled() is False

    window.set_output_path("/tmp/result.png")

    assert window.run_action.isEnabled() is True


def test_main_window_does_not_create_output_file_before_quality_gate(
    qtbot: Any,
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "source.png"
    output_path = tmp_path / "result.png"
    input_path.write_bytes(b"source")
    window = MainWindow()
    qtbot.addWidget(window)
    window.set_input_image(str(input_path))
    window.set_output_path(str(output_path))
    window.display_snapshot(
        JobSnapshot(
            job_id="job-1",
            status=JobStatus.ready_to_export,
            progress=1.0,
            stage="export_gate",
            message="Ready to save",
            can_cancel=False,
        )
    )

    window.set_final_image_result(
        FinalImageResult(
            revision_id="revision-1",
            approval_status=ApprovalStatus.approved_automatic,
            unresolved_issues=(_issue("source_remnant", QualitySeverity.critical),),
            visual_quality_checked=True,
        )
    )
    window.save_as_action.trigger()

    assert window.save_as_action.isEnabled() is False
    assert output_path.exists() is False
    assert "Save blocked" in window.status_label.text()


def test_export_controller_requires_force_reason_for_blocked_export(tmp_path: Path) -> None:
    input_path = tmp_path / "source.png"
    output_path = tmp_path / "result.png"
    input_path.write_bytes(b"source")
    controller = ExportController(
        overwrite_confirmation=lambda _path: True,
        force_reason_request=lambda _decision: " ",
        clock=lambda: datetime(2026, 6, 26, 12, 0, tzinfo=UTC),
    )
    controller.set_input_path(str(input_path))
    controller.set_output_path(str(output_path))
    controller.set_final_image_result(
        FinalImageResult(
            revision_id="revision-1",
            approval_status=ApprovalStatus.approved_automatic,
            unresolved_issues=(_issue("source_remnant", QualitySeverity.critical),),
            visual_quality_checked=True,
        )
    )

    with pytest.raises(ExportControllerError, match="Forced export requires"):
        controller.prepare_export_request(force=True)


def test_export_controller_records_forced_export_confirmation(tmp_path: Path) -> None:
    input_path = tmp_path / "source.png"
    output_path = tmp_path / "result.png"
    input_path.write_bytes(b"source")
    seen_reason_codes: list[tuple[str, ...]] = []

    def force_reason(decision: object) -> str:
        seen_reason_codes.append(tuple(getattr(decision, "reason_codes")))
        return "draft export accepted after checking remaining source remnants"

    controller = ExportController(
        overwrite_confirmation=lambda _path: True,
        force_reason_request=force_reason,
        clock=lambda: datetime(2026, 6, 26, 12, 0, tzinfo=UTC),
    )
    controller.set_input_path(str(input_path))
    controller.set_output_path(str(output_path))
    controller.set_final_image_result(
        FinalImageResult(
            revision_id="revision-1",
            approval_status=ApprovalStatus.approved_automatic,
            unresolved_issues=(_issue("source_remnant", QualitySeverity.critical),),
            visual_quality_checked=True,
        )
    )

    request = controller.prepare_export_request(force=True)

    assert seen_reason_codes == [("blocking_quality_issue",)]
    assert request.force_approval_record is not None
    assert request.force_approval_record.reason == (
        "draft export accepted after checking remaining source remnants"
    )
    assert request.force_approval_record.unresolved_issue_codes == ("source_remnant",)


def test_export_controller_confirms_overwrite_for_save_as_request(tmp_path: Path) -> None:
    input_path = tmp_path / "source.png"
    output_path = tmp_path / "result.png"
    input_path.write_bytes(b"source")
    output_path.write_bytes(b"existing")
    confirmed_paths: list[Path] = []

    def confirm_overwrite(path: Path) -> bool:
        confirmed_paths.append(path)
        return True

    controller = ExportController(overwrite_confirmation=confirm_overwrite)
    controller.set_input_path(str(input_path))
    controller.set_final_image_result(_approved_result())

    request = controller.prepare_export_request(output_path=str(output_path))

    assert confirmed_paths == [output_path]
    assert request.output_path == str(output_path)
    assert request.overwrite_confirmed is True


def test_export_controller_blocks_normal_save_until_required_confirmation(
    tmp_path: Path,
) -> None:
    input_path = tmp_path / "source.png"
    output_path = tmp_path / "result.png"
    input_path.write_bytes(b"source")
    controller = ExportController()
    controller.set_input_path(str(input_path))
    controller.set_output_path(str(output_path))
    controller.set_final_image_result(
        FinalImageResult(
            revision_id="revision-1",
            approval_status=ApprovalStatus.needs_review,
            requires_user_confirmation=("visual_quality_unconfirmed",),
            visual_quality_checked=False,
        )
    )

    with pytest.raises(ExportControllerError, match="Save blocked"):
        controller.prepare_export_request()

    assert output_path.exists() is False


def _settings_state(
    *,
    translator_provider_id: str = "mock-translator",
    reviewer_provider_id: str = "mock-reviewer",
    visual_mode: bool = False,
    image_transmission_consent: bool = False,
    translator_api_key: ApiKeyReference | None = None,
    validation_issues: tuple[SettingsValidationIssue, ...] = (),
) -> SettingsDialogState:
    return SettingsDialogState(
        provider_settings=ProviderRuntimeSettings(
            translator=_endpoint(translator_provider_id, api_key=translator_api_key),
            reviewer=_endpoint(reviewer_provider_id),
            visual_mode_default=visual_mode,
            image_transmission_consent_default=image_transmission_consent,
        ),
        primary_ocr_provider_id="mock-ocr",
        secondary_ocr_provider_id="mock-secondary-ocr",
        inpainting_backend_order=("local-mask-fill",),
        validation_issues=validation_issues,
    )


def _endpoint(
    provider_id: str,
    *,
    api_key: ApiKeyReference | None = None,
) -> ProviderEndpointSettings:
    return ProviderEndpointSettings(
        provider_id=provider_id,
        model_id=f"{provider_id}-model-v1",
        timeout_seconds=30.0,
        api_key=api_key,
    )


def _issue(issue_code: str, severity: QualitySeverity) -> QualityIssue:
    return QualityIssue(
        issue_code=issue_code,
        severity=severity,
        scope="render",
        region_ids=("region-1",),
        summary="source text remains visible",
        recommended_action="review before save",
        resolved=False,
    )


def _approved_result() -> FinalImageResult:
    return FinalImageResult(
        revision_id="revision-1",
        approval_status=ApprovalStatus.approved_automatic,
        visual_quality_checked=True,
    )
