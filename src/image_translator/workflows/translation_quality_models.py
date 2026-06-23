from __future__ import annotations

from enum import StrEnum

from image_translator.domain._base import DomainModel, NonEmptyStr, NonNegativeInt
from image_translator.domain.ids import JobId, ProjectId, RegionId, RevisionId
from image_translator.domain.ocr import NormalizedTextRegion, OCRCandidate, RawOCRRegion
from image_translator.domain.quality import QualityIssue, RegionReview
from image_translator.domain.translation import (
    TranslationCandidate,
    TranslationRequest,
    TranslationResult,
)
from image_translator.providers.base import PageContextReview
from image_translator.services.ocr_risk import OCRRiskScore


class TranslationQualityStatus(StrEnum):
    pending = "pending"
    prepared = "prepared"
    ocr_scored = "ocr_scored"
    ocr_resolved = "ocr_resolved"
    layout_classified = "layout_classified"
    context_built = "context_built"
    translating = "translating"
    translated = "translated"
    structure_validated = "structure_validated"
    reviewed = "reviewed"
    retrying = "retrying"
    needs_review = "needs_review"
    approved = "approved"
    finalized = "finalized"


class TranslationRoute(StrEnum):
    complete = "complete"
    retry_quality = "retry_quality"
    interrupt_user = "interrupt_user"


class TranslationWorkflowInput(DomainModel):
    job_id: JobId
    project_id: ProjectId
    revision_id: RevisionId
    source_image_reference: NonEmptyStr
    source_language: NonEmptyStr
    target_language: NonEmptyStr
    regions: tuple[NormalizedTextRegion, ...]
    primary_ocr_snapshots: tuple[RawOCRRegion, ...] = ()
    translator_provider_id: NonEmptyStr | None = None
    reviewer_provider_id: NonEmptyStr | None = None
    fallback_provider_ids: tuple[NonEmptyStr, ...] = ()
    visual_mode: bool = False
    image_transmission_consent: bool = False
    approved_project_context_version: NonEmptyStr | None = None
    translation_profile: NonEmptyStr = "balanced"


class RegionOCRCandidates(DomainModel):
    region_id: RegionId
    candidates: tuple[OCRCandidate, ...]
    risk_score: OCRRiskScore | None = None
    requires_cross_check: bool = False
    requires_vision_correction: bool = False


class OCRResolution(DomainModel):
    region_id: RegionId
    approved_text: str
    requires_user_review: bool = False
    evidence_summary: NonEmptyStr


class RegionTranslationAttempt(DomainModel):
    region_id: RegionId
    translation_attempt: NonNegativeInt = 0


class WorkflowInterruptPayload(DomainModel):
    interrupt_type: NonEmptyStr
    job_id: JobId
    revision_id: RevisionId
    affected_region_ids: tuple[RegionId, ...]
    issue_summaries: tuple[NonEmptyStr, ...] = ()
    preview_references: tuple[NonEmptyStr, ...] = ()
    allowed_actions: tuple[NonEmptyStr, ...] = ()
    recommended_action: NonEmptyStr


class TranslationWorkflowResult(DomainModel):
    approved_translation_results: tuple[TranslationResult, ...]
    unresolved_issues: tuple[QualityIssue, ...] = ()
    page_context: PageContextReview | None = None
    context_suggestions: tuple[NonEmptyStr, ...] = ()
    audit_references: tuple[NonEmptyStr, ...] = ()
    interrupt_payload: WorkflowInterruptPayload | None = None


class TranslationWorkflowState(DomainModel):
    input: TranslationWorkflowInput
    regions: tuple[NormalizedTextRegion, ...]
    ocr_candidates_by_region: tuple[RegionOCRCandidates, ...] = ()
    ocr_decisions_by_region: tuple[OCRResolution, ...] = ()
    reading_order_decision: NonEmptyStr | None = None
    page_context: PageContextReview | None = None
    page_context_reference: NonEmptyStr | None = None
    context_suggestions: tuple[NonEmptyStr, ...] = ()
    translation_requests: tuple[TranslationRequest, ...] = ()
    translation_candidates: tuple[TranslationCandidate, ...] = ()
    current_translation_candidates: tuple[TranslationCandidate, ...] = ()
    reviews: tuple[RegionReview, ...] = ()
    translation_attempts_by_region: tuple[RegionTranslationAttempt, ...] = ()
    provider_attempts: tuple[NonEmptyStr, ...] = ()
    approved_translations: tuple[TranslationResult, ...] = ()
    unresolved_issues: tuple[QualityIssue, ...] = ()
    interrupt_payload: WorkflowInterruptPayload | None = None
    result: TranslationWorkflowResult | None = None
    last_route: TranslationRoute | None = None
    status: TranslationQualityStatus = TranslationQualityStatus.pending

    @property
    def job_id(self) -> JobId:
        return self.input.job_id

    @property
    def revision_id(self) -> RevisionId:
        return self.input.revision_id

    def result_or_raise(self) -> TranslationWorkflowResult:
        if self.result is None:
            raise RuntimeError("translation workflow did not produce a result")
        return self.result


TranslationQualityState = TranslationWorkflowState


__all__ = [
    "OCRResolution",
    "RegionOCRCandidates",
    "RegionTranslationAttempt",
    "TranslationQualityState",
    "TranslationQualityStatus",
    "TranslationRoute",
    "TranslationWorkflowInput",
    "TranslationWorkflowResult",
    "TranslationWorkflowState",
    "WorkflowInterruptPayload",
]
