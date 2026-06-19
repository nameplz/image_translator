from __future__ import annotations

from enum import StrEnum

from image_translator.domain._base import DomainModel, NonEmptyStr
from image_translator.domain.export import VISUAL_QUALITY_UNCONFIRMED, FinalImageResult
from image_translator.domain.ids import RevisionId
from image_translator.domain.quality import ApprovalStatus, QualityIssue, QualitySeverity
from image_translator.domain.translation import TranslationResult
from image_translator.providers.base import ResultQualityReview


class ResultQualityStatus(StrEnum):
    pending = "pending"
    render_validated = "render_validated"
    reviewed = "reviewed"
    needs_review = "needs_review"
    approved = "approved"


class ResultRoute(StrEnum):
    complete = "complete"
    interrupt_user = "interrupt_user"


class ResultQualityState(DomainModel):
    revision_id: RevisionId
    approved_translations: tuple[TranslationResult, ...]
    rendered_image_reference: NonEmptyStr | None = None
    unresolved_issues: tuple[QualityIssue, ...] = ()
    visual_quality_checked: bool = False
    final_image_result: FinalImageResult | None = None
    status: ResultQualityStatus = ResultQualityStatus.pending


def create_result_quality_state(
    *,
    revision_id: RevisionId,
    approved_translations: tuple[TranslationResult, ...],
    unresolved_translation_issues: tuple[QualityIssue, ...] = (),
) -> ResultQualityState:
    return ResultQualityState(
        revision_id=revision_id,
        approved_translations=approved_translations,
        unresolved_issues=unresolved_translation_issues,
    )


def validate_render_structure(
    *,
    state: ResultQualityState,
    expected_region_ids: tuple[str, ...],
    rendered_image_reference: str,
) -> ResultQualityState:
    approved_region_ids = tuple(
        translation.region_id for translation in state.approved_translations
    )
    missing_region_ids = tuple(
        region_id for region_id in expected_region_ids if region_id not in approved_region_ids
    )
    structure_issues = tuple(
        QualityIssue(
            issue_code=f"missing_approved_translation_{region_id}",
            severity=QualitySeverity.critical,
            scope="render_structure",
            region_ids=(region_id,),
            summary="render structure is missing an approved translation",
            evidence_references=("mock-render-structure",),
            recommended_action="review translation",
        )
        for region_id in missing_region_ids
        if not _has_region_blocker(state.unresolved_issues, region_id)
    )
    status = (
        ResultQualityStatus.render_validated
        if not (*state.unresolved_issues, *structure_issues)
        else ResultQualityStatus.needs_review
    )
    return state.model_copy(
        update={
            "rendered_image_reference": rendered_image_reference,
            "unresolved_issues": (*state.unresolved_issues, *structure_issues),
            "status": status,
        }
    )


def apply_result_quality_review(
    *,
    state: ResultQualityState,
    review: ResultQualityReview,
) -> ResultQualityState:
    unresolved_issues = tuple(issue for issue in review.issues if not issue.resolved)
    status = (
        ResultQualityStatus.reviewed
        if not unresolved_issues and not review.requires_user_review
        else ResultQualityStatus.needs_review
    )
    return state.model_copy(
        update={
            "rendered_image_reference": review.rendered_image_reference.reference_id,
            "unresolved_issues": (*state.unresolved_issues, *unresolved_issues),
            "visual_quality_checked": True,
            "status": status,
        }
    )


def finalize_result_quality(state: ResultQualityState) -> ResultQualityState:
    approval_status = (
        ApprovalStatus.approved_automatic
        if not _blocking_issues(state.unresolved_issues)
        else ApprovalStatus.needs_review
    )
    final_image_result = FinalImageResult(
        revision_id=state.revision_id,
        approval_status=approval_status,
        unresolved_issues=state.unresolved_issues,
        requires_user_confirmation=(
            () if state.visual_quality_checked else (VISUAL_QUALITY_UNCONFIRMED,)
        ),
        visual_quality_checked=state.visual_quality_checked,
    )
    status = (
        ResultQualityStatus.approved
        if approval_status is ApprovalStatus.approved_automatic
        and state.visual_quality_checked
        else ResultQualityStatus.needs_review
    )
    return state.model_copy(
        update={
            "final_image_result": final_image_result,
            "status": status,
        }
    )


def route_result_decision(state: ResultQualityState) -> ResultRoute:
    if state.final_image_result is None:
        return ResultRoute.interrupt_user
    if (
        state.final_image_result.approval_status is ApprovalStatus.approved_automatic
        and state.visual_quality_checked
    ):
        return ResultRoute.complete
    return ResultRoute.interrupt_user


def _blocking_issues(issues: tuple[QualityIssue, ...]) -> tuple[QualityIssue, ...]:
    return tuple(
        issue
        for issue in issues
        if not issue.resolved
        and issue.severity in (QualitySeverity.error, QualitySeverity.critical)
    )


def _has_region_blocker(issues: tuple[QualityIssue, ...], region_id: str) -> bool:
    return any(
        not issue.resolved
        and issue.severity in (QualitySeverity.error, QualitySeverity.critical)
        and region_id in issue.region_ids
        for issue in issues
    )
