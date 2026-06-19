from __future__ import annotations

from collections.abc import Mapping
from hashlib import sha256

from image_translator.domain.errors import ProviderConfigError
from image_translator.domain.geometry import Point, Polygon, RegionGeometry
from image_translator.domain.ids import RegionId
from image_translator.domain.ocr import RawOCRRegion, WritingMode
from image_translator.domain.quality import RegionReview, RubricScores
from image_translator.domain.translation import TranslationCandidate, TranslationRequest
from image_translator.providers.base import (
    ImageReference,
    ImageReferenceKind,
    LanguagePair,
    OCRCorrectionRequest,
    OCRCorrectionReview,
    PageContextRequest,
    PageContextReview,
    PageReview,
    ProviderCapabilities,
    ProviderConfigIssue,
    ProviderType,
    ProviderUsageMetadata,
    ResultImageReviewRequest,
    ResultQualityReview,
    RevisionIntentParseResult,
    RevisionIntentRequest,
    TranslationReviewRequest,
)

MOCK_OCR_PROVIDER_ID = "mock-ocr"
MOCK_TRANSLATOR_PROVIDER_ID = "mock-translator"
MOCK_REVIEWER_PROVIDER_ID = "mock-reviewer"
MOCK_MODEL_ID = "mock-model-v1"


class MockProviderRequestRecord(ProviderUsageMetadata):
    operation: str
    region_ids: tuple[RegionId, ...] = ()
    visual_references: tuple[ImageReference, ...] = ()


class MockOCRAdapter:
    provider_id = MOCK_OCR_PROVIDER_ID
    display_name = "Mock OCR"

    def __init__(
        self,
        *,
        configured_regions: tuple[RawOCRRegion, ...] | None = None,
        config_issues: tuple[ProviderConfigIssue, ...] = (),
    ) -> None:
        self.configured_regions = configured_regions or _default_ocr_regions(self.provider_id)
        self._config_issues = config_issues
        self._loaded = False
        self._recorded_requests: tuple[MockProviderRequestRecord, ...] = ()

    @classmethod
    def with_regions(
        cls,
        regions: tuple[tuple[str, str, RegionGeometry], ...],
    ) -> MockOCRAdapter:
        configured_regions = tuple(
            RawOCRRegion(
                region_id=region_id,
                raw_text=raw_text,
                confidence=0.95,
                geometry=geometry,
                writing_mode=WritingMode.horizontal_ltr,
                writing_mode_confidence=0.95,
                provider_id=cls.provider_id,
                metadata_summary=("configured mock OCR region",),
            )
            for region_id, raw_text, geometry in regions
        )
        return cls(configured_regions=configured_regions)

    @property
    def recorded_requests(self) -> tuple[MockProviderRequestRecord, ...]:
        return self._recorded_requests

    async def load(self) -> None:
        self._loaded = True

    async def unload(self) -> None:
        self._loaded = False

    def validate_config(self) -> tuple[ProviderConfigIssue, ...]:
        return self._config_issues

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            provider_type=ProviderType.ocr,
            supports_batch=False,
            supports_structured_output=True,
            supports_visual_input=True,
            supports_full_image=True,
            supports_crop=True,
            is_cloud=False,
        )

    async def detect_regions(
        self,
        image_ref: ImageReference,
        language_hints: tuple[str, ...],
    ) -> tuple[RawOCRRegion, ...]:
        usage = _usage(
            provider_id=self.provider_id,
            operation="detect_regions",
            region_ids=tuple(region.region_id for region in self.configured_regions),
            used_visual_input=False,
            safe_metadata_summary=(
                f"language hints: {len(language_hints)}",
                f"image reference kind: {image_ref.kind.value}",
            ),
        )
        self._recorded_requests = (
            *self._recorded_requests,
            MockProviderRequestRecord(
                **usage.model_dump(),
                operation="detect_regions",
                region_ids=tuple(region.region_id for region in self.configured_regions),
            ),
        )
        return self.configured_regions


class MockTranslatorAdapter:
    provider_id = MOCK_TRANSLATOR_PROVIDER_ID
    display_name = "Mock Translator"

    def __init__(
        self,
        *,
        capabilities: ProviderCapabilities | None = None,
        configured_translations: Mapping[str, str] | None = None,
        visual_mode_enabled: bool = False,
        image_transmission_consent: bool = False,
        config_issues: tuple[ProviderConfigIssue, ...] = (),
    ) -> None:
        self._capabilities = capabilities or _default_translator_capabilities()
        self._configured_translations = dict(configured_translations or {})
        self._visual_mode_enabled = visual_mode_enabled
        self._image_transmission_consent = image_transmission_consent
        self._config_issues = config_issues
        self._loaded = False
        self._recorded_requests: tuple[MockProviderRequestRecord, ...] = ()

    @property
    def recorded_requests(self) -> tuple[MockProviderRequestRecord, ...]:
        return self._recorded_requests

    async def load(self) -> None:
        self._loaded = True

    async def unload(self) -> None:
        self._loaded = False

    def validate_config(self) -> tuple[ProviderConfigIssue, ...]:
        return self._config_issues

    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    async def translate_page(
        self,
        requests: tuple[TranslationRequest, ...],
    ) -> tuple[TranslationCandidate, ...]:
        if not requests:
            return ()

        _enforce_batch_capabilities(self._capabilities, len(requests))
        for request in requests:
            _enforce_language_pair(self._capabilities, request)

        visual_references = _authorized_visual_references(
            capabilities=self._capabilities,
            visual_mode_enabled=self._visual_mode_enabled,
            image_transmission_consent=self._image_transmission_consent,
            visual_references=tuple(
                ImageReference(reference_id=request.image_reference, kind=ImageReferenceKind.crop)
                for request in requests
                if request.image_reference is not None
            ),
        )

        candidates = tuple(
            self._candidate_for_request(request=request, index=index + 1)
            for index, request in enumerate(requests)
        )
        usage = _usage(
            provider_id=self.provider_id,
            operation="translate_page",
            region_ids=tuple(request.region_id for request in requests),
            used_visual_input=bool(visual_references),
            input_units=sum(len(request.source_text) for request in requests),
            output_units=sum(len(candidate.translated_text) for candidate in candidates),
        )
        self._recorded_requests = (
            *self._recorded_requests,
            MockProviderRequestRecord(
                **usage.model_dump(),
                operation="translate_page",
                region_ids=tuple(request.region_id for request in requests),
                visual_references=visual_references,
            ),
        )
        return candidates

    def _candidate_for_request(
        self,
        *,
        request: TranslationRequest,
        index: int,
    ) -> TranslationCandidate:
        request_fingerprint = _fingerprint(
            (
                self.provider_id,
                request.region_id,
                request.source_language,
                request.target_language,
                request.source_text,
                *request.reviewer_feedback,
            )
        )
        translated_text = self._configured_translations.get(
            request.region_id,
            f"mock translation for {request.region_id}",
        )
        return TranslationCandidate(
            candidate_id=f"mock-translation-{index}-{request.region_id}",
            region_id=request.region_id,
            translated_text=translated_text,
            provider_id=self.provider_id,
            model_id=MOCK_MODEL_ID,
            attempt=1,
            request_fingerprint=request_fingerprint,
            created_revision="mock-revision-1",
        )


class MockReviewAdapter:
    provider_id = MOCK_REVIEWER_PROVIDER_ID
    display_name = "Mock Reviewer"

    def __init__(
        self,
        *,
        configured_reviews: tuple[RegionReview, ...] = (),
        capabilities: ProviderCapabilities | None = None,
        visual_mode_enabled: bool = False,
        image_transmission_consent: bool = False,
        config_issues: tuple[ProviderConfigIssue, ...] = (),
    ) -> None:
        self._configured_reviews = {review.region_id: review for review in configured_reviews}
        self._capabilities = capabilities or _default_reviewer_capabilities()
        self._visual_mode_enabled = visual_mode_enabled
        self._image_transmission_consent = image_transmission_consent
        self._config_issues = config_issues
        self._loaded = False
        self._recorded_requests: tuple[MockProviderRequestRecord, ...] = ()

    @property
    def recorded_requests(self) -> tuple[MockProviderRequestRecord, ...]:
        return self._recorded_requests

    async def load(self) -> None:
        self._loaded = True

    async def unload(self) -> None:
        self._loaded = False

    def validate_config(self) -> tuple[ProviderConfigIssue, ...]:
        return self._config_issues

    def capabilities(self) -> ProviderCapabilities:
        return self._capabilities

    async def correct_ocr(
        self,
        request: OCRCorrectionRequest,
    ) -> OCRCorrectionReview:
        visual_references = self._authorize_visual_references(request.visual_references)
        selected_candidate = request.candidates[0] if request.candidates else None
        usage = self._record(
            operation="correct_ocr",
            region_ids=(
                (selected_candidate.region_id,) if selected_candidate is not None else ()
            ),
            visual_references=visual_references,
        )
        return OCRCorrectionReview(
            region_id=selected_candidate.region_id if selected_candidate is not None else None,
            selected_candidate_id=(
                selected_candidate.request_id if selected_candidate is not None else None
            ),
            corrected_text=selected_candidate.text if selected_candidate is not None else None,
            confidence=selected_candidate.confidence if selected_candidate is not None else 0.0,
            evidence_summary="mock OCR correction review",
            affects_reading_order=False,
            usage_metadata=usage,
        )

    async def build_page_context(
        self,
        request: PageContextRequest,
    ) -> PageContextReview:
        visual_references = self._authorize_visual_references(request.visual_references)
        usage = self._record(
            operation="build_page_context",
            region_ids=request.region_ids,
            visual_references=visual_references,
            prompt_contract_version=request.prompt_contract_version,
        )
        return PageContextReview(
            scene_summary="mock page context",
            reading_order_notes="mock reviewer did not infer new order",
            dialogue_groups=(),
            confidence=0.9,
            usage_metadata=usage,
        )

    async def review_translation(
        self,
        request: TranslationReviewRequest,
    ) -> PageReview:
        visual_references = self._authorize_visual_references(request.visual_references)
        region_ids = request.region_ids or tuple(
            candidate.region_id for candidate in request.candidates
        )
        reviews = tuple(
            self._configured_reviews.get(region_id, _default_region_review(region_id))
            for region_id in region_ids
        )
        usage = self._record(
            operation="review_translation",
            region_ids=region_ids,
            visual_references=visual_references,
            prompt_contract_version=request.prompt_contract_version,
        )
        return PageReview(
            region_reviews=reviews,
            page_level_issues=(),
            context_consistency_summary="mock review found no page-level inconsistency",
            provider_id=self.provider_id,
            model_id=MOCK_MODEL_ID,
            prompt_contract_version=request.prompt_contract_version,
            usage_metadata=usage,
        )

    async def review_result_image(
        self,
        request: ResultImageReviewRequest,
    ) -> ResultQualityReview:
        visual_references = self._authorize_visual_references(
            (request.rendered_image_reference, *request.visual_references)
        )
        usage = self._record(
            operation="review_result_image",
            region_ids=(),
            visual_references=visual_references,
            prompt_contract_version=request.prompt_contract_version,
        )
        return ResultQualityReview(
            rendered_image_reference=request.rendered_image_reference,
            issues=(),
            correction_recommendations=(),
            requires_user_review=False,
            decision="approve",
            usage_metadata=usage,
        )

    async def parse_revision_intent(
        self,
        request: RevisionIntentRequest,
    ) -> RevisionIntentParseResult:
        usage = self._record(
            operation="parse_revision_intent",
            region_ids=request.selected_region_ids,
            visual_references=(),
            prompt_contract_version=request.prompt_contract_version,
        )
        return RevisionIntentParseResult(
            normalized_intent=request.user_instruction,
            candidate_region_ids=request.selected_region_ids,
            proposed_actions=request.allowed_actions,
            requires_confirmation=bool(request.selected_region_ids),
            ambiguity_summary=None,
            usage_metadata=usage,
        )

    def _authorize_visual_references(
        self,
        visual_references: tuple[ImageReference, ...],
    ) -> tuple[ImageReference, ...]:
        return _authorized_visual_references(
            capabilities=self._capabilities,
            visual_mode_enabled=self._visual_mode_enabled,
            image_transmission_consent=self._image_transmission_consent,
            visual_references=visual_references,
        )

    def _record(
        self,
        *,
        operation: str,
        region_ids: tuple[RegionId, ...],
        visual_references: tuple[ImageReference, ...],
        prompt_contract_version: str | None = None,
    ) -> ProviderUsageMetadata:
        usage = _usage(
            provider_id=self.provider_id,
            operation=operation,
            region_ids=region_ids,
            used_visual_input=bool(visual_references),
            prompt_contract_version=prompt_contract_version,
        )
        self._recorded_requests = (
            *self._recorded_requests,
            MockProviderRequestRecord(
                **usage.model_dump(),
                operation=operation,
                region_ids=region_ids,
                visual_references=visual_references,
            ),
        )
        return usage


def _default_ocr_regions(provider_id: str) -> tuple[RawOCRRegion, ...]:
    return (
        RawOCRRegion(
            region_id="region-1",
            raw_text="mock source text 1",
            confidence=0.95,
            geometry=_triangle(x_offset=0.0),
            writing_mode=WritingMode.horizontal_ltr,
            writing_mode_confidence=0.95,
            provider_id=provider_id,
            metadata_summary=("deterministic mock OCR region",),
        ),
        RawOCRRegion(
            region_id="region-2",
            raw_text="mock source text 2",
            confidence=0.9,
            geometry=_triangle(x_offset=20.0),
            writing_mode=WritingMode.horizontal_ltr,
            writing_mode_confidence=0.9,
            provider_id=provider_id,
            metadata_summary=("deterministic mock OCR region",),
        ),
    )


def _triangle(*, x_offset: float) -> Polygon:
    return Polygon(
        points=(
            Point(x=x_offset, y=0.0),
            Point(x=x_offset + 10.0, y=0.0),
            Point(x=x_offset, y=10.0),
        )
    )


def _default_translator_capabilities() -> ProviderCapabilities:
    return ProviderCapabilities(
        provider_type=ProviderType.translator,
        supported_language_pairs=(
            LanguagePair(source_language="ja", target_language="ko"),
            LanguagePair(source_language="en", target_language="ko"),
            LanguagePair(source_language="ko", target_language="en"),
            LanguagePair(source_language="ja", target_language="en"),
        ),
        supports_batch=True,
        max_batch_size=32,
        supports_structured_output=True,
        supports_visual_input=False,
        supports_full_image=False,
        supports_crop=False,
        is_cloud=False,
    )


def _default_reviewer_capabilities() -> ProviderCapabilities:
    return ProviderCapabilities(
        provider_type=ProviderType.reviewer,
        supported_language_pairs=(
            LanguagePair(source_language="ja", target_language="ko"),
            LanguagePair(source_language="en", target_language="ko"),
            LanguagePair(source_language="ko", target_language="en"),
            LanguagePair(source_language="ja", target_language="en"),
        ),
        supports_batch=True,
        max_batch_size=32,
        supports_structured_output=True,
        supports_visual_input=False,
        supports_full_image=False,
        supports_crop=False,
        is_cloud=False,
    )


def _default_region_review(region_id: RegionId) -> RegionReview:
    scores = RubricScores(
        semantic_fidelity=4.5,
        completeness=4.5,
        naturalness=4.5,
        character_voice=4.5,
        context_fit=4.5,
        terminology=4.5,
        text_role_fit=4.5,
        renderability=4.5,
    )
    return RegionReview(
        region_id=region_id,
        rubric_scores=scores,
        total_score=4.5,
        critical_issues=(),
        non_critical_issues=(),
        evidence_summary="default mock reviewer evidence",
        improvement_instruction=None,
        decision="approve",
    )


def _enforce_batch_capabilities(capabilities: ProviderCapabilities, request_count: int) -> None:
    if request_count > 1 and not capabilities.supports_batch:
        raise ProviderConfigError("provider does not support batch requests")
    if request_count > capabilities.max_batch_size:
        raise ProviderConfigError(
            f"batch size {request_count} exceeds provider limit {capabilities.max_batch_size}"
        )


def _enforce_language_pair(
    capabilities: ProviderCapabilities,
    request: TranslationRequest,
) -> None:
    if not capabilities.supports_language_pair(
        request.source_language,
        request.target_language,
    ):
        raise ProviderConfigError(
            "unsupported language pair "
            f"{request.source_language}->{request.target_language} for provider capability"
        )


def _authorized_visual_references(
    *,
    capabilities: ProviderCapabilities,
    visual_mode_enabled: bool,
    image_transmission_consent: bool,
    visual_references: tuple[ImageReference, ...],
) -> tuple[ImageReference, ...]:
    if not visual_references:
        return ()
    if not visual_mode_enabled:
        raise ProviderConfigError("visual input requires visual mode")
    if not image_transmission_consent:
        raise ProviderConfigError("visual input requires image transmission consent")
    unsupported_reference = next(
        (
            reference
            for reference in visual_references
            if not capabilities.supports_visual_reference(reference)
        ),
        None,
    )
    if unsupported_reference is not None:
        raise ProviderConfigError(
            f"provider does not support visual input kind {unsupported_reference.kind.value}"
        )
    return visual_references


def _usage(
    *,
    provider_id: str,
    operation: str,
    region_ids: tuple[RegionId, ...],
    used_visual_input: bool,
    prompt_contract_version: str | None = None,
    input_units: int = 0,
    output_units: int = 0,
    safe_metadata_summary: tuple[str, ...] = ("mock provider request",),
) -> ProviderUsageMetadata:
    fingerprint = _fingerprint((provider_id, operation, *region_ids))
    return ProviderUsageMetadata(
        request_id=f"{operation}-{fingerprint}",
        request_fingerprint=fingerprint,
        provider_id=provider_id,
        model_id=MOCK_MODEL_ID,
        prompt_contract_version=prompt_contract_version,
        input_units=input_units,
        output_units=output_units,
        used_visual_input=used_visual_input,
        safe_metadata_summary=safe_metadata_summary,
    )


def _fingerprint(parts: tuple[str, ...]) -> str:
    payload = "\x1f".join(parts)
    return f"mock-{sha256(payload.encode('utf-8')).hexdigest()[:16]}"


__all__ = [
    "MOCK_MODEL_ID",
    "MOCK_OCR_PROVIDER_ID",
    "MOCK_REVIEWER_PROVIDER_ID",
    "MOCK_TRANSLATOR_PROVIDER_ID",
    "MockOCRAdapter",
    "MockProviderRequestRecord",
    "MockReviewAdapter",
    "MockTranslatorAdapter",
]
