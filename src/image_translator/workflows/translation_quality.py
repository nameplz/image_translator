from __future__ import annotations

from enum import StrEnum

from image_translator.domain._base import DomainModel, NonEmptyStr
from image_translator.domain.errors import InvalidRegionError, TranslationResultMismatchError
from image_translator.domain.ids import JobId, RegionId, RevisionId
from image_translator.domain.job import JobDefinition
from image_translator.domain.ocr import NormalizedTextRegion
from image_translator.domain.quality import (
    ApprovalStatus,
    QualityIssue,
    QualitySeverity,
    RegionReview,
)
from image_translator.domain.translation import (
    TranslationCandidate,
    TranslationRequest,
    TranslationResult,
)
from image_translator.providers.base import PageReview
from image_translator.services.quality_policy import (
    DEFAULT_TRANSLATION_QUALITY_POLICY,
    TranslationQualityPolicy,
    evaluate_translation_review,
)


class TranslationQualityStatus(StrEnum):
    pending = "pending"
    prepared = "prepared"
    translated = "translated"
    reviewed = "reviewed"
    needs_review = "needs_review"
    approved = "approved"


class TranslationRoute(StrEnum):
    complete = "complete"
    interrupt_user = "interrupt_user"


class TranslationQualityState(DomainModel):
    job_id: JobId
    revision_id: RevisionId
    regions: tuple[NormalizedTextRegion, ...]
    page_context_reference: NonEmptyStr | None = None
    translation_requests: tuple[TranslationRequest, ...] = ()
    translation_candidates: tuple[TranslationCandidate, ...] = ()
    reviews: tuple[RegionReview, ...] = ()
    approved_translations: tuple[TranslationResult, ...] = ()
    unresolved_issues: tuple[QualityIssue, ...] = ()
    status: TranslationQualityStatus = TranslationQualityStatus.pending


def create_translation_quality_state(
    *,
    job_id: JobId,
    revision_id: RevisionId,
    regions: tuple[NormalizedTextRegion, ...],
) -> TranslationQualityState:
    return TranslationQualityState(
        job_id=job_id,
        revision_id=revision_id,
        regions=regions,
    )


def prepare_page(state: TranslationQualityState) -> TranslationQualityState:
    region_ids = tuple(region.region_id for region in state.regions)
    duplicate_region_ids = _duplicate_values(region_ids)
    if duplicate_region_ids:
        raise InvalidRegionError(
            "duplicate normalized region IDs: " + ", ".join(duplicate_region_ids)
        )
    if not region_ids:
        raise InvalidRegionError("at least one normalized text region is required")

    return state.model_copy(update={"status": TranslationQualityStatus.prepared})


def build_translation_requests(
    *,
    state: TranslationQualityState,
    job: JobDefinition,
    page_context_reference: str | None = None,
    include_crop_references: bool = False,
) -> TranslationQualityState:
    ordered_regions = tuple(
        sorted(
            state.regions,
            key=lambda region: (
                region.reading_order.page_index,
                region.reading_order.group_index,
                region.reading_order.item_index,
                region.region_id,
            ),
        )
    )
    requests = tuple(
        TranslationRequest(
            region_id=region.region_id,
            source_text=region.source_text,
            source_language=job.source_language,
            target_language=job.target_language,
            text_role=region.text_role,
            writing_mode=region.writing_mode,
            page_context_reference=page_context_reference,
            project_context_version=None,
            image_reference=(
                f"crop-{region.region_id}" if include_crop_references else None
            ),
        )
        for region in ordered_regions
    )

    return state.model_copy(
        update={
            "page_context_reference": page_context_reference,
            "translation_requests": requests,
        }
    )


def attach_translation_candidates(
    *,
    state: TranslationQualityState,
    candidates: tuple[TranslationCandidate, ...],
) -> TranslationQualityState:
    _validate_translation_structure(state.translation_requests, candidates)
    return state.model_copy(
        update={
            "translation_candidates": candidates,
            "status": TranslationQualityStatus.translated,
        }
    )


def apply_page_review(
    *,
    state: TranslationQualityState,
    page_review: PageReview,
    policy: TranslationQualityPolicy = DEFAULT_TRANSLATION_QUALITY_POLICY,
) -> TranslationQualityState:
    candidates_by_region = {
        candidate.region_id: candidate for candidate in state.translation_candidates
    }
    review_reference = (
        page_review.usage_metadata.request_id
        if page_review.usage_metadata is not None
        else None
    )
    approved_translations: tuple[TranslationResult, ...] = ()
    unresolved_issues: tuple[QualityIssue, ...] = ()

    for review in page_review.region_reviews:
        decision = evaluate_translation_review(review, policy)
        candidate = candidates_by_region.get(review.region_id)
        if candidate is None:
            raise TranslationResultMismatchError(
                f"review returned unknown region ID {review.region_id}"
            )

        if decision.approved:
            approved_translations = (
                *approved_translations,
                TranslationResult(
                    region_id=review.region_id,
                    approved_translated_text=candidate.translated_text,
                    source_language=_request_for_region(
                        state.translation_requests,
                        review.region_id,
                    ).source_language,
                    target_language=_request_for_region(
                        state.translation_requests,
                        review.region_id,
                    ).target_language,
                    selected_candidate_id=candidate.candidate_id,
                    approval_status=ApprovalStatus.approved_automatic.value,
                    review_reference=review_reference,
                ),
            )
        else:
            review_issues = _unresolved_review_issues(review)
            unresolved_issues = (
                *unresolved_issues,
                *(
                    review_issues
                    if review_issues
                    else (_issue_from_rejected_review(review),)
                ),
            )

    status = (
        TranslationQualityStatus.approved
        if not unresolved_issues
        else TranslationQualityStatus.needs_review
    )
    return state.model_copy(
        update={
            "reviews": page_review.region_reviews,
            "approved_translations": approved_translations,
            "unresolved_issues": unresolved_issues,
            "status": status,
        }
    )


def route_translation_decision(state: TranslationQualityState) -> TranslationRoute:
    if state.unresolved_issues:
        return TranslationRoute.interrupt_user
    return TranslationRoute.complete


def _validate_translation_structure(
    requests: tuple[TranslationRequest, ...],
    candidates: tuple[TranslationCandidate, ...],
) -> None:
    request_ids = tuple(request.region_id for request in requests)
    candidate_ids = tuple(candidate.region_id for candidate in candidates)

    if len(candidates) != len(requests):
        raise TranslationResultMismatchError("translation candidate cardinality mismatch")

    duplicate_candidate_ids = _duplicate_values(candidate_ids)
    if duplicate_candidate_ids:
        raise TranslationResultMismatchError(
            "duplicate translation candidate region IDs: "
            + ", ".join(duplicate_candidate_ids)
        )

    missing_ids = tuple(region_id for region_id in request_ids if region_id not in candidate_ids)
    unknown_ids = tuple(region_id for region_id in candidate_ids if region_id not in request_ids)
    if missing_ids or unknown_ids:
        raise TranslationResultMismatchError(
            "translation candidate region ID mismatch; "
            f"missing={missing_ids}, unknown={unknown_ids}"
        )

    empty_ids = tuple(
        candidate.region_id for candidate in candidates if not candidate.translated_text.strip()
    )
    if empty_ids:
        raise TranslationResultMismatchError(
            "empty translation candidate text for region IDs: " + ", ".join(empty_ids)
        )


def _request_for_region(
    requests: tuple[TranslationRequest, ...],
    region_id: RegionId,
) -> TranslationRequest:
    request = next(
        (request for request in requests if request.region_id == region_id),
        None,
    )
    if request is None:
        raise TranslationResultMismatchError(f"missing translation request for {region_id}")
    return request


def _unresolved_review_issues(review: RegionReview) -> tuple[QualityIssue, ...]:
    return tuple(
        issue
        for issue in (*review.critical_issues, *review.non_critical_issues)
        if not issue.resolved
    )


def _issue_from_rejected_review(review: RegionReview) -> QualityIssue:
    return QualityIssue(
        issue_code=f"translation_quality_rejected_{review.region_id}",
        severity=QualitySeverity.error,
        scope="translation",
        region_ids=(review.region_id,),
        summary="translation quality review did not meet automatic approval policy",
        evidence_references=(review.evidence_summary,),
        recommended_action=review.improvement_instruction or "review translation",
    )


def _duplicate_values(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: frozenset[str] = frozenset()
    duplicates: tuple[str, ...] = ()
    for value in values:
        if value in seen and value not in duplicates:
            duplicates = (*duplicates, value)
        seen = frozenset((*seen, value))
    return duplicates
