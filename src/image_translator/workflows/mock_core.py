from __future__ import annotations

from typing import TypeAlias

from image_translator.domain._base import DomainModel
from image_translator.domain.errors import ProviderConfigError
from image_translator.domain.export import ExportEligibilityDecision, FinalImageResult
from image_translator.domain.ids import RevisionId
from image_translator.domain.job import JobDefinition, JobSnapshot, JobStatus
from image_translator.domain.ocr import (
    NormalizedTextRegion,
    RawOCRRegion,
    ReadingOrder,
    TextOrientation,
    TextRole,
    WritingMode,
)
from image_translator.providers.base import (
    ImageReference,
    ImageReferenceKind,
    OCRAdapter,
    PageContextRequest,
    ProviderAdapter,
    ProviderCapabilities,
    ResultImageReviewRequest,
    ReviewAdapter,
    TranslationReviewRequest,
    TranslatorAdapter,
)
from image_translator.services.export_gate import evaluate_export_eligibility
from image_translator.workflows.result_quality import (
    ResultQualityState,
    apply_result_quality_review,
    create_result_quality_state,
    finalize_result_quality,
    validate_render_structure,
)
from image_translator.workflows.translation_quality import (
    TranslationQualityState,
    apply_page_review,
    attach_translation_candidates,
    build_translation_requests,
    create_translation_quality_state,
    prepare_page,
)

MOCK_REVISION_ID: RevisionId = "mock-revision-1"
MockCoreOCRAdapter: TypeAlias = OCRAdapter
MockCoreTranslatorAdapter: TypeAlias = TranslatorAdapter
MockCoreReviewAdapter: TypeAlias = ReviewAdapter


class RunImageTranslationResult(DomainModel):
    snapshots: tuple[JobSnapshot, ...]
    raw_ocr_regions: tuple[RawOCRRegion, ...]
    normalized_regions: tuple[NormalizedTextRegion, ...]
    translation_state: TranslationQualityState
    result_state: ResultQualityState
    final_image_result: FinalImageResult
    export_decision: ExportEligibilityDecision


class ProviderBackedMockCoreWorkflow:
    def __init__(
        self,
        *,
        ocr_adapter: MockCoreOCRAdapter,
        translator_adapter: MockCoreTranslatorAdapter,
        review_adapter: MockCoreReviewAdapter,
        revision_id: RevisionId = MOCK_REVISION_ID,
    ) -> None:
        self._ocr_adapter = ocr_adapter
        self._translator_adapter = translator_adapter
        self._review_adapter = review_adapter
        self._revision_id = revision_id

    async def run(self, job: JobDefinition) -> RunImageTranslationResult:
        _validate_visual_mode(job)
        _validate_provider_configs(
            (self._ocr_adapter, self._translator_adapter, self._review_adapter)
        )

        await self._load_adapters()
        try:
            snapshots: tuple[JobSnapshot, ...] = (
                _snapshot(job, JobStatus.preparing, 0.02, "prepare", "Preparing mock workflow"),
            )
            source_image = _source_image_reference(job)

            raw_ocr_regions = await self._ocr_adapter.detect_regions(
                source_image,
                (job.source_language,),
            )
            snapshots = (
                *snapshots,
                _snapshot(job, JobStatus.ocr_running, 0.18, "ocr", "Mock OCR complete"),
            )

            normalized_regions = _normalize_raw_ocr_regions(
                raw_ocr_regions,
                source_language=job.source_language,
            )
            translation_state = prepare_page(
                create_translation_quality_state(
                    job_id=job.job_id,
                    revision_id=self._revision_id,
                    regions=normalized_regions,
                )
            )
            snapshots = (
                *snapshots,
                _snapshot(
                    job,
                    JobStatus.analyzing_layout,
                    0.36,
                    "layout",
                    "Mock layout prepared",
                ),
            )

            reviewer_capabilities = self._review_adapter.capabilities()
            page_context = await self._review_adapter.build_page_context(
                PageContextRequest(
                    region_ids=tuple(region.region_id for region in normalized_regions),
                    visual_references=_page_visual_references(
                        job,
                        reviewer_capabilities,
                        source_image,
                    ),
                )
            )

            translator_capabilities = self._translator_adapter.capabilities()
            translation_state = build_translation_requests(
                state=translation_state,
                job=job,
                page_context_reference=(
                    page_context.usage_metadata.request_id
                    if page_context.usage_metadata is not None
                    else None
                ),
                include_crop_references=_can_send_crop_references(
                    job,
                    translator_capabilities,
                ),
            )
            candidates = await self._translator_adapter.translate_page(
                translation_state.translation_requests
            )
            translation_state = attach_translation_candidates(
                state=translation_state,
                candidates=candidates,
            )
            snapshots = (
                *snapshots,
                _snapshot(
                    job,
                    JobStatus.translating,
                    0.58,
                    "translation",
                    "Mock translation complete",
                ),
            )

            page_review = await self._review_adapter.review_translation(
                TranslationReviewRequest(
                    region_ids=tuple(candidate.region_id for candidate in candidates),
                    candidates=candidates,
                    visual_references=_translation_review_visual_references(
                        job,
                        reviewer_capabilities,
                        source_image,
                        normalized_regions,
                    ),
                )
            )
            translation_state = apply_page_review(
                state=translation_state,
                page_review=page_review,
            )
            snapshots = (
                *snapshots,
                _snapshot(
                    job,
                    JobStatus.reviewing_translation,
                    0.70,
                    "translation_review",
                    "Mock translation review complete",
                ),
            )

            result_state = create_result_quality_state(
                revision_id=self._revision_id,
                approved_translations=translation_state.approved_translations,
                unresolved_translation_issues=translation_state.unresolved_issues,
            )
            rendered_reference = _rendered_image_reference(job)
            result_state = validate_render_structure(
                state=result_state,
                expected_region_ids=tuple(region.region_id for region in normalized_regions),
                rendered_image_reference=rendered_reference.reference_id,
            )

            if not result_state.unresolved_issues and _can_review_result_image(
                job,
                reviewer_capabilities,
                rendered_reference,
            ):
                result_review = await self._review_adapter.review_result_image(
                    ResultImageReviewRequest(
                        rendered_image_reference=rendered_reference,
                        visual_references=_page_visual_references(
                            job,
                            reviewer_capabilities,
                            source_image,
                        ),
                    )
                )
                result_state = apply_result_quality_review(
                    state=result_state,
                    review=result_review,
                )

            result_state = finalize_result_quality(result_state)
            final_image_result = _require_final_image_result(result_state)
            export_decision = evaluate_export_eligibility(final_image_result)
            final_status = (
                JobStatus.ready_to_export if export_decision.allowed else JobStatus.waiting_for_user
            )
            snapshots = (
                *snapshots,
                _snapshot(
                    job,
                    JobStatus.reviewing_result,
                    0.94,
                    "result_quality",
                    "Mock result quality evaluated",
                ),
                _snapshot(
                    job,
                    final_status,
                    1.0,
                    "export_gate",
                    "Mock export gate evaluated",
                    can_cancel=False,
                ),
            )

            return RunImageTranslationResult(
                snapshots=snapshots,
                raw_ocr_regions=raw_ocr_regions,
                normalized_regions=normalized_regions,
                translation_state=translation_state,
                result_state=result_state,
                final_image_result=final_image_result,
                export_decision=export_decision,
            )
        finally:
            await self._unload_adapters()

    async def _load_adapters(self) -> None:
        await self._ocr_adapter.load()
        await self._translator_adapter.load()
        await self._review_adapter.load()

    async def _unload_adapters(self) -> None:
        await self._review_adapter.unload()
        await self._translator_adapter.unload()
        await self._ocr_adapter.unload()


def _normalize_raw_ocr_regions(
    raw_regions: tuple[RawOCRRegion, ...],
    *,
    source_language: str,
) -> tuple[NormalizedTextRegion, ...]:
    return tuple(
        NormalizedTextRegion(
            region_id=region.region_id,
            source_text=region.raw_text,
            geometry=region.geometry,
            source_language=source_language,
            writing_mode=(
                region.writing_mode
                if region.writing_mode is not WritingMode.unknown
                else WritingMode.horizontal_ltr
            ),
            orientation=TextOrientation.upright,
            reading_order=ReadingOrder(
                page_index=0,
                group_index=0,
                item_index=index,
                confidence=region.confidence,
            ),
            text_role=TextRole.dialogue,
            ocr_provenance=(f"{region.provider_id}-{region.region_id}",),
        )
        for index, region in enumerate(raw_regions)
    )


def _validate_visual_mode(job: JobDefinition) -> None:
    if job.visual_mode and not job.image_transmission_consent:
        raise ProviderConfigError("visual mode requires image transmission consent")


def _validate_provider_configs(adapters: tuple[ProviderAdapter, ...]) -> None:
    config_issues = tuple(issue for adapter in adapters for issue in adapter.validate_config())
    blocking_issues = tuple(
        issue
        for issue in config_issues
        if issue.severity.value in {"error", "critical"}
    )
    if blocking_issues:
        safe_messages = tuple(issue.safe_message for issue in blocking_issues)
        raise ProviderConfigError("; ".join(safe_messages))


def _source_image_reference(job: JobDefinition) -> ImageReference:
    return ImageReference(
        reference_id=f"source-{job.job_id}",
        kind=ImageReferenceKind.full_page,
        uri=f"local://source/{job.job_id}",
    )


def _rendered_image_reference(job: JobDefinition) -> ImageReference:
    return ImageReference(
        reference_id=f"rendered-{job.job_id}",
        kind=ImageReferenceKind.rendered,
        uri=f"local://rendered/{job.job_id}",
    )


def _page_visual_references(
    job: JobDefinition,
    capabilities: ProviderCapabilities,
    source_image: ImageReference,
) -> tuple[ImageReference, ...]:
    if _can_send_reference(job, capabilities, source_image):
        return (source_image,)
    return ()


def _translation_review_visual_references(
    job: JobDefinition,
    capabilities: ProviderCapabilities,
    source_image: ImageReference,
    regions: tuple[NormalizedTextRegion, ...],
) -> tuple[ImageReference, ...]:
    page_references = _page_visual_references(job, capabilities, source_image)
    crop_references = tuple(
        reference
        for reference in (
            ImageReference(
                reference_id=f"crop-{region.region_id}",
                kind=ImageReferenceKind.crop,
                uri=None,
            )
            for region in regions
        )
        if _can_send_reference(job, capabilities, reference)
    )
    return (*page_references, *crop_references)


def _can_send_crop_references(
    job: JobDefinition,
    capabilities: ProviderCapabilities,
) -> bool:
    sample_reference = ImageReference(
        reference_id="crop-capability-check",
        kind=ImageReferenceKind.crop,
    )
    return _can_send_reference(job, capabilities, sample_reference)


def _can_review_result_image(
    job: JobDefinition,
    capabilities: ProviderCapabilities,
    rendered_reference: ImageReference,
) -> bool:
    return _can_send_reference(job, capabilities, rendered_reference)


def _can_send_reference(
    job: JobDefinition,
    capabilities: ProviderCapabilities,
    reference: ImageReference,
) -> bool:
    return (
        job.visual_mode
        and job.image_transmission_consent
        and capabilities.supports_visual_reference(reference)
    )


def _require_final_image_result(state: ResultQualityState) -> FinalImageResult:
    if state.final_image_result is None:
        raise RuntimeError("result quality workflow did not produce a final image result")
    return state.final_image_result


def _snapshot(
    job: JobDefinition,
    status: JobStatus,
    progress: float,
    stage: str,
    message: str,
    *,
    can_cancel: bool = True,
    interrupt_summary: str | None = None,
) -> JobSnapshot:
    return JobSnapshot(
        job_id=job.job_id,
        status=status,
        progress=progress,
        stage=stage,
        message=message,
        can_cancel=can_cancel,
        interrupt_summary=interrupt_summary,
    )


__all__ = [
    "MOCK_REVISION_ID",
    "MockCoreOCRAdapter",
    "MockCoreReviewAdapter",
    "MockCoreTranslatorAdapter",
    "ProviderBackedMockCoreWorkflow",
    "RunImageTranslationResult",
]
