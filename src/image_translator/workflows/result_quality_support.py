from __future__ import annotations

from enum import StrEnum

from image_translator.domain._base import DomainModel, NonEmptyStr
from image_translator.domain.export import VISUAL_QUALITY_UNCONFIRMED
from image_translator.domain.ids import RegionId
from image_translator.domain.ocr import WritingMode
from image_translator.domain.quality import QualityIssue, QualitySeverity
from image_translator.domain.render import RenderPlan
from image_translator.services.rendering import text_has_supported_glyphs


class ResultCorrectionAction(StrEnum):
    render_plan_update = "render_plan_update"
    mask_update = "mask_update"
    backend_escalation = "backend_escalation"
    rerender = "rerender"


class ResultCorrection(DomainModel):
    issue_code: NonEmptyStr
    action: ResultCorrectionAction
    region_ids: tuple[RegionId, ...] = ()
    summary: NonEmptyStr


def blocking_issues(issues: tuple[QualityIssue, ...]) -> tuple[QualityIssue, ...]:
    return tuple(
        issue
        for issue in issues
        if not issue.resolved
        and issue.severity in (QualitySeverity.error, QualitySeverity.critical)
    )


def required_confirmations(
    *,
    requires_user_confirmation: tuple[NonEmptyStr, ...],
    visual_quality_checked: bool,
) -> tuple[NonEmptyStr, ...]:
    confirmations = list(requires_user_confirmation)
    if not visual_quality_checked:
        _append_unique(confirmations, VISUAL_QUALITY_UNCONFIRMED)
    return tuple(confirmations)


def add_unique_confirmation(
    confirmations: tuple[NonEmptyStr, ...],
    reason: str,
) -> tuple[NonEmptyStr, ...]:
    updated = list(confirmations)
    _append_unique(updated, reason)
    return tuple(updated)


def missing_translation_issues(
    region_ids: tuple[str, ...],
    existing_issues: tuple[QualityIssue, ...],
) -> tuple[QualityIssue, ...]:
    return tuple(
        QualityIssue(
            issue_code=f"missing_approved_translation_{region_id}",
            severity=QualitySeverity.critical,
            scope="render_structure",
            region_ids=(region_id,),
            summary="render structure is missing an approved translation",
            evidence_references=("render-structure",),
            recommended_action="review translation",
        )
        for region_id in region_ids
        if not has_region_blocker(existing_issues, region_id)
    )


def missing_mapping_issues(
    *,
    expected_region_ids: tuple[str, ...],
    actual_region_ids: tuple[str, ...],
    issue_code: str,
    summary: str,
    action: str,
) -> tuple[QualityIssue, ...]:
    if not actual_region_ids:
        return ()
    return tuple(
        _issue(
            code=issue_code,
            severity=QualitySeverity.critical,
            scope="render_structure",
            region_ids=(region_id,),
            summary=summary,
            action=action,
        )
        for region_id in expected_region_ids
        if region_id not in actual_region_ids
    )


def unknown_mapping_issues(
    *,
    expected_region_ids: tuple[str, ...],
    actual_region_ids: tuple[str, ...],
    issue_code: str,
    summary: str,
) -> tuple[QualityIssue, ...]:
    expected = frozenset(expected_region_ids)
    return tuple(
        _issue(
            code=issue_code,
            severity=QualitySeverity.error,
            scope="render_structure",
            region_ids=(region_id,),
            summary=summary,
            action="remove unknown region mapping before export",
        )
        for region_id in actual_region_ids
        if region_id not in expected
    )


def duplicate_mapping_issues(
    region_ids: tuple[str, ...],
    *,
    issue_code: str,
    summary: str,
) -> tuple[QualityIssue, ...]:
    duplicates = tuple(
        region_id for region_id in dict.fromkeys(region_ids) if region_ids.count(region_id) > 1
    )
    return tuple(
        _issue(
            code=issue_code,
            severity=QualitySeverity.error,
            scope="render_structure",
            region_ids=(region_id,),
            summary=summary,
            action="deduplicate render mappings",
        )
        for region_id in duplicates
    )


def render_plan_schema_issues(plans: tuple[RenderPlan, ...]) -> tuple[QualityIssue, ...]:
    issues: tuple[QualityIssue, ...] = ()
    for plan in plans:
        if plan.style.writing_mode is WritingMode.unknown:
            issues = (
                *issues,
                _issue(
                    code="unknown_render_writing_mode",
                    severity=QualitySeverity.error,
                    scope="render_structure",
                    region_ids=(plan.region_id,),
                    summary="RenderPlan has unknown writing mode",
                    action="choose a concrete writing mode before rendering",
                ),
            )
        if not text_has_supported_glyphs(plan.translated_text):
            issues = (
                *issues,
                _issue(
                    code="unsupported_glyph",
                    severity=QualitySeverity.error,
                    scope="render_structure",
                    region_ids=(plan.region_id,),
                    summary="RenderPlan text has unsupported glyphs",
                    action="choose a supported font or replace unsupported glyphs",
                ),
            )
    return issues


def replace_scope_issues(
    issues: tuple[QualityIssue, ...],
    *,
    scope: str,
    replacement: tuple[QualityIssue, ...],
) -> tuple[QualityIssue, ...]:
    return (
        *(issue for issue in issues if issue.scope != scope),
        *replacement,
    )


def corrections_for_issue(issue: QualityIssue) -> tuple[ResultCorrection, ...]:
    action = correction_action_for_issue(issue)
    if action is None:
        return ()
    corrections: tuple[ResultCorrection, ...] = (
        ResultCorrection(
            issue_code=issue.issue_code,
            action=action,
            region_ids=issue.region_ids,
            summary=issue.recommended_action or issue.summary,
        ),
    )
    if action != ResultCorrectionAction.rerender:
        corrections = (
            *corrections,
            ResultCorrection(
                issue_code=issue.issue_code,
                action=ResultCorrectionAction.rerender,
                region_ids=issue.region_ids,
                summary="rerender after applying result correction",
            ),
        )
    return corrections


def correction_action_for_issue(issue: QualityIssue) -> ResultCorrectionAction | None:
    if issue.severity not in (QualitySeverity.error, QualitySeverity.critical):
        return None
    if issue.issue_code in {
        "text_clipping",
        "text_overlap",
        "minimum_font_size",
        "low_contrast",
        "unsupported_glyph",
        "missing_region",
        "missing_render_plan",
        "missing_rendered_region",
        "unknown_render_writing_mode",
    }:
        return ResultCorrectionAction.render_plan_update
    if "mask" in issue.issue_code or "source_remnant" in issue.issue_code:
        return ResultCorrectionAction.mask_update
    if "inpainting" in issue.issue_code or "backend" in issue.issue_code:
        return ResultCorrectionAction.backend_escalation
    return None


def affected_region_ids(issues: tuple[QualityIssue, ...]) -> tuple[RegionId, ...]:
    region_ids: list[RegionId] = []
    for issue in issues:
        if issue.resolved:
            continue
        for region_id in issue.region_ids:
            if region_id not in region_ids:
                region_ids.append(region_id)
    return tuple(region_ids)


def has_region_blocker(issues: tuple[QualityIssue, ...], region_id: str) -> bool:
    return any(
        not issue.resolved
        and issue.severity in (QualitySeverity.error, QualitySeverity.critical)
        and region_id in issue.region_ids
        for issue in issues
    )


def _append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def _issue(
    *,
    code: str,
    severity: QualitySeverity,
    scope: str,
    region_ids: tuple[RegionId, ...],
    summary: str,
    action: str,
) -> QualityIssue:
    return QualityIssue(
        issue_code=code,
        severity=severity,
        scope=scope,
        region_ids=region_ids,
        summary=summary,
        recommended_action=action,
    )
