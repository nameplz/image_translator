from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from image_translator.domain._base import NonEmptyStr
from image_translator.domain.errors import ProviderConfigError, TranslationResultMismatchError
from image_translator.domain.ids import RegionId
from image_translator.domain.ocr import NormalizedTextRegion, OCRCandidate, RawOCRRegion
from image_translator.domain.quality import QualityIssue, QualitySeverity, RegionReview
from image_translator.domain.translation import (
    TranslationCandidate,
    TranslationRequest,
    TranslationResult,
)
from image_translator.providers.base import (
    ImageReference,
    ImageReferenceKind,
    ProviderCapabilities,
    ProviderType,
)
from image_translator.services.ocr_risk import score_ocr_risk as calculate_ocr_risk
from image_translator.workflows.translation_quality_models import (
    RegionOCRCandidates,
    RegionTranslationAttempt,
    TranslationWorkflowInput,
    TranslationWorkflowResult,
    TranslationWorkflowState,
    WorkflowInterruptPayload,
)


def validate_provider_capability(
    *,
    adapter_capabilities: ProviderCapabilities,
    expected_type: ProviderType,
    source_language: str,
    target_language: str,
) -> None:
    if adapter_capabilities.provider_type is not expected_type:
        raise ProviderConfigError(
            f"provider type {adapter_capabilities.provider_type.value} "
            f"does not match {expected_type.value}"
        )
    if not adapter_capabilities.supports_language_pair(source_language, target_language):
        raise ProviderConfigError(
            f"unsupported language pair {source_language}->{target_language}"
        )


def ocr_candidate_set_for_region(
    region: NormalizedTextRegion,
    raw_region: RawOCRRegion | None,
) -> RegionOCRCandidates:
    if raw_region is None:
        candidate = OCRCandidate(
            region_id=region.region_id,
            text=region.source_text,
            language=region.source_language,
            provider_id="normalized-ocr",
            confidence=1.0,
            evidence_summary="normalized OCR text",
            request_id=f"normalized-{region.region_id}",
        )
        return RegionOCRCandidates(region_id=region.region_id, candidates=(candidate,))

    risk_score = calculate_ocr_risk(
        raw_region,
        reading_order=region.reading_order,
        text_role=region.text_role,
        ruby_target_region_id=region.ruby_target_region_id,
    )
    return RegionOCRCandidates(
        region_id=region.region_id,
        candidates=(ocr_candidate_from_raw(raw_region, region.source_language),),
        risk_score=risk_score,
        requires_cross_check=risk_score.requires_review,
        requires_vision_correction=risk_score.requires_review,
    )


def ocr_candidate_from_raw(
    raw_region: RawOCRRegion,
    language: str,
) -> OCRCandidate:
    return OCRCandidate(
        region_id=raw_region.region_id,
        text=raw_region.raw_text,
        language=language,
        provider_id=raw_region.provider_id,
        confidence=raw_region.confidence,
        evidence_summary=", ".join(raw_region.metadata_summary) or "raw OCR candidate",
        request_id=f"{raw_region.provider_id}-{raw_region.region_id}",
    )


def with_ocr_correction(
    candidate_set: RegionOCRCandidates,
    review: Any,
) -> RegionOCRCandidates:
    corrected_text = getattr(review, "corrected_text", None)
    if not corrected_text:
        return candidate_set
    usage = getattr(review, "usage_metadata", None)
    request_id = (
        usage.request_id
        if usage is not None
        else f"ocr-correction-{candidate_set.region_id}"
    )
    corrected_candidate = OCRCandidate(
        region_id=candidate_set.region_id,
        text=corrected_text,
        language=candidate_set.candidates[0].language,
        provider_id=usage.provider_id if usage is not None else "vision-reviewer",
        confidence=getattr(review, "confidence", 0.0),
        evidence_summary=getattr(review, "evidence_summary", "vision OCR correction"),
        request_id=request_id,
    )
    return candidate_set.model_copy(
        update={"candidates": (*candidate_set.candidates, corrected_candidate)}
    )


def candidate_set_for_region(
    candidate_sets: tuple[RegionOCRCandidates, ...],
    region_id: RegionId,
) -> RegionOCRCandidates:
    candidate_set = next(
        (
            candidate_set
            for candidate_set in candidate_sets
            if candidate_set.region_id == region_id
        ),
        None,
    )
    if candidate_set is None:
        raise TranslationResultMismatchError(f"missing OCR candidate set for {region_id}")
    return candidate_set


def select_ocr_candidate(candidate_set: RegionOCRCandidates) -> OCRCandidate:
    return max(candidate_set.candidates, key=lambda candidate: candidate.confidence)


def review_reason_issues(
    *,
    scope: str,
    reasons: tuple[str, ...],
    issue_prefix: str,
) -> tuple[QualityIssue, ...]:
    return tuple(
        QualityIssue(
            issue_code=f"{issue_prefix}_{index}",
            severity=QualitySeverity.error,
            scope=scope,
            region_ids=region_ids_from_reason(reason),
            summary=reason,
            evidence_references=(reason,),
            recommended_action="review page layout",
        )
        for index, reason in enumerate(reasons, start=1)
    )


def region_ids_from_reason(reason: str) -> tuple[RegionId, ...]:
    region_id = reason.split(":", maxsplit=1)[0].strip()
    return (region_id,) if region_id else ()


def source_image_reference(workflow_input: TranslationWorkflowInput) -> ImageReference:
    return ImageReference(
        reference_id=workflow_input.source_image_reference,
        kind=ImageReferenceKind.full_page,
        uri=None,
    )


def crop_reference(region_id: RegionId) -> ImageReference:
    return ImageReference(reference_id=f"crop-{region_id}", kind=ImageReferenceKind.crop)


def page_visual_references(
    workflow_input: TranslationWorkflowInput,
    capabilities: ProviderCapabilities,
) -> tuple[ImageReference, ...]:
    reference = source_image_reference(workflow_input)
    if can_send_reference(workflow_input, capabilities, reference):
        return (reference,)
    return ()


def ocr_correction_visual_references(
    workflow_input: TranslationWorkflowInput,
    capabilities: ProviderCapabilities,
    region_id: RegionId,
) -> tuple[ImageReference, ...]:
    crop = crop_reference(region_id)
    if can_send_reference(workflow_input, capabilities, crop):
        return (crop,)
    return ()


def translation_review_visual_references(
    workflow_input: TranslationWorkflowInput,
    capabilities: ProviderCapabilities,
    candidates: tuple[TranslationCandidate, ...],
) -> tuple[ImageReference, ...]:
    page_references = page_visual_references(workflow_input, capabilities)
    crop_references = tuple(
        reference
        for reference in (crop_reference(candidate.region_id) for candidate in candidates)
        if can_send_reference(workflow_input, capabilities, reference)
    )
    return (*page_references, *crop_references)


def can_send_crop_references(
    workflow_input: TranslationWorkflowInput,
    capabilities: ProviderCapabilities,
) -> bool:
    return can_send_reference(
        workflow_input,
        capabilities,
        ImageReference(reference_id="crop-capability-check", kind=ImageReferenceKind.crop),
    )


def can_send_reference(
    workflow_input: TranslationWorkflowInput,
    capabilities: ProviderCapabilities,
    reference: ImageReference,
) -> bool:
    return (
        workflow_input.visual_mode
        and workflow_input.image_transmission_consent
        and capabilities.supports_visual_reference(reference)
    )


def ordered_regions(
    regions: tuple[NormalizedTextRegion, ...],
) -> tuple[NormalizedTextRegion, ...]:
    return tuple(
        sorted(
            regions,
            key=lambda region: (
                region.reading_order.page_index,
                region.reading_order.group_index,
                region.reading_order.item_index,
                region.region_id,
            ),
        )
    )


def ordered_translations(
    translations: tuple[TranslationResult, ...],
    regions: tuple[NormalizedTextRegion, ...],
) -> tuple[TranslationResult, ...]:
    order_by_region = {
        region.region_id: index for index, region in enumerate(ordered_regions(regions))
    }
    return tuple(
        sorted(
            translations,
            key=lambda translation: (
                order_by_region.get(translation.region_id, len(order_by_region)),
                translation.region_id,
            ),
        )
    )


def reviewer_feedback_for_region(
    state: TranslationWorkflowState,
    region_id: RegionId,
) -> tuple[NonEmptyStr, ...]:
    latest_reviews = latest_reviews_by_region(state.reviews)
    review = latest_reviews.get(region_id)
    feedback: tuple[NonEmptyStr, ...] = ()
    if review is not None and review.improvement_instruction:
        feedback = (*feedback, review.improvement_instruction)
    feedback = (
        *feedback,
        *(
            issue.recommended_action
            for issue in state.unresolved_issues
            if region_id in issue.region_ids and issue.recommended_action is not None
        ),
    )
    return feedback


def increment_attempts(
    attempts: tuple[RegionTranslationAttempt, ...],
    region_ids: tuple[RegionId, ...],
) -> tuple[RegionTranslationAttempt, ...]:
    region_id_set = frozenset(region_ids)
    existing_region_ids = frozenset(attempt.region_id for attempt in attempts)
    updated = tuple(
        attempt.model_copy(
            update={"translation_attempt": attempt.translation_attempt + 1}
        )
        if attempt.region_id in region_id_set
        else attempt
        for attempt in attempts
    )
    missing = tuple(
        RegionTranslationAttempt(region_id=region_id, translation_attempt=1)
        for region_id in region_ids
        if region_id not in existing_region_ids
    )
    return (*updated, *missing)


def attempt_count(
    attempts: tuple[RegionTranslationAttempt, ...],
    region_id: RegionId,
) -> int:
    attempt = next((attempt for attempt in attempts if attempt.region_id == region_id), None)
    return int(attempt.translation_attempt) if attempt is not None else 0


def validate_translation_structure(
    requests: tuple[TranslationRequest, ...],
    candidates: tuple[TranslationCandidate, ...],
) -> None:
    request_ids = tuple(request.region_id for request in requests)
    candidate_ids = tuple(candidate.region_id for candidate in candidates)

    if len(candidates) != len(requests):
        raise TranslationResultMismatchError("translation candidate cardinality mismatch")

    duplicate_candidate_ids = duplicate_values(candidate_ids)
    if duplicate_candidate_ids:
        raise TranslationResultMismatchError(
            "duplicate translation candidate region IDs: "
            + ", ".join(duplicate_candidate_ids)
        )

    missing_ids = tuple(
        region_id for region_id in request_ids if region_id not in candidate_ids
    )
    unknown_ids = tuple(
        region_id for region_id in candidate_ids if region_id not in request_ids
    )
    if missing_ids or unknown_ids:
        raise TranslationResultMismatchError(
            "translation candidate region ID mismatch; "
            f"missing={missing_ids}, unknown={unknown_ids}"
        )

    empty_ids = tuple(
        candidate.region_id
        for candidate in candidates
        if not candidate.translated_text.strip()
    )
    if empty_ids:
        raise TranslationResultMismatchError(
            "empty translation candidate text for region IDs: " + ", ".join(empty_ids)
        )


def validate_review_structure(
    candidate_region_ids: tuple[RegionId, ...],
    reviews: tuple[RegionReview, ...],
) -> None:
    review_ids = tuple(review.region_id for review in reviews)
    duplicate_review_ids = duplicate_values(review_ids)
    if duplicate_review_ids:
        raise TranslationResultMismatchError(
            "duplicate translation review region IDs: " + ", ".join(duplicate_review_ids)
        )
    missing_ids = tuple(
        region_id for region_id in candidate_region_ids if region_id not in review_ids
    )
    unknown_ids = tuple(
        region_id for region_id in review_ids if region_id not in candidate_region_ids
    )
    if missing_ids or unknown_ids:
        raise TranslationResultMismatchError(
            "translation review region ID mismatch; "
            f"missing={missing_ids}, unknown={unknown_ids}"
        )


def request_for_region(
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


def append_approved_translation(
    translations: tuple[TranslationResult, ...],
    translation: TranslationResult,
) -> tuple[TranslationResult, ...]:
    if any(existing.region_id == translation.region_id for existing in translations):
        return translations
    return (*translations, translation)


def unresolved_review_issues(review: RegionReview) -> tuple[QualityIssue, ...]:
    return tuple(
        issue
        for issue in (*review.critical_issues, *review.non_critical_issues)
        if not issue.resolved
    )


def issue_from_rejected_review(review: RegionReview) -> QualityIssue:
    return QualityIssue(
        issue_code=f"translation_quality_rejected_{review.region_id}",
        severity=QualitySeverity.error,
        scope="translation",
        region_ids=(review.region_id,),
        summary="translation quality review did not meet automatic approval policy",
        evidence_references=(review.evidence_summary,),
        recommended_action=review.improvement_instruction or "review translation",
    )


def latest_reviews_by_region(
    reviews: tuple[RegionReview, ...],
) -> Mapping[RegionId, RegionReview]:
    latest: dict[RegionId, RegionReview] = {}
    for review in reviews:
        latest[review.region_id] = review
    return latest


def has_actionable_feedback(review: RegionReview) -> bool:
    if review.improvement_instruction:
        return True
    return any(issue.recommended_action for issue in unresolved_review_issues(review))


def is_approved(state: TranslationWorkflowState, region_id: RegionId) -> bool:
    return any(translation.region_id == region_id for translation in state.approved_translations)


def unapproved_region_ids(state: TranslationWorkflowState) -> tuple[RegionId, ...]:
    approved_region_ids = frozenset(
        translation.region_id for translation in state.approved_translations
    )
    return tuple(
        region.region_id
        for region in ordered_regions(state.regions)
        if region.region_id not in approved_region_ids
    )


def affected_interrupt_region_ids(state: TranslationWorkflowState) -> tuple[RegionId, ...]:
    issue_region_ids = unique_region_ids(
        region_id
        for issue in state.unresolved_issues
        if not issue.resolved
        for region_id in issue.region_ids
        if not is_approved(state, region_id)
    )
    if issue_region_ids:
        return issue_region_ids
    return unapproved_region_ids(state)


def issues_outside_regions(
    issues: tuple[QualityIssue, ...],
    region_ids: tuple[RegionId, ...],
) -> tuple[QualityIssue, ...]:
    region_id_set = frozenset(region_ids)
    return tuple(
        issue
        for issue in issues
        if not issue.region_ids
        or not any(region_id in region_id_set for region_id in issue.region_ids)
    )


def issues_for_scopes(
    issues: tuple[QualityIssue, ...],
    *,
    excluded_scopes: tuple[str, ...],
) -> tuple[QualityIssue, ...]:
    excluded = frozenset(excluded_scopes)
    return tuple(issue for issue in issues if issue.scope not in excluded)


def blocking_issues(issues: tuple[QualityIssue, ...]) -> tuple[QualityIssue, ...]:
    return tuple(
        issue
        for issue in issues
        if not issue.resolved
        and issue.severity in {QualitySeverity.error, QualitySeverity.critical}
    )


def has_ocr_review_issue(issues: tuple[QualityIssue, ...]) -> bool:
    return any(
        not issue.resolved
        and issue.scope in {"ocr", "reading_order"}
        and issue.severity in {QualitySeverity.error, QualitySeverity.critical}
        for issue in issues
    )


def issue_affects_any(
    issue: QualityIssue,
    region_ids: tuple[RegionId, ...],
) -> bool:
    region_id_set = frozenset(region_ids)
    return not issue.region_ids or any(region_id in region_id_set for region_id in issue.region_ids)


def result_from_state(
    state: TranslationWorkflowState,
    *,
    interrupt_payload: WorkflowInterruptPayload | None,
) -> TranslationWorkflowResult:
    audit_references = tuple(
        candidate.request_fingerprint for candidate in state.translation_candidates
    )
    return TranslationWorkflowResult(
        approved_translation_results=state.approved_translations,
        unresolved_issues=state.unresolved_issues,
        page_context=state.page_context,
        context_suggestions=state.context_suggestions,
        audit_references=audit_references,
        interrupt_payload=interrupt_payload,
    )


def duplicate_values(values: tuple[str, ...]) -> tuple[str, ...]:
    seen: frozenset[str] = frozenset()
    duplicates: tuple[str, ...] = ()
    for value in values:
        if value in seen and value not in duplicates:
            duplicates = (*duplicates, value)
        seen = frozenset((*seen, value))
    return duplicates


def unique_region_ids(values: Iterable[RegionId]) -> tuple[RegionId, ...]:
    unique_values: tuple[RegionId, ...] = ()
    for value in values:
        if value not in unique_values:
            unique_values = (*unique_values, value)
    return unique_values


__all__ = [
    "affected_interrupt_region_ids",
    "append_approved_translation",
    "attempt_count",
    "blocking_issues",
    "can_send_crop_references",
    "candidate_set_for_region",
    "duplicate_values",
    "has_actionable_feedback",
    "has_ocr_review_issue",
    "is_approved",
    "issue_affects_any",
    "issue_from_rejected_review",
    "issues_for_scopes",
    "issues_outside_regions",
    "latest_reviews_by_region",
    "ocr_candidate_from_raw",
    "ocr_candidate_set_for_region",
    "ocr_correction_visual_references",
    "ordered_regions",
    "ordered_translations",
    "page_visual_references",
    "request_for_region",
    "result_from_state",
    "review_reason_issues",
    "reviewer_feedback_for_region",
    "select_ocr_candidate",
    "source_image_reference",
    "translation_review_visual_references",
    "unapproved_region_ids",
    "unresolved_review_issues",
    "validate_provider_capability",
    "validate_review_structure",
    "validate_translation_structure",
    "with_ocr_correction",
]
