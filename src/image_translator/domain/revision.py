from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from image_translator.domain._base import DomainModel, NonEmptyStr
from image_translator.domain.errors import RevisionPlanRejected
from image_translator.domain.ids import RegionId, RevisionId


class RevisionAction(StrEnum):
    replace_translation = "replace_translation"
    adjust_tone = "adjust_tone"
    adjust_localization = "adjust_localization"
    propose_glossary_change = "propose_glossary_change"
    propose_character_rule = "propose_character_rule"
    change_font = "change_font"
    change_font_size = "change_font_size"
    change_weight = "change_weight"
    change_alignment = "change_alignment"
    change_color = "change_color"
    change_outline = "change_outline"
    change_writing_mode = "change_writing_mode"
    move_region = "move_region"
    resize_region = "resize_region"
    retry_inpainting = "retry_inpainting"
    retry_translation = "retry_translation"
    retry_quality_review = "retry_quality_review"


class RevisionScope(StrEnum):
    current_region = "current_region"
    current_page = "current_page"
    project_rule = "project_rule"


class RevisionApprovalStatus(StrEnum):
    pending = "pending"
    approved = "approved"
    rejected = "rejected"


class ApprovalRecord(DomainModel):
    approval_id: NonEmptyStr
    approved_by: NonEmptyStr
    approved_at: datetime
    approval_note: NonEmptyStr | None = None


class RevisionTarget(DomainModel):
    region_ids: tuple[RegionId, ...] = ()
    target_scope: RevisionScope = RevisionScope.current_region
    resolution_evidence: tuple[NonEmptyStr, ...] = ()
    is_ambiguous: bool = False
    ambiguity_summary: NonEmptyStr | None = None


class RevisionProposal(DomainModel):
    action: RevisionAction
    before: NonEmptyStr
    after: NonEmptyStr
    region_ids: tuple[RegionId, ...] = ()


class RevisionPlan(DomainModel):
    plan_id: NonEmptyStr
    base_revision_id: RevisionId
    normalized_user_instruction: NonEmptyStr
    target: RevisionTarget
    actions: tuple[RevisionAction, ...]
    proposals: tuple[RevisionProposal, ...] = ()
    required_validation: tuple[NonEmptyStr, ...] = ()
    warnings: tuple[NonEmptyStr, ...] = ()
    approval_status: RevisionApprovalStatus = RevisionApprovalStatus.pending
    approval_record: ApprovalRecord | None = None
    requires_project_rule_approval: bool = False
    project_rule_approval_record: ApprovalRecord | None = None


class RevisionDomainDiff(DomainModel):
    action: RevisionAction
    region_ids: tuple[RegionId, ...] = ()
    summary: NonEmptyStr


class RevisionRecord(DomainModel):
    revision_id: RevisionId
    parent_revision_id: RevisionId | None
    approved_plan: RevisionPlan
    domain_diff: tuple[RevisionDomainDiff, ...] = ()
    validation_results: tuple[NonEmptyStr, ...] = ()
    created_at: datetime
    approval_record: ApprovalRecord


def approve_revision_plan(
    plan: RevisionPlan,
    *,
    approval_record: ApprovalRecord,
    project_rule_approval_record: ApprovalRecord | None = None,
) -> RevisionPlan:
    if plan.requires_project_rule_approval and project_rule_approval_record is None:
        return plan.model_copy(
            update={
                "approval_status": RevisionApprovalStatus.approved,
                "approval_record": approval_record,
            }
        )
    return plan.model_copy(
        update={
            "approval_status": RevisionApprovalStatus.approved,
            "approval_record": approval_record,
            "project_rule_approval_record": project_rule_approval_record,
        }
    )


def require_approved_revision_plan(plan: RevisionPlan | None) -> RevisionPlan:
    if plan is None or plan.approval_status is not RevisionApprovalStatus.approved:
        raise RevisionPlanRejected("natural revision requires an approved RevisionPlan")
    if plan.approval_record is None:
        raise RevisionPlanRejected("approved RevisionPlan is missing approval record")
    if plan.requires_project_rule_approval and plan.project_rule_approval_record is None:
        raise RevisionPlanRejected("project rule revision requires separate approval")
    return plan


__all__ = [
    "ApprovalRecord",
    "RevisionAction",
    "RevisionApprovalStatus",
    "RevisionDomainDiff",
    "RevisionPlan",
    "RevisionProposal",
    "RevisionRecord",
    "RevisionScope",
    "RevisionTarget",
    "approve_revision_plan",
    "require_approved_revision_plan",
]
