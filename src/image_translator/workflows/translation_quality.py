from __future__ import annotations

from typing import Any, TypedDict, cast

from langgraph.graph import END, START, StateGraph

from image_translator.domain.errors import (
    InvalidRegionError,
    ProviderConfigError,
    TranslationResultMismatchError,
)
from image_translator.domain.ids import JobId, RegionId, RevisionId
from image_translator.domain.job import JobDefinition
from image_translator.domain.ocr import NormalizedTextRegion
from image_translator.domain.quality import (
    ApprovalStatus,
    QualityIssue,
    QualitySeverity,
)
from image_translator.domain.translation import (
    TranslationCandidate,
    TranslationRequest,
    TranslationResult,
)
from image_translator.providers.base import (
    OCRAdapter,
    OCRCorrectionRequest,
    PageContextRequest,
    PageReview,
    ProviderType,
    ReviewAdapter,
    TranslationReviewRequest,
    TranslatorAdapter,
)
from image_translator.services.layout_analysis import analyze_reading_order
from image_translator.services.quality_policy import (
    DEFAULT_TRANSLATION_QUALITY_POLICY,
    TranslationQualityPolicy,
    evaluate_translation_review,
)
from image_translator.services.text_role_classifier import classify_text_roles
from image_translator.workflows import translation_quality_support as _support
from image_translator.workflows.translation_quality_models import (
    OCRResolution as OCRResolution,
)
from image_translator.workflows.translation_quality_models import (
    RegionOCRCandidates as RegionOCRCandidates,
)
from image_translator.workflows.translation_quality_models import (
    RegionTranslationAttempt as RegionTranslationAttempt,
)
from image_translator.workflows.translation_quality_models import (
    TranslationQualityState as TranslationQualityState,
)
from image_translator.workflows.translation_quality_models import (
    TranslationQualityStatus as TranslationQualityStatus,
)
from image_translator.workflows.translation_quality_models import (
    TranslationRoute as TranslationRoute,
)
from image_translator.workflows.translation_quality_models import (
    TranslationWorkflowInput as TranslationWorkflowInput,
)
from image_translator.workflows.translation_quality_models import (
    TranslationWorkflowResult as TranslationWorkflowResult,
)
from image_translator.workflows.translation_quality_models import (
    TranslationWorkflowState as TranslationWorkflowState,
)
from image_translator.workflows.translation_quality_models import (
    WorkflowInterruptPayload as WorkflowInterruptPayload,
)


class _GraphState(TypedDict):
    workflow_state: TranslationWorkflowState


class TranslationQualityGraph:
    def __init__(
        self,
        *,
        translator: TranslatorAdapter,
        reviewer: ReviewAdapter,
        secondary_ocr: OCRAdapter | None = None,
        policy: TranslationQualityPolicy = DEFAULT_TRANSLATION_QUALITY_POLICY,
    ) -> None:
        self._translator = translator
        self._reviewer = reviewer
        self._secondary_ocr = secondary_ocr
        self._policy = policy
        self._compiled_graph: Any = _build_langgraph(
            translator=translator,
            reviewer=reviewer,
            secondary_ocr=secondary_ocr,
            policy=policy,
        )

    async def run(self, workflow_input: TranslationWorkflowInput) -> TranslationWorkflowResult:
        _support.validate_provider_capability(
            adapter_capabilities=self._translator.capabilities(),
            expected_type=ProviderType.translator,
            source_language=workflow_input.source_language,
            target_language=workflow_input.target_language,
        )
        _support.validate_provider_capability(
            adapter_capabilities=self._reviewer.capabilities(),
            expected_type=ProviderType.reviewer,
            source_language=workflow_input.source_language,
            target_language=workflow_input.target_language,
        )
        initial_state: _GraphState = {
            "workflow_state": create_translation_workflow_state(workflow_input)
        }
        final_state = cast(_GraphState, await self._compiled_graph.ainvoke(initial_state))
        workflow_state = final_state["workflow_state"]
        if workflow_state.result is not None:
            return workflow_state.result
        return finalize_translation(workflow_state).result_or_raise()


def create_translation_workflow_state(
    workflow_input: TranslationWorkflowInput,
) -> TranslationWorkflowState:
    return TranslationWorkflowState(
        input=workflow_input,
        regions=workflow_input.regions,
        translation_attempts_by_region=tuple(
            RegionTranslationAttempt(region_id=region.region_id)
            for region in workflow_input.regions
        ),
    )


def create_translation_quality_state(
    *,
    job_id: JobId,
    revision_id: RevisionId,
    regions: tuple[NormalizedTextRegion, ...],
) -> TranslationQualityState:
    source_language = regions[0].source_language if regions else "unknown"
    workflow_input = TranslationWorkflowInput(
        job_id=job_id,
        project_id="project-unknown",
        revision_id=revision_id,
        source_image_reference=f"source-{job_id}",
        source_language=source_language,
        target_language="unknown",
        regions=regions,
        primary_ocr_snapshots=(),
    )
    return create_translation_workflow_state(workflow_input)


def prepare_page(state: TranslationWorkflowState) -> TranslationWorkflowState:
    region_ids = tuple(region.region_id for region in state.regions)
    duplicate_region_ids = _support.duplicate_values(region_ids)
    if duplicate_region_ids:
        raise InvalidRegionError(
            "duplicate normalized region IDs: " + ", ".join(duplicate_region_ids)
        )
    if not region_ids:
        raise InvalidRegionError("at least one normalized text region is required")
    if state.input.visual_mode and not state.input.image_transmission_consent:
        raise ProviderConfigError("visual mode requires image transmission consent")
    return state.model_copy(update={"status": TranslationQualityStatus.prepared})


def score_ocr_risk(state: TranslationWorkflowState) -> TranslationWorkflowState:
    primary_by_region = {
        raw_region.region_id: raw_region for raw_region in state.input.primary_ocr_snapshots
    }
    candidate_sets = tuple(
        _support.ocr_candidate_set_for_region(
            region,
            primary_by_region.get(region.region_id),
        )
        for region in state.regions
    )
    return state.model_copy(
        update={
            "ocr_candidates_by_region": candidate_sets,
            "status": TranslationQualityStatus.ocr_scored,
        }
    )


async def cross_check_ocr(
    state: TranslationWorkflowState,
    *,
    secondary_ocr: OCRAdapter | None = None,
) -> TranslationWorkflowState:
    risky_region_ids = tuple(
        candidate_set.region_id
        for candidate_set in state.ocr_candidates_by_region
        if candidate_set.requires_cross_check
    )
    if secondary_ocr is None or not risky_region_ids:
        return state

    raw_regions = await secondary_ocr.detect_regions(
        _support.source_image_reference(state.input),
        (state.input.source_language,),
    )
    secondary_candidates_by_region = {
        raw_region.region_id: _support.ocr_candidate_from_raw(
            raw_region,
            state.input.source_language,
        )
        for raw_region in raw_regions
        if raw_region.region_id in risky_region_ids
    }
    candidate_sets = tuple(
        candidate_set.model_copy(
            update={
                "candidates": (
                    *candidate_set.candidates,
                    secondary_candidates_by_region[candidate_set.region_id],
                )
            }
        )
        if candidate_set.region_id in secondary_candidates_by_region
        else candidate_set
        for candidate_set in state.ocr_candidates_by_region
    )
    return state.model_copy(update={"ocr_candidates_by_region": candidate_sets})


async def correct_ocr_with_vision(
    state: TranslationWorkflowState,
    *,
    reviewer: ReviewAdapter | None = None,
) -> TranslationWorkflowState:
    if reviewer is None:
        return state

    updated_sets: tuple[RegionOCRCandidates, ...] = ()
    capabilities = reviewer.capabilities()
    for candidate_set in state.ocr_candidates_by_region:
        if not candidate_set.requires_vision_correction:
            updated_sets = (*updated_sets, candidate_set)
            continue
        visual_references = _support.ocr_correction_visual_references(
            state.input,
            capabilities,
            candidate_set.region_id,
        )
        if not visual_references:
            updated_sets = (*updated_sets, candidate_set)
            continue
        review = await reviewer.correct_ocr(
            OCRCorrectionRequest(
                candidates=candidate_set.candidates,
                visual_references=visual_references,
            )
        )
        updated_sets = (*updated_sets, _support.with_ocr_correction(candidate_set, review))

    return state.model_copy(update={"ocr_candidates_by_region": updated_sets})


def resolve_ocr(state: TranslationWorkflowState) -> TranslationWorkflowState:
    resolutions: tuple[OCRResolution, ...] = ()
    updated_regions: tuple[NormalizedTextRegion, ...] = ()
    issues = _support.issues_for_scopes(state.unresolved_issues, excluded_scopes=("ocr",))

    for region in state.regions:
        candidate_set = _support.candidate_set_for_region(
            state.ocr_candidates_by_region,
            region.region_id,
        )
        selected = _support.select_ocr_candidate(candidate_set)
        requires_review = (
            candidate_set.risk_score.requires_review
            if candidate_set.risk_score is not None
            else False
        ) and selected.confidence < 0.9
        resolutions = (
            *resolutions,
            OCRResolution(
                region_id=region.region_id,
                approved_text=selected.text,
                requires_user_review=requires_review,
                evidence_summary=selected.evidence_summary,
            ),
        )
        updated_regions = (
            *updated_regions,
            region.model_copy(update={"source_text": selected.text}),
        )
        if requires_review:
            issues = (
                *issues,
                QualityIssue(
                    issue_code=f"ocr_review_required_{region.region_id}",
                    severity=QualitySeverity.error,
                    scope="ocr",
                    region_ids=(region.region_id,),
                    summary="OCR result needs user review before translation",
                    evidence_references=(selected.evidence_summary,),
                    recommended_action="review OCR text or reading order",
                ),
            )

    return state.model_copy(
        update={
            "regions": updated_regions,
            "ocr_decisions_by_region": resolutions,
            "unresolved_issues": issues,
            "status": (
                TranslationQualityStatus.needs_review
                if _support.has_ocr_review_issue(issues)
                else TranslationQualityStatus.ocr_resolved
            ),
        }
    )


def classify_page_layout(state: TranslationWorkflowState) -> TranslationWorkflowState:
    layout_result = analyze_reading_order(state.regions, raise_on_uncertain=False)
    role_result = classify_text_roles(layout_result.regions)
    issues = (
        *state.unresolved_issues,
        *_support.review_reason_issues(
            scope="reading_order",
            reasons=layout_result.review_reasons,
            issue_prefix="reading_order_review_required",
        ),
        *_support.review_reason_issues(
            scope="text_role",
            reasons=role_result.review_reasons,
            issue_prefix="text_role_review_required",
        ),
    )
    return state.model_copy(
        update={
            "regions": role_result.regions,
            "reading_order_decision": (
                "requires_user_review"
                if layout_result.requires_review or role_result.requires_review
                else "automatic"
            ),
            "unresolved_issues": issues,
            "status": TranslationQualityStatus.layout_classified,
        }
    )


async def build_page_context(
    state: TranslationWorkflowState,
    *,
    reviewer: ReviewAdapter,
) -> TranslationWorkflowState:
    capabilities = reviewer.capabilities()
    page_context = await reviewer.build_page_context(
        PageContextRequest(
            region_ids=tuple(region.region_id for region in state.regions),
            visual_references=_support.page_visual_references(state.input, capabilities),
        )
    )
    page_context_reference = (
        page_context.usage_metadata.request_id
        if page_context.usage_metadata is not None
        else f"page-context-{state.input.revision_id}"
    )
    return state.model_copy(
        update={
            "page_context": page_context,
            "page_context_reference": page_context_reference,
            "status": TranslationQualityStatus.context_built,
        }
    )


async def translate_page(
    state: TranslationWorkflowState,
    *,
    translator: TranslatorAdapter,
) -> TranslationWorkflowState:
    state_with_requests = build_translation_requests(
        state=state,
        source_language=state.input.source_language,
        target_language=state.input.target_language,
        page_context_reference=state.page_context_reference,
        include_crop_references=_support.can_send_crop_references(
            state.input,
            translator.capabilities(),
        ),
    )
    if not state_with_requests.translation_requests:
        return state_with_requests.model_copy(
            update={"status": TranslationQualityStatus.translated}
        )
    candidates = await translator.translate_page(state_with_requests.translation_requests)
    return attach_translation_candidates(state=state_with_requests, candidates=candidates)


def build_translation_requests(
    *,
    state: TranslationWorkflowState,
    job: JobDefinition | None = None,
    source_language: str | None = None,
    target_language: str | None = None,
    page_context_reference: str | None = None,
    include_crop_references: bool = False,
) -> TranslationWorkflowState:
    active_source_language = source_language or (
        job.source_language if job else state.input.source_language
    )
    active_target_language = target_language or (
        job.target_language if job else state.input.target_language
    )
    approved_region_ids = frozenset(
        translation.region_id for translation in state.approved_translations
    )
    ordered_regions = _support.ordered_regions(
        tuple(region for region in state.regions if region.region_id not in approved_region_ids)
    )
    requests = tuple(
        TranslationRequest(
            region_id=region.region_id,
            source_text=region.source_text,
            source_language=active_source_language,
            target_language=active_target_language,
            text_role=region.text_role,
            writing_mode=region.writing_mode,
            page_context_reference=page_context_reference,
            region_context_summary=None,
            project_context_version=state.input.approved_project_context_version,
            reviewer_feedback=_support.reviewer_feedback_for_region(state, region.region_id),
            image_reference=f"crop-{region.region_id}" if include_crop_references else None,
        )
        for region in ordered_regions
    )

    return state.model_copy(
        update={
            "page_context_reference": page_context_reference,
            "translation_requests": requests,
            "status": TranslationQualityStatus.translating,
        }
    )


def attach_translation_candidates(
    *,
    state: TranslationWorkflowState,
    candidates: tuple[TranslationCandidate, ...],
) -> TranslationWorkflowState:
    _support.validate_translation_structure(state.translation_requests, candidates)
    return state.model_copy(
        update={
            "translation_candidates": (*state.translation_candidates, *candidates),
            "current_translation_candidates": candidates,
            "translation_attempts_by_region": _support.increment_attempts(
                state.translation_attempts_by_region,
                tuple(request.region_id for request in state.translation_requests),
            ),
            "status": TranslationQualityStatus.translated,
        }
    )


def validate_translation_structure(state: TranslationWorkflowState) -> TranslationWorkflowState:
    _support.validate_translation_structure(
        state.translation_requests,
        state.current_translation_candidates,
    )
    return state.model_copy(update={"status": TranslationQualityStatus.structure_validated})


async def review_page_translation(
    state: TranslationWorkflowState,
    *,
    reviewer: ReviewAdapter,
) -> TranslationWorkflowState:
    if not state.current_translation_candidates:
        return state.model_copy(update={"status": TranslationQualityStatus.reviewed})
    capabilities = reviewer.capabilities()
    page_review = await reviewer.review_translation(
        TranslationReviewRequest(
            region_ids=tuple(
                candidate.region_id for candidate in state.current_translation_candidates
            ),
            candidates=state.current_translation_candidates,
            visual_references=_support.translation_review_visual_references(
                state.input,
                capabilities,
                state.current_translation_candidates,
            ),
        )
    )
    return apply_page_review(
        state=state,
        page_review=page_review,
        policy=DEFAULT_TRANSLATION_QUALITY_POLICY,
    )


def apply_page_review(
    *,
    state: TranslationWorkflowState,
    page_review: PageReview,
    policy: TranslationQualityPolicy = DEFAULT_TRANSLATION_QUALITY_POLICY,
) -> TranslationWorkflowState:
    candidates_by_region = {
        candidate.region_id: candidate for candidate in state.current_translation_candidates
    }
    current_region_ids = tuple(candidates_by_region)
    _support.validate_review_structure(current_region_ids, page_review.region_reviews)
    review_reference = (
        page_review.usage_metadata.request_id
        if page_review.usage_metadata is not None
        else None
    )
    approved_translations = state.approved_translations
    unresolved_issues = _support.issues_outside_regions(
        state.unresolved_issues,
        tuple(review.region_id for review in page_review.region_reviews),
    )

    for review in page_review.region_reviews:
        decision = evaluate_translation_review(review, policy)
        candidate = candidates_by_region.get(review.region_id)
        if candidate is None:
            raise TranslationResultMismatchError(
                f"review returned unknown region ID {review.region_id}"
            )

        if decision.approved:
            approved_translations = _support.append_approved_translation(
                approved_translations,
                TranslationResult(
                    region_id=review.region_id,
                    approved_translated_text=candidate.translated_text,
                    source_language=_support.request_for_region(
                        state.translation_requests,
                        review.region_id,
                    ).source_language,
                    target_language=_support.request_for_region(
                        state.translation_requests,
                        review.region_id,
                    ).target_language,
                    selected_candidate_id=candidate.candidate_id,
                    approval_status=ApprovalStatus.approved_automatic.value,
                    review_reference=review_reference,
                ),
            )
        else:
            review_issues = _support.unresolved_review_issues(review)
            unresolved_issues = (
                *unresolved_issues,
                *(
                    review_issues
                    if review_issues
                    else (_support.issue_from_rejected_review(review),)
                ),
            )

    unresolved_issues = (*unresolved_issues, *page_review.page_level_issues)
    status = (
        TranslationQualityStatus.approved
        if len(approved_translations) == len(state.regions)
        and not _support.blocking_issues(unresolved_issues)
        else TranslationQualityStatus.reviewed
    )
    return state.model_copy(
        update={
            "reviews": (*state.reviews, *page_review.region_reviews),
            "approved_translations": _support.ordered_translations(
                approved_translations,
                state.regions,
            ),
            "unresolved_issues": unresolved_issues,
            "status": status,
        }
    )


def route_translation_decision(state: TranslationWorkflowState) -> TranslationRoute:
    if _support.has_ocr_review_issue(state.unresolved_issues):
        return TranslationRoute.interrupt_user

    latest_reviews = _support.latest_reviews_by_region(state.reviews)
    retry_region_ids: tuple[RegionId, ...] = ()
    interrupt_region_ids: tuple[RegionId, ...] = ()

    for candidate in state.current_translation_candidates:
        if _support.is_approved(state, candidate.region_id):
            continue
        review = latest_reviews.get(candidate.region_id)
        if review is None:
            interrupt_region_ids = (*interrupt_region_ids, candidate.region_id)
            continue
        if (
            _support.attempt_count(state.translation_attempts_by_region, candidate.region_id) < 2
            and _support.has_actionable_feedback(review)
        ):
            retry_region_ids = (*retry_region_ids, candidate.region_id)
        else:
            interrupt_region_ids = (*interrupt_region_ids, candidate.region_id)

    if retry_region_ids:
        return TranslationRoute.retry_quality
    if interrupt_region_ids or _support.unapproved_region_ids(state):
        return TranslationRoute.interrupt_user
    return TranslationRoute.complete


def route_translation_decision_node(state: TranslationWorkflowState) -> TranslationWorkflowState:
    route = route_translation_decision(state)
    status = (
        TranslationQualityStatus.retrying
        if route is TranslationRoute.retry_quality
        else TranslationQualityStatus.needs_review
        if route is TranslationRoute.interrupt_user
        else TranslationQualityStatus.approved
    )
    return state.model_copy(update={"last_route": route, "status": status})


def interrupt_for_translation_review(
    state: TranslationWorkflowState,
) -> TranslationWorkflowState:
    affected_region_ids = _support.affected_interrupt_region_ids(state)
    issue_summaries = tuple(
        issue.summary
        for issue in state.unresolved_issues
        if not issue.resolved and _support.issue_affects_any(issue, affected_region_ids)
    )
    payload = WorkflowInterruptPayload(
        interrupt_type="translation_review",
        job_id=state.input.job_id,
        revision_id=state.input.revision_id,
        affected_region_ids=affected_region_ids,
        issue_summaries=issue_summaries or ("translation requires user review",),
        preview_references=tuple(
            f"region-preview-{region_id}" for region_id in affected_region_ids
        ),
        allowed_actions=(
            "edit_translation",
            "edit_ocr",
            "retry_translation",
            "force_approve",
            "cancel",
        ),
        recommended_action="review affected regions before rendering",
    )
    result = _support.result_from_state(state, interrupt_payload=payload)
    return state.model_copy(
        update={
            "interrupt_payload": payload,
            "result": result,
            "status": TranslationQualityStatus.needs_review,
        }
    )


def finalize_translation(state: TranslationWorkflowState) -> TranslationWorkflowState:
    result = _support.result_from_state(state, interrupt_payload=state.interrupt_payload)
    return state.model_copy(
        update={
            "result": result,
            "status": (
                TranslationQualityStatus.finalized
                if not result.unresolved_issues
                else TranslationQualityStatus.needs_review
            ),
        }
    )


def _build_langgraph(
    *,
    translator: TranslatorAdapter,
    reviewer: ReviewAdapter,
    secondary_ocr: OCRAdapter | None,
    policy: TranslationQualityPolicy,
) -> Any:
    builder = StateGraph(_GraphState)

    builder.add_node("prepare_page", _sync_node(prepare_page))
    builder.add_node("score_ocr_risk", _sync_node(score_ocr_risk))
    builder.add_node(
        "cross_check_ocr",
        _async_node(lambda state: cross_check_ocr(state, secondary_ocr=secondary_ocr)),
    )
    builder.add_node(
        "correct_ocr_with_vision",
        _async_node(lambda state: correct_ocr_with_vision(state, reviewer=reviewer)),
    )
    builder.add_node("resolve_ocr", _sync_node(resolve_ocr))
    builder.add_node("classify_page_layout", _sync_node(classify_page_layout))
    builder.add_node(
        "build_page_context",
        _async_node(lambda state: build_page_context(state, reviewer=reviewer)),
    )
    builder.add_node(
        "translate_page",
        _async_node(lambda state: translate_page(state, translator=translator)),
    )
    builder.add_node("validate_translation_structure", _sync_node(validate_translation_structure))
    builder.add_node(
        "review_page_translation",
        _async_node(lambda state: review_page_translation(state, reviewer=reviewer)),
    )
    builder.add_node(
        "route_translation_decision",
        _sync_node(lambda state: route_translation_decision_node_with_policy(state, policy)),
    )
    builder.add_node(
        "interrupt_for_translation_review",
        _sync_node(interrupt_for_translation_review),
    )
    builder.add_node("finalize_translation", _sync_node(finalize_translation))

    builder.add_edge(START, "prepare_page")
    builder.add_edge("prepare_page", "score_ocr_risk")
    builder.add_edge("score_ocr_risk", "cross_check_ocr")
    builder.add_edge("cross_check_ocr", "correct_ocr_with_vision")
    builder.add_edge("correct_ocr_with_vision", "resolve_ocr")
    builder.add_conditional_edges(
        "resolve_ocr",
        _route_after_ocr,
        {
            "interrupt_user": "interrupt_for_translation_review",
            "continue": "classify_page_layout",
        },
    )
    builder.add_edge("classify_page_layout", "build_page_context")
    builder.add_edge("build_page_context", "translate_page")
    builder.add_edge("translate_page", "validate_translation_structure")
    builder.add_edge("validate_translation_structure", "review_page_translation")
    builder.add_edge("review_page_translation", "route_translation_decision")
    builder.add_conditional_edges(
        "route_translation_decision",
        _route_after_translation_review,
        {
            TranslationRoute.retry_quality.value: "translate_page",
            TranslationRoute.interrupt_user.value: "interrupt_for_translation_review",
            TranslationRoute.complete.value: "finalize_translation",
        },
    )
    builder.add_edge("interrupt_for_translation_review", END)
    builder.add_edge("finalize_translation", END)
    return builder.compile()


def route_translation_decision_node_with_policy(
    state: TranslationWorkflowState,
    policy: TranslationQualityPolicy,
) -> TranslationWorkflowState:
    _ = policy
    return route_translation_decision_node(state)


def _sync_node(func: Any) -> Any:
    def node(graph_state: _GraphState) -> _GraphState:
        return {"workflow_state": func(graph_state["workflow_state"])}

    return node


def _async_node(func: Any) -> Any:
    async def node(graph_state: _GraphState) -> _GraphState:
        return {"workflow_state": await func(graph_state["workflow_state"])}

    return node


def _route_after_ocr(graph_state: _GraphState) -> str:
    state = graph_state["workflow_state"]
    if _support.has_ocr_review_issue(state.unresolved_issues):
        return "interrupt_user"
    return "continue"


def _route_after_translation_review(graph_state: _GraphState) -> str:
    state = graph_state["workflow_state"]
    route = state.last_route or route_translation_decision(state)
    return route.value
