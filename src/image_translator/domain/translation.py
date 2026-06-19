from __future__ import annotations

from image_translator.domain._base import DomainModel, NonEmptyStr, PositiveInt
from image_translator.domain.ids import ProviderRequestId, RegionId, RevisionId
from image_translator.domain.ocr import TextRole, WritingMode


class TranslationRequest(DomainModel):
    region_id: RegionId
    source_text: str
    source_language: NonEmptyStr
    target_language: NonEmptyStr
    text_role: TextRole
    writing_mode: WritingMode
    page_context_reference: NonEmptyStr | None = None
    region_context_summary: NonEmptyStr | None = None
    project_context_version: NonEmptyStr | None = None
    reviewer_feedback: tuple[NonEmptyStr, ...] = ()
    image_reference: NonEmptyStr | None = None


class TranslationCandidate(DomainModel):
    candidate_id: ProviderRequestId
    region_id: RegionId
    translated_text: str
    provider_id: NonEmptyStr
    model_id: NonEmptyStr
    attempt: PositiveInt
    request_fingerprint: ProviderRequestId
    created_revision: RevisionId


class TranslationResult(DomainModel):
    region_id: RegionId
    approved_translated_text: str
    source_language: NonEmptyStr
    target_language: NonEmptyStr
    selected_candidate_id: ProviderRequestId
    approval_status: NonEmptyStr
    review_reference: NonEmptyStr | None = None
