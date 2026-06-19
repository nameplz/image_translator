from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from image_translator.domain.export import (
    VISUAL_QUALITY_UNCONFIRMED,
    ApprovalStatus,
    ExportMode,
    FinalImageResult,
    ForceApprovalRecord,
)
from image_translator.domain.quality import QualityIssue, QualitySeverity
from image_translator.services.export_gate import evaluate_export_eligibility


def _issue(issue_code: str, severity: QualitySeverity) -> QualityIssue:
    return QualityIssue(
        issue_code=issue_code,
        severity=severity,
        scope="render",
        region_ids=("region-1",),
        summary="export visible issue",
        evidence_references=("render-check-1",),
        recommended_action="review",
        resolved=False,
    )


def _result(
    *,
    approval_status: ApprovalStatus = ApprovalStatus.approved_automatic,
    unresolved_issues: tuple[QualityIssue, ...] = (),
    requires_user_confirmation: tuple[str, ...] = (),
    visual_quality_checked: bool = True,
) -> FinalImageResult:
    return FinalImageResult(
        revision_id="revision-1",
        approval_status=approval_status,
        unresolved_issues=unresolved_issues,
        requires_user_confirmation=requires_user_confirmation,
        visual_quality_checked=visual_quality_checked,
    )


def _force_record(
    *,
    unresolved_issue_codes: tuple[str, ...] = (),
    requires_user_confirmation: tuple[str, ...] = (),
) -> ForceApprovalRecord:
    return ForceApprovalRecord(
        affected_revision="revision-1",
        reason="user accepts the remaining visible issues",
        created_at=datetime(2026, 6, 19, 12, 0, tzinfo=UTC),
        unresolved_issue_codes=unresolved_issue_codes,
        requires_user_confirmation=requires_user_confirmation,
    )


def test_normal_export_blocks_unresolved_error_or_critical_issue() -> None:
    result = _result(unresolved_issues=(_issue("text_overlap", QualitySeverity.error),))

    decision = evaluate_export_eligibility(result)

    assert decision.allowed is False
    assert decision.mode is ExportMode.normal
    assert "blocking_quality_issue" in decision.reason_codes
    assert decision.blocking_issue_codes == ("text_overlap",)


def test_visual_mode_off_keeps_required_user_confirmation_blocker() -> None:
    result = _result(visual_quality_checked=False)

    decision = evaluate_export_eligibility(result)

    assert decision.allowed is False
    assert VISUAL_QUALITY_UNCONFIRMED in decision.requires_user_confirmation
    assert "user_confirmation_required" in decision.reason_codes


def test_confirmed_warning_can_use_normal_export() -> None:
    result = _result(unresolved_issues=(_issue("low_contrast_warning", QualitySeverity.warning),))

    unconfirmed_decision = evaluate_export_eligibility(result)
    confirmed_decision = evaluate_export_eligibility(
        result,
        confirmed_warning_issue_codes=("low_contrast_warning",),
    )

    assert unconfirmed_decision.allowed is False
    assert "warning_confirmation_required" in unconfirmed_decision.reason_codes
    assert confirmed_decision.allowed is True
    assert confirmed_decision.mode is ExportMode.normal


def test_force_export_requires_explicit_record_with_user_reason() -> None:
    result = _result(
        unresolved_issues=(_issue("source_remnant", QualitySeverity.critical),),
        requires_user_confirmation=(VISUAL_QUALITY_UNCONFIRMED,),
    )

    with pytest.raises(ValidationError):
        ForceApprovalRecord(
            affected_revision="revision-1",
            reason=" ",
            created_at=datetime(2026, 6, 19, 12, 0, tzinfo=UTC),
            unresolved_issue_codes=("source_remnant",),
            requires_user_confirmation=(VISUAL_QUALITY_UNCONFIRMED,),
        )

    forced_decision = evaluate_export_eligibility(
        result,
        force_approval_record=_force_record(
            unresolved_issue_codes=("source_remnant",),
            requires_user_confirmation=(VISUAL_QUALITY_UNCONFIRMED,),
        ),
    )

    assert forced_decision.allowed is True
    assert forced_decision.mode is ExportMode.forced
    assert forced_decision.force_approval_record is not None


def test_force_record_must_match_current_blockers() -> None:
    result = _result(unresolved_issues=(_issue("source_remnant", QualitySeverity.critical),))

    decision = evaluate_export_eligibility(result, force_approval_record=_force_record())

    assert decision.allowed is False
    assert decision.mode is ExportMode.forced
    assert "force_record_missing_blockers" in decision.reason_codes
