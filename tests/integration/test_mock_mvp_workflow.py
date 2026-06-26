from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from image_translator.config.settings import (
    FallbackProviderSettings,
    ProviderEndpointSettings,
    ProviderRole,
    ProviderRuntimeSettings,
)
from image_translator.domain import (
    ApprovalRecord,
    ApprovalStatus,
    ExportFormat,
    ExportRequest,
    FormatOptions,
    ImageDimensions,
    JobDefinition,
    JobStatus,
    Point,
    Polygon,
    QualityIssue,
    QualitySeverity,
    RawOCRRegion,
    ReadingOrder,
    RegionReview,
    RenderStyle,
    RubricScores,
    TextRole,
    WorkflowCancelled,
    WritingMode,
)
from image_translator.domain.revision import approve_revision_plan
from image_translator.persistence.checkpoints import SQLiteCheckpointStore, WorkflowGraphKind
from image_translator.providers import (
    ImageReference,
    ImageReferenceKind,
    LanguagePair,
    MockOCRAdapter,
    MockReviewAdapter,
    MockTranslatorAdapter,
    ProviderCapabilities,
    ProviderType,
)
from image_translator.providers.local_inpainting import LocalMaskFillInpaintingBackend
from image_translator.providers.registry import ProviderRegistry
from image_translator.providers.retry import (
    ProviderAttemptState,
    ProviderErrorKind,
    ProviderRecoveryAction,
    ProviderRetryPolicy,
    classify_provider_error,
)
from image_translator.services.export_service import export_image
from image_translator.services.image_io import load_image_reference
from image_translator.services.inpainting import InpaintingRequest, inpaint_text
from image_translator.services.layout_analysis import analyze_reading_order
from image_translator.services.ocr_normalization import normalize_ocr_regions
from image_translator.services.rendering import create_render_plan, render_page
from image_translator.use_cases.resume_job import ResumeJobUseCase
from image_translator.use_cases.run_image_translation import RunImageTranslationUseCase
from image_translator.workflows.natural_revision import (
    NaturalRevisionGraph,
    NaturalRevisionInput,
    NaturalRevisionStatus,
    apply_revision,
    commit_revision,
    revalidate_revision,
)
from image_translator.workflows.result_quality import (
    ResultQualityGraph,
    ResultQualityInput,
)
from image_translator.workflows.translation_quality import (
    TranslationQualityGraph,
    TranslationWorkflowInput,
)


class PrimaryTranslator(MockTranslatorAdapter):
    provider_id = "primary-translator"


class BackupTranslator(MockTranslatorAdapter):
    provider_id = "backup-translator"


class PrimaryReviewer(MockReviewAdapter):
    provider_id = "primary-reviewer"


@pytest.mark.asyncio
async def test_mock_mvp_full_image_workflow_exports_after_revision_preview(
    tmp_path: Path,
) -> None:
    input_path = _fixture_image(tmp_path)
    output_path = tmp_path / "translated-result.png"
    image_reference = load_image_reference(input_path)
    ocr = MockOCRAdapter(configured_regions=_mixed_layout_raw_regions())

    raw_regions = await ocr.detect_regions(
        ImageReference(
            reference_id="fixture-source",
            kind=ImageReferenceKind.full_page,
            uri="local://fixture/source-page",
        ),
        ("ja",),
    )
    normalized = normalize_ocr_regions(
        raw_regions,
        image_dimensions=image_reference.dimensions,
        source_language="ja",
        reading_orders={
            region.region_id: ReadingOrder(
                page_index=0,
                group_index=0,
                item_index=0,
                confidence=0.96,
            )
            for region in raw_regions
        },
        text_roles={region.region_id: TextRole.dialogue for region in raw_regions},
    )
    layout = analyze_reading_order(normalized)
    ordered_region_ids = tuple(region.region_id for region in layout.regions)

    assert ordered_region_ids == (
        "region-v-right-top",
        "region-v-right-bottom",
        "region-v-left",
        "region-h-bottom",
    )

    translator = MockTranslatorAdapter(
        configured_translations={
            "region-v-right-top": "top right translation",
            "region-v-right-bottom": "bottom right translation",
            "region-v-left": "left column translation",
            "region-h-bottom": "bottom caption translation",
        }
    )
    translation_result = await TranslationQualityGraph(
        translator=translator,
        reviewer=MockReviewAdapter(),
    ).run(
        TranslationWorkflowInput(
            job_id="job-mock-mvp-full",
            project_id="project-1",
            revision_id="revision-1",
            source_image_reference="fixture-source",
            source_language="ja",
            target_language="ko",
            regions=layout.regions,
            primary_ocr_snapshots=raw_regions,
            translator_provider_id="mock-translator",
            reviewer_provider_id="mock-reviewer",
            visual_mode=False,
            image_transmission_consent=False,
        )
    )

    assert translation_result.unresolved_issues == ()
    assert tuple(
        translation.region_id
        for translation in translation_result.approved_translation_results
    ) == ordered_region_ids
    assert translator.recorded_requests[0].region_ids == ordered_region_ids

    with Image.open(input_path) as source_image:
        inpainted = inpaint_text(
            InpaintingRequest(
                image=source_image.convert("RGB"),
                regions=layout.regions,
                padding=1,
                fill_color=(255, 255, 255),
            ),
            backend=LocalMaskFillInpaintingBackend(),
        )
    translations_by_region = {
        translation.region_id: translation
        for translation in translation_result.approved_translation_results
    }
    render_plans = tuple(
        create_render_plan(
            region=region,
            translation=translations_by_region[region.region_id],
            target_language="ko",
            style=RenderStyle(size=14),
        )
        for region in layout.regions
    )
    rendered = render_page(image=inpainted.image, plans=render_plans)
    reviewer = MockReviewAdapter(
        capabilities=_visual_reviewer_capabilities(),
        visual_mode_enabled=True,
        image_transmission_consent=True,
    )
    result_state = await ResultQualityGraph(reviewer=reviewer).run_state(
        ResultQualityInput(
            revision_id="revision-1",
            approved_translations=translation_result.approved_translation_results,
            source_image_reference="fixture-source",
            inpainted_image_reference="fixture-inpainted",
            rendered_image_reference="fixture-rendered",
            expected_region_ids=ordered_region_ids,
            render_plans=render_plans,
            rendered_regions=rendered.regions,
            image_size=rendered.image.size,
            visual_mode=True,
            image_transmission_consent=True,
            inpainting_backend_id=inpainted.backend_id,
        )
    )

    assert result_state.final_image_result is not None
    assert result_state.final_image_result.approval_status is ApprovalStatus.approved_automatic
    assert result_state.export_decision is not None
    assert result_state.export_decision.allowed is True
    assert reviewer.recorded_requests[-1].operation == "review_result_image"

    preview_state = await NaturalRevisionGraph().run_state(
        NaturalRevisionInput(
            revision_id="revision-2",
            base_revision_id="revision-1",
            user_instruction="Make this line more polite.",
            available_region_ids=ordered_region_ids,
            selected_region_ids=("region-v-right-top",),
        )
    )
    assert preview_state.status is NaturalRevisionStatus.waiting_for_plan_approval
    assert preview_state.plan is not None
    assert preview_state.interrupt_payload is not None
    assert preview_state.interrupt_payload.plan_id == preview_state.plan.plan_id

    approved_plan = approve_revision_plan(
        preview_state.plan,
        approval_record=_approval_record("approval-1"),
    )
    committed_revision = commit_revision(
        revalidate_revision(
            apply_revision(preview_state.model_copy(update={"plan": approved_plan}))
        )
    )
    assert committed_revision.committed_record is not None
    assert committed_revision.committed_record.revision_id == "revision-2"

    assert output_path.exists() is False
    export_result = export_image(
        image=rendered.image,
        request=ExportRequest(
            input_path=str(input_path),
            output_path=str(output_path),
            job_id="job-mock-mvp-full",
            final_image_result=result_state.final_image_result,
            format=ExportFormat.png,
            format_options=FormatOptions(),
        ),
        exported_at=datetime(2026, 6, 26, 12, 0, tzinfo=UTC),
    )

    assert output_path.exists()
    assert export_result.file_size_bytes > 0
    assert export_result.eligibility_decision.allowed is True


@pytest.mark.asyncio
async def test_mock_mvp_translation_interrupt_blocks_export() -> None:
    graph = TranslationQualityGraph(
        translator=MockTranslatorAdapter(),
        reviewer=MockReviewAdapter(configured_reviews=(_critical_review("region-2"),)),
    )

    result = await graph.run(_translation_input(_basic_regions()))

    assert tuple(
        translation.region_id for translation in result.approved_translation_results
    ) == ("region-1",)
    assert tuple(issue.issue_code for issue in result.unresolved_issues) == (
        "meaning_reversal",
    )
    assert result.interrupt_payload is not None
    assert result.interrupt_payload.affected_region_ids == ("region-2",)
    assert "force_approve" in result.interrupt_payload.allowed_actions


def test_mock_mvp_provider_retry_uses_configured_fallback_only_after_retry_limit() -> None:
    policy = ProviderRetryPolicy(max_provider_attempts=1)
    classification = classify_provider_error(ProviderErrorKind.timeout)
    first_attempt = ProviderAttemptState()
    retry_attempt = first_attempt.next_provider_retry()

    assert policy.decide_provider_recovery(
        classification,
        attempts=first_attempt,
        fallback_configured=True,
    ) is ProviderRecoveryAction.retry_provider
    assert policy.decide_provider_recovery(
        classification,
        attempts=retry_attempt,
        fallback_configured=True,
    ) is ProviderRecoveryAction.use_fallback

    fallback = FallbackProviderSettings(
        role=ProviderRole.translator,
        provider_id="backup-translator",
        model_id="backup-translator-model-v1",
        timeout_seconds=20.0,
    )
    registry = ProviderRegistry((PrimaryTranslator(), BackupTranslator(), PrimaryReviewer()))
    selected = registry.select_fallback(
        settings=ProviderRuntimeSettings(
            translator=_endpoint("primary-translator"),
            reviewer=_endpoint("primary-reviewer"),
            fallback_order=(fallback,),
        ),
        role=ProviderRole.translator,
        failed_provider_id="primary-translator",
        source_language="ja",
        target_language="ko",
    )

    assert selected == fallback
    assert registry.select_fallback(
        settings=ProviderRuntimeSettings(
            translator=_endpoint("primary-translator"),
            reviewer=_endpoint("primary-reviewer"),
        ),
        role=ProviderRole.translator,
        failed_provider_id="primary-translator",
        source_language="ja",
        target_language="ko",
    ) is None


@pytest.mark.asyncio
async def test_mock_mvp_resume_skips_repeated_provider_calls(tmp_path: Path) -> None:
    store = SQLiteCheckpointStore(database_path=tmp_path / "checkpoints.sqlite3")
    translator = MockTranslatorAdapter()
    use_case = ResumeJobUseCase(
        checkpoint_store=store,
        workflow=RunImageTranslationUseCase(
            ocr_adapter=MockOCRAdapter(),
            translator_adapter=translator,
            review_adapter=MockReviewAdapter(),
        ),
        graph_kind=WorkflowGraphKind.translation_quality,
        revision_id="mock-revision-1",
    )
    job = _job()

    first = await use_case.resume(job)
    second = await use_case.resume(job)

    assert first.resumed_from_checkpoint is False
    assert second.resumed_from_checkpoint is True
    assert len(translator.recorded_requests) == 1
    assert second.snapshot.status is first.snapshot.status


@pytest.mark.asyncio
async def test_mock_mvp_cancel_serializes_cancelled_checkpoint(tmp_path: Path) -> None:
    class CancellingWorkflow:
        async def run(self, job: JobDefinition) -> object:
            raise asyncio.CancelledError

    store = SQLiteCheckpointStore(database_path=tmp_path / "checkpoints.sqlite3")
    use_case = ResumeJobUseCase(
        checkpoint_store=store,
        workflow=CancellingWorkflow(),
        graph_kind=WorkflowGraphKind.translation_quality,
        revision_id="mock-revision-1",
    )
    job = _job()

    result = await use_case.resume(job)

    assert result.snapshot.status is JobStatus.cancelled
    assert store.load(use_case.thread_id_for(job)).status == JobStatus.cancelled.value


@pytest.mark.asyncio
async def test_mock_mvp_cancel_can_raise_typed_error(tmp_path: Path) -> None:
    class CancellingWorkflow:
        async def run(self, job: JobDefinition) -> object:
            raise asyncio.CancelledError

    use_case = ResumeJobUseCase(
        checkpoint_store=SQLiteCheckpointStore(
            database_path=tmp_path / "checkpoints.sqlite3"
        ),
        workflow=CancellingWorkflow(),
        graph_kind=WorkflowGraphKind.translation_quality,
        revision_id="mock-revision-1",
        raise_on_cancel=True,
    )

    with pytest.raises(WorkflowCancelled):
        await use_case.resume(_job())


def _fixture_image(tmp_path: Path) -> Path:
    path = tmp_path / "source-page.png"
    image = Image.new("RGB", (240, 180), color=(255, 255, 255))
    draw = ImageDraw.Draw(image)
    for region in _mixed_layout_raw_regions():
        left, top, right, bottom = _bounds(region.geometry)
        draw.rectangle((left, top, right, bottom), outline=(0, 0, 0), width=1)
        draw.text((left + 2, top + 2), region.raw_text, fill=(0, 0, 0))
    image.save(path, format="PNG")
    return path


def _mixed_layout_raw_regions() -> tuple[RawOCRRegion, ...]:
    return (
        _raw_region(
            "region-v-left",
            "left column",
            _box(82, 24, 122, 105),
            WritingMode.vertical_rl,
        ),
        _raw_region(
            "region-h-bottom",
            "bottom caption",
            _box(28, 130, 160, 164),
            WritingMode.horizontal_ltr,
        ),
        _raw_region(
            "region-v-right-bottom",
            "right lower",
            _box(168, 88, 212, 152),
            WritingMode.vertical_rl,
        ),
        _raw_region(
            "region-v-right-top",
            "right upper",
            _box(168, 18, 212, 78),
            WritingMode.vertical_rl,
        ),
    )


def _basic_regions() -> tuple[RawOCRRegion, ...]:
    return (
        _raw_region("region-1", "source 1", _box(10, 10, 70, 50), WritingMode.horizontal_ltr),
        _raw_region("region-2", "source 2", _box(90, 10, 150, 50), WritingMode.horizontal_ltr),
    )


def _translation_input(raw_regions: tuple[RawOCRRegion, ...]) -> TranslationWorkflowInput:
    normalized = normalize_ocr_regions(
        raw_regions,
        image_dimensions=ImageDimensions(width=200, height=100),
        source_language="ja",
        reading_orders={
            region.region_id: ReadingOrder(
                page_index=0,
                group_index=0,
                item_index=index,
                confidence=0.95,
            )
            for index, region in enumerate(raw_regions)
        },
        text_roles={region.region_id: TextRole.dialogue for region in raw_regions},
    )
    return TranslationWorkflowInput(
        job_id="job-interrupt",
        project_id="project-1",
        revision_id="revision-1",
        source_image_reference="source-page",
        source_language="ja",
        target_language="ko",
        regions=normalized,
        primary_ocr_snapshots=raw_regions,
        translator_provider_id="mock-translator",
        reviewer_provider_id="mock-reviewer",
    )


def _raw_region(
    region_id: str,
    raw_text: str,
    geometry: Polygon,
    writing_mode: WritingMode,
) -> RawOCRRegion:
    return RawOCRRegion(
        region_id=region_id,
        raw_text=raw_text,
        confidence=0.96,
        geometry=geometry,
        writing_mode=writing_mode,
        writing_mode_confidence=0.96,
        provider_id="mock-ocr",
        metadata_summary=("mock MVP OCR fixture",),
    )


def _box(left: float, top: float, right: float, bottom: float) -> Polygon:
    return Polygon(
        points=(
            Point(x=left, y=top),
            Point(x=right, y=top),
            Point(x=right, y=bottom),
            Point(x=left, y=bottom),
        )
    )


def _bounds(geometry: Polygon) -> tuple[int, int, int, int]:
    xs = tuple(point.x for point in geometry.points)
    ys = tuple(point.y for point in geometry.points)
    return (int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys)))


def _critical_review(region_id: str) -> RegionReview:
    issue = QualityIssue(
        issue_code="meaning_reversal",
        severity=QualitySeverity.critical,
        scope="translation",
        region_ids=(region_id,),
        summary="mock reviewer found a critical translation error",
        evidence_references=("review",),
        recommended_action="retry_translation",
    )
    return RegionReview(
        region_id=region_id,
        rubric_scores=_scores(),
        total_score=4.5,
        critical_issues=(issue,),
        evidence_summary="critical issue evidence",
        improvement_instruction="preserve the source meaning",
        decision="needs_review",
    )


def _scores() -> RubricScores:
    return RubricScores(
        semantic_fidelity=4.5,
        completeness=4.5,
        naturalness=4.5,
        character_voice=4.5,
        context_fit=4.5,
        terminology=4.5,
        text_role_fit=4.5,
        renderability=4.5,
    )


def _visual_reviewer_capabilities() -> ProviderCapabilities:
    return ProviderCapabilities(
        provider_type=ProviderType.reviewer,
        supported_language_pairs=(LanguagePair(source_language="ja", target_language="ko"),),
        supports_batch=True,
        max_batch_size=16,
        supports_structured_output=True,
        supports_visual_input=True,
        supports_full_image=True,
        supports_crop=True,
        is_cloud=False,
    )


def _approval_record(approval_id: str) -> ApprovalRecord:
    return ApprovalRecord(
        approval_id=approval_id,
        approved_by="user",
        approved_at=datetime(2026, 6, 26, 12, 0, tzinfo=UTC),
    )


def _endpoint(provider_id: str) -> ProviderEndpointSettings:
    return ProviderEndpointSettings(
        provider_id=provider_id,
        model_id=f"{provider_id}-model-v1",
        timeout_seconds=20.0,
    )


def _job() -> JobDefinition:
    return JobDefinition(
        job_id="job-resume-mvp",
        project_id="project-1",
        input_path="/safe/local/input.png",
        requested_output_path="/safe/local/output.png",
        source_language="ja",
        target_language="ko",
        provider_selection=("mock-ocr", "mock-translator", "mock-reviewer"),
    )
