from __future__ import annotations

import pytest

from image_translator.domain.export import VISUAL_QUALITY_UNCONFIRMED
from image_translator.domain.geometry import Point, Polygon
from image_translator.domain.ocr import WritingMode
from image_translator.domain.quality import ApprovalStatus
from image_translator.domain.render import RenderedRegion, RenderPlan, RenderStyle, RGBColor
from image_translator.domain.translation import TranslationResult
from image_translator.providers import MockReviewAdapter
from image_translator.providers.base import ProviderCapabilities, ProviderType
from image_translator.workflows.result_quality import ResultQualityGraph, ResultQualityInput


@pytest.mark.asyncio
async def test_mock_result_graph_blocks_export_when_visual_mode_is_off() -> None:
    reviewer = MockReviewAdapter(visual_mode_enabled=False, image_transmission_consent=False)
    graph = ResultQualityGraph(reviewer=reviewer)

    state = await graph.run_state(_workflow_input(visual_mode=False))

    assert state.final_image_result is not None
    assert state.final_image_result.approval_status is ApprovalStatus.needs_review
    assert state.final_image_result.requires_user_confirmation == (
        VISUAL_QUALITY_UNCONFIRMED,
    )
    assert state.export_decision is not None
    assert state.export_decision.allowed is False
    assert reviewer.recorded_requests == ()


@pytest.mark.asyncio
async def test_mock_result_graph_reviews_final_image_when_visual_mode_is_enabled() -> None:
    reviewer = MockReviewAdapter(
        capabilities=ProviderCapabilities(
            provider_type=ProviderType.reviewer,
            supports_visual_input=True,
            supports_full_image=True,
            supports_structured_output=True,
            is_cloud=False,
        ),
        visual_mode_enabled=True,
        image_transmission_consent=True,
    )
    graph = ResultQualityGraph(reviewer=reviewer)

    state = await graph.run_state(
        _workflow_input(visual_mode=True, image_transmission_consent=True)
    )

    assert state.final_image_result is not None
    assert state.final_image_result.approval_status is ApprovalStatus.approved_automatic
    assert state.export_decision is not None
    assert state.export_decision.allowed is True
    assert tuple(record.operation for record in reviewer.recorded_requests) == (
        "review_result_image",
    )


def _workflow_input(
    *,
    visual_mode: bool,
    image_transmission_consent: bool = False,
) -> ResultQualityInput:
    return ResultQualityInput(
        revision_id="revision-result-quality-mock",
        approved_translations=(_translation("region-1"),),
        source_image_reference="source-page",
        inpainted_image_reference="inpainted-page",
        rendered_image_reference="rendered-page",
        expected_region_ids=("region-1",),
        render_plans=(_plan("region-1"),),
        rendered_regions=(_rendered_region("region-1"),),
        image_size=(100, 100),
        visual_mode=visual_mode,
        image_transmission_consent=image_transmission_consent,
    )


def _translation(region_id: str) -> TranslationResult:
    return TranslationResult(
        region_id=region_id,
        approved_translated_text="translated text",
        source_language="ja",
        target_language="ko",
        selected_candidate_id=f"candidate-{region_id}",
        approval_status=ApprovalStatus.approved_automatic.value,
    )


def _rendered_region(region_id: str) -> RenderedRegion:
    plan = _plan(region_id)
    return RenderedRegion(
        region_id=region_id,
        applied_plan=plan,
        output_geometry=plan.geometry,
    )


def _plan(region_id: str) -> RenderPlan:
    return RenderPlan(
        region_id=region_id,
        geometry=_polygon(10, 10, 50, 30),
        translated_text="translated text",
        style=RenderStyle(
            size=14,
            color=RGBColor(red=0, green=0, blue=0),
            writing_mode=WritingMode.horizontal_ltr,
        ),
    )


def _polygon(left: float, top: float, right: float, bottom: float) -> Polygon:
    return Polygon(
        points=(
            Point(x=left, y=top),
            Point(x=right, y=top),
            Point(x=right, y=bottom),
            Point(x=left, y=bottom),
        )
    )
