from __future__ import annotations

from collections.abc import Iterable

from image_translator.domain.export import (
    VISUAL_QUALITY_UNCONFIRMED,
    ExportEligibilityDecision,
    ExportMode,
    FinalImageResult,
    ForceApprovalRecord,
)
from image_translator.domain.quality import ApprovalStatus, QualityIssue, QualitySeverity

NORMAL_EXPORT_APPROVAL_STATUSES = frozenset(
    (ApprovalStatus.approved_automatic, ApprovalStatus.approved_user)
)
FORCED_EXPORT_APPROVAL_STATUSES = frozenset(
    (
        ApprovalStatus.approved_automatic,
        ApprovalStatus.approved_user,
        ApprovalStatus.approved_forced,
    )
)


def evaluate_export_eligibility(
    result: FinalImageResult,
    *,
    confirmed_warning_issue_codes: Iterable[str] = (),
    confirmed_user_confirmation_reasons: Iterable[str] = (),
    force_approval_record: ForceApprovalRecord | None = None,
) -> ExportEligibilityDecision:
    blocking_issue_codes = _issue_codes(
        result.unresolved_issues,
        severities=(QualitySeverity.error, QualitySeverity.critical),
    )
    warning_issue_codes = _issue_codes(
        result.unresolved_issues,
        severities=(QualitySeverity.warning,),
    )
    unconfirmed_warning_codes = _unconfirmed_codes(
        warning_issue_codes,
        confirmed_warning_issue_codes,
    )
    pending_confirmations = _pending_confirmations(
        result,
        confirmed_user_confirmation_reasons,
    )

    if force_approval_record is not None:
        return _evaluate_forced_export(
            result=result,
            blocking_issue_codes=blocking_issue_codes,
            warning_issue_codes=warning_issue_codes,
            pending_confirmations=pending_confirmations,
            force_approval_record=force_approval_record,
        )

    reason_codes: list[str] = []
    if result.approval_status not in NORMAL_EXPORT_APPROVAL_STATUSES:
        reason_codes.append("result_not_approved")
    if blocking_issue_codes:
        reason_codes.append("blocking_quality_issue")
    if pending_confirmations:
        reason_codes.append("user_confirmation_required")
    if unconfirmed_warning_codes:
        reason_codes.append("warning_confirmation_required")

    return ExportEligibilityDecision(
        allowed=not reason_codes,
        mode=ExportMode.normal,
        reason_codes=tuple(reason_codes),
        blocking_issue_codes=blocking_issue_codes,
        warning_issue_codes=unconfirmed_warning_codes,
        requires_user_confirmation=pending_confirmations,
    )


def _evaluate_forced_export(
    *,
    result: FinalImageResult,
    blocking_issue_codes: tuple[str, ...],
    warning_issue_codes: tuple[str, ...],
    pending_confirmations: tuple[str, ...],
    force_approval_record: ForceApprovalRecord,
) -> ExportEligibilityDecision:
    reason_codes: list[str] = []

    if result.approval_status not in FORCED_EXPORT_APPROVAL_STATUSES:
        reason_codes.append("result_not_approved_for_forced_export")
    if force_approval_record.affected_revision != result.revision_id:
        reason_codes.append("force_record_revision_mismatch")
    if _missing_blockers(
        blocking_issue_codes,
        force_approval_record.unresolved_issue_codes,
    ) or _missing_blockers(
        pending_confirmations,
        force_approval_record.requires_user_confirmation,
    ):
        reason_codes.append("force_record_missing_blockers")

    return ExportEligibilityDecision(
        allowed=not reason_codes,
        mode=ExportMode.forced,
        reason_codes=tuple(reason_codes),
        blocking_issue_codes=blocking_issue_codes,
        warning_issue_codes=warning_issue_codes,
        requires_user_confirmation=pending_confirmations,
        force_approval_record=force_approval_record,
    )


def _issue_codes(
    issues: tuple[QualityIssue, ...],
    *,
    severities: tuple[QualitySeverity, ...],
) -> tuple[str, ...]:
    return _unique(
        issue.issue_code
        for issue in issues
        if not issue.resolved and issue.severity in severities
    )


def _pending_confirmations(
    result: FinalImageResult,
    confirmed_user_confirmation_reasons: Iterable[str],
) -> tuple[str, ...]:
    required_reasons = list(result.requires_user_confirmation)
    if not result.visual_quality_checked:
        _append_unique(required_reasons, VISUAL_QUALITY_UNCONFIRMED)

    confirmed_reasons = frozenset(confirmed_user_confirmation_reasons)
    return tuple(reason for reason in required_reasons if reason not in confirmed_reasons)


def _unconfirmed_codes(
    issue_codes: tuple[str, ...],
    confirmed_issue_codes: Iterable[str],
) -> tuple[str, ...]:
    confirmed_codes = frozenset(confirmed_issue_codes)
    return tuple(issue_code for issue_code in issue_codes if issue_code not in confirmed_codes)


def _missing_blockers(required_codes: tuple[str, ...], recorded_codes: tuple[str, ...]) -> bool:
    recorded_code_set = frozenset(recorded_codes)
    return any(required_code not in recorded_code_set for required_code in required_codes)


def _unique(values: Iterable[str]) -> tuple[str, ...]:
    unique_values: list[str] = []
    for value in values:
        _append_unique(unique_values, value)
    return tuple(unique_values)


def _append_unique(items: list[str], value: str) -> None:
    if value not in items:
        items.append(value)
