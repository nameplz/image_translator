from __future__ import annotations

from collections.abc import Iterable

from image_translator.domain.export import (
    ExportEligibilityDecision,
    FinalImageResult,
    ForceApprovalRecord,
)
from image_translator.services.export_gate import evaluate_export_eligibility


class ExportGateUseCase:
    def evaluate(
        self,
        result: FinalImageResult,
        *,
        confirmed_warning_issue_codes: Iterable[str] = (),
        confirmed_user_confirmation_reasons: Iterable[str] = (),
        force_approval_record: ForceApprovalRecord | None = None,
    ) -> ExportEligibilityDecision:
        return evaluate_export_eligibility(
            result,
            confirmed_warning_issue_codes=confirmed_warning_issue_codes,
            confirmed_user_confirmation_reasons=confirmed_user_confirmation_reasons,
            force_approval_record=force_approval_record,
        )


__all__ = ["ExportGateUseCase"]
