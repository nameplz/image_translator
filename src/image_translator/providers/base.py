from __future__ import annotations

from enum import StrEnum
from typing import Protocol, Self

from image_translator.domain._base import (
    DomainModel,
    NonEmptyStr,
    NonNegativeInt,
    PositiveInt,
    UnitInterval,
)
from image_translator.domain.ids import ProviderRequestId, RegionId, RevisionId
from image_translator.domain.ocr import OCRCandidate, RawOCRRegion
from image_translator.domain.quality import QualityIssue, QualitySeverity, RegionReview
from image_translator.domain.translation import TranslationCandidate, TranslationRequest

REDACTED_SECRET = "[redacted]"


class ProviderType(StrEnum):
    ocr = "ocr"
    translator = "translator"
    reviewer = "reviewer"
    inpainting = "inpainting"
    rendering = "rendering"


class ImageReferenceKind(StrEnum):
    full_page = "full_page"
    crop = "crop"
    inpainted = "inpainted"
    rendered = "rendered"


class ImageReference(DomainModel):
    reference_id: NonEmptyStr
    kind: ImageReferenceKind
    uri: NonEmptyStr | None = None


class LanguagePair(DomainModel):
    source_language: NonEmptyStr
    target_language: NonEmptyStr


class ProviderCapabilities(DomainModel):
    provider_type: ProviderType
    supported_language_pairs: tuple[LanguagePair, ...] = ()
    supports_batch: bool = False
    max_batch_size: PositiveInt = 1
    supports_structured_output: bool = False
    supports_visual_input: bool = False
    supports_full_image: bool = False
    supports_crop: bool = False
    max_input_size_bytes: PositiveInt | None = None
    supports_streaming: bool = False
    supports_cost_metadata: bool = False
    is_cloud: bool = True

    def supports_language_pair(self, source_language: str, target_language: str) -> bool:
        if not self.supported_language_pairs:
            return True
        return any(
            pair.source_language == source_language and pair.target_language == target_language
            for pair in self.supported_language_pairs
        )

    def supports_visual_reference(self, reference: ImageReference) -> bool:
        if not self.supports_visual_input:
            return False
        if reference.kind is ImageReferenceKind.crop:
            return self.supports_crop
        return self.supports_full_image


class ProviderConfigIssue(DomainModel):
    issue_code: NonEmptyStr
    safe_message: NonEmptyStr
    severity: QualitySeverity = QualitySeverity.error
    environment_variable: NonEmptyStr | None = None

    @classmethod
    def from_message(
        cls,
        *,
        issue_code: str,
        message: str,
        secret_values: tuple[str, ...] = (),
        severity: QualitySeverity = QualitySeverity.error,
        environment_variable: str | None = None,
    ) -> Self:
        return cls(
            issue_code=issue_code,
            safe_message=redact_secret_values(message, secret_values),
            severity=severity,
            environment_variable=environment_variable,
        )


class ProviderUsageMetadata(DomainModel):
    request_id: ProviderRequestId
    request_fingerprint: ProviderRequestId
    provider_id: NonEmptyStr
    model_id: NonEmptyStr | None = None
    prompt_contract_version: NonEmptyStr | None = None
    input_units: NonNegativeInt = 0
    output_units: NonNegativeInt = 0
    used_visual_input: bool = False
    safe_metadata_summary: tuple[NonEmptyStr, ...] = ()


class OCRCorrectionRequest(DomainModel):
    candidates: tuple[OCRCandidate, ...] = ()
    visual_references: tuple[ImageReference, ...] = ()


class OCRCorrectionReview(DomainModel):
    region_id: RegionId | None = None
    selected_candidate_id: ProviderRequestId | None = None
    corrected_text: str | None = None
    confidence: UnitInterval = 0.0
    evidence_summary: NonEmptyStr
    affects_reading_order: bool = False
    usage_metadata: ProviderUsageMetadata | None = None


class PageContextRequest(DomainModel):
    region_ids: tuple[RegionId, ...] = ()
    visual_references: tuple[ImageReference, ...] = ()
    prompt_contract_version: NonEmptyStr = "page-context/v1"


class PageContextReview(DomainModel):
    scene_summary: NonEmptyStr
    reading_order_notes: NonEmptyStr | None = None
    dialogue_groups: tuple[NonEmptyStr, ...] = ()
    confidence: UnitInterval = 0.0
    usage_metadata: ProviderUsageMetadata | None = None


class TranslationReviewRequest(DomainModel):
    region_ids: tuple[RegionId, ...] = ()
    candidates: tuple[TranslationCandidate, ...] = ()
    visual_references: tuple[ImageReference, ...] = ()
    prompt_contract_version: NonEmptyStr = "translation-review/v1"


class PageReview(DomainModel):
    region_reviews: tuple[RegionReview, ...]
    page_level_issues: tuple[QualityIssue, ...] = ()
    context_consistency_summary: NonEmptyStr
    provider_id: NonEmptyStr
    model_id: NonEmptyStr
    prompt_contract_version: NonEmptyStr
    usage_metadata: ProviderUsageMetadata | None = None


class ResultImageReviewRequest(DomainModel):
    rendered_image_reference: ImageReference
    visual_references: tuple[ImageReference, ...] = ()
    prompt_contract_version: NonEmptyStr = "result-image-review/v1"


class ResultQualityReview(DomainModel):
    rendered_image_reference: ImageReference
    issues: tuple[QualityIssue, ...] = ()
    correction_recommendations: tuple[NonEmptyStr, ...] = ()
    requires_user_review: bool = False
    decision: NonEmptyStr
    usage_metadata: ProviderUsageMetadata | None = None


class RevisionIntentRequest(DomainModel):
    user_instruction: NonEmptyStr
    selected_region_ids: tuple[RegionId, ...] = ()
    allowed_actions: tuple[NonEmptyStr, ...] = ()
    prompt_contract_version: NonEmptyStr = "revision-intent/v1"


class RevisionIntentParseResult(DomainModel):
    normalized_intent: NonEmptyStr
    candidate_region_ids: tuple[RegionId, ...] = ()
    proposed_actions: tuple[NonEmptyStr, ...] = ()
    requires_confirmation: bool = False
    ambiguity_summary: NonEmptyStr | None = None
    usage_metadata: ProviderUsageMetadata | None = None


class InpaintingRequest(DomainModel):
    image_reference: ImageReference
    region_ids: tuple[RegionId, ...] = ()
    mask_reference: ImageReference | None = None


class InpaintingResult(DomainModel):
    image_reference: ImageReference
    usage_metadata: ProviderUsageMetadata | None = None


class RenderRequest(DomainModel):
    revision_id: RevisionId
    render_plan_references: tuple[NonEmptyStr, ...] = ()


class RenderResult(DomainModel):
    image_reference: ImageReference
    usage_metadata: ProviderUsageMetadata | None = None


class ProviderAdapter(Protocol):
    provider_id: str
    display_name: str

    async def load(self) -> None: ...

    async def unload(self) -> None: ...

    def validate_config(self) -> tuple[ProviderConfigIssue, ...]: ...

    def capabilities(self) -> ProviderCapabilities: ...


class OCRAdapter(ProviderAdapter, Protocol):
    async def detect_regions(
        self,
        image_ref: ImageReference,
        language_hints: tuple[str, ...],
    ) -> tuple[RawOCRRegion, ...]: ...


class TranslatorAdapter(ProviderAdapter, Protocol):
    async def translate_page(
        self,
        requests: tuple[TranslationRequest, ...],
    ) -> tuple[TranslationCandidate, ...]: ...


class ReviewAdapter(ProviderAdapter, Protocol):
    async def correct_ocr(
        self,
        request: OCRCorrectionRequest,
    ) -> OCRCorrectionReview: ...

    async def build_page_context(
        self,
        request: PageContextRequest,
    ) -> PageContextReview: ...

    async def review_translation(
        self,
        request: TranslationReviewRequest,
    ) -> PageReview: ...

    async def review_result_image(
        self,
        request: ResultImageReviewRequest,
    ) -> ResultQualityReview: ...

    async def parse_revision_intent(
        self,
        request: RevisionIntentRequest,
    ) -> RevisionIntentParseResult: ...


class InpaintingBackend(Protocol):
    backend_id: str

    async def remove_text(self, request: InpaintingRequest) -> InpaintingResult: ...


class RenderingBackend(Protocol):
    backend_id: str

    async def render(self, request: RenderRequest) -> RenderResult: ...


def redact_secret_values(message: str, secret_values: tuple[str, ...]) -> str:
    redacted = message
    for secret_value in secret_values:
        if secret_value:
            redacted = redacted.replace(secret_value, REDACTED_SECRET)
    return redacted


__all__ = [
    "ImageReference",
    "ImageReferenceKind",
    "InpaintingBackend",
    "InpaintingRequest",
    "InpaintingResult",
    "LanguagePair",
    "OCRAdapter",
    "OCRCorrectionRequest",
    "OCRCorrectionReview",
    "PageContextRequest",
    "PageContextReview",
    "PageReview",
    "ProviderAdapter",
    "ProviderCapabilities",
    "ProviderConfigIssue",
    "ProviderType",
    "ProviderUsageMetadata",
    "REDACTED_SECRET",
    "RenderRequest",
    "RenderResult",
    "RenderingBackend",
    "ResultImageReviewRequest",
    "ResultQualityReview",
    "ReviewAdapter",
    "RevisionIntentParseResult",
    "RevisionIntentRequest",
    "TranslationReviewRequest",
    "TranslatorAdapter",
    "redact_secret_values",
]
