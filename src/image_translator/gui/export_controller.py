from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

from image_translator.domain.export import (
    ExportEligibilityDecision,
    ExportFormat,
    ExportRequest,
    FinalImageResult,
    ForceApprovalRecord,
    FormatOptions,
)
from image_translator.use_cases.export_gate import ExportGateUseCase

OverwriteConfirmation = Callable[[Path], bool]
ForceReasonRequest = Callable[[ExportEligibilityDecision], str | None]
Clock = Callable[[], datetime]

_EXTENSION_FORMATS = {
    ".png": ExportFormat.png,
    ".jpg": ExportFormat.jpeg,
    ".jpeg": ExportFormat.jpeg,
    ".webp": ExportFormat.webp,
}
_T = TypeVar("_T")


class ExportControllerError(Exception):
    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


@dataclass(frozen=True, slots=True)
class ExportControllerState:
    input_path: str | None = None
    output_path: str | None = None
    review_before_save: bool = True
    final_image_result: FinalImageResult | None = None
    confirmed_warning_issue_codes: tuple[str, ...] = ()
    confirmed_user_confirmation_reasons: tuple[str, ...] = ()


class ExportController:
    """Collects export UI decisions without writing image files on the GUI thread."""

    def __init__(
        self,
        *,
        overwrite_confirmation: OverwriteConfirmation | None = None,
        force_reason_request: ForceReasonRequest | None = None,
        export_gate: ExportGateUseCase | None = None,
        clock: Clock | None = None,
    ) -> None:
        self._state = ExportControllerState()
        self._overwrite_confirmation = overwrite_confirmation or _reject_overwrite
        self._force_reason_request = force_reason_request or _no_force_reason
        self._export_gate = export_gate or ExportGateUseCase()
        self._clock = clock or _utc_now

    @property
    def state(self) -> ExportControllerState:
        return self._state

    @property
    def requested_output_path(self) -> str | None:
        return self._state.output_path

    @property
    def normal_save_allowed_if_result_known(self) -> bool:
        decision = self.normal_export_decision()
        return True if decision is None else decision.allowed

    def set_input_path(self, path: str) -> None:
        self._state = replace(self._state, input_path=path)

    def set_output_path(self, path: str | None) -> None:
        self._state = replace(self._state, output_path=path)

    def set_review_before_save(self, enabled: bool) -> None:
        self._state = replace(self._state, review_before_save=enabled)

    def set_final_image_result(self, result: FinalImageResult | None) -> None:
        self._state = replace(self._state, final_image_result=result)

    def confirm_warning_issue_codes(self, issue_codes: tuple[str, ...]) -> None:
        self._state = replace(self._state, confirmed_warning_issue_codes=issue_codes)

    def confirm_user_confirmation_reasons(self, reasons: tuple[str, ...]) -> None:
        self._state = replace(self._state, confirmed_user_confirmation_reasons=reasons)

    def normal_export_decision(self) -> ExportEligibilityDecision | None:
        result = self._state.final_image_result
        if result is None:
            return None
        return self._export_gate.evaluate(
            result,
            confirmed_warning_issue_codes=self._state.confirmed_warning_issue_codes,
            confirmed_user_confirmation_reasons=(
                self._state.confirmed_user_confirmation_reasons
            ),
        )

    def export_blocking_text(self) -> str:
        decision = self.normal_export_decision()
        if decision is None:
            return "Export result is not ready."
        if decision.allowed:
            return "Export gate passed."
        details = _decision_details(decision)
        return f"Save blocked: {details}"

    def prepare_export_request(
        self,
        *,
        output_path: str | None = None,
        force: bool = False,
        job_id: str | None = None,
        export_format: ExportFormat | None = None,
        format_options: FormatOptions | None = None,
    ) -> ExportRequest:
        input_path = _required_value(self._state.input_path, "Select an input image first.")
        final_image_result = _required_value(
            self._state.final_image_result,
            "Export result is not ready.",
        )
        selected_output_path = _required_value(
            output_path or self._state.output_path,
            "Choose an output path before saving.",
        )
        output = Path(selected_output_path).expanduser()
        resolved_format = export_format or _format_from_extension(output)
        overwrite_confirmed = self._confirm_overwrite_if_needed(output)
        normal_decision = _required_value(
            self.normal_export_decision(),
            "Export result is not ready.",
        )

        force_record: ForceApprovalRecord | None = None
        if force and not normal_decision.allowed:
            force_record = self._create_force_record(final_image_result, normal_decision)
            forced_decision = self._export_gate.evaluate(
                final_image_result,
                confirmed_warning_issue_codes=self._state.confirmed_warning_issue_codes,
                confirmed_user_confirmation_reasons=(
                    self._state.confirmed_user_confirmation_reasons
                ),
                force_approval_record=force_record,
            )
            if not forced_decision.allowed:
                raise ExportControllerError(
                    f"Forced save blocked: {_decision_details(forced_decision)}"
                )
        elif not normal_decision.allowed:
            raise ExportControllerError(self.export_blocking_text())

        return ExportRequest(
            input_path=input_path,
            output_path=str(output),
            final_image_result=final_image_result,
            job_id=job_id,
            format=resolved_format,
            format_options=format_options or FormatOptions(),
            overwrite_confirmed=overwrite_confirmed,
            confirmed_warning_issue_codes=self._state.confirmed_warning_issue_codes,
            confirmed_user_confirmation_reasons=(
                self._state.confirmed_user_confirmation_reasons
            ),
            force_approval_record=force_record,
        )

    def _confirm_overwrite_if_needed(self, output_path: Path) -> bool:
        if not output_path.exists():
            return False
        if self._overwrite_confirmation(output_path):
            return True
        raise ExportControllerError("Overwrite confirmation is required before replacing a file.")

    def _create_force_record(
        self,
        final_image_result: FinalImageResult,
        decision: ExportEligibilityDecision,
    ) -> ForceApprovalRecord:
        reason = (self._force_reason_request(decision) or "").strip()
        if not reason:
            raise ExportControllerError("Forced export requires a user reason.")
        return ForceApprovalRecord(
            affected_revision=final_image_result.revision_id,
            reason=reason,
            created_at=self._clock(),
            unresolved_issue_codes=decision.blocking_issue_codes,
            requires_user_confirmation=decision.requires_user_confirmation,
        )


def _format_from_extension(path: Path) -> ExportFormat:
    export_format = _EXTENSION_FORMATS.get(path.suffix.lower())
    if export_format is None:
        raise ExportControllerError("Choose a PNG, JPEG, or WebP output file.")
    return export_format


def _decision_details(decision: ExportEligibilityDecision) -> str:
    details = (
        *decision.reason_codes,
        *decision.blocking_issue_codes,
        *decision.warning_issue_codes,
        *decision.requires_user_confirmation,
    )
    return ", ".join(details) if details else "export gate rejected the result"


def _required_value(value: _T | None, message: str) -> _T:
    if value is None:
        raise ExportControllerError(message)
    return value


def _reject_overwrite(_path: Path) -> bool:
    return False


def _no_force_reason(_decision: ExportEligibilityDecision) -> str | None:
    return None


def _utc_now() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "ExportController",
    "ExportControllerError",
    "ExportControllerState",
]
