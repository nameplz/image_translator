from __future__ import annotations

from enum import StrEnum
from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from image_translator.domain._base import DomainModel, NonEmptyStr, NonNegativeInt, PositiveInt
from image_translator.domain.export import (
    VISUAL_QUALITY_UNCONFIRMED,
    ExportEligibilityDecision,
    FinalImageResult,
    ForceApprovalRecord,
)
from image_translator.domain.ids import RegionId, RevisionId
from image_translator.domain.quality import ApprovalStatus, QualityIssue, QualitySeverity
from image_translator.domain.render import RenderedRegion, RenderPlan
from image_translator.domain.translation import TranslationResult
from image_translator.providers.base import (
    ImageReference,
    ImageReferenceKind,
    ResultImageReviewRequest,
    ResultQualityReview,
    ReviewAdapter,
)
from image_translator.services.export_gate import evaluate_export_eligibility
from image_translator.services.result_validation import validate_result_layout
from image_translator.workflows import result_quality_support as _support
from image_translator.workflows.result_quality_support import (
    ResultCorrection,
    ResultCorrectionAction,
)

MAX_RESULT_CORRECTION_ATTEMPTS = 2


class ResultQualityStatus(StrEnum):
    pending = "pending"
    structure_validated = "structure_validated"
    layout_inspected = "layout_inspected"
    inpainting_inspected = "inpainting_inspected"
    reviewed = "reviewed"
    correction_planned = "correction_planned"
    correcting = "correcting"
    needs_review = "needs_review"
    approved = "approved"
    finalized = "finalized"


class ResultRoute(StrEnum):
    complete = "complete"
    retry_quality = "retry_quality"
    interrupt_user = "interrupt_user"


class ResultReviewInterruptPayload(DomainModel):
    interrupt_type: NonEmptyStr = "result_review"
    revision_id: RevisionId
    affected_region_ids: tuple[RegionId, ...] = ()
    issue_summaries: tuple[NonEmptyStr, ...] = ()
    preview_references: tuple[NonEmptyStr, ...] = ()
    allowed_actions: tuple[NonEmptyStr, ...] = ("adjust_render_plan", "adjust_mask",
                                                "escalate_inpainting_backend", "rerender",
                                                "force_export", "cancel")
    recommended_action: NonEmptyStr = "review final image quality before export"


class ResultQualityInput(DomainModel):
    revision_id: RevisionId
    approved_translations: tuple[TranslationResult, ...]
    source_image_reference: NonEmptyStr
    inpainted_image_reference: NonEmptyStr | None = None
    rendered_image_reference: NonEmptyStr
    expected_region_ids: tuple[RegionId, ...]
    render_plans: tuple[RenderPlan, ...] = ()
    rendered_regions: tuple[RenderedRegion, ...] = ()
    image_size: tuple[PositiveInt, PositiveInt]
    visual_mode: bool = False
    image_transmission_consent: bool = False
    mask_reference: NonEmptyStr | None = None
    inpainting_backend_id: NonEmptyStr | None = None


class ResultQualityState(DomainModel):
    input: ResultQualityInput | None = None
    revision_id: RevisionId
    approved_translations: tuple[TranslationResult, ...]
    source_image_reference: NonEmptyStr | None = None
    inpainted_image_reference: NonEmptyStr | None = None
    rendered_image_reference: NonEmptyStr | None = None
    expected_region_ids: tuple[RegionId, ...] = ()
    render_plans: tuple[RenderPlan, ...] = ()
    rendered_regions: tuple[RenderedRegion, ...] = ()
    image_size: tuple[PositiveInt, PositiveInt] | None = None
    unresolved_issues: tuple[QualityIssue, ...] = ()
    requires_user_confirmation: tuple[NonEmptyStr, ...] = ()
    visual_quality_checked: bool = False
    correction_attempts: NonNegativeInt = 0
    correction_plan: tuple[ResultCorrection, ...] = ()
    applied_correction_actions: tuple[ResultCorrectionAction, ...] = ()
    interrupt_payload: ResultReviewInterruptPayload | None = None
    final_image_result: FinalImageResult | None = None
    export_decision: ExportEligibilityDecision | None = None
    last_route: ResultRoute | None = None
    status: ResultQualityStatus = ResultQualityStatus.pending


class _GraphState(TypedDict):
    workflow_state: ResultQualityState


class ResultQualityGraph:
    def __init__(self, *, reviewer: ReviewAdapter | None = None) -> None:
        self._reviewer = reviewer
        self._compiled_graph: Any = _build_langgraph(reviewer=reviewer)

    async def run_state(self, workflow_input: ResultQualityInput) -> ResultQualityState:
        initial_state: _GraphState = {
            "workflow_state": create_result_quality_workflow_state(workflow_input)
        }
        final_state = cast(_GraphState, await self._compiled_graph.ainvoke(initial_state))
        state = final_state["workflow_state"]
        if state.final_image_result is not None:
            return state
        return finalize_result(state)

    async def run(self, workflow_input: ResultQualityInput) -> FinalImageResult:
        state = await self.run_state(workflow_input)
        if state.final_image_result is None:
            raise RuntimeError("result quality graph finished without a final image result")
        return state.final_image_result


def create_result_quality_workflow_state(
    workflow_input: ResultQualityInput,
) -> ResultQualityState:
    return ResultQualityState(
        input=workflow_input,
        revision_id=workflow_input.revision_id,
        approved_translations=workflow_input.approved_translations,
        source_image_reference=workflow_input.source_image_reference,
        inpainted_image_reference=workflow_input.inpainted_image_reference,
        rendered_image_reference=workflow_input.rendered_image_reference,
        expected_region_ids=workflow_input.expected_region_ids,
        render_plans=workflow_input.render_plans,
        rendered_regions=workflow_input.rendered_regions,
        image_size=workflow_input.image_size,
    )


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
    expected_region_ids: tuple[str, ...] | None = None,
    rendered_image_reference: str | None = None,
) -> ResultQualityState:
    active_expected_region_ids = tuple(expected_region_ids or state.expected_region_ids)
    active_rendered_image_reference = rendered_image_reference or state.rendered_image_reference
    approved_region_ids = tuple(
        translation.region_id for translation in state.approved_translations
    )
    plan_region_ids = tuple(plan.region_id for plan in state.render_plans)
    rendered_region_ids = tuple(region.region_id for region in state.rendered_regions)
    missing_region_ids = tuple(
        region_id
        for region_id in active_expected_region_ids
        if region_id not in approved_region_ids
    )
    structure_issues = (
        *_support.missing_translation_issues(missing_region_ids, state.unresolved_issues),
        *_support.missing_mapping_issues(
            expected_region_ids=active_expected_region_ids,
            actual_region_ids=plan_region_ids,
            issue_code="missing_render_plan",
            summary="render structure is missing a RenderPlan",
            action="create a RenderPlan for the missing region",
        ),
        *_support.missing_mapping_issues(
            expected_region_ids=active_expected_region_ids,
            actual_region_ids=rendered_region_ids,
            issue_code="missing_rendered_region",
            summary="render structure is missing rendered output",
            action="rerender the missing region",
        ),
        *_support.unknown_mapping_issues(
            expected_region_ids=active_expected_region_ids,
            actual_region_ids=plan_region_ids,
            issue_code="unknown_render_plan_region",
            summary="RenderPlan references an unknown region",
        ),
        *_support.unknown_mapping_issues(
            expected_region_ids=active_expected_region_ids,
            actual_region_ids=rendered_region_ids,
            issue_code="unknown_rendered_region",
            summary="rendered output references an unknown region",
        ),
        *_support.duplicate_mapping_issues(
            plan_region_ids,
            issue_code="duplicate_render_plan_region",
            summary="RenderPlan contains duplicate region IDs",
        ),
        *_support.duplicate_mapping_issues(
            rendered_region_ids,
            issue_code="duplicate_rendered_region",
            summary="rendered output contains duplicate region IDs",
        ),
        *_support.render_plan_schema_issues(state.render_plans),
    )
    unresolved_issues = _support.replace_scope_issues(
        state.unresolved_issues,
        scope="render_structure",
        replacement=structure_issues,
    )
    status = (
        ResultQualityStatus.structure_validated
        if not _support.blocking_issues(unresolved_issues)
        else ResultQualityStatus.needs_review
    )
    return state.model_copy(
        update={
            "rendered_image_reference": active_rendered_image_reference,
            "expected_region_ids": active_expected_region_ids,
            "unresolved_issues": unresolved_issues,
            "status": status,
        }
    )


def inspect_layout(state: ResultQualityState) -> ResultQualityState:
    if state.image_size is None:
        return state.model_copy(update={"status": ResultQualityStatus.layout_inspected})
    validation = validate_result_layout(
        expected_region_ids=state.expected_region_ids,
        rendered_regions=state.rendered_regions,
        image_size=state.image_size,
    )
    unresolved_issues = _support.replace_scope_issues(
        state.unresolved_issues,
        scope="result_layout",
        replacement=validation.issues,
    )
    return state.model_copy(
        update={
            "unresolved_issues": unresolved_issues,
            "status": (
                ResultQualityStatus.layout_inspected
                if not _support.blocking_issues(unresolved_issues)
                else ResultQualityStatus.needs_review
            ),
        }
    )


def inspect_inpainting(state: ResultQualityState) -> ResultQualityState:
    issues: tuple[QualityIssue, ...] = ()
    if state.input is not None and not state.input.inpainted_image_reference:
        issues = (
            QualityIssue(
                issue_code="missing_inpainted_image",
                severity=QualitySeverity.error,
                scope="result_inpainting",
                region_ids=state.expected_region_ids,
                summary="inpainted image reference is missing",
                recommended_action="rerun inpainting before final review",
            ),
        )
    unresolved_issues = _support.replace_scope_issues(
        state.unresolved_issues,
        scope="result_inpainting",
        replacement=issues,
    )
    return state.model_copy(
        update={
            "unresolved_issues": unresolved_issues,
            "status": (
                ResultQualityStatus.inpainting_inspected
                if not _support.blocking_issues(unresolved_issues)
                else ResultQualityStatus.needs_review
            ),
        }
    )


async def review_final_image(
    state: ResultQualityState,
    *,
    reviewer: ReviewAdapter | None = None,
) -> ResultQualityState:
    if state.input is None or not state.input.visual_mode:
        return _add_user_confirmation(state, VISUAL_QUALITY_UNCONFIRMED)
    if not state.input.image_transmission_consent or reviewer is None:
        return _add_user_confirmation(state, "visual_review_unavailable")

    capabilities = reviewer.capabilities()
    rendered_reference = ImageReference(
        reference_id=state.input.rendered_image_reference,
        kind=ImageReferenceKind.rendered,
    )
    visual_references = tuple(
        reference
        for reference in (
            ImageReference(
                reference_id=state.input.source_image_reference,
                kind=ImageReferenceKind.full_page,
            ),
            ImageReference(
                reference_id=state.input.inpainted_image_reference,
                kind=ImageReferenceKind.inpainted,
            )
            if state.input.inpainted_image_reference is not None
            else None,
        )
        if reference is not None and capabilities.supports_visual_reference(reference)
    )
    if not capabilities.supports_visual_reference(rendered_reference):
        return _add_user_confirmation(state, "visual_review_unavailable")

    review = await reviewer.review_result_image(
        ResultImageReviewRequest(
            rendered_image_reference=rendered_reference,
            visual_references=visual_references,
        )
    )
    return apply_result_quality_review(state=state, review=review)


def apply_result_quality_review(
    *,
    state: ResultQualityState,
    review: ResultQualityReview,
) -> ResultQualityState:
    unresolved_issues = _support.replace_scope_issues(
        state.unresolved_issues,
        scope="result_visual_review",
        replacement=tuple(issue for issue in review.issues if not issue.resolved),
    )
    if review.requires_user_review and not _support.blocking_issues(unresolved_issues):
        unresolved_issues = (
            *unresolved_issues,
            QualityIssue(
                issue_code="result_review_required",
                severity=QualitySeverity.error,
                scope="result_visual_review",
                summary="reviewer requires user review of the final image",
                evidence_references=("result-image-review",),
                recommended_action="review final image preview",
            ),
        )
    status = (
        ResultQualityStatus.reviewed
        if not _support.blocking_issues(unresolved_issues) and not review.requires_user_review
        else ResultQualityStatus.needs_review
    )
    return state.model_copy(
        update={
            "rendered_image_reference": review.rendered_image_reference.reference_id,
            "unresolved_issues": unresolved_issues,
            "visual_quality_checked": True,
            "status": status,
        }
    )


def plan_result_corrections(state: ResultQualityState) -> ResultQualityState:
    if state.correction_attempts >= MAX_RESULT_CORRECTION_ATTEMPTS:
        return state.model_copy(
            update={
                "correction_plan": (),
                "status": ResultQualityStatus.needs_review,
            }
        )
    corrections = tuple(
        correction
        for issue in state.unresolved_issues
        if not issue.resolved
        for correction in _support.corrections_for_issue(issue)
    )
    return state.model_copy(
        update={
            "correction_plan": corrections,
            "status": (
                ResultQualityStatus.correction_planned
                if corrections
                else ResultQualityStatus.reviewed
            ),
        }
    )


def apply_result_corrections(state: ResultQualityState) -> ResultQualityState:
    if not state.correction_plan:
        return state
    applied_actions = tuple(correction.action for correction in state.correction_plan)
    return state.model_copy(
        update={
            "correction_attempts": min(
                state.correction_attempts + 1,
                MAX_RESULT_CORRECTION_ATTEMPTS,
            ),
            "applied_correction_actions": (
                *state.applied_correction_actions,
                *applied_actions,
            ),
            "status": ResultQualityStatus.correcting,
        }
    )


def route_result_decision(state: ResultQualityState) -> ResultRoute:
    if state.final_image_result is not None:
        if (
            state.final_image_result.approval_status is ApprovalStatus.approved_automatic
            and not state.final_image_result.requires_user_confirmation
        ):
            return ResultRoute.complete
        return ResultRoute.interrupt_user

    if state.correction_plan and state.correction_attempts < MAX_RESULT_CORRECTION_ATTEMPTS:
        return ResultRoute.retry_quality
    if _support.blocking_issues(state.unresolved_issues):
        return ResultRoute.interrupt_user
    return ResultRoute.complete


def route_result_decision_node(state: ResultQualityState) -> ResultQualityState:
    route = route_result_decision(state)
    status = (
        ResultQualityStatus.correcting
        if route is ResultRoute.retry_quality
        else ResultQualityStatus.needs_review
        if route is ResultRoute.interrupt_user
        else ResultQualityStatus.approved
    )
    return state.model_copy(update={"last_route": route, "status": status})


def interrupt_for_result_review(state: ResultQualityState) -> ResultQualityState:
    affected_region_ids = _support.affected_region_ids(state.unresolved_issues)
    issue_summaries = tuple(
        issue.summary for issue in state.unresolved_issues if not issue.resolved
    )
    payload = ResultReviewInterruptPayload(
        revision_id=state.revision_id,
        affected_region_ids=affected_region_ids,
        issue_summaries=issue_summaries or ("result requires user review",),
        preview_references=tuple(
            reference
            for reference in (
                state.source_image_reference,
                state.inpainted_image_reference,
                state.rendered_image_reference,
            )
            if reference is not None
        ),
    )
    finalized_state = finalize_result(state)
    return finalized_state.model_copy(
        update={
            "interrupt_payload": payload,
            "status": ResultQualityStatus.needs_review,
        }
    )


def finalize_result(
    state: ResultQualityState,
    *,
    force_approval_record: ForceApprovalRecord | None = None,
) -> ResultQualityState:
    requires_user_confirmation = _support.required_confirmations(
        requires_user_confirmation=state.requires_user_confirmation,
        visual_quality_checked=state.visual_quality_checked,
    )
    if force_approval_record is not None:
        approval_status = ApprovalStatus.approved_forced
    elif (
        not _support.blocking_issues(state.unresolved_issues)
        and state.visual_quality_checked
        and not requires_user_confirmation
    ):
        approval_status = ApprovalStatus.approved_automatic
    else:
        approval_status = ApprovalStatus.needs_review
    final_image_result = FinalImageResult(
        revision_id=state.revision_id,
        approval_status=approval_status,
        unresolved_issues=state.unresolved_issues,
        requires_user_confirmation=requires_user_confirmation,
        visual_quality_checked=state.visual_quality_checked,
    )
    export_decision = evaluate_export_eligibility(
        final_image_result,
        force_approval_record=force_approval_record,
    )
    status = (
        ResultQualityStatus.approved
        if export_decision.allowed and force_approval_record is None
        else ResultQualityStatus.needs_review
        if not export_decision.allowed
        else ResultQualityStatus.finalized
    )
    return state.model_copy(
        update={
            "final_image_result": final_image_result,
            "export_decision": export_decision,
            "status": status,
        }
    )


def finalize_result_quality(state: ResultQualityState) -> ResultQualityState:
    return finalize_result(state)


def _build_langgraph(*, reviewer: ReviewAdapter | None) -> Any:
    builder = StateGraph(_GraphState)
    sync_nodes = {
        "validate_render_structure": validate_render_structure_node,
        "inspect_layout": inspect_layout,
        "inspect_inpainting": inspect_inpainting,
        "plan_result_corrections": plan_result_corrections,
        "route_result_decision": route_result_decision_node,
        "apply_result_corrections": apply_result_corrections,
        "interrupt_for_result_review": interrupt_for_result_review,
        "finalize_result": finalize_result,
    }
    for name, node in sync_nodes.items():
        builder.add_node(name, _sync_node(node))
    builder.add_node(
        "review_final_image",
        _async_node(lambda state: review_final_image(state, reviewer=reviewer)),
    )
    edges = (
        (START, "validate_render_structure"),
        ("validate_render_structure", "inspect_layout"),
        ("inspect_layout", "inspect_inpainting"),
        ("inspect_inpainting", "review_final_image"),
        ("review_final_image", "plan_result_corrections"),
        ("plan_result_corrections", "route_result_decision"),
    )
    for source, target in edges:
        builder.add_edge(source, target)
    builder.add_conditional_edges(
        "route_result_decision",
        _route_after_result_review,
        {
            ResultRoute.retry_quality.value: "apply_result_corrections",
            ResultRoute.interrupt_user.value: "interrupt_for_result_review",
            ResultRoute.complete.value: "finalize_result",
        },
    )
    builder.add_edge("apply_result_corrections", "inspect_layout")
    builder.add_edge("interrupt_for_result_review", END)
    builder.add_edge("finalize_result", END)
    return builder.compile()


def validate_render_structure_node(state: ResultQualityState) -> ResultQualityState:
    return validate_render_structure(state=state)


def _sync_node(func: Any) -> Any:
    def node(graph_state: _GraphState) -> _GraphState:
        return {"workflow_state": func(graph_state["workflow_state"])}

    return node


def _async_node(func: Any) -> Any:
    async def node(graph_state: _GraphState) -> _GraphState:
        return {"workflow_state": await func(graph_state["workflow_state"])}

    return node


def _route_after_result_review(graph_state: _GraphState) -> str:
    state = graph_state["workflow_state"]
    route = state.last_route or route_result_decision(state)
    return route.value


def _add_user_confirmation(state: ResultQualityState, reason: str) -> ResultQualityState:
    return state.model_copy(
        update={
            "requires_user_confirmation": _support.add_unique_confirmation(
                state.requires_user_confirmation,
                reason,
            ),
            "visual_quality_checked": False,
            "status": ResultQualityStatus.needs_review,
        }
    )
